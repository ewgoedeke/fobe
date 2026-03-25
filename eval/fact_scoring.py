#!/usr/bin/env python3
"""
fact_scoring.py — Per-fact corroboration scoring.

Every indexed fact gets a status based on how many independent checks
corroborate it:

  CONFIRMED     — ≥2 independent checks pass
  CORROBORATED  — exactly 1 check passes
  UNCONFIRMED   — no checks testable
  CONTRADICTED  — ≥1 check fails with no explaining ambiguity
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CorroborationStatus(Enum):
    CONFIRMED = "CONFIRMED"
    CORROBORATED = "CORROBORATED"
    UNCONFIRMED = "UNCONFIRMED"
    CONTRADICTED = "CONTRADICTED"


@dataclass
class CheckResult:
    """One validation check applied to a fact."""
    check_type: str    # SUMMATION, CROSS_STATEMENT_TIE, DISAGGREGATION,
                       # NOTE_TO_FACE, IC_DECOMPOSITION, TABLE_ARITHMETIC
    edge_name: str     # ontology edge or "table_arith_{table_id}"
    passed: bool
    delta: float = 0.0
    explained: bool = False  # True if failure is explained by ambiguity/pattern
    detail: str = ""


@dataclass
class FactScore:
    """Corroboration score for a single indexed fact."""
    table_id: str
    context: str
    concept_id: str
    period_key: str
    col_idx: int
    amount: float
    label: str
    page: int = 0
    row_id: str = ""
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def status(self) -> CorroborationStatus:
        if not self.checks:
            return CorroborationStatus.UNCONFIRMED
        passing = [c for c in self.checks if c.passed]
        failing_unexplained = [c for c in self.checks if not c.passed and not c.explained]
        if failing_unexplained:
            return CorroborationStatus.CONTRADICTED
        if len(passing) >= 2:
            return CorroborationStatus.CONFIRMED
        if len(passing) == 1:
            return CorroborationStatus.CORROBORATED
        # All checks were explained failures — not contradicted, but not confirmed
        return CorroborationStatus.UNCONFIRMED

    @property
    def fact_key(self) -> tuple:
        return (self.table_id, self.concept_id, self.col_idx)

    def to_dict(self) -> dict:
        d = {
            "table_id": self.table_id,
            "context": self.context,
            "concept_id": self.concept_id,
            "period_key": self.period_key,
            "amount": self.amount,
            "label": self.label,
            "status": self.status.value,
        }
        if self.checks:
            d["checks"] = [
                {
                    "type": c.check_type,
                    "edge": c.edge_name,
                    "passed": c.passed,
                    "delta": c.delta,
                }
                for c in self.checks
            ]
        return d


def build_score_registry(facts: dict) -> dict[tuple, FactScore]:
    """Create a FactScore for every indexed fact.

    Key: (table_id, concept_id, col_idx) → FactScore
    """
    registry: dict[tuple, FactScore] = {}
    for (ctx, cid, pk), fact_list in facts.items():
        for f in fact_list:
            key = (f.table_id, f.concept_id, f.col_idx)
            if key not in registry:
                registry[key] = FactScore(
                    table_id=f.table_id,
                    context=f.context,
                    concept_id=f.concept_id,
                    period_key=pk,
                    col_idx=f.col_idx,
                    amount=f.amount,
                    label=f.label,
                    page=f.page,
                    row_id=getattr(f, "row_id", ""),
                )
    return registry


# Map Finding categories to check pass/fail/explained
_PASSING_CATEGORIES = {"VALID_DISAGGREGATION", "VALID_TIE"}
_EXPLAINED_CATEGORIES = {"EXPLAINED_MISMATCH", "UNEXPLAINED_INCONSISTENCY", "IC_LEAKAGE"}


def apply_findings_to_scores(
    findings: list,
    facts: dict,
    registry: dict[tuple, FactScore],
) -> None:
    """Map each Finding to the Facts it tested, append CheckResults."""
    for finding in findings:
        cat_val = finding.category.value
        passed = cat_val in _PASSING_CATEGORIES
        explained = cat_val in _EXPLAINED_CATEGORIES

        # Determine check_type from edge or category
        check_type = finding.edge_name.split("_")[0].upper() if finding.edge_name else cat_val
        if finding.pattern_id:
            check_type = f"PATTERN_{finding.pattern_id}"

        cr = CheckResult(
            check_type=check_type,
            edge_name=finding.edge_name or finding.pattern_id or cat_val,
            passed=passed,
            delta=finding.delta or 0.0,
            explained=explained,
            detail=finding.message[:120] if finding.message else "",
        )

        period = finding.details.get("period", "")

        # Find all facts that participated in this finding
        for concept_id in finding.concepts:
            if not concept_id:
                continue
            for (ctx, cid, pk), fact_list in facts.items():
                if cid != concept_id:
                    continue
                if period and pk != period:
                    continue
                for f in fact_list:
                    key = (f.table_id, f.concept_id, f.col_idx)
                    if key in registry:
                        # Avoid duplicate checks from same edge
                        existing = registry[key].checks
                        if not any(
                            c.edge_name == cr.edge_name and c.check_type == cr.check_type
                            for c in existing
                        ):
                            existing.append(cr)
