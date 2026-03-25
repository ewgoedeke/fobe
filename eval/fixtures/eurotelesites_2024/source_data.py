#!/usr/bin/env python3
"""
Build table_graphs.json for EuroTeleSites AG 2024 UGB financial statements.

Source: Annual Financial Report 2024, pages 105-106
Framework: Austrian UGB (Gesamtkostenverfahren / total cost format)
Currency: EUR (2024), tEUR (2023 comparative)
Sign convention: PRESENTATION (positive = normal direction)
"""

import json

# ── SFP (Statement of Financial Position) — page 105 ──────────────
# § 224 UGB structure, amounts in EUR for 2024, tEUR for 2023

SFP_ROWS = [
    # Assets
    {"label": "Assets", "type": "SECTION"},
    {"label": "A. Long-term assets", "type": "SECTION"},
    {"label": "I. Financial assets", "type": "SECTION"},
    {"label": "1. Investments in affiliated companies", "type": "DATA", "y2024": 820488724, "y2023": 820489000, "concept": "FS.SFP.INVESTMENT_IN_SUB"},
    {"label": "B. Current assets", "type": "SECTION"},
    {"label": "I. Receivables", "type": "SECTION"},
    {"label": "1. Receivables - affiliated companies", "type": "DATA", "y2024": 12848669, "y2023": 1348000, "concept": "FS.SFP.RELATED_PARTY_RECEIVABLES"},
    {"label": "2. Other accounts receivable", "type": "DATA", "y2024": 0, "y2023": 6000, "concept": "FS.SFP.OTHER_NON_FINANCIAL_ASSETS"},
    {"label": "Receivables subtotal", "type": "TOTAL_EXPLICIT", "y2024": 12848669, "y2023": 1354000, "children": [5, 6]},
    {"label": "C. Prepaid expenses", "type": "DATA", "y2024": 95416, "y2023": 87000, "concept": "FS.SFP.PREPAYMENTS"},
    {"label": "Total assets", "type": "TOTAL_EXPLICIT", "y2024": 833432809, "y2023": 821930000, "concept": "FS.SFP.TOTAL_ASSETS", "children": [3, 8, 9]},
    # Liabilities and Stockholders' Equity
    {"label": "Liabilities and Stockholders' Equity", "type": "SECTION"},
    {"label": "A. Common stock issued", "type": "SECTION"},
    {"label": "I. Common stock", "type": "DATA", "y2024": 166125000, "y2023": 166125000, "concept": "FS.SFP.SHARE_CAPITAL"},
    {"label": "II. Additional paid-in capital", "type": "SECTION"},
    {"label": "1. Appropriated", "type": "DATA", "y2024": 650472857, "y2023": 652071000, "concept": "FS.SFP.SHARE_PREMIUM"},
    {"label": "Common stock subtotal", "type": "TOTAL_EXPLICIT", "y2024": 816597857, "y2023": 818196000, "children": [13, 15]},
    {"label": "B. Provisions", "type": "SECTION"},
    {"label": "1. Provisions for taxes", "type": "DATA", "y2024": 2311122, "y2023": 0, "concept": "FS.SFP.CURRENT_TAX_LIABILITIES"},
    {"label": "2. Other provisions", "type": "DATA", "y2024": 612968, "y2023": 320000, "concept": "FS.SFP.PROVISIONS"},
    {"label": "Provisions subtotal", "type": "TOTAL_EXPLICIT", "y2024": 2924090, "y2023": 320000, "children": [18, 19]},
    {"label": "C. Liabilities", "type": "SECTION"},
    {"label": "1. Accounts payable trade", "type": "DATA", "y2024": 31434, "y2023": 80000, "concept": "FS.SFP.TRADE_PAYABLES"},
    {"label": "2. Liabilities due to affiliated companies", "type": "DATA", "y2024": 9298925, "y2023": 3328000, "concept": "FS.SFP.RELATED_PARTY_PAYABLES"},
    {"label": "3. Other liabilities", "type": "DATA", "y2024": 4580503, "y2023": 5000, "concept": "FS.SFP.OTHER_LIABILITIES"},
    {"label": "Liabilities subtotal", "type": "TOTAL_EXPLICIT", "y2024": 13910862, "y2023": 3413000, "children": [22, 23, 24]},
    {"label": "Total equity and liabilities", "type": "TOTAL_EXPLICIT", "y2024": 833432809, "y2023": 821930000, "concept": "FS.SFP.TOTAL_EQUITY_AND_LIABILITIES", "children": [16, 20, 25]},
]

# ── PNL (Statement of Profit or Loss) — page 106 ──────────────────
# § 231 UGB Gesamtkostenverfahren (total cost format)

PNL_ROWS = [
    {"label": "1. Revenues", "type": "DATA", "y2024": 3995099, "y2023": 1348000, "concept": "FS.PNL.REVENUE"},
    {"label": "2. Miscellaneous other operation income", "type": "SECTION"},
    {"label": "a) Income from reversal of reserves", "type": "DATA", "y2024": 103142, "y2023": 0, "concept": "FS.PNL.OTHER_INCOME"},
    {"label": "3. Subtotal from line 1 to 2", "type": "TOTAL_EXPLICIT", "y2024": 4098241, "y2023": 1348000, "children": [0, 2]},
    {"label": "4. Expenses for material and other purchased manufacturing services:", "type": "SECTION"},
    {"label": "a) Purchased services", "type": "DATA", "y2024": -985091, "y2023": -1505000, "concept": "FS.PNL.PURCHASED_SERVICES"},
    {"label": "5. Personnel expenses", "type": "SECTION"},
    {"label": "a) Salaries", "type": "DATA", "y2024": -1072293, "y2023": -337000, "concept": "FS.PNL.STAFF_COSTS"},
    {"label": "b) Social security contributions", "type": "SECTION"},
    {"label": "thereof pension expense", "type": "DATA", "y2024": -13211, "y2023": -2000},
    {"label": "aa) Expenses for statutory social security", "type": "DATA", "y2024": -211833, "y2023": -79000},
    {"label": "Personnel expenses subtotal", "type": "TOTAL_EXPLICIT", "y2024": -1297337, "y2023": -418000, "children": [7, 9, 10]},
    {"label": "6. Other operating expenses", "type": "DATA", "y2024": -4459517, "y2023": -1716000, "concept": "FS.PNL.OTHER_EXPENSES"},
    {"label": "7. Subtotal from line 3 to 6 (operating result)", "type": "TOTAL_EXPLICIT", "y2024": -2643704, "y2023": -2290000, "concept": "FS.PNL.OPERATING_PROFIT", "children": [3, 5, 11, 12]},
    {"label": "8. Interest and similar income", "type": "DATA", "y2024": 512, "y2023": 0, "concept": "FS.PNL.FINANCE_INCOME"},
    {"label": "9. Interest and similar expenses", "type": "DATA", "y2024": -90253, "y2023": -2000, "concept": "FS.PNL.FINANCE_COSTS"},
    {"label": "10. Subtotal from line 8-9 (financial result)", "type": "TOTAL_EXPLICIT", "y2024": -89741, "y2023": -2000, "concept": "FS.PNL.NET_FINANCE_COSTS", "children": [14, 15]},
    {"label": "11. Earnings before Taxes", "type": "TOTAL_EXPLICIT", "y2024": -2733445, "y2023": -2292000, "concept": "FS.PNL.PROFIT_BEFORE_TAX", "children": [13, 16]},
    {"label": "12. Taxes on income and earnings", "type": "DATA", "y2024": 1135035, "y2023": 0, "concept": "FS.PNL.INCOME_TAX_EXPENSE"},
    {"label": "13. Earnings after income taxes", "type": "TOTAL_EXPLICIT", "y2024": -1598410, "y2023": -2292000, "concept": "FS.PNL.NET_PROFIT", "children": [17, 18]},
    {"label": "14. Release from appropriated additional paid-in capital", "type": "DATA", "y2024": 1598410, "y2023": 2292000},
    {"label": "15. Retained Earnings", "type": "TOTAL_EXPLICIT", "y2024": 0, "y2023": 0, "children": [19, 20]},
]


def build_table(table_id, sc, rows_data, page):
    """Convert row data to table_graphs.json format."""
    columns = [
        {"colIdx": 0, "role": "LABEL", "headerLabel": "", "detectedAxes": {}},
        {"colIdx": 1, "role": "VALUE", "headerLabel": "31 December 2024",
         "detectedAxes": {"AXIS.PERIOD": "PERIOD.Y2024", "AXIS.VALUE_TYPE": "VALTYPE.TERMINAL"}},
        {"colIdx": 2, "role": "VALUE", "headerLabel": "31 December 2023",
         "detectedAxes": {"AXIS.PERIOD": "PERIOD.Y2023", "AXIS.VALUE_TYPE": "VALTYPE.TERMINAL"}},
    ]

    rows = []
    for i, rd in enumerate(rows_data):
        row_id = f"row:{table_id}:{i}"
        row_type = rd.get("type", "DATA")

        cells = [
            {"colIdx": 0, "text": rd["label"], "parsedValue": None, "isNegative": False},
        ]

        for col_idx, year_key in [(1, "y2024"), (2, "y2023")]:
            val = rd.get(year_key)
            cells.append({
                "colIdx": col_idx,
                "text": f"{val:,}" if val is not None else "",
                "parsedValue": val,
                "isNegative": val is not None and val < 0,
            })

        # Build childIds from "children" indices
        child_ids = [f"row:{table_id}:{ci}" for ci in rd.get("children", [])]

        pre_tagged = None
        if rd.get("concept"):
            pre_tagged = {"conceptId": rd["concept"]}

        rows.append({
            "rowId": row_id,
            "rowIdx": i,
            "label": rd["label"],
            "rowType": row_type,
            "indentLevel": 0,
            "depth": 0,
            "parentId": None,
            "childIds": child_ids,
            "cells": cells,
            "preTagged": pre_tagged,
        })

    # Set parentId on children
    for row in rows:
        for child_id in row.get("childIds", []):
            for r in rows:
                if r["rowId"] == child_id:
                    r["parentId"] = row["rowId"]

    return {
        "tableId": table_id,
        "pageNo": page,
        "headerRowCount": 0,
        "labelColIdx": 0,
        "metadata": {
            "statementComponent": sc,
            "detectedCurrency": "CURRENCY.EUR",
            "detectedUnit": "UNIT.UNITS",
            "signConvention": "PRESENTATION",
            "sectionPath": [],
            "scope": None,
        },
        "columns": columns,
        "rows": rows,
        "aggregationGroups": [],
        "pipelineSteps": [
            {"id": "manual_extract", "label": "Manually extracted from PDF", "params": {"source": "EuroTeleSites AG Annual Financial Report 2024"}},
        ],
        "rawHeaders": [],
        "filledHeaders": [],
    }


def main():
    sfp = build_table("sfp_eurotelesites", "SFP", SFP_ROWS, 105)
    pnl = build_table("pnl_eurotelesites", "PNL", PNL_ROWS, 106)

    output = {"tables": [sfp, pnl]}

    out_path = "eval/fixtures/eurotelesites_2024/table_graphs.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    for t in output["tables"]:
        sc = t["metadata"]["statementComponent"]
        data_rows = sum(1 for r in t["rows"] if r["rowType"] == "DATA")
        total_rows = sum(1 for r in t["rows"] if r["rowType"] == "TOTAL_EXPLICIT")
        with_children = sum(1 for r in t["rows"] if r.get("childIds"))
        print(f"{sc}: {data_rows} data rows, {total_rows} totals, {with_children} with children")

    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
