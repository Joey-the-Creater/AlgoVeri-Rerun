"""Dafny verifier adapter.

Supports Apptainer, Docker, and Local execution strategies via hierarchical config.
"""
from .base import BaseVerifier
from typing import Dict, Any, Optional, List
from pathlib import Path
import subprocess
import time
import os
import yaml  # Requires: pip install pyyaml

class DafnyVerifier(BaseVerifier):
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the DafnyVerifier.
        
        Args:
            config_path: Path to the YAML config file. If None, defaults to 
                         repo_root/config/config.yaml
        """
        self.config = self._load_config(config_path)
        
        # Load Dafny specific config
        self.dafny_cfg = self.config.get("dafny", {})
        self.timeout = self.dafny_cfg.get("timeout", 60)
        self.method = self.dafny_cfg.get("method", "local")
        
        # Resolve global results directory
        self.results_dir = (
            self.config.get("results_dir")
            or os.environ.get("RESULTS_DIR")
            or "results/dafny"
        )
        Path(self.results_dir).mkdir(parents=True, exist_ok=True)

    def _load_config(self, path: Optional[str]) -> Dict[str, Any]:
        """Load hierarchical YAML config safely."""
        if path:
            p = Path(path)
        else:
            # Default to config/config.yaml relative to this file's location
            p = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
        
        if not p.exists():
            print(f"Warning: Config file not found at {p}")
            return {}
            
        try:
            with open(p, 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Failed to parse config file: {e}")
            return {}

    def _build_command(self, source_file: Path) -> List[str]:
        """Construct the execution command based on the configured method."""
        
        if self.method == "apptainer":
            cfg = self.dafny_cfg.get("apptainer", {})
            image = cfg.get("image_path")
            container_mount_point = cfg.get("container_mount_point", "/work")
            
            # Validation
            if not image or not Path(image).exists():
                raise FileNotFoundError(f"Apptainer image not found at: {image}")

            # Ensure results_dir is absolute for reliable mounting
            results_dir_abs = Path(self.results_dir).resolve()
            
            # Construct Apptainer Command with explicit bind mount
            # This avoids permission issues in SLURM cluster environments where
            # automatic mounting of /tmp or NFS filesystems may fail
            source_file_name = source_file.name
            
            cmd = [
                "apptainer", "exec",
                "--bind", f"{results_dir_abs}:{container_mount_point}",
                str(image),
                "dafny",
                "verify",
                "--allow-warnings:true",
                f"{container_mount_point}/{source_file_name}"  # Use container path
            ]
            return cmd

        elif self.method == "docker":
            # Placeholder for future Docker implementation
            raise NotImplementedError("Docker support not yet implemented")

        elif self.method == "local":
            cfg = self.dafny_cfg.get("local", {})
            bin_path = cfg.get("bin_path", "dafny") # Assumes 'dafny' is in PATH
            return [str(bin_path), "verify", str(source_file.resolve())]

        else:
            raise ValueError(f"Unknown verification method: {self.method}")

    def verify(self, source: str, spec: str = "", filename: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        """Write source to a file and run the verifier.
        
        Note: 'spec' is included for interface consistency but Dafny 
        files usually contain both spec and impl, so it might be empty.
        """
        
        # 1. Prepare File Name
        ts = int(time.time() * 1000)
        safe_name = (filename or "submission").replace("/", "_")
        out_name = f"{safe_name}_{ts}.dfy"
        
        # Ensure results dir is absolute so apptainer mounts work reliably
        out_path = Path(self.results_dir).resolve() / out_name
        
        # 2. Write Source Code

        # For now, we assume 'source' contains the full Dafny program.
        full_content = source
        out_path.write_text(full_content)

        # 3. Build Command
        try:
            cmd = self._build_command(out_path)
        except Exception as e:
            return {
                "ok": False, 
                "reason": f"Configuration Error: {str(e)}", 
                "raw": None, 
                "file": str(out_path)
            }

        # 4. Execute
        try:
            proc = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=self.timeout
            )
            
            stdout = proc.stdout
            stderr = proc.stderr
            rc = proc.returncode
            
            raw = {"stdout": stdout, "stderr": stderr, "returncode": rc}
            
            # 5. Determine Success
            # Dafny 'verify' command exit codes:
            # 0 = Verified
            # 1 = Verification Error (or command line error)
            # 2/3/4 = Internal errors
            
            ok = (rc == 0)
            reason = None
            
            # Double check stdout for standard success message just in case
            # Standard success: "Dafny program verifier finished with X verified, 0 errors"
            if ok and "0 errors" not in stdout:
                ok = False
                reason = "Exit code 0 but '0 errors' not found in output"
            
            if not ok:
                if "verification error" in stdout.lower() or "errors" in stdout.lower():
                     reason = "Verification failed (found in stdout)"
                else:
                     reason = f"Dafny exited with code {rc}"

            return {
                "ok": ok, 
                "reason": reason, 
                "raw": raw, 
                "file": str(out_path)
            }

        except subprocess.TimeoutExpired:
            return {
                "ok": False, 
                "reason": f"Timeout after {self.timeout}s", 
                "raw": None, 
                "file": str(out_path)
            }
        except Exception as e:
            return {
                "ok": False, 
                "reason": f"Execution Error: {str(e)}", 
                "raw": None, 
                "file": str(out_path)
            }