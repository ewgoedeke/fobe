#!/usr/bin/env python3
"""
convert_saldenliste.py — Austrian Saldenliste (trial balance) → UGB financial statements.

Reads an EKR-format CSV trial balance and produces:
  1. UGB Bilanz (SFP) per § 224 UGB
  2. UGB GuV Gesamtkostenverfahren (PNL) per § 231 UGB

in table_graphs.json format for the consistency engine.

The EKR account mapping from accounts/ekr_austria.yaml drives the conversion.
Sign convention: NATURAL_DRCR (debit positive, credit negative — native trial balance).

Usage:
    python3 eval/convert_saldenliste.py <saldenliste.csv> [output.json]
"""

import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import yaml


def load_ekr_mapping(ontology_root: str) -> dict[str, dict]:
    """Load EKR account → concept mapping.

    Returns: {account_prefix → {concept, de, en, ref, ...}}
    """
    ekr_path = Path(ontology_root) / "accounts" / "ekr_austria.yaml"
    data = yaml.safe_load(open(ekr_path))

    mapping = {}
    for class_key in [f"class_{i}" for i in range(10)]:
        for acct in data.get(class_key, []):
            mapping[acct["acct"]] = acct
    return mapping


def parse_saldenliste(csv_path: str) -> list[dict]:
    """Parse Austrian Saldenliste CSV (semicolon-delimited, EU number format)."""
    rows = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            acct = row.get("Konto", "").strip()
            label = row.get("Bezeichnung", "").strip()
            saldo_str = row.get("Saldo", "0").strip()
            # Parse EU number format: 1.234.567,89
            saldo = float(
                saldo_str.replace(".", "").replace(",", ".")
            )
            rows.append({
                "acct": acct,
                "label": label,
                "saldo": saldo,  # Dr+/Cr- (positive=debit, negative=credit)
            })
    return rows


def _find_mapping(acct: str, ekr: dict[str, dict]) -> dict | None:
    """Find EKR mapping for an account number (exact or prefix match)."""
    # Exact match first
    if acct in ekr:
        return ekr[acct]
    # Try shorter prefixes (0450 → 0400 → 0000)
    for length in (3, 2, 1):
        prefix = acct[:length] + "0" * (4 - length)
        if prefix in ekr:
            return ekr[prefix]
    return None


def build_ugb_statements(
    tb_rows: list[dict],
    ekr: dict[str, dict],
) -> tuple[list[dict], list[dict]]:
    """Aggregate trial balance into UGB SFP (§ 224) and PNL (§ 231) line items.

    Returns (sfp_lines, pnl_lines) where each line is:
      {concept, label_de, ref, amount, children: [{acct, label, amount}]}
    """
    # Aggregate by concept
    by_concept: dict[str, dict] = {}

    for row in tb_rows:
        mapping = _find_mapping(row["acct"], ekr)
        if not mapping:
            continue

        concept = mapping["concept"]
        if concept not in by_concept:
            by_concept[concept] = {
                "concept": concept,
                "label_de": mapping.get("de", ""),
                "label_en": mapping.get("en", ""),
                "ref": mapping.get("ref", ""),
                "amount": 0.0,
                "children": [],
            }
        by_concept[concept]["amount"] += row["saldo"]
        by_concept[concept]["children"].append({
            "acct": row["acct"],
            "label": row["label"],
            "amount": row["saldo"],
        })

    # Split into SFP (class 0-2 assets, 3 liabilities, 9 equity) and PNL (4-8)
    sfp_lines = []
    pnl_lines = []

    for concept, data in sorted(by_concept.items()):
        if concept.startswith("FS.SFP.") or concept.startswith("FS.SFP.UGB."):
            sfp_lines.append(data)
        elif concept.startswith("FS.PNL.") or concept.startswith("FS.PNL.UGB."):
            pnl_lines.append(data)

    return sfp_lines, pnl_lines


def _build_table(
    table_id: str,
    statement_component: str,
    lines: list[dict],
    period_label: str = "2024",
) -> dict:
    """Build a table_graphs.json table from aggregated line items."""
    columns = [
        {"colIdx": 0, "role": "LABEL", "headerLabel": "", "detectedAxes": {}},
        {
            "colIdx": 1,
            "role": "VALUE",
            "headerLabel": period_label,
            "detectedAxes": {
                "AXIS.PERIOD": f"PERIOD.Y{period_label}",
                "AXIS.VALUE_TYPE": "VALTYPE.TERMINAL",
            },
        },
    ]

    rows = []
    child_row_ids = []

    for i, line in enumerate(lines):
        row_id = f"row:{table_id}:{i}"
        label = line.get("label_de") or line.get("label_en") or line["concept"]
        ref = line.get("ref", "")
        if ref:
            label = f"{label} ({ref})"

        rows.append({
            "rowId": row_id,
            "rowIdx": i,
            "label": label,
            "rowType": "DATA",
            "indentLevel": 0,
            "depth": 0,
            "parentId": None,
            "childIds": [],
            "cells": [
                {"colIdx": 0, "text": label, "parsedValue": None, "isNegative": False},
                {"colIdx": 1, "text": f"{line['amount']:,.2f}", "parsedValue": line["amount"], "isNegative": line["amount"] < 0},
            ],
            "preTagged": {"conceptId": line["concept"]},
        })
        child_row_ids.append(row_id)

    # Add total row
    total_amount = sum(line["amount"] for line in lines)
    total_label = "Bilanzsumme" if statement_component == "SFP" else "Jahresüberschuss/-fehlbetrag"
    total_concept = "FS.SFP.TOTAL_ASSETS" if statement_component == "SFP" else "FS.PNL.NET_PROFIT"

    total_row_id = f"row:{table_id}:total"
    rows.append({
        "rowId": total_row_id,
        "rowIdx": len(lines),
        "label": total_label,
        "rowType": "TOTAL_EXPLICIT",
        "indentLevel": 0,
        "depth": 0,
        "parentId": None,
        "childIds": child_row_ids,
        "cells": [
            {"colIdx": 0, "text": total_label, "parsedValue": None, "isNegative": False},
            {"colIdx": 1, "text": f"{total_amount:,.2f}", "parsedValue": total_amount, "isNegative": total_amount < 0},
        ],
        "preTagged": {"conceptId": total_concept},
    })

    return {
        "tableId": table_id,
        "pageNo": 1 if statement_component == "SFP" else 2,
        "headerRowCount": 0,
        "labelColIdx": 0,
        "metadata": {
            "statementComponent": statement_component,
            "detectedCurrency": "CURRENCY.EUR",
            "detectedUnit": "UNIT.UNITS",
            "signConvention": "NATURAL_DRCR",
            "sectionPath": [],
            "scope": None,
        },
        "columns": columns,
        "rows": rows,
        "aggregationGroups": [],
        "pipelineSteps": [
            {"id": "saldenliste_convert", "label": "Converted from Austrian Saldenliste", "params": {}},
        ],
        "rawHeaders": [],
        "filledHeaders": [],
    }


def convert_saldenliste(csv_path: str, ontology_root: str) -> dict:
    """Convert Saldenliste to table_graphs.json with UGB SFP + PNL."""
    ekr = load_ekr_mapping(ontology_root)
    tb_rows = parse_saldenliste(csv_path)

    sfp_lines, pnl_lines = build_ugb_statements(tb_rows, ekr)

    # Split SFP into Aktiva (debit balances) and Passiva (credit balances)
    # In UGB, Aktiva = debit (positive), Passiva = credit (negative)
    sfp_table = _build_table("sfp_ugb", "SFP", sfp_lines)
    pnl_table = _build_table("pnl_ugb", "PNL", pnl_lines)

    return {"tables": [sfp_table, pnl_table]}


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <saldenliste.csv> [output.json]")
        sys.exit(1)

    csv_path = sys.argv[1]
    ontology_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    result = convert_saldenliste(csv_path, ontology_root)

    out_path = sys.argv[2] if len(sys.argv) > 2 else csv_path.replace(".csv", "_table_graphs.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    tables = result["tables"]
    for t in tables:
        sc = t["metadata"]["statementComponent"]
        rows = len(t["rows"])
        total = sum(c.get("parsedValue", 0) or 0 for r in t["rows"] for c in r["cells"] if c.get("colIdx") == 1 and r.get("rowType") == "DATA")
        print(f"{sc}: {rows} rows, total={total:,.2f}")

    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
