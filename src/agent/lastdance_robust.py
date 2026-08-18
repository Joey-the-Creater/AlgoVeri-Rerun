"""Robustness controls and durable artifacts for the LastDance Lean agent."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .lean_candidate import EDITABLE_SECTIONS, MergedCandidate, has_teacher_owned_sorry


@dataclass(frozen=True)
class LastDanceFeatures:
    """A fully recorded experimental condition.

    ``legacy`` reproduces the previously published runner behavior. ``robust``
    enables the additions without changing the legacy defaults.
    """

    profile: str = "legacy"
    algorithm_plan: bool = False
    lemma_plan: bool = False
    leansearch: bool = False
    semantic_audit: bool = True
    semantic_reminder: bool = True
    early_check: bool = True
    feedback_mode: str = "exact"
    backtracking: bool = False
    stagnation_threshold: int = 2

    @classmethod
    def profile_defaults(cls, profile: str) -> "LastDanceFeatures":
        if profile == "api":
            return cls(
                profile="api",
                semantic_audit=False,
                semantic_reminder=False,
                early_check=False,
            )
        if profile == "legacy":
            return cls(profile="legacy")
        if profile == "robust":
            return cls(
                profile="robust",
                algorithm_plan=True,
                lemma_plan=True,
                leansearch=True,
                semantic_audit=True,
                semantic_reminder=True,
                early_check=True,
                feedback_mode="structured",
                backtracking=True,
                stagnation_threshold=2,
            )
        raise ValueError(f"unknown LastDance profile: {profile}")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


_DIAGNOSTIC_LOCATION = re.compile(r"(?P<file>[^\s:]+\.lean):\d+:\d+")
_VOLATILE_PATH = re.compile(r"(?:/[^\s:]+)+/(?:tmp|temp)[^\s:]*", re.IGNORECASE)


def normalize_diagnostic(feedback: str) -> str:
    """Remove volatile paths/coordinates while preserving the actual errors."""
    text = _DIAGNOSTIC_LOCATION.sub(lambda m: f"{Path(m.group('file')).name}:<loc>", feedback)
    text = _VOLATILE_PATH.sub("<temporary-path>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def diagnostic_fingerprint(feedback: str) -> str:
    return sha256_text(normalize_diagnostic(feedback))[:16]


def structured_feedback(feedback: str, limit: int = 8000) -> str:
    """Return targeted Lean diagnostics plus a bounded exact tail.

    The exact text remains available in the result and ledger. This view reduces
    repeated boilerplate in a repair prompt while retaining goals and errors.
    """
    lines = feedback.splitlines()
    selected: list[str] = []
    keep_following = 0
    keywords = (
        "error:",
        "unsolved goals",
        "type mismatch",
        "application type mismatch",
        "unknown identifier",
        "failed to synthesize",
        "declaration uses 'sorry'",
        "candidate validation failed",
    )
    for line in lines:
        lowered = line.lower()
        if any(keyword in lowered for keyword in keywords):
            selected.append(line)
            keep_following = 12
        elif keep_following > 0:
            selected.append(line)
            keep_following -= 1
    compact = "\n".join(selected).strip()
    if not compact:
        compact = feedback.strip()
    if len(compact) > limit:
        compact = compact[-limit:]
    return compact or "No verifier details were returned."


_LEAN_ERROR_LINE = re.compile(
    r"(?P<file>[^\s:]+\.lean):(?P<line>\d+):(?P<column>\d+):\s*(?P<kind>error|warning):\s*(?P<message>.*)"
)
_DECLARATION = re.compile(
    r"^\s*(?:private\s+|protected\s+)?(?:def|theorem|lemma|instance|structure)\s+([^\s:{(]+)"
)


def targeted_diagnostics(feedback: str, merged_code: str) -> list[dict[str, Any]]:
    """Map verifier locations to a model-owned section and nearest declaration."""
    lines = merged_code.splitlines()
    ranges = marker_ranges(merged_code)
    targets: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()
    for match in _LEAN_ERROR_LINE.finditer(feedback):
        line = int(match.group("line"))
        column = int(match.group("column"))
        key = (line, column, match.group("message"))
        if key in seen:
            continue
        seen.add(key)
        section = next(
            (
                name
                for name, span in ranges.items()
                if span["start_line"] <= line <= span["end_line"]
            ),
            "teacher-owned-or-generated",
        )
        declaration = None
        for source_line in reversed(lines[: min(line, len(lines))]):
            declaration_match = _DECLARATION.match(source_line)
            if declaration_match:
                declaration = declaration_match.group(1)
                break
        targets.append(
            {
                "line": line,
                "column": column,
                "kind": match.group("kind"),
                "message": match.group("message").strip(),
                "section": section,
                "nearest_declaration": declaration,
            }
        )
    return targets


def targeted_diagnostics_markdown(targets: list[dict[str, Any]]) -> str:
    if not targets:
        return "No source-mapped diagnostic target was detected."
    rows = []
    for target in targets:
        declaration = target.get("nearest_declaration") or "unknown declaration"
        rows.append(
            f"- `{target['section']}` / `{declaration}` at "
            f"{target['line']}:{target['column']}: {target['message']}"
        )
    return "\n".join(rows)


def marker_ranges(source: str) -> dict[str, dict[str, int]]:
    ranges: dict[str, dict[str, int]] = {}
    for name in EDITABLE_SECTIONS:
        start_marker = f"-- !benchmark @start {name}"
        end_marker = f"-- !benchmark @end {name}"
        start = source.find(start_marker)
        end = source.find(end_marker, start)
        if start >= 0 and end >= 0:
            ranges[name] = {
                "start_line": source.count("\n", 0, start) + 1,
                "end_line": source.count("\n", 0, end) + 1,
            }
    return ranges


def provenance_record(
    original: str,
    candidate: str,
    merged: MergedCandidate,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ownership": {
            "model_owned_sections": list(EDITABLE_SECTIONS),
            "teacher_owned": "all source outside the four marker regions",
            "teacher_owned_sorry_present": has_teacher_owned_sorry(original),
            "model_section_ranges": marker_ranges(merged.code),
        },
        "hashes": {
            "original_sha256": sha256_text(original),
            "candidate_sha256": sha256_text(candidate),
            "merged_sha256": sha256_text(merged.code),
            "model_sections_sha256": {
                name: sha256_text(block) for name, block in merged.sections.items()
            },
        },
    }


@dataclass
class Checkpoint:
    path: Path
    candidate_sha256: str
    pass_number: int
    stage: str
    verified: bool | None
    diagnostic_score: int
    fingerprint: str | None


class CheckpointManager:
    """Harness-owned candidate snapshots used for safe rollback."""

    def __init__(self, workspace: Path, max_checkpoints: int = 20) -> None:
        self.root = workspace / ".lastdance" / "checkpoints"
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_checkpoints = max_checkpoints
        self.items: list[Checkpoint] = []

    @staticmethod
    def diagnostic_score(feedback: str) -> int:
        lowered = feedback.lower()
        return (
            10 * lowered.count("error:")
            + 6 * lowered.count("unsolved goals")
            + 2 * lowered.count("warning:")
            + min(len(feedback) // 2000, 9)
        )

    def save(
        self,
        solution: Path,
        pass_number: int,
        stage: str,
        verified: bool | None = None,
        feedback: str = "",
    ) -> Checkpoint:
        text = solution.read_text()
        digest = sha256_text(text)
        filename = f"{len(self.items) + 1:03d}-pass-{pass_number}-{stage}.lean"
        path = self.root / filename
        shutil.copy2(solution, path)
        checkpoint = Checkpoint(
            path=path,
            candidate_sha256=digest,
            pass_number=pass_number,
            stage=stage,
            verified=verified,
            diagnostic_score=0 if verified else self.diagnostic_score(feedback),
            fingerprint=diagnostic_fingerprint(feedback) if feedback else None,
        )
        self.items.append(checkpoint)
        metadata = {**asdict(checkpoint), "path": str(path)}
        append_jsonl(self.root / "manifest.jsonl", metadata)
        while len(self.items) > self.max_checkpoints:
            old = self.items.pop(0)
            try:
                old.path.unlink()
            except OSError:
                pass
        return checkpoint

    def restore_best(self, solution: Path, exclude_sha256: str = "") -> Checkpoint | None:
        eligible = [
            item
            for item in self.items
            if item.candidate_sha256 != exclude_sha256 and item.stage == "after"
        ]
        if not eligible:
            return None
        best = min(
            eligible,
            key=lambda item: (not bool(item.verified), item.diagnostic_score, -item.pass_number),
        )
        shutil.copy2(best.path, solution)
        return best
