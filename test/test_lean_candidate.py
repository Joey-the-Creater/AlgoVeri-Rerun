from __future__ import annotations

import unittest

from src.agent.lean_candidate import (
    CandidateValidationError,
    has_teacher_owned_sorry,
    merge_candidate_sections,
)


def source(aux: str = "", code: str = "sorry", lemma: str = "", proof: str = "sorry") -> str:
    return f"""import Mathlib
-- teacher-owned termination proof
decreasing_by sorry
-- !benchmark @start auxcode
{aux}
-- !benchmark @end auxcode
def answer : Nat :=
  -- !benchmark @start code
  {code}
  -- !benchmark @end code
-- !benchmark @start lemma
{lemma}
-- !benchmark @end lemma
theorem answer_ok : answer = 1 := by
  -- !benchmark @start proof
  {proof}
  -- !benchmark @end proof
"""


class LeanCandidateTests(unittest.TestCase):
    def test_merges_only_editable_sections(self) -> None:
        original = source()
        candidate = source(code="1", proof="rfl").replace("import Mathlib", "import Bogus")
        merged = merge_candidate_sections(original, candidate).code
        self.assertTrue(merged.startswith("import Mathlib"))
        self.assertIn("decreasing_by sorry", merged)
        self.assertIn("  1", merged)
        self.assertIn("  rfl", merged)
        self.assertNotIn("import Bogus", merged)

    def test_allows_teacher_sorry_outside_editable_sections(self) -> None:
        merge_candidate_sections(source(), source(code="1", proof="rfl"))

    def test_rejects_generated_sorry(self) -> None:
        with self.assertRaisesRegex(CandidateValidationError, "prohibited term 'sorry'"):
            merge_candidate_sections(source(), source(code="sorry", proof="rfl"))

    def test_detects_only_teacher_owned_sorry(self) -> None:
        self.assertTrue(has_teacher_owned_sorry(source(code="rfl", proof="rfl")))
        without_teacher_sorry = source(code="rfl", proof="rfl").replace(
            "decreasing_by sorry", "decreasing_by decreasing_tactic"
        )
        self.assertFalse(has_teacher_owned_sorry(without_teacher_sorry))

    def test_ignores_editable_sorry_for_teacher_filter(self) -> None:
        without_teacher_sorry = source().replace(
            "decreasing_by sorry", "decreasing_by decreasing_tactic"
        )
        self.assertFalse(has_teacher_owned_sorry(without_teacher_sorry))

    def test_rejects_missing_section(self) -> None:
        candidate = source(code="1", proof="rfl").replace(
            "-- !benchmark @start lemma\n\n-- !benchmark @end lemma\n", ""
        )
        with self.assertRaisesRegex(CandidateValidationError, "exactly one 'lemma'"):
            merge_candidate_sections(source(), candidate)

    def test_rejects_duplicate_section(self) -> None:
        candidate = source(code="1", proof="rfl") + "\n-- !benchmark @start code\n1\n-- !benchmark @end code\n"
        with self.assertRaisesRegex(CandidateValidationError, "exactly one 'code'"):
            merge_candidate_sections(source(), candidate)


if __name__ == "__main__":
    unittest.main()
