#!/usr/bin/env python3
"""
Build table_graphs.json for CA Immobilien Anlagen AG 2024 UGB financial statements.

Source: Financial Statements as at 31.12.2024 (English), pages 2-4
Framework: Austrian UGB (Gesamtkostenverfahren / nature of expense)
Currency: EUR (2024), €1,000 (2023 comparative)
Sign convention: PRESENTATION
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# ── SFP (Balance Sheet) — pages 2-3 ──────────────────────────────
# § 224 UGB structure. 2024 in EUR, 2023 in €1,000

SFP_ROWS = [
    # ASSETS (page 2)
    {"label": "Assets", "type": "SECTION"},
    {"label": "A. Fixed assets", "type": "SECTION"},
    {"label": "I. Intangible fixed assets", "type": "SECTION"},
    {"label": "Software", "type": "DATA", "y2024": 17189.58, "y2023": 111000, "concept": "FS.SFP.INTANGIBLE_ASSETS"},
    {"label": "II. Tangible fixed assets", "type": "SECTION"},
    {"label": "1. Land and buildings", "type": "DATA", "y2024": 141129629.96, "y2023": 174807000, "concept": "FS.SFP.PPE_NET"},
    {"label": "2. Other assets, office furniture and equipment", "type": "DATA", "y2024": 445547.84, "y2023": 537000},
    {"label": "3. Prepayments made and construction in progress", "type": "DATA", "y2024": 0.00, "y2023": 165000},
    {"label": "Tangible fixed assets subtotal", "type": "TOTAL_EXPLICIT", "y2024": 141575177.80, "y2023": 175509000, "children": [5, 6, 7]},
    {"label": "III. Financial assets", "type": "SECTION"},
    {"label": "1. Investments in affiliated companies", "type": "DATA", "y2024": 3111697706.21, "y2023": 3004939000, "concept": "FS.SFP.INVESTMENT_IN_SUB"},
    {"label": "2. Loans to affiliated companies", "type": "DATA", "y2024": 38576430.98, "y2023": 90152000, "concept": "FS.SFP.OTHER_INVESTMENTS"},
    {"label": "3. Investments in associated companies", "type": "DATA", "y2024": 245851.50, "y2023": 246000, "concept": "FS.SFP.EQUITY_ACCOUNTED_INVESTEES"},
    {"label": "Financial assets subtotal", "type": "TOTAL_EXPLICIT", "y2024": 3150519988.69, "y2023": 3095337000, "children": [10, 11, 12]},
    {"label": "Fixed assets total", "type": "TOTAL_EXPLICIT", "y2024": 3292112356.07, "y2023": 3270957000, "concept": "FS.SFP.NON_CURRENT_ASSETS", "children": [3, 8, 13]},
    {"label": "B. Current assets", "type": "SECTION"},
    {"label": "I. Receivables", "type": "SECTION"},
    {"label": "1. Trade receivables", "type": "DATA", "y2024": 698174.95, "y2023": 929000, "concept": "FS.SFP.TRADE_RECEIVABLES"},
    {"label": "2. Receivables from affiliated companies", "type": "DATA", "y2024": 4189463.76, "y2023": 88653000, "concept": "FS.SFP.RELATED_PARTY_RECEIVABLES"},
    {"label": "3. Other receivables", "type": "DATA", "y2024": 2856967.47, "y2023": 884000, "concept": "FS.SFP.OTHER_NON_FINANCIAL_ASSETS"},
    {"label": "Receivables subtotal", "type": "TOTAL_EXPLICIT", "y2024": 7744606.18, "y2023": 90466000, "children": [17, 18, 19]},
    {"label": "II. Cash and cash equivalents", "type": "DATA", "y2024": 305015669.75, "y2023": 215027000, "concept": "FS.SFP.CASH"},
    {"label": "Current assets total", "type": "TOTAL_EXPLICIT", "y2024": 312760275.93, "y2023": 305493000, "concept": "FS.SFP.CURRENT_ASSETS", "children": [20, 21]},
    {"label": "C. Deferred charges", "type": "DATA", "y2024": 4840397.38, "y2023": 5025000, "concept": "FS.SFP.PREPAYMENTS"},
    {"label": "D. Deferred tax asset", "type": "DATA", "y2024": 901025.81, "y2023": 789000, "concept": "FS.SFP.DEFERRED_TAX_ASSETS"},
    {"label": "Total assets", "type": "TOTAL_EXPLICIT", "y2024": 3610614055.19, "y2023": 3582264000, "concept": "FS.SFP.TOTAL_ASSETS", "children": [14, 22, 23, 24]},

    # LIABILITIES AND EQUITY (page 3)
    {"label": "Liabilities and shareholders' equity", "type": "SECTION"},
    {"label": "A. Shareholders' equity", "type": "SECTION"},
    {"label": "I. Share capital", "type": "SECTION"},
    {"label": "Share capital drawn", "type": "DATA", "y2024": 774229017.02, "y2023": 774229000, "concept": "FS.SFP.SHARE_CAPITAL"},
    {"label": "Treasury shares", "type": "DATA", "y2024": -67914035.41, "y2023": -63831000, "concept": "FS.SFP.TREASURY_SHARES"},
    {"label": "Share capital subtotal", "type": "TOTAL_EXPLICIT", "y2024": 706314981.61, "y2023": 710398000, "children": [29, 30]},
    {"label": "II. Tied capital reserves", "type": "DATA", "y2024": 998958619.09, "y2023": 998959000, "concept": "FS.SFP.SHARE_PREMIUM"},
    {"label": "III. Tied reserves for treasury shares", "type": "DATA", "y2024": 67914035.41, "y2023": 63831000, "concept": "FS.SFP.RESERVES"},
    {"label": "IV. Net profit", "type": "DATA", "y2024": 454845258.79, "y2023": 460572000, "concept": "FS.SFP.RETAINED_EARNINGS"},
    {"label": "Shareholders' equity total", "type": "TOTAL_EXPLICIT", "y2024": 2228032894.90, "y2023": 2233760000, "concept": "FS.SFP.TOTAL_EQUITY", "children": [31, 32, 33, 34]},
    {"label": "B. Grants from public funds", "type": "DATA", "y2024": 231979.53, "y2023": 334000, "concept": "FS.SFP.DEFERRED_INCOME"},
    {"label": "C. Provisions", "type": "SECTION"},
    {"label": "1. Provision for severance payment", "type": "DATA", "y2024": 629595.00, "y2023": 527000, "concept": "FS.SFP.EMPLOYEE_BENEFITS_LIABILITY"},
    {"label": "2. Tax provisions", "type": "DATA", "y2024": 1215000.00, "y2023": 860000, "concept": "FS.SFP.CURRENT_TAX_LIABILITIES"},
    {"label": "3. Other provisions", "type": "DATA", "y2024": 12348060.23, "y2023": 11811000, "concept": "FS.SFP.PROVISIONS"},
    {"label": "Provisions total", "type": "TOTAL_EXPLICIT", "y2024": 14192655.23, "y2023": 13198000, "children": [38, 39, 40]},
    {"label": "D. Liabilities", "type": "SECTION"},
    {"label": "1. Bonds", "type": "DATA", "y2024": 1275900000.00, "y2023": 1175000000, "concept": "FS.SFP.LOANS_BORROWINGS"},
    {"label": "2. Liabilities to banks", "type": "DATA", "y2024": 71215668.69, "y2023": 135897000},
    {"label": "3. Trade payables", "type": "DATA", "y2024": 350837.17, "y2023": 746000, "concept": "FS.SFP.TRADE_PAYABLES"},
    {"label": "4. Payables to affiliated companies", "type": "DATA", "y2024": 520201.92, "y2023": 3068000, "concept": "FS.SFP.RELATED_PARTY_PAYABLES"},
    {"label": "5. Other liabilities", "type": "DATA", "y2024": 17061279.33, "y2023": 16483000, "concept": "FS.SFP.OTHER_LIABILITIES"},
    {"label": "Liabilities total", "type": "TOTAL_EXPLICIT", "y2024": 1365047987.11, "y2023": 1331194000, "children": [43, 44, 45, 46, 47]},
    {"label": "E. Deferred income", "type": "DATA", "y2024": 3108538.42, "y2023": 3778000, "concept": "FS.SFP.DEFERRED_INCOME"},
    {"label": "Total equity and liabilities", "type": "TOTAL_EXPLICIT", "y2024": 3610614055.19, "y2023": 3582264000, "concept": "FS.SFP.TOTAL_EQUITY_AND_LIABILITIES", "children": [35, 36, 41, 48, 49]},
]

# ── PNL (Income Statement) — page 4 ──────────────────────────────
# § 231 UGB Gesamtkostenverfahren (nature of expense format)
# 2024 in EUR, 2023 in €1,000. Expenses shown as negative.

PNL_ROWS = [
    {"label": "1. Gross revenues", "type": "DATA", "y2024": 26885476.84, "y2023": 29466000, "concept": "FS.PNL.REVENUE"},
    {"label": "2. Other operating income", "type": "SECTION"},
    {"label": "a) Income from the disposal and write-ups of fixed assets", "type": "DATA", "y2024": 23023706.21, "y2023": 368000},
    {"label": "b) Income from the reversal of provisions", "type": "DATA", "y2024": 1058660.07, "y2023": 198000},
    {"label": "c) Other income", "type": "DATA", "y2024": 2325040.54, "y2023": 1196000},
    {"label": "Other operating income total", "type": "TOTAL_EXPLICIT", "y2024": 26407406.82, "y2023": 1762000, "concept": "FS.PNL.OTHER_INCOME", "children": [2, 3, 4]},
    {"label": "3. Staff expense", "type": "SECTION"},
    {"label": "a) Salaries", "type": "DATA", "y2024": -12123958.68, "y2023": -13044000},
    {"label": "b) Social expenses", "type": "DATA", "y2024": -2605204.85, "y2023": -4259000},
    {"label": "Staff expense total", "type": "TOTAL_EXPLICIT", "y2024": -14729163.53, "y2023": -17303000, "concept": "FS.PNL.STAFF_COSTS", "children": [7, 8]},
    {"label": "4. Depreciation on intangible fixed assets and tangible fixed assets", "type": "DATA", "y2024": -6483380.57, "y2023": -6674000, "concept": "FS.PNL.DEPRECIATION_AMORTISATION"},
    {"label": "5. Other operating expenses", "type": "SECTION"},
    {"label": "a) Taxes", "type": "DATA", "y2024": -502205.64, "y2023": -464000},
    {"label": "b) Other expenses", "type": "DATA", "y2024": -19060610.02, "y2023": -18083000},
    {"label": "Other operating expenses total", "type": "TOTAL_EXPLICIT", "y2024": -19562815.66, "y2023": -18547000, "concept": "FS.PNL.OTHER_EXPENSES", "children": [12, 13]},
    {"label": "6. Subtotal from lines 1 to 5 (operating result)", "type": "TOTAL_EXPLICIT", "y2024": 12517523.90, "y2023": -11296000, "concept": "FS.PNL.OPERATING_PROFIT", "children": [0, 5, 9, 10, 14]},
    {"label": "7. Income from investments", "type": "DATA", "y2024": 103460642.17, "y2023": 623249000, "concept": "FS.PNL.DIVIDEND_INCOME"},
    {"label": "8. Income from loans from financial assets", "type": "DATA", "y2024": 2551445.23, "y2023": 5773000, "concept": "FS.PNL.FINANCE_INCOME"},
    {"label": "9. Income from repurchase of bonds", "type": "DATA", "y2024": 2071835.91, "y2023": 0},
    {"label": "10. Other interest and similar income", "type": "DATA", "y2024": 4419592.56, "y2023": 4257000},
    {"label": "11. Income from the disposal and revaluation of financial assets", "type": "DATA", "y2024": 14430251.65, "y2023": 1133000},
    {"label": "12. Expenses for financial assets, thereof", "type": "DATA", "y2024": -33327593.22, "y2023": -186987000, "concept": "FS.PNL.IMPAIRMENT_FINANCIAL_ASSETS"},
    {"label": "13. Interest and similar expenses", "type": "DATA", "y2024": -22109944.87, "y2023": -26351000, "concept": "FS.PNL.FINANCE_COSTS"},
    {"label": "14. Subtotal from lines 7 to 13 (financial result)", "type": "TOTAL_EXPLICIT", "y2024": 71496229.43, "y2023": 421074000, "concept": "FS.PNL.NET_FINANCE_COSTS", "children": [16, 17, 18, 19, 20, 21, 22]},
    {"label": "15. Result before taxes", "type": "TOTAL_EXPLICIT", "y2024": 84013753.33, "y2023": 409778000, "concept": "FS.PNL.PROFIT_BEFORE_TAX", "children": [15, 23]},
    {"label": "16. Taxes on income", "type": "DATA", "y2024": 1642674.47, "y2023": 11199000, "concept": "FS.PNL.INCOME_TAX_EXPENSE"},
    {"label": "17. Net profit for the year", "type": "TOTAL_EXPLICIT", "y2024": 85656427.80, "y2023": 420977000, "concept": "FS.PNL.NET_PROFIT", "children": [24, 25]},
    {"label": "18. Allocation to reserve from retained earnings", "type": "DATA", "y2024": -13210531.28, "y2023": -50963000},
    {"label": "19. Profit carried forward from the previous year", "type": "DATA", "y2024": 382399362.27, "y2023": 90558000},
    {"label": "20. Net profit", "type": "TOTAL_EXPLICIT", "y2024": 454845258.79, "y2023": 460572000, "children": [26, 27, 28]},
]


def build_table(table_id, sc, rows_data, page):
    """Convert row data to table_graphs.json format."""
    columns = [
        {"colIdx": 0, "role": "LABEL", "headerLabel": "", "detectedAxes": {}},
        {"colIdx": 1, "role": "VALUE", "headerLabel": "31.12.2024",
         "detectedAxes": {"AXIS.PERIOD": "PERIOD.Y2024", "AXIS.VALUE_TYPE": "VALTYPE.TERMINAL"}},
        {"colIdx": 2, "role": "VALUE", "headerLabel": "31.12.2023",
         "detectedAxes": {"AXIS.PERIOD": "PERIOD.Y2023", "AXIS.VALUE_TYPE": "VALTYPE.TERMINAL"}},
    ]

    rows = []
    for i, rd in enumerate(rows_data):
        row_id = f"row:{table_id}:{i}"
        row_type = rd.get("type", "DATA")

        cells = [{"colIdx": 0, "text": rd["label"], "parsedValue": None, "isNegative": False}]
        for col_idx, year_key in [(1, "y2024"), (2, "y2023")]:
            val = rd.get(year_key)
            cells.append({
                "colIdx": col_idx,
                "text": f"{val:,.2f}" if val is not None else "",
                "parsedValue": val,
                "isNegative": val is not None and val < 0,
            })

        child_ids = [f"row:{table_id}:{ci}" for ci in rd.get("children", [])]
        pre_tagged = {"conceptId": rd["concept"]} if rd.get("concept") else None

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
            {"id": "manual_extract", "label": "Manually extracted from PDF",
             "params": {"source": "CA Immobilien Anlagen AG Financial Statements 31.12.2024 (EN)"}},
        ],
        "rawHeaders": [],
        "filledHeaders": [],
    }


def main():
    os.makedirs("eval/fixtures/ca_immo_2024", exist_ok=True)
    sfp = build_table("sfp_ca_immo", "SFP", SFP_ROWS, 2)
    pnl = build_table("pnl_ca_immo", "PNL", PNL_ROWS, 4)

    output = {"tables": [sfp, pnl]}
    out_path = "eval/fixtures/ca_immo_2024/table_graphs.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    for t in output["tables"]:
        sc = t["metadata"]["statementComponent"]
        data_rows = sum(1 for r in t["rows"] if r["rowType"] == "DATA")
        total_rows = sum(1 for r in t["rows"] if r["rowType"] == "TOTAL_EXPLICIT")
        print(f"{sc}: {data_rows} data, {total_rows} totals")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
