from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class BaseEval(ABC):
    """Abstract evaluator: drives multi-turn LLM interaction and verification.

    Subclasses must implement prompt generation and response handling for specific
    languages (Dafny, Lean, Rust).
    """

    def __init__(self, llm_client, verifier=None, max_rounds: int = 5):
        # llm_client is a provider
        self.llm_client = llm_client
        self.verifier = verifier
        self.max_rounds = max_rounds
    
    @abstractmethod
    def make_sys_prompt(self) -> str:
        raise NotImplementedError()

    @abstractmethod
    def make_initial_prompt(self, natural_language, formal_code) -> str:
        raise NotImplementedError()
    
    @abstractmethod
    def make_revision_prompt(self, compiler_messages: str) -> str:
        raise NotImplementedError()

    @abstractmethod
    def parse_llm_response(self, response: str, formal_code: str = None) -> Dict[str, str]:
        """Parse LLM response and extract language code and any other channels.

        Should return a dict with at least the 'code' key and the original response in 'original'.
        """
        raise NotImplementedError()
    
    @abstractmethod
    def parse_verifier_response(self, response: Dict[str, str]) -> Dict[str, str]:
        """Parse verifier response and extract stdout, stderr, exitcode, and judge the result.

        return a dict with at least 'verified' key and other information included in a 'feedback' key.
        """
        raise NotImplementedError()

    def call_verifier(self, code: str, filename: str, spec: str = "") -> Dict[str, str]:
        if not self.verifier:
            raise RuntimeError("No verifier configured")
        # verifier should expose a `verify(code: str) -> dict` interface
        res = self.verifier.verify(source=code,spec=spec,filename=filename)

        return res

    def run_single(self, natural_language: str, formal_code: str, model: str, filename: str, spec: str = "", system_prompt: str = "", debug: bool=False) -> Dict[str, str]:
        """Run a single problem through multi-turn loop until verified or exhausted using model."""
        sys_prompt = system_prompt
        # initial user prompt
        prompt = self.make_initial_prompt(natural_language, formal_code)

        if debug:
            print(f"Creating chat session with model: {model}")
        
        mt_chat = self.llm_client.new_chat(model=model, system_prompt=system_prompt)
        if debug:
            print(f"General Instruction:\n{sys_prompt}\n")
            print(f"Initial User Prompt:\n{prompt}\n")

        for round_i in range(self.max_rounds):
            # send messages to LLM and receive response
            response = mt_chat.send_message(prompt)['text']
            parsed = self.parse_llm_response(response, formal_code)
            code = parsed.get("code", "")

            # call verifier
            if code:
                ver_res = self.call_verifier(code, filename, spec=spec)
            else:
                if parsed.get("comment", ""):
                    ver_res = {
                        "ok": False, 
                        "reason": parsed.get("comment", ""), 
                        "raw": None, 
                        "file": ""
                    }
                else:
                    ver_res = {
                        "ok": False, 
                        "reason": f"Cannot parse code from LLM response.", 
                        "raw": None, 
                        "file": ""
                    }

            parsed_ver_res = self.parse_verifier_response(ver_res)
            verified = parsed_ver_res.get("verified", False)

            if debug:
                print(f"Round {round_i+1} LLM Response:\n{response}\n")
                print(f"Parsed Code:\n{code}\n")
                print(f"Verifier Response:\n{ver_res}\n")
                print(f"Parsed Verifier Result:\n{parsed_ver_res}\n")

            # otherwise ask LLM to fix using feedback
            followup = parsed_ver_res.get("feedback", "")

            if verified:
                history = mt_chat.get_history()
                return {
                    "verified": True,
                    "details": {
                        "rounds": round_i,
                        "llm_response": parsed,
                        "verifier_response": parsed_ver_res,
                        "history": history,
                        "tokens": mt_chat.get_total_tokens(),
                    },
                }

            prompt = self.make_revision_prompt(followup)

        history = mt_chat.get_history()
        return {
                    "verified": False,
                    "details": {
                        "rounds": round_i,
                        "llm_response": parsed,
                        "verifier_response": parsed_ver_res,
                        "history": history,
                        "tokens": mt_chat.get_total_tokens(),
                    },
                }
