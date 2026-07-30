"""Lean 4 verifier adapter for a local Lake project or Apptainer.

Generated files are placed in a configured Lake project so that imports such as
``import Mathlib`` resolve against that project's dependencies.
"""
from .base import BaseVerifier
from typing import Dict, Any, Optional, List
from pathlib import Path
import subprocess
import time
import re
import shutil
import os
import yaml

class LeanVerifier(BaseVerifier):
    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
        
        self.lean_cfg = self.config.get("lean", {})
        self.timeout = self.lean_cfg.get("timeout", 300)
        self.method = self.lean_cfg.get("method", "local")
        self.repo_root = Path(__file__).resolve().parents[2]
        
        # We don't strictly use a global 'results_dir' for the .lean file itself
        # because the file needs to live inside the project to pick up dependencies.
        # However, we can use it for logging if needed.

    def _load_config(self, path: Optional[str]) -> Dict[str, Any]:
        if path:
            p = Path(path)
        else:
            p = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
        
        if not p.exists():
            return {}
        try:
            with open(p, 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Config load error: {e}")
            return {}

    def _resolve_path(self, value: str) -> Path:
        """Resolve configuration paths relative to the repository root."""
        path = Path(value).expanduser()
        return path if path.is_absolute() else self.repo_root / path

    def _project_path(self) -> Path:
        section = self.lean_cfg.get(self.method, {})
        value = section.get("project_path")
        if not value:
            raise ValueError(f"lean.{self.method}.project_path is required")
        project = self._resolve_path(value).resolve()
        if not project.is_dir():
            raise FileNotFoundError(f"Lean project not found: {project}")
        if not ((project / "lakefile.lean").is_file() or (project / "lakefile.toml").is_file()):
            raise FileNotFoundError(f"No lakefile.lean or lakefile.toml in Lean project: {project}")
        return project

    def _local_lake_path(self) -> str:
        value = self.lean_cfg.get("local", {}).get("lake_path", "lake")
        if Path(value).is_absolute() or "/" in value:
            path = self._resolve_path(value).resolve()
            if not path.is_file() or not os.access(path, os.X_OK):
                raise FileNotFoundError(f"Lake executable not found: {path}")
            return str(path)

        executable = shutil.which(value)
        if executable is None:
            raise FileNotFoundError(
                f"Lake executable '{value}' was not found on PATH; "
                "set lean.local.lake_path in the config"
            )
        return executable

    def _build_command(self, source_file_path: Path) -> List[str]:
        """Construct the configured Lean command."""
        
        if self.method == "apptainer":
            cfg = self.lean_cfg.get("apptainer", {})
            image = self._resolve_path(cfg.get("image_path", ""))
            host_elan = self._resolve_path(cfg.get("elan_home", ""))
            host_project = self._project_path()
            
            if not image.is_file():
                raise FileNotFoundError(f"Lean image not found: {image}")
            if not host_elan.is_dir():
                raise FileNotFoundError(f"Elan home not found: {host_elan}")

            # Define internal mount points
            container_elan = "/elan_home"
            container_work = "/work"

            # Based on your provided command:
            # --env ELAN_HOME=/elan_home/.elan_data
            # --env PATH=/elan_home/lean_bin/bin:$PATH
            # Note: The exact internal path for 'bin' depends on your folder structure. 
            # I am following your snippet: `/elan_home/lean_bin/bin`
            
            cmd = [
                "apptainer", "exec",
                # Bind Elan toolchains
                "--bind", f"{host_elan}:{container_elan}",
                # Bind the Project folder to /work
                "--bind", f"{host_project}:{container_work}",
                # Set CWD to /work so 'lake' finds lakefile.lean
                "--pwd", container_work,
                # Environment Setup
                "--env", f"ELAN_HOME={container_elan}/.elan_data",
                "--env", f"PATH={container_elan}/lean_bin/bin:$PATH",
                str(image.resolve()),
                # The actual command: use lake to setup env, then run lean on the file
                "lake", "env", "lean", source_file_path.name
            ]
            return cmd
        
        elif self.method == "local":
            # Lake supplies the pinned Lean toolchain and Mathlib package paths.
            return [self._local_lake_path(), "env", "lean", source_file_path.name]
            
        else:
            raise NotImplementedError(f"Method {self.method} not implemented for Lean")

    def verify(self, source: str, spec: str, filename: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        """Verify the source code using Lean."""
        
        # 1. Determine Location
        # Crucial: We must write the file INTO the project directory so imports work.
        try:
            project_path = self._project_path()
        except Exception as e:
            return {"ok": False, "reason": f"Config Error: {e}", "raw": None, "file": None}
            
        ts = int(time.time() * 1000)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", filename or "submission")
        out_name = f"{safe_name}_{ts}.lean"
        
        # The file is written to the host's project folder
        out_path = project_path / out_name
        
        # 2. Write File
        try:
            out_path.write_text(source)
        except Exception as e:
            return {"ok": False, "reason": f"Write Error: {e}", "raw": None, "file": str(out_path)}

        # 3. Build Command
        try:
            cmd = self._build_command(out_path)
        except Exception as e:
            return {"ok": False, "reason": f"Config Error: {e}", "raw": None, "file": str(out_path)}

        # 4. Execute
        try:
            cwd = project_path if self.method == "local" else None
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            
            stdout = proc.stdout
            stderr = proc.stderr
            rc = proc.returncode
            
            raw = {"stdout": stdout, "stderr": stderr, "returncode": rc}
            
            # Lean logic:
            # Usually exit code 0 is success. 
            # Output might contain "error:" strings even if rc=1 (or sometimes 0 in older versions).
            ok = (rc == 0)
            reason = None
            
            if not ok:
                reason = "Lean exited with error code"
                if stderr:
                    reason += f": {stderr[:200]}..."
                elif stdout:
                    reason += f": {stdout[:200]}..."
            
            return {"ok": ok, "reason": reason, "raw": raw, "file": str(out_path)}

        except subprocess.TimeoutExpired:
            return {"ok": False, "reason": f"Timeout after {self.timeout}s", "raw": None, "file": str(out_path)}
        except Exception as e:
            return {"ok": False, "reason": f"Execution Error: {e}", "raw": None, "file": str(out_path)}
