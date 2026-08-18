from __future__ import annotations

import unittest
from pathlib import Path

from src.agent.experiment_catalog import (
    ExperimentCatalog,
    first_semantic_pass,
    first_success_pass,
    first_success_try,
)


class ExperimentMetricTests(unittest.TestCase):
    def test_success_metrics_distinguish_repair_try_and_pass(self) -> None:
        attempts = [
            {"verified": False, "details": {"rounds": 14}},
            {
                "verified": True,
                "parsed": True,
                "verdict": True,
                "details": {"rounds": 2},
            },
        ]
        self.assertEqual(first_success_try(attempts), 3)
        self.assertEqual(first_success_pass(attempts), 2)
        self.assertEqual(first_semantic_pass(attempts), 2)


class PublishedExperimentCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(__file__).resolve().parents[1]
        cls.catalog = ExperimentCatalog(
            cls.repo,
            cls.repo / "config" / "dashboard_experiments.json",
            cls.repo / "algoveri_data",
        )
        cls.summaries = {item["id"]: item for item in cls.catalog.list()}

    def test_completed_baseline_totals(self) -> None:
        expected = {
            "gpt-5.5": (77, 77, 75, 24, 77, 21),
            "gpt-5.6-sol": (77, 77, 71, 25, 77, 19),
            "opus-5-thinking": (77, 49, 49, 29, 49, 33),
            "opus-5-no-thinking": (77, 77, 76, 36, 77, 24),
        }
        for run_id, values in expected.items():
            summary = self.summaries[run_id]
            actual = (
                summary["total"],
                summary["outputs"],
                summary["compile_success"],
                summary["semantic_success"],
                summary["semantic_evaluated"],
                summary["try_curve"][0]["successes"],
            )
            self.assertEqual(actual, values, run_id)

    def test_success_curves_are_cumulative(self) -> None:
        for summary in self.summaries.values():
            successes = [point["successes"] for point in summary["try_curve"]]
            self.assertEqual(successes, sorted(successes), summary["id"])
            self.assertLessEqual(successes[-1], summary["compile_success"])

    def test_lightweight_catalog_preserves_grouping_without_result_metrics(self) -> None:
        metadata = self.catalog.list_metadata()
        self.assertEqual(
            [item["id"] for item in metadata[:4]],
            [
                "architecture-legacy-combined",
                "architecture-enhanced-combined",
                "architecture-current-capped-combined",
                "lastdance-current-unlimited-fail9",
            ],
        )
        self.assertNotIn("compile_success", metadata[0])
        self.assertIn("comparison_default", metadata[0])

    def test_common_scope_applies_to_summary_and_matrix(self) -> None:
        comparison = self.catalog.compare(
            ["gpt-5.5", "claude-code-hard10"], scope_mode="common"
        )
        self.assertEqual(comparison["scope_count"], 10)
        self.assertEqual(len(comparison["matrix"]), 10)
        self.assertTrue(all(item["total"] == 10 for item in comparison["experiments"]))

    def test_native_scope_preserves_each_experiment_scope(self) -> None:
        comparison = self.catalog.compare(
            ["gpt-5.5", "claude-code-hard10"], scope_mode="native"
        )
        totals = {item["id"]: item["total"] for item in comparison["experiments"]}
        self.assertEqual(totals, {"gpt-5.5": 77, "claude-code-hard10": 10})
        self.assertEqual(len(comparison["matrix"]), 77)

    def test_matrix_uses_exactly_four_colored_outcomes(self) -> None:
        comparison = self.catalog.compare(
            ["gpt-5.5", "gpt-5.6-sol", "opus-5-no-thinking"],
            scope_mode="common",
        )
        allowed = {
            "semantic_success",
            "compiled_no_semantic_pass",
            "compile_failed",
            "missing",
        }
        states = {
            value["state"]
            for row in comparison["matrix"]
            for value in row["models"].values()
        }
        self.assertTrue(states <= allowed)
        self.assertIn("semantic_success", states)
        self.assertIn("compiled_no_semantic_pass", states)
        self.assertIn("compile_failed", states)

    def test_live_run_state_merges_semantic_results(self) -> None:
        state = self.catalog.get("claude-code-hard10").dashboard_state()
        self.assertEqual(state["summary"]["semantic_success"], 3)
        self.assertEqual(state["summary"]["semantic_evaluated"], 10)
        tasks = {item["name"]: item for item in state["tasks"]}
        self.assertEqual(tasks["gcd"]["outcome_state"], "semantic_success")
        self.assertEqual(
            tasks["llrbt_rotateright"]["outcome_state"],
            "compiled_no_semantic_pass",
        )
        detail = self.catalog.get("claude-code-hard10").dashboard_detail("gcd")
        self.assertTrue(detail["summary"]["semantic_success"])
        semantic_event = detail["timeline"][-1]
        self.assertEqual(semantic_event["title"], "Semantic judge accepted")
        self.assertEqual(semantic_event["status"], "verified")

        rejected = self.catalog.get("claude-code-hard10").dashboard_detail(
            "llrbt_rotateright"
        )
        semantic_event = rejected["timeline"][-1]
        self.assertEqual(semantic_event["title"], "Semantic judge rejected")
        self.assertEqual(semantic_event["status"], "failed")
        self.assertTrue(semantic_event["body"])

    def test_historical_run_trace_uses_semantic_outcome_colors(self) -> None:
        state = self.catalog.get("gpt-5.5").dashboard_state()
        tasks = {item["name"]: item for item in state["tasks"]}
        self.assertEqual(
            tasks["ac_automata"]["outcome_state"],
            "compiled_no_semantic_pass",
        )
        self.assertEqual(tasks["trie_search"]["outcome_state"], "compile_failed")
        self.assertEqual(
            state["summary"]["compiled_no_semantic_pass"],
            state["summary"]["verified"] - state["summary"]["semantic_success"],
        )

    def test_combined_claude_code_view_spans_batches(self) -> None:
        visible = {item["id"] for item in self.catalog.list()}
        self.assertIn("claude-code-opus5-combined", visible)
        self.assertNotIn("claude-code-hard10", visible)
        self.assertNotIn("claude-code-opus5-nonthinking20", visible)

        experiment = self.catalog.get("claude-code-opus5-combined")
        summary = experiment.summary()
        self.assertEqual(
            (
                summary["total"],
                summary["outputs"],
                summary["compile_success"],
                summary["semantic_success"],
                summary["semantic_evaluated"],
            ),
            (30, 30, 17, 14, 30),
        )
        self.assertEqual(
            experiment.dashboard_detail("gcd")["timeline"][-1]["title"],
            "Semantic judge accepted",
        )
        self.assertEqual(
            experiment.dashboard_detail("bfs")["timeline"][-1]["title"],
            "Semantic judge accepted",
        )

    def test_enhanced_run_tracks_clean_65_case_scope(self) -> None:
        experiment = self.catalog.get("claude-code-opus5-enhanced")
        summary = experiment.summary()
        self.assertEqual(summary["total"], 65)
        self.assertNotIn("trie_search", experiment.task_names)
        self.assertIn("stack_push", experiment.task_names)

    def test_dashboard_splits_current_runs_by_budget_and_tracks_legacy_scope(self) -> None:
        visible = self.catalog.list()
        self.assertEqual(
            [item["id"] for item in visible[:4]],
            [
                "architecture-legacy-combined",
                "architecture-enhanced-combined",
                "architecture-current-capped-combined",
                "lastdance-current-unlimited-fail9",
            ],
        )
        self.assertTrue(
            all(item["group"] == "Architecture results by budget" for item in visible[:4])
        )
        self.assertTrue(all(item["comparison_default"] for item in visible[:4]))
        self.assertFalse(any(item["comparison_default"] for item in visible[4:]))
        self.assertIn("maximum $4/task", visible[2]["condition"])
        self.assertIn("uncapped", visible[3]["label"])

        legacy = self.catalog.get("claude-code-legacy65")
        self.assertEqual(legacy.summary()["total"], 65)
        self.assertNotIn("trie_search", legacy.task_names)
        self.assertIn("stack_push", legacy.task_names)
        self.assertNotIn(
            "claude-code-api-equivalent-fail9",
            {item["id"] for item in visible},
        )
        self.assertNotIn(
            "architecture-current-combined",
            {item["id"] for item in visible},
        )
        self.assertNotIn(
            "lastdance-current-enhanced-fail5",
            {item["id"] for item in visible},
        )

    def test_combined_architectures_merge_completed_sources_with_provenance(self) -> None:
        legacy = self.catalog.get("architecture-legacy-combined")
        enhanced = self.catalog.get("architecture-enhanced-combined")
        current = self.catalog.get("architecture-current-combined")
        capped_current = self.catalog.get("architecture-current-capped-combined")

        legacy_summary = legacy.summary()
        self.assertEqual(legacy_summary["outputs"], legacy_summary["total"])
        self.assertLessEqual(legacy_summary["total"], 65)
        self.assertEqual(enhanced.summary()["total"], 65)
        self.assertTrue(
            any(
                source.get("results_root")
                == "results/claude_code_original_plus_repair30"
                for source in enhanced.source_configs
            )
        )
        self.assertEqual(
            enhanced.task_result("max_matching")["source_label"],
            "Enhanced 65 · GPT-5.4 T0",
        )
        self.assertEqual(current.summary()["total"], 11)
        capped_summary = capped_current.summary()
        self.assertEqual(capped_summary["total"], 18)
        self.assertEqual(capped_summary["outputs"], 18)
        self.assertEqual(
            capped_current.task_result("bellman_ford")["source_label"],
            "Current capped · budget-13 batch",
        )
        self.assertEqual(
            capped_current.task_result("bubble_sort")["source_label"],
            "Current capped · fail-5 batch",
        )

        self.assertEqual(
            current.task_result("ac_automata")["source_label"],
            "Current · uncapped fail-9",
        )
        self.assertEqual(
            current.task_result("bubble_sort")["source_label"],
            "Current · Enhanced failure-set run",
        )
        self.assertEqual(
            current.task_result("polymul_naive")["source_label"],
            "Current · Enhanced failure-set run",
        )
        self.assertNotIn("bellman_ford", current.task_names)
        self.assertNotIn(
            "claude-code-original-plus-repair30",
            {item["id"] for item in self.catalog.list()},
        )

    def test_temperature_zero_dashboard_condition_is_separate(self) -> None:
        expected = {
            "gpt-5.5-temp0",
            "gpt-5.6-sol-temp0",
            "opus-5-thinking-temp0",
            "opus-5-no-thinking-temp0",
            "claude-code-opus5-enhanced-temp0",
        }
        self.assertTrue(expected <= self.summaries.keys())
        self.assertTrue(
            all(
                self.summaries[run_id]["judge_temperature"] == 0
                and self.summaries[run_id]["judge_model"] == "gpt-5.4"
                for run_id in expected
            )
        )
        enhanced = self.catalog.get("claude-code-opus5-enhanced-temp0")
        self.assertEqual(enhanced.summary()["total"], 65)
        self.assertNotEqual(
            enhanced.semantic_root,
            self.catalog.get("claude-code-opus5-enhanced").semantic_root,
        )

    def test_gpt56_temperature_zero_judge_is_separate(self) -> None:
        expected = {
            "gpt-5.5-judge-gpt56-temp0",
            "gpt-5.6-sol-judge-gpt56-temp0",
            "opus-5-thinking-judge-gpt56-temp0",
            "opus-5-no-thinking-judge-gpt56-temp0",
            "claude-code-opus5-enhanced-judge-gpt56-temp0",
        }
        self.assertTrue(expected <= self.summaries.keys())
        self.assertTrue(
            all(
                self.summaries[run_id]["judge_model"] == "gpt-5.6-sol"
                and self.summaries[run_id]["judge_temperature"] == 0
                and self.summaries[run_id]["judge_reasoning_effort"] == "none"
                for run_id in expected
            )
        )
        gpt56 = self.catalog.get("claude-code-opus5-enhanced-judge-gpt56-temp0")
        gpt54 = self.catalog.get("claude-code-opus5-enhanced-temp0")
        self.assertEqual(gpt56.summary()["total"], 65)
        self.assertNotEqual(gpt56.semantic_root, gpt54.semantic_root)


if __name__ == "__main__":
    unittest.main()
