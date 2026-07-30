"""Verus (Rust + verus) verifier adapter.

Supports Apptainer, Docker, and Local execution strategies via hierarchical config.
"""
from .base import BaseVerifier
from typing import Dict, Any, Optional, List
from pathlib import Path
import subprocess
import time
import os
import yaml # Requires: pip install pyyaml

class VerusVerifier(BaseVerifier):
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the VerusVerifier.
        
        Args:
            config_path: Path to the YAML config file. If None, defaults to 
                         repo_root/config/config.yaml
        """
        self.config = self._load_config(config_path)
        
        # Load Verus specific config
        self.verus_cfg = self.config.get("verus", {})
        self.timeout = self.verus_cfg.get("timeout", 60)
        self.method = self.verus_cfg.get("method", "local")
        
        # Resolve global results directory
        self.results_dir = (
            self.config.get("results_dir")
            or os.environ.get("RESULTS_DIR")
            or "results/verus"
        )
        Path(self.results_dir).mkdir(parents=True, exist_ok=True)

    def _load_config(self, path: Optional[str]) -> Dict[str, Any]:
        """Load hierarchical YAML config safely."""
        if path:
            p = Path(path)
        else:
            # Default to config/config.yaml relative to this file's location
            # Assuming structure: repo/src/verifiers/verus_verifier.py -> repo/config/config.yaml
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
            cfg = self.verus_cfg.get("apptainer", {})
            image = cfg.get("image_path")
            host_rust_home = cfg.get("rust_home")

            # Validation
            if not image or not Path(image).exists():
                raise FileNotFoundError(f"Apptainer image not found at: {image}")
            if not host_rust_home or not Path(host_rust_home).exists():
                raise FileNotFoundError(f"Rust home dir not found at: {host_rust_home}")

            # Construct Apptainer Command
            # Bind cargo and toolchains separately to match installation configuration
            # This matches the setup in README where rust_home contains cargo/ and toolchains/ subdirs
            cmd = [
                "apptainer", "exec",
                "--bind", f"{host_rust_home}/cargo:/rust/cargo",
                "--bind", f"{host_rust_home}/toolchains:/rust/toolchains",
                "--env", "CARGO_HOME=/rust/cargo",
                "--env", "RUSTUP_HOME=/rust/toolchains",
                str(image),
                "verus",
                str(source_file.resolve()) # Use absolute path for safety
            ]
            return cmd

        elif self.method == "docker":
            # Placeholder for future Docker implementation
            raise NotImplementedError("Docker support not yet implemented")

        elif self.method == "local":
            # Fallback to local execution
            raise NotImplementedError("Docker support not yet implemented")
            cfg = self.verus_cfg.get("local", {})
            bin_path = cfg.get("bin_path", "verus")
            return [str(bin_path), str(source_file.resolve())]

        else:
            raise ValueError(f"Unknown verification method: {self.method}")

    def verify(self, source: str, spec: str, filename: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        """Write source to a file and run the verifier."""
        
        # 1. Prepare File Name
        ts = int(time.time() * 1000)
        safe_name = (filename or "submission").replace("/", "_")
        out_name = f"{safe_name}_{ts}.rs"
        
        # Ensure results dir is absolute so apptainer mounts work reliably if needed
        out_path = Path(self.results_dir).resolve() / out_name
        
        # 2. Write Source Code
        out_path.write_text(source)

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
            # Verus usually returns 0 on success.
            # Sometimes it returns 0 but prints verification errors to stdout, 
            # so we check stdout for failure keywords if RC is 0 (optional based on Verus version)
            ok = (rc == 0)
            reason = None
            
            if not ok:
                reason = f"Verus exited with code {rc}"
            elif "verification failed" in stdout.lower():
                # Some verifier versions might exit 0 even if verification fails
                ok = False
                reason = "Verification failed (found in stdout)"

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