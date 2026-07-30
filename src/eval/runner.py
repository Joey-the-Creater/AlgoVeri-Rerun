"""High-level runner that loads problems and runs evaluations.

This Runner focuses on Verus (Rust) evaluation for now. It reads the
natural-language description from `verus_nl.txt` and the incomplete
spec/implementation from `verus_spec.rs` inside a problem folder and
uses `VerusEval` (which in turn uses the configured VerusVerifier)
to run the multi-round evaluation loop.
"""
from __future__ import annotations
from pathlib import Path
import sys
from typing import Optional, Dict, Any
import asyncio
import json
import os

from .base_eval import BaseEval
from src.verifiers.verus_verifier import VerusVerifier
from src.verifiers.dafny_verifier import DafnyVerifier
from src.verifiers.lean_verifier import LeanVerifier



class Runner:
    def __init__(self, llm_provider, language: str = "verus", cfg_path: str = None, results_root: Optional[str] = None):
        self.llm = llm_provider
        self.language = (language or "verus").lower()
        default_results = f"results/{self.language}"
        self.results_root = Path(results_root or os.environ.get("RESULTS_DIR") or default_results)
        self.results_root.mkdir(parents=True, exist_ok=True)
        self.cfg_path = cfg_path


    def _read_problem_files(self, problem_dir: Path) -> Dict[str, str]:
        """Read problem files according to `self.language`.

        Currently supports 'verus' (expects `verus_nl.txt` and `verus_spec.rs`), 'dafny' (expects 'dafny_nl.txt' and `dafny_spec.dfy`).
        Future languages should be added here.
        """
        lang = self.language
        if lang.startswith("verus") or lang.startswith("rust"):
            nl_path = problem_dir / "verus_nl.txt"
            spec_path = problem_dir / "verus_spec.rs"
            if not nl_path.exists():
                raise FileNotFoundError(f"Missing natural-language file: {nl_path}")
            if not spec_path.exists():
                raise FileNotFoundError(f"Missing verus spec file: {spec_path}")
            return {"natural": nl_path.read_text(), "spec": spec_path.read_text()}
        elif lang.startswith("dafny"):
            nl_path = problem_dir / "dafny_nl.txt"
            spec_path = problem_dir / "dafny_spec.dfy"
            if not nl_path.exists():
                raise FileNotFoundError(f"Missing natural-language file: {nl_path}")
            if not spec_path.exists():
                raise FileNotFoundError(f"Missing verus spec file: {spec_path}")
            return {"natural": nl_path.read_text(), "spec": spec_path.read_text()}
        elif lang.startswith("lean"):
            nl_path = problem_dir / "lean_nl.txt"
            spec_path = problem_dir / "lean_spec.lean"
            if not nl_path.exists():
                raise FileNotFoundError(f"Missing natural-language file: {nl_path}")
            if not spec_path.exists():
                raise FileNotFoundError(f"Missing verus spec file: {spec_path}")
            return {"natural": nl_path.read_text(), "spec": spec_path.read_text()}

        # Unknown language: raise for now
        raise NotImplementedError(f"Problem file reading not implemented for language: {self.language}")

    def run_problem(self, problem_dir: str, max_rounds: int = 5, num_passes: int = 1, model: str = "gemini-2.5-flash", system_prompt: str = "", debug: bool = False) -> Dict[str, Any]:
        """Run a single problem directory using the generic BaseEval factory.

        By default this will attempt to construct an evaluator appropriate for
        the dataset/problem language. `language` should be provided by the
        caller via the `run_problem` or `run_folder` higher-level calls. This
        function assumes Verus (Rust) by default if the caller does not pass
        a language (for backward compatibility).

        `problem_dir` may be a path to a directory containing `verus_nl.txt` and `verus_spec.rs` (for Verus/Rust) or `dafny_nl.txt` and `dafny_spec.dfy` (for Dafny).
        Returns the evaluation result dict and writes a JSON file to results.
        """
        # If stdin is piped (not a TTY) and contains a path, prefer it.
        try:
            if not sys.stdin.isatty():
                piped = sys.stdin.read().strip()
                if piped:
                    p = Path(piped)
                else:
                    p = Path(problem_dir)
            else:
                p = Path(problem_dir)
        except Exception:
            p = Path(problem_dir)

        if not p.exists() or not p.is_dir():
            raise FileNotFoundError(f"Problem directory not found: {p}")

        data = self._read_problem_files(p)
        natural = data["natural"]
        spec_code = data["spec"]

        # Determine evaluator using self.language
        evaler = self._make_evaluator(language=self.language, max_rounds=max_rounds)

        #
        friendly_model_name = model.split("/")[-1]

        # Use filename as last part of problem directory
        # e.g., for algoveri_data/binary_search, use "binary_search"
        problem_name = p.name
        print(f"Running {self.language} problem in {problem_name} using model {friendly_model_name}")
        filename = f"{friendly_model_name}_{problem_name}_eval"

        if num_passes == 1:
            result = evaler.run_single(natural_language=natural, formal_code=spec_code, model=model, filename=filename, spec=problem_name, system_prompt=system_prompt, debug=debug)
        else:
            # run multiple passes concurrently using a threadpool so that the
            # synchronous run_single can execute in parallel
            async def _run_passes():
                loop = asyncio.get_running_loop()

                async def _run_one(_idx: int):
                    pass_filename = f"{filename}_pass{_idx}"
                    return await loop.run_in_executor(
                        None,
                        evaler.run_single,
                        natural,
                        spec_code,
                        model,
                        pass_filename,
                        problem_name,
                        system_prompt,
                        debug,
                    )

                tasks = [_run_one(i) for i in range(int(num_passes))]
                return await asyncio.gather(*tasks)

            result = asyncio.run(_run_passes())

        out_path = self.results_root / f"{friendly_model_name}_{problem_name}_{self.language}.json"
        out_path.write_text(json.dumps(result, indent=4))
        return result

    def run_folder(self, folder: str, max_rounds: int = 5, model: str = "gemini-2.5-flash", system_prompt: str = "", debug: bool = False) -> Dict[str, Dict[str, Any]]:
        """Run every problem directory inside `folder`.

        For each immediate subdirectory that contains the expected files, run `run_problem`.
        Returns a mapping problem_name -> result.
        """
        folder_p = Path(folder)
        if not folder_p.exists() or not folder_p.is_dir():
            raise FileNotFoundError(f"Folder not found: {folder_p}")

        results: Dict[str, Dict[str, Any]] = {}
        for child in sorted(folder_p.iterdir()):
            if not child.is_dir():
                continue
            # skip hidden
            if child.name.startswith("."):
                continue
            # check presence of language-specific files by delegating to _read_problem_files
            try:
                # _read_problem_files will raise if required files are missing
                _ = self._read_problem_files(child)
                res = self.run_problem(str(child), max_rounds=max_rounds, model=model, system_prompt=system_prompt, debug=debug)
                results[child.name] = res
            except Exception as e:
                results[child.name] = {"error": str(e)}
        return results

    def _make_evaluator(self, language: str, max_rounds: int) -> BaseEval:
        """Factory that returns a BaseEval subclass instance for `language`.

        Currently supports:
          - 'verus' or 'rust' -> VerusEval

        Raises NotImplementedError for Dafny/Lean until their evaluators are available.
        """
        lang = (language or "").lower()
        if lang.startswith("verus") or lang.startswith("rust"):
            try:
                from .verus_eval import VerusEval

                # create with llm client and verifier handled by VerusEval
                verifier = VerusVerifier(config_path=self.cfg_path)
                return VerusEval(llm_client=self.llm, verifier=verifier, max_rounds=max_rounds)
            except Exception as e:
                raise RuntimeError(f"Failed to construct VerusEval: {e}")
        elif lang.startswith("dafny"):
            try:
                from .dafny_eval import DafnyEval

                # create with llm client and verifier handled by VerusEval
                verifier = DafnyVerifier(config_path=self.cfg_path)
                return DafnyEval(llm_client=self.llm, verifier=verifier, max_rounds=max_rounds)
            except Exception as e:
                raise RuntimeError(f"Failed to construct VerusEval: {e}")
        elif lang.startswith("lean"):
            try:
                from .lean_eval import LeanEval

                # create with llm client and verifier handled by VerusEval
                verifier = LeanVerifier(config_path=self.cfg_path)
                return LeanEval(llm_client=self.llm, verifier=verifier, max_rounds=max_rounds)
            except Exception as e:
                raise RuntimeError(f"Failed to construct LeanEval: {e}")
        else:
            raise NotImplementedError(f"Evaluator for language '{language}' is not implemented yet")

        raise NotImplementedError(f"Unknown/unsupported language: {language}")
