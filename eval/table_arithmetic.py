#!/usr/bin/env python3
"""
table_arithmetic.py — Pass 0: same-table structural validation.

For every row with childIds, checks that parsedValue(parent) =
SUM(parsedValue(children)) per VALUE column. No ontology needed —
pure structural validation of the parsed data.

When a passing check involves an indexed fact (matched by row_id),
both the parent and child facts receive a TABLE_ARITHMETIC CheckResult.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TableArithmeticResult:
    """Result of a same-table parent/child summation check."""
    table_id: str
    parent_row_id: str
    parent_row_type: str   # TOTAL_EXPLICIT or TOTAL_IMPLICIT
    child_row_ids: list[str]
    col_idx: int
    expected_sum: float    # SUM(child parsedValues)
    actual_total: float    # parent parsedValue
    passed: bool
    delta: float


def _get_value_col_indices(table: dict) -> list[int]:
    """Get sorted VALUE column indices."""
    return sorted(
        c["colIdx"]
        for c in table.get("columns", [])
        if c.get("role") == "VALUE"
    )


def _get_cell_value(row: dict, col_idx: int) -> Optional[float]:
    """Get parsedValue for a specific column in a row."""
    for cell in row.get("cells", []):
        if cell.get("colIdx") == col_idx and cell.get("parsedValue") is not None:
            return cell["parsedValue"]
    return None


def pass0_table_arithmetic(
    tables: list[dict],
    tolerance: float = 0.5,
) -> list[TableArithmeticResult]:
    """Validate parent/child summations within each table.

    For every row with childIds, checks each VALUE column:
      parent.parsedValue == SUM(child.parsedValue)

    Both TOTAL_EXPLICIT and TOTAL_IMPLICIT are checked. TOTAL_EXPLICIT
    validates source data; TOTAL_IMPLICIT validates parser computation
    but still confirms child values are internally consistent.
    """
    results = []

    for table in tables:
        table_id = table["tableId"]
        rows_by_id = {r["rowId"]: r for r in table.get("rows", [])}
        value_cols = _get_value_col_indices(table)

        for row in table.get("rows", []):
            child_ids = row.get("childIds", [])
            if not child_ids:
                continue

            row_type = row.get("rowType", "DATA")
            children = [rows_by_id[cid] for cid in child_ids if cid in rows_by_id]
            if not children:
                continue

            for col_idx in value_cols:
                total_val = _get_cell_value(row, col_idx)
                if total_val is None:
                    continue

                child_vals = []
                for child in children:
                    cv = _get_cell_value(child, col_idx)
                    if cv is not None:
                        child_vals.append(cv)

                if not child_vals:
                    continue

                child_sum = sum(child_vals)
                delta = abs(total_val - child_sum)
                # Tolerance: absolute tolerance OR 0.1% of the total (for rounding in Mio tables)
                effective_tolerance = max(tolerance, abs(total_val) * 0.001) if total_val != 0 else tolerance
                passed = delta <= effective_tolerance

                results.append(TableArithmeticResult(
                    table_id=table_id,
                    parent_row_id=row["rowId"],
                    parent_row_type=row_type,
                    child_row_ids=child_ids,
                    col_idx=col_idx,
                    expected_sum=child_sum,
                    actual_total=total_val,
                    passed=passed,
                    delta=delta,
                ))

    return results


def apply_table_arithmetic_to_scores(
    results: list[TableArithmeticResult],
    registry: dict,
) -> int:
    """Link passing arithmetic checks to indexed facts via row_id.

    For each passing result, finds FactScores whose row_id matches
    the parent or any child row, and adds a TABLE_ARITHMETIC CheckResult.

    Returns the number of facts that received a check.
    """
    from fact_scoring import CheckResult

    # Build row_id → list of FactScore keys for fast lookup
    row_to_keys: dict[str, list[tuple]] = {}
    for key, fs in registry.items():
        if fs.row_id:
            row_to_keys.setdefault(fs.row_id, []).append(key)

    scored_count = 0

    for result in results:
        cr = CheckResult(
            check_type="TABLE_ARITHMETIC",
            edge_name=f"table_arith_{result.table_id}",
            passed=result.passed,
            delta=result.delta,
            detail=f"{'PASS' if result.passed else 'FAIL'}: parent {result.parent_row_id} ({result.parent_row_type}), {len(result.child_row_ids)} children, col {result.col_idx}",
        )

        # Apply to parent fact
        all_row_ids = [result.parent_row_id] + result.child_row_ids
        for row_id in all_row_ids:
            for key in row_to_keys.get(row_id, []):
                fs = registry[key]
                # Only add if same column and no duplicate
                if fs.col_idx == result.col_idx:
                    if not any(
                        c.check_type == "TABLE_ARITHMETIC" and c.edge_name == cr.edge_name
                        for c in fs.checks
                    ):
                        fs.checks.append(cr)
                        scored_count += 1

    return scored_count
