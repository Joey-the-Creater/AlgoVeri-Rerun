from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.agent.lastdance_robust import (
    CheckpointManager,
    LastDanceFeatures,
    diagnostic_fingerprint,
    provenance_record,
    structured_feedback,
    targeted_diagnostics,
)
from src.agent.lean_candidate import MergedCandidate


class LastDanceRobustTests(unittest.TestCase):
    def test_profiles_keep_legacy_off_and_enable_robust_measures(self) -> None:
        api = LastDanceFeatures.profile_defaults("api")
        legacy = LastDanceFeatures.profile_defaults("legacy")
        robust = LastDanceFeatures.profile_defaults("robust")
        self.assertFalse(api.semantic_audit)
        self.assertFalse(api.leansearch)
        self.assertFalse(api.algorithm_plan)
        self.assertFalse(legacy.leansearch)
        self.assertTrue(robust.algorithm_plan)
        self.assertTrue(robust.lemma_plan)
        self.assertTrue(robust.leansearch)
        self.assertTrue(robust.backtracking)

    def test_diagnostic_fingerprint_ignores_locations(self) -> None:
        first = "/tmp/a.lean:12:4: error: unsolved goals\n⊢ True"
        second = "/tmp/a.lean:99:18: error: unsolved goals\n⊢ True"
        self.assertEqual(diagnostic_fingerprint(first), diagnostic_fingerprint(second))
        self.assertIn("unsolved goals", structured_feedback(first))

    def test_maps_lean_error_to_marker_section_and_declaration(self) -> None:
        code = """theorem teacher : True := by trivial
-- !benchmark @start code
def requested : Nat :=
  missingName
-- !benchmark @end code
-- !benchmark @start auxcode
-- !benchmark @end auxcode
-- !benchmark @start lemma
-- !benchmark @end lemma
-- !benchmark @start proof
by trivial
-- !benchmark @end proof
"""
        feedback = "candidate.lean:4:3: error: unknown identifier 'missingName'"
        targets = targeted_diagnostics(feedback, code)
        self.assertEqual(targets[0]["section"], "code")
        self.assertEqual(targets[0]["nearest_declaration"], "requested")

    def test_provenance_separates_teacher_sorry_from_model_sections(self) -> None:
        original = """-- teacher\ntheorem helper : True := by sorry
-- !benchmark @start auxcode\n-- !benchmark @end auxcode
-- !benchmark @start code\n-- !benchmark @end code
-- !benchmark @start lemma\n-- !benchmark @end lemma
-- !benchmark @start proof\nby trivial\n-- !benchmark @end proof\n"""
        candidate = original.replace("by trivial", "by exact True.intro")
        merged = MergedCandidate(
            code=candidate,
            sections={
                "auxcode": "-- !benchmark @start auxcode\n-- !benchmark @end auxcode",
                "code": "-- !benchmark @start code\n-- !benchmark @end code",
                "lemma": "-- !benchmark @start lemma\n-- !benchmark @end lemma",
                "proof": "-- !benchmark @start proof\nby exact True.intro\n-- !benchmark @end proof",
            },
        )
        record = provenance_record(original, candidate, merged)
        self.assertTrue(record["ownership"]["teacher_owned_sorry_present"])
        self.assertIn("proof", record["hashes"]["model_sections_sha256"])

    def test_checkpoint_restores_best_distinct_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            solution = workspace / "Solution.lean"
            manager = CheckpointManager(workspace)
            solution.write_text("candidate one")
            manager.save(solution, 1, "after", verified=False, feedback="error: first")
            solution.write_text("candidate two")
            manager.save(
                solution,
                2,
                "after",
                verified=False,
                feedback="error: second\nerror: third",
            )
            restored = manager.restore_best(solution)
            self.assertIsNotNone(restored)
            self.assertEqual(solution.read_text(), "candidate one")


if __name__ == "__main__":
    unittest.main()
