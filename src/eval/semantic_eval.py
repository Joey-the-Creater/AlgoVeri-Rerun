from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import re
from .prompt.semantic_check_prompt import SEMANTIC_SYS_PROMPT, SEMANTIC_INITIAL_PROMPT, SEMANTIC_REVISION_PROMPT

class SemanticEval:
    """Abstract evaluator: drives multi-turn LLM interaction and verification.

    Subclasses must implement prompt generation and response handling for specific
    languages (Dafny, Lean, Rust).
    """

    def __init__(self, llm_client, max_rounds: int = 5, temperature: float = 1.0):
        # llm_client is a provider
        self.llm_client = llm_client
        self.max_rounds = max_rounds
        self.temperature = temperature
    
    def make_sys_prompt(self) -> str:
        return SEMANTIC_SYS_PROMPT

    def make_initial_prompt(self, natural_language, formal_code) -> str:
        return SEMANTIC_INITIAL_PROMPT.format(description=natural_language, code=formal_code)
    
    def make_revision_prompt(self) -> str:
        return SEMANTIC_REVISION_PROMPT

    def parse_llm_response(self, response: str, formal_code: str = None) -> Dict[str, str]:
        """Parse LLM response to extract analysis and conclusion."""
        analysis_match = re.search(r"<analysis>(.*?)</analysis>", response, re.DOTALL)
        conclusion_match = re.search(r"<conclusion>(.*?)</conclusion>", response, re.DOTALL)

        analysis = analysis_match.group(1).strip() if analysis_match else ""
        conclusion = conclusion_match.group(1).strip().upper() if conclusion_match else ""

        verdict = None
        if conclusion == "YES":
            verdict = True
        elif conclusion == "NO":
            verdict = False

        parsed = ( (verdict is not None) and (analysis != "") )

        return {
            "parsed": parsed,
            "verdict": verdict,
            "analysis": analysis,
        }

    def run_single(self, natural_language: str, formal_code: str, model: str, filename: str, spec: str = "", system_prompt: str = "", debug: bool=False) -> Dict[str, str]:
        """Run a single problem through multi-turn loop until verified or exhausted using model."""
        sys_prompt = self.make_sys_prompt()
        # initial user prompt
        prompt = self.make_initial_prompt(natural_language, formal_code)

        if debug:
            print(f"Creating chat session with model: {model}")
        
        mt_chat = self.llm_client.new_chat(model=model, system_prompt=system_prompt or sys_prompt)
        if debug:
            print(f"General Instruction:\n{sys_prompt}\n")
            print(f"Initial User Prompt:\n{prompt}\n")

        for round_i in range(self.max_rounds):
            # send messages to LLM and receive response
            response = mt_chat.send_message(prompt, temperature=self.temperature)['text']
            parsed = self.parse_llm_response(response, formal_code)

            if debug:
                print(f"LLM Response (Round {round_i + 1}):\n{response}\n")
                print(f"Parsed Result:\n{parsed}\n")


            if parsed.get("parsed", False):
                return {
                    "parsed": True,
                    "verdict": parsed.get("verdict", False),
                    "analysis": parsed.get("analysis", ""),
                }

            prompt = self.make_revision_prompt()

        return {
                    "parsed": False,
                    "verdict": False,
                    "analysis": "",
                }
