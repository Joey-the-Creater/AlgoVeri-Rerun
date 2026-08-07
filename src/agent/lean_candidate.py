"""Validate and merge the editable regions of an AlgoVeri Lean candidate."""

from __future__ import annotations

import re
from dataclasses import dataclass


EDITABLE_SECTIONS = ("auxcode", "code", "lemma", "proof")
PROHIBITED_TERMS = (
    "sorry",
    "admit",
    "axiom",
    "constant",
    "partial",
    "unsafe",
    "@[extern",
    "@[implemented_by",
)


class CandidateValidationError(ValueError):
    """The agent candidate does not obey the benchmark editing contract."""


@dataclass(frozen=True)
class MergedCandidate:
    code: str
    sections: dict[str, str]


def _section_pattern(name: str) -> re.Pattern[str]:
    return re.compile(
        rf"-- !benchmark @start {re.escape(name)}.*?"
        rf"-- !benchmark @end {re.escape(name)}",
        re.DOTALL,
    )


def _extract_single(source: str, name: str, label: str) -> str:
    matches = _section_pattern(name).findall(source)
    if len(matches) != 1:
        raise CandidateValidationError(
            f"{label} must contain exactly one {name!r} section; found {len(matches)}"
        )
    return matches[0]


def merge_candidate_sections(original: str, candidate: str) -> MergedCandidate:
    """Merge only the four agent-editable blocks into the original source.

    This intentionally permits teacher-provided ``sorry`` occurrences elsewhere in
    the original file. Prohibited terms are checked only in candidate-owned blocks,
    matching the baseline's intended parsing policy.
    """

    sections: dict[str, str] = {}
    merged = original
    for name in EDITABLE_SECTIONS:
        _extract_single(original, name, "original")
        block = _extract_single(candidate, name, "candidate")
        for term in PROHIBITED_TERMS:
            if term in block:
                raise CandidateValidationError(
                    f"candidate {name!r} section contains prohibited term {term!r}"
                )
        sections[name] = block
        merged, replacements = _section_pattern(name).subn(lambda _: block, merged)
        if replacements != 1:
            raise CandidateValidationError(
                f"failed to replace exactly one {name!r} section in original"
            )

    return MergedCandidate(code=merged, sections=sections)


def has_teacher_owned_sorry(source: str) -> bool:
    """Return whether ``sorry`` occurs outside all agent-editable sections."""
    teacher_owned = source
    for name in EDITABLE_SECTIONS:
        _extract_single(source, name, "source")
        teacher_owned, replacements = _section_pattern(name).subn("", teacher_owned)
        if replacements != 1:
            raise CandidateValidationError(
                f"failed to remove exactly one {name!r} section from source"
            )
    return re.search(r"\bsorry\b", teacher_owned) is not None
