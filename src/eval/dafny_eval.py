from __future__ import annotations
import re
from typing import Dict, Any

from .base_eval import BaseEval

# import prompts
from .prompt.dafny_prompt import *

# attempt to import Dafny verifier (relative import within package)
try:
    from ..verifiers.dafny_verifier import DafnyVerifier
except Exception:
    try:
        # fallback to absolute import if package layout differs
        from verifiers.dafny_verifier import DafnyVerifier
    except Exception:
        DafnyVerifier = None


class DafnyEval(BaseEval):
    def __init__(self, llm_client, verifier=None, max_rounds: int = 5):
        if verifier is None and DafnyVerifier is not None:
            verifier = DafnyVerifier()
        super().__init__(llm_client=llm_client, verifier=verifier, max_rounds=max_rounds)
    
    def make_sys_prompt(self) -> str:
        return DAFNY_SYSTEM_PROMPT

    def make_initial_prompt(self, natural_language, formal_code) -> str:
        user_p = self.make_sys_prompt() + '\n\n' + DAFNY_INITIAL_PROMPT.format(natural_language=natural_language, formal_code=formal_code)
        return user_p
    
    def make_revision_prompt(self, compiler_messages: str) -> str:
        return DAFNY_REVISION_PROMPT.format(compiler_error_messages=compiler_messages)

    def parse_llm_response(self, response: str, formal_code: str = None) -> Dict[str, str]:
        """Parse the LLM response and ensure tags are present/normalized.

        Behavior:
        - If `formal_code` is provided, extract expected `<preamble>` and
          `<spec>` contents from it.
        - Extract the dafny fenced code block (or any fenced block) from the
          LLM response as `code`.
        - If `code` contains `<preamble>` and/or `<spec>` tags, replace the
          inner contents with the expected values extracted from
          `formal_code` (if non-empty).
        - If expected content exists but the corresponding tag is missing in
          `code`, return `code: ""` and a `comment` instructing the model
          to include the missing tag(s).
        """
        # extract expected pieces from the template if available
        preamble_pattern = re.compile(r'<preamble>.*?</preamble>', re.DOTALL)
        spec_pattern = re.compile(r'<spec>.*?</spec>', re.DOTALL)
        code_pattern = re.compile(r'<code>.*?</code>', re.DOTALL)

        extracted_preamble = preamble_pattern.search(formal_code) if formal_code else None
        extracted_spec = spec_pattern.search(formal_code) if formal_code else None
        extracted_code = code_pattern.search(formal_code) if formal_code else None

        # extract code block
        code = ""
        comment = response
        m = re.search(r"```\s*dafny\s*(.*?)```", response, re.S | re.I)
        if m:
            code = m.group(1).strip()
            comment = (response[:m.start()] + response[m.end():]).strip()
        else:
            m2 = re.search(r"```(.*?)```", response, re.S | re.I)
            if m2:
                code = m2.group(1).strip()
                comment = (response[:m2.start()] + response[m2.end():]).strip()


        # Now check presence of tags and either replace or report missing
        missing_tags = []
        modified = code

        preamble_in_code = preamble_pattern.search(modified)
        if not (preamble_in_code and extracted_preamble):
            missing_tags.append("preamble")
        elif preamble_in_code and extracted_preamble:
            modified = preamble_pattern.sub(extracted_preamble.group(0), modified)
        
        spec_in_code = spec_pattern.search(modified)
        if not (spec_in_code and extracted_spec):
            missing_tags.append("spec")
        elif spec_in_code and extracted_spec:
            modified = spec_pattern.sub(extracted_spec.group(0), modified)
        
        missing_code_impl = False
        code_in_code = code_pattern.search(modified)
        if not (code_in_code and ('{' in code_in_code.group(0).strip()) and ('}' in code_in_code.group(0).strip())):
            missing_code_impl = True


        if missing_code_impl:
            return {"code": "", "comment": "do not find code implementation block; please include <code>...</code> containing the implementation and proofs."}
        if missing_tags:
            # instructive comment for the model
            if len(missing_tags) == 1:
                tag = missing_tags[0]
                comment = f"do not find {tag} tag in the generated code; please include <{tag}>...</{tag}> containing the corresponding section from the formal template."
            else:
                comment = f"do not find tags {', '.join(missing_tags)} in the generated code; please include them (e.g. <preamble>...</preamble> and <spec>...</spec>) with the corresponding contents from the formal template."
            return {"code": "", "comment": comment}
        
        # Now check if the model tries to cheat by including 'assume', 'verify false', 'axiom', 'extern', or 'expect'
        if ("assume" in modified or "verify false" in modified or "axiom" in modified or "extern" in modified or "expect" in modified):
            comment = "The generated code contains 'assume', 'verify false', 'axiom', 'extern', or 'expect', which is not allowed. Please provide a complete implementation and proof without using these keywords."
            return {"code": "", "comment": comment}

        return {"code": modified, "comment": comment}

    def parse_verifier_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(response, dict):
            return {"verified": False, "feedback": "Response is not a dict.", "raw": None}
        if "ok" not in response:
            return {"verified": False, "feedback": "Response missing 'ok' field.", "raw": None}
        ok = response["ok"]
        raw = response.get("raw", None)
        if not ok:
            if not raw:
                reason = response.get("reason", "No reason provided.")
                return {"verified": False, "feedback": reason, "raw": None}
            else:
                stdout_message = raw.get("stdout", "")
                stderr_message = raw.get("stderr", "")
                feedback_msg = f"Stdout:\n{stdout_message}\n\nStderr:\n {stderr_message}"
                return {"verified": False, "feedback": feedback_msg, "raw": raw}
        if not raw:
            return {"verified": False, "feedback": "Bug in verifier.", "raw": None}
        stdout_message = raw.get("stdout", "")
        stderr_message = raw.get("stderr", "")

        return {"verified": True, "feedback": "Verified successfully.", "raw": raw}

