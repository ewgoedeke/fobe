#!/usr/bin/env python3
"""
pretag_all.py — Automated pre-tagging of financial statement rows using ontology label matching.

Reads table_graphs.json for a document, matches row labels against ontology concepts
using exact, normalized, and fuzzy matching, then writes back preTagged fields.

Usage:
    python3 eval/pretag_all.py <path_to_table_graphs.json> [--dry-run]
    python3 eval/pretag_all.py /tmp/doc_tag/006/Wienerberger_AG_Annual_Report_2024_tables_stitched/table_graphs.json
"""

import json
import os
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from reference_graph import parse_label, build_reference_graph, DocumentRefGraph

# ── Ontology loading ─────────────────────────────────────────────────────────

def parse_ontology_full(path):
    """Parse ontology.yaml extracting concepts with labels and aliases."""
    with open(path) as f:
        content = f.read()

    concepts = []
    current = None
    in_axes_used = False
    in_aliases = False
    in_concepts_section = False

    for line in content.split("\n"):
        # The 'concepts:' top-level key gates the concept section
        if line.strip() == "concepts:":
            in_concepts_section = True
            continue
        # Other top-level keys end the section
        if not line.startswith(" ") and not line.startswith("-") and line.strip().endswith(":") and line.strip() != "concepts:":
            if in_concepts_section and current:
                concepts.append(current)
                current = None
            # axes: or dimension_axes: etc are new sections
            if in_concepts_section and not line.strip().startswith("#"):
                in_concepts_section = False

        if not in_concepts_section:
            # Also grab DOC/NOTES section defs for their aliases
            m_doc = re.match(r"^- id:\s+((?:DOC|NOTES|FS\.(?:CONSOLIDATED|SEPARATE))\.\S+)", line)
            if m_doc:
                if current:
                    concepts.append(current)
                current = {
                    "id": m_doc.group(1),
                    "label": "",
                    "aliases": [],
                    "axes_used": [],
                    "family": m_doc.group(1).split(".")[0],
                    "statement": m_doc.group(1).split(".")[1] if "." in m_doc.group(1) else "",
                }
                in_axes_used = False
                in_aliases = False
            elif current:
                lm = re.match(r"^\s+label:\s*(.+)", line)
                if lm:
                    current["label"] = lm.group(1).strip().strip("'\"")
                if re.match(r"^\s+aliases:", line):
                    in_aliases = True
                    in_axes_used = False
                if in_aliases:
                    ai = re.match(r"^\s+- ([^A][^\n]+)", line)
                    if ai and not ai.group(1).startswith("AXIS"):
                        current["aliases"].append(ai.group(1).strip().strip("'\""))
                if re.match(r"^- id:", line) and not m_doc:
                    if current:
                        concepts.append(current)
                    current = None
                    in_aliases = False
            continue

        m = re.match(r"^- id:\s+(\S+)", line)
        if m:
            if current:
                concepts.append(current)
            current = {
                "id": m.group(1),
                "label": "",
                "aliases": [],
                "axes_used": [],
                "family": m.group(1).split(".")[0],
                "statement": m.group(1).split(".")[1] if "." in m.group(1) else "",
            }
            in_axes_used = False
            in_aliases = False
            continue

        if current:
            lm = re.match(r"^\s+label:\s*(.+)", line)
            if lm:
                current["label"] = lm.group(1).strip().strip("'\"")
                in_axes_used = False
                in_aliases = False
                continue

            if re.match(r"^\s+axes_used:", line):
                in_axes_used = True
                in_aliases = False
                continue

            if re.match(r"^\s+aliases:", line):
                in_aliases = True
                in_axes_used = False
                continue

            if in_axes_used:
                ai = re.match(r"^\s+- (AXIS\.\S+)", line)
                if ai:
                    current["axes_used"].append(ai.group(1))
                    continue
                else:
                    in_axes_used = False

            if in_aliases:
                ai = re.match(r"^\s+- (.+)", line)
                if ai:
                    current["aliases"].append(ai.group(1).strip().strip("'\""))
                    continue
                else:
                    in_aliases = False

    if current:
        concepts.append(current)

    return concepts


def normalize(text):
    """Normalize a label for matching."""
    t = text.lower().strip()
    # Remove note references like "(1)", "(note 5)", "1)"
    t = re.sub(r"\(note\s*\d+\)", "", t)
    t = re.sub(r"\(\d+\)", "", t)
    t = re.sub(r"\d+\)\s*$", "", t)
    # Remove trailing superscripts/footnote markers
    t = re.sub(r"\s*[¹²³⁴⁵⁶⁷⁸⁹⁰]+\s*$", "", t)
    t = re.sub(r"\s*\*+\s*$", "", t)
    # Remove leading "a) ", "b) ", "c) " etc.
    t = re.sub(r"^[a-z]\)\s*", "", t)
    # Remove leading "category 3.1 " etc.
    t = re.sub(r"^category\s+\d+\.\d+\s+", "", t)
    # Normalize whitespace
    t = re.sub(r"\s+", " ", t).strip()
    # Remove trailing punctuation
    t = t.rstrip(":")
    return t


# ESG / sustainability patterns — rows matching these are skipped
ESG_PATTERNS = [
    re.compile(r"(ghg|greenhouse|co2|carbon|emission|scope\s*[123])", re.I),
    re.compile(r"(energy\s*consumption|fossil|renewable|nuclear|biomass)", re.I),
    re.compile(r"(water\s*(consumption|withdrawal|discharge|recycl|stored|intensity))", re.I),
    re.compile(r"(waste|hazardous|non-hazardous|landfill|incineration|recycl)", re.I),
    re.compile(r"(biodiversity|fauna|trees\s+planted|ambassadors)", re.I),
    re.compile(r"(microplastic|nmvoc|sulphur|fluorine|chlorine)", re.I),
    re.compile(r"(training\s+hours|performance\s+review|apprentice|inclusion|diversity)", re.I),
    re.compile(r"(visible\s+leadership|employee.*(age|gender|male|female))", re.I),
    re.compile(r"(permanent\s+employees|temporary\s+employees|non-guaranteed)", re.I),
    re.compile(r"^(male|female|not reported|< 30|30 - 50|> 50)\s*(years)?$", re.I),
    re.compile(r"(training\s+per\s+employee|performance.*career.*review)", re.I),
    re.compile(r"(water\s+harvested|reduction.*specific.*water)", re.I),
    re.compile(r"^(usa|france|germany|rest of the world)$", re.I),  # country breakdown in ESG context
    re.compile(r"(purchased\s+goods\s+and\s+services|fuel\s+and\s+energy.related|downstream\s+transport)", re.I),
]


def is_esg_label(label):
    """Check if a label is ESG/sustainability content that should be skipped."""
    for pattern in ESG_PATTERNS:
        if pattern.search(label):
            return True
    return False


# ── Extended label map ───────────────────────────────────────────────────────
# Manual mappings for common Wienerberger / IFRS labels not directly in ontology

EXTRA_LABEL_MAP = {
    # PNL items
    "revenues": "FS.PNL.REVENUE",
    "revenue": "FS.PNL.REVENUE",
    "net revenues": "FS.PNL.REVENUE",
    "cost of goods sold": "FS.PNL.COST_OF_SALES",
    "cost of sales": "FS.PNL.COST_OF_SALES",
    "gross profit": "FS.PNL.GROSS_PROFIT",
    "other operating income": "FS.PNL.OTHER_INCOME",
    "other income": "FS.PNL.OTHER_INCOME",
    "selling expenses": "FS.PNL.SELLING_DISTRIBUTION",
    "selling and distribution expenses": "FS.PNL.SELLING_DISTRIBUTION",
    "administrative expenses": "FS.PNL.ADMIN_EXPENSES",
    "general and administrative expenses": "FS.PNL.ADMIN_EXPENSES",
    "research and development expenses": "FS.PNL.RD_EXPENSES",
    "other expenses": "FS.PNL.OTHER_EXPENSES",
    "other operating expenses": "FS.PNL.OTHER_EXPENSES",
    "operating profit": "FS.PNL.OPERATING_PROFIT",
    "profit from operations": "FS.PNL.OPERATING_PROFIT",
    "ebit": "FS.PNL.OPERATING_PROFIT",
    "operating ebit": "FS.PNL.OPERATING_PROFIT",
    "finance income": "FS.PNL.FINANCE_INCOME",
    "interest income": "FS.PNL.FINANCE_INCOME",
    "financial income": "FS.PNL.FINANCE_INCOME",
    "finance costs": "FS.PNL.FINANCE_COSTS",
    "interest expense": "FS.PNL.FINANCE_COSTS",
    "financial expenses": "FS.PNL.FINANCE_COSTS",
    "interest expenses": "FS.PNL.FINANCE_COSTS",
    "net finance costs": "FS.PNL.NET_FINANCE_COSTS",
    "net financial result": "FS.PNL.NET_FINANCE_COSTS",
    "financial result": "FS.PNL.NET_FINANCE_COSTS",
    "interest result": "FS.PNL.NET_FINANCE_COSTS",
    "share of profit of equity-accounted investees": "FS.PNL.SHARE_OF_PROFIT_ASSOCIATES",
    "share of profit of associates": "FS.PNL.SHARE_OF_PROFIT_ASSOCIATES",
    "income from investments in associates and joint ventures": "FS.PNL.SHARE_OF_PROFIT_ASSOCIATES",
    "profit before income tax": "FS.PNL.PROFIT_BEFORE_TAX",
    "profit before tax": "FS.PNL.PROFIT_BEFORE_TAX",
    "earnings before tax": "FS.PNL.PROFIT_BEFORE_TAX",
    "result before tax": "FS.PNL.PROFIT_BEFORE_TAX",
    "income tax expense": "FS.PNL.INCOME_TAX_EXPENSE",
    "income taxes": "FS.PNL.INCOME_TAX_EXPENSE",
    "tax expense": "FS.PNL.INCOME_TAX_EXPENSE",
    "profit for the period": "FS.PNL.PROFIT_FOR_PERIOD",
    "profit for the year": "FS.PNL.PROFIT_FOR_PERIOD",
    "net profit": "FS.PNL.PROFIT_FOR_PERIOD",
    "net income": "FS.PNL.PROFIT_FOR_PERIOD",
    "result for the period": "FS.PNL.PROFIT_FOR_PERIOD",
    "profit from continuing operations": "FS.PNL.PROFIT_CONTINUING",
    "result from continuing operations": "FS.PNL.PROFIT_CONTINUING",
    "profit from discontinued operations": "FS.PNL.PROFIT_DISCONTINUED",
    "result from discontinued operations": "FS.PNL.PROFIT_DISCONTINUED",
    "profit attributable to owners of the company": "FS.PNL.PROFIT_ATTR_OWNERS",
    "attributable to equity holders of the parent": "FS.PNL.PROFIT_ATTR_OWNERS",
    "attributable to equity holders": "FS.PNL.PROFIT_ATTR_OWNERS",
    "thereof equity holders of the parent": "FS.PNL.PROFIT_ATTR_OWNERS",
    "thereof shareholders of the parent company": "FS.PNL.PROFIT_ATTR_OWNERS",
    "of which attributable to equity holders of wienerberger ag": "FS.PNL.PROFIT_ATTR_OWNERS",
    "equity holders of wienerberger ag": "FS.PNL.PROFIT_ATTR_OWNERS",
    "profit attributable to non-controlling interests": "FS.PNL.PROFIT_ATTR_NCI",
    "attributable to non-controlling interests": "FS.PNL.PROFIT_ATTR_NCI",
    "thereof non-controlling interests": "FS.PNL.PROFIT_ATTR_NCI",
    "non-controlling interests": "FS.PNL.PROFIT_ATTR_NCI",
    "of which non-controlling interests": "FS.PNL.PROFIT_ATTR_NCI",
    "staff costs": "FS.PNL.STAFF_COSTS",
    "personnel expenses": "FS.PNL.STAFF_COSTS",
    "employee benefits expense": "FS.PNL.STAFF_COSTS",
    "depreciation and amortisation": "FS.PNL.DEPRECIATION_AMORTISATION",
    "depreciation and amortization": "FS.PNL.DEPRECIATION_AMORTISATION",
    "depreciation, amortization and impairment": "FS.PNL.DEPRECIATION_AMORTISATION",
    "depreciation, amortization, impairments and special write-offs": "FS.PNL.DEPRECIATION_AMORTISATION",
    "impairment losses": "FS.PNL.IMPAIRMENT_EXPENSE",
    "impairment charges to assets and special write-offs related to restructuring": "FS.PNL.IMPAIRMENT_EXPENSE",
    "raw materials and consumables used": "FS.PNL.MATERIAL_COSTS",
    "material costs": "FS.PNL.MATERIAL_COSTS",
    "cost of material": "FS.PNL.MATERIAL_COSTS",

    # EBITDA / metrics
    "ebitda": "DISC.EBITDA.EBITDA",
    "operating ebitda": "DISC.EBITDA.EBITDA",
    "ebitda margin": "DISC.EBITDA.EBITDA",  # close enough — metric
    "operating ebitda margin": "DISC.EBITDA.EBITDA",

    # EPS
    "earnings per share": "DISC.EPS_BASIC.EPS",
    "basic earnings per share": "DISC.EPS_BASIC.EPS",
    "diluted earnings per share": "DISC.EPS_DILUTED.EPS",
    "earnings per share (basic)": "DISC.EPS_BASIC.EPS",
    "earnings per share (diluted)": "DISC.EPS_DILUTED.EPS",
    "basic earnings per share in eur": "DISC.EPS_BASIC.EPS",
    "diluted earnings per share in eur": "DISC.EPS_DILUTED.EPS",

    # SFP items
    "property, plant and equipment": "FS.SFP.PPE_NET",
    "property plant and equipment": "FS.SFP.PPE_NET",
    "intangible assets": "FS.SFP.INTANGIBLE_ASSETS_GOODWILL",
    "intangible assets and goodwill": "FS.SFP.INTANGIBLE_ASSETS_GOODWILL",
    "goodwill": "DISC.GOODWILL.CARRYING_AMOUNT",
    "inventories": "FS.SFP.INVENTORIES",
    "trade and other receivables": "FS.SFP.TRADE_RECEIVABLES",
    "trade receivables": "FS.SFP.TRADE_RECEIVABLES",
    "other receivables": "FS.SFP.TRADE_RECEIVABLES",
    "cash and cash equivalents": "FS.SFP.CASH_AND_EQUIVALENTS",
    "cash and short-term deposits": "FS.SFP.CASH_AND_EQUIVALENTS",
    "non-current assets": "FS.SFP.NON_CURRENT_ASSETS",
    "total non-current assets": "FS.SFP.NON_CURRENT_ASSETS",
    "current assets": "FS.SFP.CURRENT_ASSETS",
    "total current assets": "FS.SFP.CURRENT_ASSETS",
    "total assets": "FS.SFP.TOTAL_ASSETS",
    "share capital": "FS.SFP.SHARE_CAPITAL",
    "issued capital": "FS.SFP.SHARE_CAPITAL",
    "subscribed capital": "FS.SFP.SHARE_CAPITAL",
    "retained earnings": "FS.SFP.RETAINED_EARNINGS",
    "revenue reserves": "FS.SFP.RETAINED_EARNINGS",
    "equity attributable to owners": "FS.SFP.EQUITY_ATTR_OWNERS",
    "equity attributable to owners of the company": "FS.SFP.EQUITY_ATTR_OWNERS",
    "equity attributable to equity holders of the parent": "FS.SFP.EQUITY_ATTR_OWNERS",
    "equity attributable to equity holders of wienerberger ag": "FS.SFP.EQUITY_ATTR_OWNERS",
    "total equity": "FS.SFP.TOTAL_EQUITY",
    "equity": "FS.SFP.TOTAL_EQUITY",
    "loans and borrowings": "FS.SFP.LOANS_BORROWINGS",
    "financial liabilities": "FS.SFP.LOANS_BORROWINGS",
    "bonds": "FS.SFP.LOANS_BORROWINGS",
    "trade and other payables": "FS.SFP.TRADE_PAYABLES",
    "trade payables": "FS.SFP.TRADE_PAYABLES",
    "total liabilities": "FS.SFP.TOTAL_LIABILITIES",
    "total equity and liabilities": "FS.SFP.TOTAL_EQUITY_AND_LIABILITIES",
    "investment property": "FS.SFP.INVESTMENT_PROPERTY",
    "equity-accounted investees": "FS.SFP.EQUITY_ACCOUNTED_INVESTEES",
    "investments in associates and joint ventures": "FS.SFP.EQUITY_ACCOUNTED_INVESTEES",
    "deferred tax assets": "FS.SFP.DEFERRED_TAX_ASSETS",
    "deferred tax liabilities": "FS.SFP.DEFERRED_TAX_LIABILITIES",
    "provisions": "FS.SFP.PROVISIONS",
    "non-current liabilities": "FS.SFP.NON_CURRENT_LIABILITIES",
    "total non-current liabilities": "FS.SFP.NON_CURRENT_LIABILITIES",
    "current liabilities": "FS.SFP.CURRENT_LIABILITIES",
    "total current liabilities": "FS.SFP.CURRENT_LIABILITIES",
    "share premium": "FS.SFP.SHARE_PREMIUM",
    "capital reserves": "FS.SFP.SHARE_PREMIUM",
    "reserves": "FS.SFP.RESERVES",
    "other reserves": "FS.SFP.RESERVES",
    "treasury shares": "FS.SFP.TREASURY_SHARES",
    "employee benefits": "FS.SFP.EMPLOYEE_BENEFITS_LIABILITY",
    "employee benefit obligations": "FS.SFP.EMPLOYEE_BENEFITS_LIABILITY",
    "contract assets": "FS.SFP.CONTRACT_ASSETS",
    "contract liabilities": "FS.SFP.CONTRACT_LIABILITIES",
    "right-of-use assets": "FS.SFP.RIGHT_OF_USE_ASSETS",
    "lease liabilities": "FS.SFP.LEASE_LIABILITIES",
    "other financial assets": "FS.SFP.OTHER_INVESTMENTS",
    "other investments": "FS.SFP.OTHER_INVESTMENTS",
    "other financial liabilities": "FS.SFP.OTHER_FINANCIAL_LIABILITIES",
    "prepayments": "FS.SFP.PREPAYMENTS",
    "assets held for sale": "FS.SFP.ASSETS_HELD_FOR_SALE",
    "current tax assets": "FS.SFP.CURRENT_TAX_ASSETS",
    "income tax receivables": "FS.SFP.CURRENT_TAX_ASSETS",
    "current tax liabilities": "FS.SFP.CURRENT_TAX_LIABILITIES",
    "income tax liabilities": "FS.SFP.CURRENT_TAX_LIABILITIES",
    "other payables": "FS.SFP.OTHER_PAYABLES",
    "other non-financial assets": "FS.SFP.OTHER_NON_FINANCIAL_ASSETS",
    "deferred income": "FS.SFP.DEFERRED_INCOME",
    "derivative financial instruments": "FS.SFP.DERIVATIVE_ASSETS",

    # CFS items
    "cash generated from operations": "FS.CFS.CASH_FROM_OPERATIONS",
    "cash flows from operating activities": "FS.CFS.CASH_FROM_OPERATIONS",
    "net cash from operating activities": "FS.CFS.CASH_FROM_OPERATIONS",
    "cash flows from investing activities": "FS.CFS.CASH_FROM_INVESTING",
    "net cash used in investing activities": "FS.CFS.CASH_FROM_INVESTING",
    "cash flows from financing activities": "FS.CFS.CASH_FROM_FINANCING",
    "net cash used in financing activities": "FS.CFS.CASH_FROM_FINANCING",
    "net increase in cash": "FS.CFS.NET_CHANGE_CASH",
    "net change in cash and cash equivalents": "FS.CFS.NET_CHANGE_CASH",
    "cash at beginning of period": "FS.CFS.CASH_OPENING",
    "cash and cash equivalents at beginning of period": "FS.CFS.CASH_OPENING",
    "cash at end of period": "FS.CFS.CASH_CLOSING",
    "cash and cash equivalents at end of period": "FS.CFS.CASH_CLOSING",
    "capital expenditure": "FS.CFS.CAPEX",
    "capital expenditures": "FS.CFS.CAPEX",
    "purchase of property, plant and equipment": "FS.CFS.CAPEX",
    "dividends paid": "FS.CFS.DIVIDENDS_PAID",
    "dividends": "DISC.DIVIDENDS.DIVIDEND_PAID",
    "interest paid": "FS.CFS.INTEREST_PAID",
    "interest received": "FS.CFS.INTEREST_RECEIVED",
    "income taxes paid": "FS.CFS.TAXES_PAID",
    "taxes paid": "FS.CFS.TAXES_PAID",
    "acquisition of subsidiaries": "FS.CFS.ACQUISITION_SUBSIDIARIES",
    "proceeds from disposal of subsidiaries": "FS.CFS.DISPOSAL_SUBSIDIARIES",
    "proceeds from borrowings": "FS.CFS.PROCEEDS_BORROWINGS",
    "repayment of borrowings": "FS.CFS.REPAYMENT_BORROWINGS",
    "purchase of treasury shares": "FS.CFS.PURCHASE_TREASURY_SHARES",
    "free cash flow": "FS.CFS.FREE_CASH_FLOW",

    # OCI items
    "other comprehensive income": "FS.OCI.OCI_TOTAL",
    "total comprehensive income": "FS.OCI.TOTAL_COMPREHENSIVE_INCOME",
    "total comprehensive income for the period": "FS.OCI.TOTAL_COMPREHENSIVE_INCOME",
    "items that will not be reclassified to profit or loss": "FS.OCI.ITEMS_NOT_RECLASSIFIED",
    "items that may be reclassified subsequently to profit or loss": "FS.OCI.ITEMS_MAY_RECLASSIFY",
    "remeasurements of defined benefit plans": "FS.OCI.REMEASUREMENT_DEFINED_BENEFIT",
    "foreign currency translation": "FS.OCI.FOREIGN_CURRENCY_TRANSLATION",
    "currency translation differences": "FS.OCI.FOREIGN_CURRENCY_TRANSLATION",
    "cash flow hedges": "FS.OCI.CASH_FLOW_HEDGES",
    "effective portion of changes in fair value of cash flow hedges": "FS.OCI.CASH_FLOW_HEDGES",

    # SOCIE items
    "balance at beginning of period": "FS.SOCIE.OPENING_BALANCE",
    "balance at 1 january": "FS.SOCIE.OPENING_BALANCE",
    "opening balance": "FS.SOCIE.OPENING_BALANCE",
    "balance at end of period": "FS.SOCIE.CLOSING_BALANCE",
    "balance at 31 december": "FS.SOCIE.CLOSING_BALANCE",
    "closing balance": "FS.SOCIE.CLOSING_BALANCE",
    "profit for the year": "FS.SOCIE.PROFIT_LOSS",
    "dividends to owners": "FS.SOCIE.DIVIDENDS",
    "dividend distributions": "FS.SOCIE.DIVIDENDS",
    "share-based payment": "FS.SOCIE.SHARE_BASED_PAYMENT",
    "treasury shares acquired": "FS.SOCIE.TREASURY_SHARES_ACQUIRED",

    # Disclosure / Notes items
    "external revenues": "DISC.SEGMENTS.EXTERNAL_REVENUE",
    "inter-segment revenue": "DISC.SEGMENTS.INTERSEGMENT_REVENUE",
    "segment assets": "DISC.SEGMENTS.SEGMENT_ASSETS",
    "segment liabilities": "DISC.SEGMENTS.SEGMENT_LIABILITIES",
    "depreciation": "DISC.PPE.DEPRECIATION_CHARGE",
    "amortisation": "DISC.INTANGIBLE_ASSETS.AMORTISATION_CHARGE",
    "amortization": "DISC.INTANGIBLE_ASSETS.AMORTISATION_CHARGE",
    "net debt": "DISC.BORROWINGS.NET_DEBT",
    "capital employed": "DISC.MEASURE.CAPITAL_EMPLOYED",
    "equity ratio": "DISC.MEASURE.EQUITY_RATIO",
    "gearing": "DISC.MEASURE.GEARING",
    "working capital": "DISC.MEASURE.WORKING_CAPITAL",
    "number of employees": "DISC.STAFF_COSTS.HEADCOUNT",
    "headcount": "DISC.STAFF_COSTS.HEADCOUNT",
    "average number of employees": "DISC.STAFF_COSTS.HEADCOUNT",

    # Wienerberger specific segment labels → use segment concept
    "europe west": "DISC.SEGMENTS.EXTERNAL_REVENUE",
    "europe east": "DISC.SEGMENTS.EXTERNAL_REVENUE",
    "north america": "DISC.SEGMENTS.EXTERNAL_REVENUE",

    # Rollforward items (common in notes)
    "additions": "DISC.PPE.ADDITIONS",
    "disposals": "DISC.PPE.DISPOSALS",
    "depreciation charge": "DISC.PPE.DEPRECIATION_CHARGE",
    "impairment": "DISC.PPE.IMPAIRMENT",
    "reversal of impairments": "DISC.PPE.REVERSAL_IMPAIRMENT",
    "currency translation and other": "DISC.PPE.FX_AND_OTHER",
    "change in the scope of consolidation": "DISC.PPE.SCOPE_CHANGES",

    # Share data
    "shares outstanding": "DISC.SHARE_CAPITAL.SHARES_OUTSTANDING",
    "shares outstanding (weighted)": "DISC.EPS_DENOMINATOR_BASIC.WEIGHTED_SHARES",
    "market capitalization": "DISC.MEASURE.MARKET_CAP",
    "market capitalization at year-end": "DISC.MEASURE.MARKET_CAP",
    "share price at year-end": "DISC.MEASURE.SHARE_PRICE",
    "share price high": "DISC.MEASURE.SHARE_PRICE",
    "share price low": "DISC.MEASURE.SHARE_PRICE",
    "dividend per share": "DISC.DIVIDENDS.DIVIDEND_PER_SHARE",
    "dividend": "DISC.DIVIDENDS.DIVIDEND_PAID",

    # Tax note items
    "current tax": "DISC.INCOME_TAX.CURRENT_TAX",
    "deferred tax": "DISC.INCOME_TAX.DEFERRED_TAX",
    "effective tax rate": "DISC.INCOME_TAX.EFFECTIVE_TAX_RATE",
    "tax rate": "DISC.INCOME_TAX.EFFECTIVE_TAX_RATE",

    # Financial instruments
    "fair value": "DISC.FINANCIAL_INSTRUMENTS.FAIR_VALUE",
    "carrying amount": "DISC.FINANCIAL_INSTRUMENTS.CARRYING_AMOUNT",
    "amortised cost": "DISC.FINANCIAL_INSTRUMENTS.AMORTISED_COST",
    "fair value through profit or loss": "DISC.FINANCIAL_INSTRUMENTS.FVTPL",
    "fair value through other comprehensive income": "DISC.FINANCIAL_INSTRUMENTS.FVOCI",

    # Lease items
    "lease liabilities": "DISC.LEASE_LIABILITIES.CARRYING_AMOUNT",

    # Related party
    "related party transactions": "DISC.RELATED_PARTY.TRANSACTION_AMOUNT",

    # Provisions note
    "provision for warranties": "DISC.PROVISIONS.WARRANTY",
    "provision for restructuring": "DISC.PROVISIONS.RESTRUCTURING",
    "other provisions": "DISC.PROVISIONS.OTHER",

    # Revenue disaggregation
    "revenue from contracts with customers": "FS.PNL.REVENUE",

    # PNL — Wienerberger specific labels
    "cost of goods sold": "FS.PNL.COST_OF_SALES",
    "gross profit": "FS.PNL.GROSS_PROFIT",
    "selling expenses": "FS.PNL.SELLING_DISTRIBUTION",
    "income from investments in associates and joint ventures": "FS.PNL.SHARE_OF_PROFIT_ASSOCIATES",
    "interest and similar income": "FS.PNL.FINANCE_INCOME",
    "interest and similar expenses": "FS.PNL.FINANCE_COSTS",
    "financial result": "FS.PNL.NET_FINANCE_COSTS",
    "profit/loss before tax": "FS.PNL.PROFIT_BEFORE_TAX",
    "profit/loss after tax": "FS.PNL.PROFIT_FOR_PERIOD",
    "profit/ loss after tax": "FS.PNL.PROFIT_FOR_PERIOD",
    "thereof attributabletoequityholdersoftheparentcompany": "FS.PNL.PROFIT_ATTR_OWNERS",
    "earnings per share (ineur)": "DISC.EPS_BASIC.EPS",
    "(ineur)": None,  # sub-label of EPS, skip
    "other": None,  # too ambiguous without context

    # SFP — Wienerberger specific
    "other financial investments and non-current receivables": "FS.SFP.OTHER_INVESTMENTS",
    "trade receivables": "FS.SFP.TRADE_RECEIVABLES",
    "other current receivables": "FS.SFP.TRADE_RECEIVABLES",
    "issued capital": "FS.SFP.SHARE_CAPITAL",
    "controlling interests": "FS.SFP.EQUITY_ATTR_OWNERS",
    "employee-related provisions": "FS.SFP.EMPLOYEE_BENEFITS_LIABILITY",
    "other non-current provisions": "FS.SFP.PROVISIONS",
    "other non-current liabilities": "FS.SFP.OTHER_FINANCIAL_LIABILITIES",
    "other current liabilities": "FS.SFP.OTHER_PAYABLES",

    # CFS — Wienerberger CFS detail (raw_119 p.192)
    "gross cash flow": "FS.CFS.GROSS_CASH_FLOW",
    "cashflowfromoperatingactivities": "FS.CFS.CASH_FROM_OPERATIONS",
    "cash flow from operating activities": "FS.CFS.CASH_FROM_OPERATIONS",
    "cashflowfrominvesting activities": "FS.CFS.CASH_FROM_INVESTING",
    "cash flow from investing activities": "FS.CFS.CASH_FROM_INVESTING",
    "cashflowfromfinancing activities": "FS.CFS.CASH_FROM_FINANCING",
    "cash flow from financing activities": "FS.CFS.CASH_FROM_FINANCING",
    "changeincashandcashequivalents": "FS.CFS.NET_CHANGE_CASH",
    "change in cash and cash equivalents": "FS.CFS.NET_CHANGE_CASH",
    "effects of exchange rate fluctuations on cash held": "FS.CFS.FX_EFFECT",
    "cash and cash equivalents at the beginning of the period": "FS.CFS.CASH_OPENING",
    "cashandcashequivalentsattheendoftheperiod": "FS.CFS.CASH_CLOSING",
    "cash and cash equivalents at the end of the period": "FS.CFS.CASH_CLOSING",
    "increase/decrease in inventories": "FS.CFS.CHANGE_INVENTORIES",
    "increase/decrease in trade receivables": "FS.CFS.CHANGE_RECEIVABLES",
    "increase/decrease in trade payables": "FS.CFS.CHANGE_PAYABLES",
    "increase/decrease in other net current assets": "FS.CFS.CHANGE_OTHER_WORKING_CAPITAL",
    "increase/decrease in non-current provisions": "FS.CFS.CHANGE_PROVISIONS",
    "impairment charges to assets, special write-offs and other valuation effects": "FS.PNL.IMPAIRMENT_EXPENSE",
    "gains/losses from the disposal of fixed and financial assets": "FS.CFS.GAIN_LOSS_DISPOSAL",
    "interest result": "FS.PNL.NET_FINANCE_COSTS",
    "other non-cash income and expenses": "FS.CFS.OTHER_NON_CASH",
    "proceeds from the sale of assets (including financial assets)": "FS.CFS.PROCEEDS_DISPOSAL",
    "payments madefor property, plant and equipment and intangible assets": "FS.CFS.CAPEX",
    "payments madefor investments in financial assets": "FS.CFS.PURCHASE_INVESTMENTS",
    "dividend payments from associates and joint ventures": "FS.CFS.DIVIDENDS_FROM_ASSOCIATES",
    "increase/decrease in securities and other financial assets": "FS.CFS.CHANGE_FINANCIAL_ASSETS",
    "net payments madefor the acquisition of companies": "FS.CFS.ACQUISITION_SUBSIDIARIES",
    "net proceeds from the sale of companies": "FS.CFS.DISPOSAL_SUBSIDIARIES",
    "cash inflows from the increase in short-term financial liabilities": "FS.CFS.PROCEEDS_BORROWINGS",
    "cash outflows from the repayment of short-term financial liabilities": "FS.CFS.REPAYMENT_BORROWINGS",
    "cash inflows from the increase in long-term financial liabilities": "FS.CFS.PROCEEDS_BORROWINGS",
    "cash outflows from the repayment of lease liabilities": "FS.CFS.REPAYMENT_LEASES",
    "dividends paid by wienerbergerag": "FS.CFS.DIVIDENDS_PAID",
    "dividends paid to non-controlling interests": "FS.CFS.DIVIDENDS_PAID_NCI",

    # SOCIE — Wienerberger specific (OCR merged text)
    "balanceon31/12/2022": "FS.SOCIE.OPENING_BALANCE",
    "balanceon31/12/2023": "FS.SOCIE.OPENING_BALANCE",
    "balanceon31/12/2024": "FS.SOCIE.CLOSING_BALANCE",
    "profit/loss after tax": "FS.SOCIE.PROFIT_LOSS",
    "foreign exchange adjustments": "FS.OCI.FOREIGN_CURRENCY_TRANSLATION",
    "foreign exchange adjustments to investments in associates and joint ventures": "FS.OCI.FOREIGN_CURRENCY_TRANSLATION",
    "totalcomprehensiveincome": "FS.OCI.TOTAL_COMPREHENSIVE_INCOME",
    "total comprehensive income": "FS.OCI.TOTAL_COMPREHENSIVE_INCOME",
    "dividend/hybrid coupon payment": "FS.SOCIE.DIVIDENDS",
    "effects from hyperinflation (ias 29)": "FS.SOCIE.HYPERINFLATION",
    "changes in stock option plan": "FS.SOCIE.SHARE_BASED_PAYMENT",

    # Entity list / consolidation (table_100)
    "change in consolidation method": "DISC.ENTITY_LIST.SCOPE_CHANGE",
    "included during reporting year for the first time": "DISC.ENTITY_LIST.ADDITIONS",
    "merged/ liquidated during the reporting period": "DISC.ENTITY_LIST.DISPOSALS",
    "divested during the reporting period": "DISC.ENTITY_LIST.DISPOSALS",
    "thereof foreign companies": "DISC.ENTITY_LIST.COUNT",
    "thereof domestic companies": "DISC.ENTITY_LIST.COUNT",

    # OCI misclassified table_102 (actually associate/JV summary)
    # These are PNL-like labels in an OCI-classified table — see WBI-005

    # Revenue disaggregation by product (table_109)
    "wall": "DISC.REVENUE.PRODUCT_LINE",
    "façade": "DISC.REVENUE.PRODUCT_LINE",
    "roof": "DISC.REVENUE.PRODUCT_LINE",
    "pavers": "DISC.REVENUE.PRODUCT_LINE",
    "pipes": "DISC.REVENUE.PRODUCT_LINE",
    "total": None,  # Too generic — skip

    # Staff cost allocation (table_117)
    "production": "DISC.STAFF_COSTS.BY_FUNCTION",
    "sales": "DISC.STAFF_COSTS.BY_FUNCTION",
    "administration": "DISC.STAFF_COSTS.BY_FUNCTION",

    # Financial result detail (table_121)
    "interest expense on lease liabilities": "FS.PNL.FINANCE_COSTS",
    "net interest result from defined benefit pension and severance obligations as well as anniversary bonuses": "FS.PNL.FINANCE_COSTS",
    "income from third parties (dividends)": "FS.PNL.FINANCE_INCOME",
    "incomefrominvestments": "FS.PNL.FINANCE_INCOME",
    "result from the disposal of investments": "FS.PNL.FINANCE_INCOME",
    "valuation of derivative financial instruments": "FS.PNL.FINANCE_COSTS",
    "impairment of financial instruments": "FS.PNL.IMPAIRMENT_EXPENSE",
    "write-ups on financial instruments": "FS.PNL.FINANCE_INCOME",
    "valuation of other investments": "FS.PNL.FINANCE_COSTS",
    "recycling foreign currency effects from deconsolidation": "FS.PNL.FINANCE_COSTS",
    "foreign exchange differences": "FS.PNL.FINANCE_COSTS",
    "netresult": "FS.PNL.NET_FINANCE_COSTS",
    "bank charges": "FS.PNL.FINANCE_COSTS",
    "other financial result": "FS.PNL.NET_FINANCE_COSTS",

    # Share capital note (table_124)
    "outstanding": "DISC.SHARE_CAPITAL.SHARES_OUTSTANDING",
    "weighted average": "DISC.EPS_DENOMINATOR_BASIC.WEIGHTED_SHARES",

    # Segment revenue tables (tables 129, 130)
    "western europe": "DISC.SEGMENTS.EXTERNAL_REVENUE",
    "northern europe": "DISC.SEGMENTS.EXTERNAL_REVENUE",
    "uk/ireland": "DISC.SEGMENTS.EXTERNAL_REVENUE",
    "wienerberger building solution": "DISC.SEGMENTS.EXTERNAL_REVENUE",
    "wienerberger piping solution": "DISC.SEGMENTS.EXTERNAL_REVENUE",
    "emerging markets": "DISC.SEGMENTS.EXTERNAL_REVENUE",
    "bricks north america": "DISC.SEGMENTS.EXTERNAL_REVENUE",
    "pipes north america": "DISC.SEGMENTS.EXTERNAL_REVENUE",
    "smart hubsolutions": "DISC.SEGMENTS.EXTERNAL_REVENUE",
    "central east": "DISC.SEGMENTS.EXTERNAL_REVENUE",
    "south east": "DISC.SEGMENTS.EXTERNAL_REVENUE",
    "wienerberger": "DISC.SEGMENTS.EXTERNAL_REVENUE",

    # Financial instruments (tables 142-143)
    "shares in funds": "DISC.FINANCIAL_INSTRUMENTS.FAIR_VALUE",
    "stock": "DISC.FINANCIAL_INSTRUMENTS.FAIR_VALUE",
    "other securities": "DISC.FINANCIAL_INSTRUMENTS.FAIR_VALUE",
    "securities": "DISC.FINANCIAL_INSTRUMENTS.FAIR_VALUE",

    # Employee benefit assumptions (tables 150, 154)
    "discount rate": "DISC.RETIREMENT_BENEFITS.DISCOUNT_RATE",
    "salary increases": "DISC.RETIREMENT_BENEFITS.SALARY_GROWTH",
    "employee turnover": "DISC.RETIREMENT_BENEFITS.TURNOVER_RATE",
    "life expectancy": "DISC.RETIREMENT_BENEFITS.MORTALITY",

    # Liabilities breakdown (table_156)
    "interest-bearing loans": "FS.SFP.LOANS_BORROWINGS",
    "payables for current taxes": "FS.SFP.CURRENT_TAX_LIABILITIES",
    "contract liability": "FS.SFP.CONTRACT_LIABILITIES",
    "amounts owedto tax authorities and social security institutions": "FS.SFP.OTHER_PAYABLES",
    "refund liabilities": "DISC.REFUND_LIABILITY.CARRYING_AMOUNT",
    "miscellaneous liabilities": "FS.SFP.OTHER_PAYABLES",
    "other liabilities": "FS.SFP.OTHER_PAYABLES",
    "total liabilities": "FS.SFP.TOTAL_LIABILITIES",

    # Borrowings maturity / CFS detail (table_159)
    "bonds": "DISC.BORROWINGS.BONDS",
    "liabilities to banks": "DISC.BORROWINGS.BANK_LOANS",
    "liabilities to non-banks": "DISC.BORROWINGS.OTHER_BORROWINGS",
    "financial instruments": "DISC.FINANCIAL_INSTRUMENTS.CARRYING_AMOUNT",
    "forward exchange contracts and swaps": "DISC.DERIVATIVE_INSTRUMENTS.NOTIONAL_AMOUNT",
    "carryingamounts/ contractual cash flows": None,  # header-like label

    # Hedging instruments (tables 161-162)
    "interest rate hedging instruments": "DISC.DERIVATIVE_INSTRUMENTS.NOTIONAL_AMOUNT",
    "foreign currency hedging instruments": "DISC.DERIVATIVE_INSTRUMENTS.NOTIONAL_AMOUNT",
    "interest rate and foreign currency hedging instruments": "DISC.DERIVATIVE_INSTRUMENTS.NOTIONAL_AMOUNT",

    # Currency risk (table_167)
    "euro": "DISC.MARKET_RISK.CURRENCY_EXPOSURE",
    "eastern european currencies": "DISC.MARKET_RISK.CURRENCY_EXPOSURE",
    "usdollar": "DISC.MARKET_RISK.CURRENCY_EXPOSURE",
    "british pound": "DISC.MARKET_RISK.CURRENCY_EXPOSURE",
    "capital employedafter hedgingeffect": "DISC.MEASURE.CAPITAL_EMPLOYED",

    # Trade receivables by geography (table_171)
    "central-eastern europe": "DISC.TRADE_RECEIVABLES.BY_GEOGRAPHY",
    "total trade receivables andmiscellaneous receivables": "FS.SFP.TRADE_RECEIVABLES",
    "thereof insured against default": "DISC.CREDIT_RISK.INSURED_RECEIVABLES",

    # Ageing (table_173)
    "not due": "DISC.CREDIT_RISK.NOT_PAST_DUE",
    "upto 30 days overdue": "DISC.CREDIT_RISK.PAST_DUE_30",
    "31 to 60 days overdue": "DISC.CREDIT_RISK.PAST_DUE_60",
    "61 to 90 days overdue": "DISC.CREDIT_RISK.PAST_DUE_90",
    "more than 90 days overdue": "DISC.CREDIT_RISK.PAST_DUE_90_PLUS",

    # 10-year overview KPIs (table_179)
    "operating ebitda": "DISC.EBITDA.EBITDA",
    "total investments": "FS.CFS.CAPEX",
    "return on equity": "DISC.MEASURE.ROE",
    "roce": "DISC.MEASURE.ROCE",
    "øemployees": "DISC.STAFF_COSTS.HEADCOUNT",

    # Rollforward opening/closing dates
    "31/12/2023": None,  # Date label, not a concept
    "31/12/2024": None,

    # Metrics / ratios
    "net debt/operating ebitda": "DISC.MEASURE.NET_DEBT_TO_EBITDA",
    "operating ebitda/interest result": "DISC.MEASURE.INTEREST_COVERAGE",
    "asset coverage": "DISC.MEASURE.ASSET_COVERAGE",
    "working capital to revenues": "DISC.MEASURE.WORKING_CAPITAL_RATIO",
    "adjusted earnings": "DISC.MEASURE.ADJUSTED_EARNINGS",
    "p/e ratio high": "DISC.MEASURE.PE_RATIO",
    "p/e ratio low": "DISC.MEASURE.PE_RATIO",
    "p/e ratio at year-end": "DISC.MEASURE.PE_RATIO",
    "earnings": "FS.PNL.PROFIT_FOR_PERIOD",
    "equity": "FS.SFP.TOTAL_EQUITY",
    "result from the sale of non-core assets": "FS.PNL.OTHER_INCOME",
    "sale of disposal group": "FS.PNL.PROFIT_DISCONTINUED",
    "structural adjustments": "FS.PNL.OTHER_EXPENSES",
    "operatingebitda": "DISC.EBITDA.EBITDA",

    # Capital employed breakdown (table_21)
    "equity and non-controlling interests": "FS.SFP.TOTAL_EQUITY",
    "cash and financial assets": "FS.SFP.CASH_AND_EQUIVALENTS",
    "capital employedatreporting date": "DISC.MEASURE.CAPITAL_EMPLOYED",
    "average capitalemployed": "DISC.MEASURE.CAPITAL_EMPLOYED",

    # ESG / sustainability — explicitly skip
    "fuel consumption from coal and coal products": None,
    "fuel consumption from crude oil and petroleum products": None,
    "fuel consumption from natural gas": None,
    "fuel consumption from other fossil sources": None,
    "total energy consumption": None,
    "total fossilenergyconsumption": None,
    "totalrenewableenergyconsumption": None,
    "totalenergyconsumption": None,
    "total ghgemissions": None,
    "totalghgemissions": None,
    "gross scope 1 ghgemissions": None,
    "water consumption": None,
    "water withdrawals": None,
    "water discharges": None,
    "østock exchange turnover/day": None,

    # Financial ratios
    "gross profit to revenues": "DISC.MEASURE.GROSS_MARGIN",
    "administrative expenses to revenues": "DISC.MEASURE.ADMIN_RATIO",
    "selling expenses to revenues": "DISC.MEASURE.SELLING_RATIO",
}


def build_label_index(concepts):
    """Build normalized label → (concept_id, confidence) index."""
    index = {}

    # From ontology concepts
    for c in concepts:
        if c["label"]:
            norm = normalize(c["label"])
            if norm:
                index[norm] = (c["id"], 0.90)
        for alias in c.get("aliases", []):
            norm = normalize(alias)
            if norm:
                index[norm] = (c["id"], 0.85)

    # From extra label map (higher confidence since hand-curated)
    for label, concept_id in EXTRA_LABEL_MAP.items():
        norm = normalize(label)
        if norm and concept_id is not None:
            index[norm] = (concept_id, 0.85)
        elif concept_id is None:
            index[norm] = (None, 0.0)  # explicit skip

    return index


def fuzzy_match(label, index, threshold=0.75):
    """Find best fuzzy match in the label index."""
    norm = normalize(label)
    if not norm or len(norm) < 3:
        return None, 0.0

    # Exact match
    if norm in index:
        return index[norm]

    # Try with "total" prefix removed
    sans_total = re.sub(r"^total\s+", "", norm)
    if sans_total != norm and sans_total in index:
        cid, conf = index[sans_total]
        return cid, conf * 0.95

    # Try with "thereof" / "of which" prefix removed
    sans_thereof = re.sub(r"^(thereof|of which|davon)\s+", "", norm)
    if sans_thereof != norm and sans_thereof in index:
        cid, conf = index[sans_thereof]
        return cid, conf * 0.90

    # Fuzzy matching via SequenceMatcher
    best_score = 0.0
    best_match = None
    for idx_label, (cid, conf) in index.items():
        if cid is None:
            continue
        score = SequenceMatcher(None, norm, idx_label).ratio()
        if score > best_score:
            best_score = score
            best_match = (cid, conf * score)

    if best_score >= threshold:
        return best_match

    return None, 0.0


def infer_dimensions(table, row, concept_id):
    """Infer basic dimensions from table context."""
    dims = {}
    stmt = table["metadata"]["statementComponent"]

    # Entity dimension
    dims["AXIS.ENTITY"] = "ENTITY.CONSOLIDATED"

    # Scope for PNL
    if stmt == "PNL" and concept_id and concept_id.startswith("FS.PNL."):
        dims["AXIS.SCOPE"] = "SCOPE.CONTINUING"

    # Segment dimension for segment tables
    label_lower = row["label"].lower().strip()
    if label_lower in ("europe west", "europe east", "north america"):
        dims["AXIS.SEGMENT_DOC"] = f"SEG.{label_lower.upper().replace(' ', '_')}"

    return dims


def pretag_document(tg_path, dry_run=False):
    """Pre-tag all financial statement rows in a table_graphs.json file."""
    # Find ontology — prefer /tmp/doc_tag which has the full concepts section
    ontology_path = "/tmp/doc_tag/ontology.yaml"
    if not os.path.exists(ontology_path):
        ontology_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                      "ontology.yaml")
    if not os.path.exists(ontology_path):
        print(f"Error: ontology.yaml not found")
        sys.exit(1)

    concepts = parse_ontology_full(ontology_path)
    label_index = build_label_index(concepts)
    print(f"Loaded ontology: {len(concepts)} concepts, {len(label_index)} label entries")

    with open(tg_path) as f:
        data = json.load(f)

    # Build reference graph for note-constrained matching
    ref_graph = build_reference_graph(data["tables"])

    stats = {"already_tagged": 0, "newly_tagged": 0, "skipped": 0, "no_match": 0}
    unmatched = []

    for table in data["tables"]:
        stmt = table.get("metadata", {}).get("statementComponent")
        if not stmt:
            continue

        # Collect note column indices for this table
        note_col_indices = set()
        for col in table.get("columns", []):
            if col.get("role") == "NOTES":
                note_col_indices.add(col["colIdx"])
            elif col.get("headerLabel", "").lower().strip() in (
                "note", "notes", "anhang", "anmerkung", "anmerkungen",
            ):
                note_col_indices.add(col["colIdx"])

        for row in table["rows"]:
            if row["rowType"] not in ("DATA", "TOTAL_EXPLICIT", "TOTAL_IMPLICIT"):
                continue

            # Skip already tagged
            if row.get("preTagged") and row["preTagged"].get("conceptId"):
                stats["already_tagged"] += 1
                continue

            label = row["label"]

            # Skip empty labels or pure numeric labels
            if not label.strip() or re.match(r"^\d+$", label.strip()):
                stats["skipped"] += 1
                continue

            # Skip ESG/sustainability rows
            if is_esg_label(label):
                stats["skipped"] += 1
                continue

            # Use parse_label for cleaner matching (strips footnote letters etc.)
            parsed = parse_label(label)
            clean_label = parsed.clean

            # Get note number from note column if available
            row_note_num = None
            if note_col_indices:
                for cell in row.get("cells", []):
                    if cell.get("colIdx") in note_col_indices:
                        note_text = cell.get("text", "").strip()
                        if note_text:
                            m = re.match(r"(\d+)", note_text)
                            if m:
                                row_note_num = int(m.group(1))
                        break

            # Try matching with clean label first, then fall back to raw
            concept_id, confidence = fuzzy_match(clean_label, label_index)
            if concept_id is None and confidence == 0.0:
                # Fall back to raw label matching
                concept_id, confidence = fuzzy_match(label, label_index)

            if concept_id is None:
                if confidence == 0.0 and (normalize(label) in label_index or normalize(clean_label) in label_index):
                    # Explicitly skipped
                    stats["skipped"] += 1
                else:
                    stats["no_match"] += 1
                    unmatched.append(f"  {table['tableId']:12s} [{stmt:5s}] {label}")
                continue

            # Note-constrained context enrichment: if row has a note number,
            # look up the note's disclosure context and store it
            note_context = None
            if row_note_num is not None:
                note_context = ref_graph.context_for_note(row_note_num)

            dims = infer_dimensions(table, row, concept_id)
            stmt_role = stmt

            pre_tagged = {
                "conceptId": concept_id,
                "dimensions": dims,
                "matchConfidence": round(confidence, 3),
                "statementRole": stmt_role,
            }
            if note_context:
                pre_tagged["noteContext"] = note_context
            if row_note_num is not None:
                pre_tagged["noteNumber"] = row_note_num
            row["preTagged"] = pre_tagged
            stats["newly_tagged"] += 1

    print(f"\n=== Pre-tagging results ===")
    print(f"  Already tagged:  {stats['already_tagged']}")
    print(f"  Newly tagged:    {stats['newly_tagged']}")
    print(f"  Skipped (ESG):   {stats['skipped']}")
    print(f"  No match:        {stats['no_match']}")
    total = stats['already_tagged'] + stats['newly_tagged'] + stats['skipped'] + stats['no_match']
    tagged = stats['already_tagged'] + stats['newly_tagged']
    print(f"  Coverage:        {tagged}/{total} ({100*tagged/total:.0f}%)")

    if unmatched:
        print(f"\n  Unmatched rows ({len(unmatched)}):")
        for u in unmatched[:50]:
            print(u)
        if len(unmatched) > 50:
            print(f"  ... and {len(unmatched) - 50} more")

    if not dry_run:
        # Backup original
        backup_path = tg_path + ".bak"
        if not os.path.exists(backup_path):
            import shutil
            shutil.copy2(tg_path, backup_path)
            print(f"\n  Backup: {backup_path}")

        with open(tg_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  Written: {tg_path}")
    else:
        print(f"\n  [DRY RUN] No changes written.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    path = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    if not os.path.exists(path):
        print(f"Error: {path} not found")
        sys.exit(1)

    pretag_document(path, dry_run=dry_run)
