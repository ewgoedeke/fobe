#!/usr/bin/env python3
"""
table_classifier.py — Shared table classification logic.

Classifies financial statement tables into statement types (PNL, SFP, OCI,
CFS, SOCIE) and disclosure note contexts (DISC.*) based on row labels and
column headers.

Used by:
  - convert_isg.py (ISG format conversion)
  - classify_tables.py (Docling-extracted documents)
"""


def classify_table(labels_first10: str, labels_all: str,
                   col_headers: str, first_label: str = "",
                   has_values: bool = True) -> str | None:
    """Classify a table into a statement type based on keyword patterns.

    Args:
        labels_first10: Lowered, space-joined row labels from first ~10 rows.
        labels_all: Lowered, space-joined row labels from ALL rows.
        col_headers: Lowered, space-joined column header labels.
        first_label: Lowered, stripped first row label.
        has_values: Whether the table has any numeric values.

    Returns:
        Statement type string (e.g., "PNL", "SFP", "DISC.PPE") or None.
    """
    labels = labels_first10
    kw = labels_all
    col_kw = col_headers

    # ── Primary statements ────────────────────────────────────────

    # SFP: assets side (header mentions statement of financial position / "as at")
    is_sfp_header = ("statement of financial position" in col_kw
                     or "as at" in col_kw
                     or ("31 december" in col_kw and "for the year" not in col_kw)
                     or "31. dezember" in col_kw)
    if is_sfp_header:
        if "assets" in labels or "aktiva" in labels:
            return "SFP"
        if "equity" in labels and "liabilities" in kw:
            return "SFP"

    # PNL must be checked before SFP equity side (both contain "equity" keyword)
    if "revenue" in labels and ("cost of sales" in labels or "gross profit" in labels):
        return "PNL"
    # Banking PNL
    if "net interest income" in labels or "zinsüberschuss" in labels:
        return "PNL"
    # Insurance PNL
    if "insurance revenue" in labels or "versicherungserlöse" in labels:
        return "PNL"
    # UGB PNL (Gesamtkostenverfahren)
    if "umsatzerlöse" in labels and ("materialaufwand" in kw or "personalaufwand" in kw
                                      or "rohergebnis" in kw or "betriebsleistung" in kw):
        return "PNL"
    # Generic PNL
    if any(w in labels for w in ["operating profit", "betriebsergebnis", "operating result"]):
        if any(w in kw for w in ["revenue", "umsatz", "income tax", "profit before tax"]):
            return "PNL"

    if "other comprehensive income" in labels or "sonstiges ergebnis" in labels:
        return "OCI"
    if "cash flows" in labels or "cash flow" in col_kw or "kapitalflussrechnung" in labels:
        return "CFS"
    if "attributable to" in labels and "comprehensive" in labels:
        return "OCI"
    if "segment" in col_kw or "segment" in labels[:200]:
        return "DISC.SEGMENTS"

    # SFP equity+liabilities side (split table)
    if first_label in ("equity", "liabilities", "liabilities and equity",
                       "eigenkapital", "passiva"):
        if any(w in kw for w in ["share capital", "retained earnings",
                                 "total equity and liabilities",
                                 "total equity", "borrowings",
                                 "grundkapital", "gewinnrücklage",
                                 "summe passiva"]):
            return "SFP"

    # UGB SFP
    if "aktiva" in labels or "anlagevermögen" in labels:
        if any(w in kw for w in ["umlaufvermögen", "sachanlagen", "summe aktiva",
                                 "bilanzsumme"]):
            return "SFP"

    if not has_values:
        return None

    # ── SOCIE ─────────────────────────────────────────────────────

    if any(w in col_kw for w in ["retained earnings", "treasury share",
                                 "revaluation reserve", "hedging reserve",
                                 "translation reserve", "fair value reserve",
                                 "non- controlling interests", "total equity",
                                 "gewinnrücklage", "kapitalrücklage"]):
        if any(w in col_kw for w in ["reserve", "retained", "nci", "total",
                                     "rücklage"]):
            return "SOCIE"

    # ── Disclosure notes (row-label-driven) ───────────────────────

    # Segments (IFRS 8) — column headers often name segments
    if any(w in col_kw for w in ["reportable segment", "all other segment",
                                 "total reportable", "segment total"]):
        return "DISC.SEGMENTS"
    if "segment" in kw and any(w in kw for w in ["revenue", "assets", "liabilities",
                                                 "reportable", "operating"]):
        return "DISC.SEGMENTS"

    # Revenue disaggregation (IFRS 15)
    if "revenue" in kw and any(w in kw for w in ["disaggregat", "timing",
                                                 "geography", "product",
                                                 "point in time", "over time",
                                                 "contract"]):
        return "DISC.REVENUE"

    # PPE rollforward (IAS 16)
    if any(w in kw for w in ["property, plant", "ppe", "sachanlagen"]):
        if any(w in kw for w in ["cost", "depreciation", "carrying", "additions",
                                 "disposals", "balance at", "anschaffungskosten",
                                 "abschreibung", "buchwert"]):
            return "DISC.PPE"

    # Intangibles rollforward (IAS 38)
    if any(w in kw for w in ["intangible", "immaterielle"]):
        if any(w in kw for w in ["cost", "amortis", "carrying",
                                 "additions", "balance at"]):
            return "DISC.INTANGIBLES"

    # Goodwill (IFRS 3 / IAS 36)
    if any(w in kw for w in ["goodwill", "firmenwert"]):
        if any(w in kw for w in ["impairment", "carrying", "cgu", "balance at"]):
            return "DISC.GOODWILL"

    # Investment property (IAS 40)
    if "investment property" in kw or "als finanzinvestition" in kw:
        return "DISC.INV_PROP"

    # Leases (IFRS 16)
    if "right-of-use" in kw or "nutzungsrecht" in kw:
        return "DISC.LEASES"
    if "lease" in kw and any(w in kw for w in ["maturity", "liability", "right",
                                               "depreciation"]):
        return "DISC.LEASES"
    if "leasing" in kw and any(w in kw for w in ["verbindlichkeit", "laufzeit"]):
        return "DISC.LEASES"

    # Provisions rollforward (IAS 37)
    if any(w in kw for w in ["provision", "rückstellung"]):
        if any(w in kw for w in ["opening", "closing", "beginning", "reversal",
                                 "utilised", "balance at", "anfangsbestand",
                                 "verbrauch", "auflösung"]):
            return "DISC.PROVISIONS"

    # Tax (IAS 12)
    if "deferred tax" in kw or "latente steuer" in kw:
        return "DISC.TAX"
    if "tax" in kw and any(w in kw for w in ["effective", "reconcil", "rate",
                                             "current tax expense"]):
        return "DISC.TAX"
    if "steuer" in kw and any(w in kw for w in ["effektiv", "überleit", "satz"]):
        return "DISC.TAX"

    # Employee benefits (IAS 19)
    if any(w in kw for w in ["employee benefit", "pension", "defined benefit",
                             "actuarial", "post-employment",
                             "abfertigung", "pensionsverpflichtung"]):
        return "DISC.EMPLOYEE_BENEFITS"
    if any(w in kw for w in ["employee", "personal"]):
        if any(w in kw for w in ["wages", "salaries", "social", "contribution",
                                 "löhne", "gehälter", "sozial"]):
            return "DISC.EMPLOYEE_BENEFITS"

    # Earnings per share (IAS 33)
    if "earnings per share" in kw or ("weighted" in kw and "shares" in kw):
        return "DISC.EPS"
    if "profit" in kw and "attributable" in kw and "ordinary" in kw:
        return "DISC.EPS"
    if "ergebnis je aktie" in kw:
        return "DISC.EPS"

    # Share-based payments (IFRS 2)
    if "share" in kw and any(w in kw for w in ["option", "based", "plan",
                                               "granted", "vested", "exercised"]):
        return "DISC.SHARE_BASED"

    # Business combinations (IFRS 3)
    if any(w in kw for w in ["acquisition", "business combination", "purchase price",
                             "consideration transferred", "unternehmenserwerb"]):
        return "DISC.BCA"

    # Financial instruments (IFRS 7/9)
    if "financial" in kw and any(w in kw for w in ["asset", "instrument",
                                                   "liability", "fvoci",
                                                   "amortised cost"]):
        return "DISC.FIN_INST"
    if "finanzinstrument" in kw:
        return "DISC.FIN_INST"

    # Fair value hierarchy (IFRS 13)
    if "fair value" in kw and any(w in kw for w in ["level", "hierarch"]):
        return "DISC.FAIR_VALUE"

    # Inventories (IAS 2)
    if any(w in kw for w in ["inventor", "raw material", "finished good",
                             "work in progress", "vorräte", "roh-",
                             "fertige erzeugnisse"]):
        return "DISC.INVENTORIES"

    # Borrowings / debt (IFRS 7)
    if any(w in kw for w in ["borrowing", "bond issue", "loan"]):
        if any(w in kw for w in ["maturity", "repayment", "carrying",
                                 "balance at", "proceeds"]):
            return "DISC.BORROWINGS"

    # Related parties (IAS 24)
    if "related party" in kw or "key management" in kw or "nahestehende" in kw:
        return "DISC.RELATED_PARTIES"

    # Contingencies and commitments (IAS 37)
    if "contingent" in kw or "commitment" in kw or "eventualverbindlichkeit" in kw:
        return "DISC.CONTINGENCIES"

    # Held for sale / discontinued ops (IFRS 5)
    if any(w in kw for w in ["held for sale", "disposal group", "discontinued",
                             "zur veräußerung gehalten"]):
        return "DISC.HELD_FOR_SALE"

    # Hedge accounting (IFRS 9)
    if any(w in kw for w in ["hedge", "hedging", "cash flow hedge",
                             "forward exchange contract", "sicherungsgeschäft"]):
        return "DISC.HEDGE"

    # Credit risk / ECL (IFRS 9)
    if "credit" in kw and any(w in kw for w in ["risk", "ecl", "loss allowance",
                                                "expected"]):
        return "DISC.CREDIT_RISK"
    if "receivable" in kw and any(w in kw for w in ["ageing", "past due",
                                                    "allowance"]):
        return "DISC.CREDIT_RISK"

    # Biological assets (IAS 41)
    if "biological" in kw or "biologische vermögenswerte" in kw:
        return "DISC.BIOLOGICAL_ASSETS"

    # Government grants (IAS 20)
    if "government grant" in kw or "zuwendungen der öffentlichen hand" in kw:
        return "DISC.GOV_GRANTS"

    # Dividends
    if "dividend" in kw or "dividende" in kw:
        return "DISC.DIVIDENDS"

    # Associates / Joint ventures (IAS 28)
    if any(w in kw for w in ["associate", "joint venture",
                             "assoziierte", "gemeinschaftsunternehmen"]):
        return "DISC.ASSOCIATES"

    # Impairment (IAS 36)
    if "impairment" in kw and any(w in kw for w in ["loss", "test", "recoverable"]):
        return "DISC.IMPAIRMENT"
    if "wertminderung" in kw and any(w in kw for w in ["test", "erzielbarer"]):
        return "DISC.IMPAIRMENT"

    # Depreciation/amortisation detail
    if any(w in kw for w in ["depreciation", "amortisation", "abschreibung"]):
        if "useful" in kw or "nutzungsdauer" in kw:
            return "DISC.PPE"

    # ── Column-header-driven classification ───────────────────────

    # Financing reconciliation (IAS 7.44)
    if any(w in col_kw for w in ["lease liabilities", "redeemable preference",
                                 "derivatives (assets)"]):
        return "DISC.BORROWINGS"

    # Fair value hierarchy
    if any(w in col_kw for w in ["level 1", "level 2", "level 3"]):
        return "DISC.FAIR_VALUE"
    if "carrying amount" in col_kw and "fair value" in col_kw:
        return "DISC.FAIR_VALUE"

    # NCI subsidiary detail (IFRS 12)
    if any(w in col_kw for w in ["intra-group", "individually immaterial"]):
        return "DISC.NCI"

    # Credit risk columns
    if any(w in col_kw for w in ["loss rate", "loss allowance", "credit-",
                                 "gross carrying amount", "ecl"]):
        return "DISC.CREDIT_RISK"
    if any(w in kw for w in ["past due", "low risk", "substandard", "doubtful"]):
        return "DISC.CREDIT_RISK"

    # Credit concentration
    if "carrying amount" in col_kw or "net carrying" in col_kw:
        if any(w in kw for w in ["country", "region", "wholesale",
                                 "retail", "end-user"]):
            return "DISC.CREDIT_RISK"

    # Hedge accounting detail
    if any(w in col_kw for w in ["hedge ineffectiveness", "hedging reserve",
                                 "costs of hedging"]):
        return "DISC.HEDGE"

    # FX / interest rate sensitivity
    if any(w in col_kw for w in ["strengthening", "weakening"]):
        return "DISC.FX_RISK"
    if any(w in col_kw for w in ["bp increase", "bp decrease", "100 bp"]):
        return "DISC.INTEREST_RATE_RISK"
    if any(w in col_kw for w in ["average rate", "spot rate"]):
        return "DISC.FX_RISK"

    # Lease maturity
    if any(w in kw for w in ["less than one year", "one to two years",
                             "two to three years", "more than five years",
                             "bis 1 jahr", "über 5 jahre"]):
        return "DISC.LEASES"

    # Revenue by geography/product in columns
    if any(w in col_kw for w in ["geographical", "product"]):
        if "revenue" in kw or "revenue" in col_kw:
            return "DISC.REVENUE"

    # Deferred tax movement columns
    if any(w in col_kw for w in ["recognised in oci", "recognised directly in equity",
                                 "acquired in business"]):
        return "DISC.TAX"

    # Tax losses
    if any(w in kw for w in ["deductible temporary", "tax losses", "never expire"]):
        return "DISC.TAX"

    # Segment detail via column headers
    if any(w in col_kw for w in ["segment total", "consolidated total",
                                 "reportable segment"]):
        return "DISC.SEGMENTS"
    if "inter-segment" in kw and ("revenue" in kw or "elimination" in kw):
        return "DISC.SEGMENTS"

    # Share options movement
    if any(w in kw for w in ["outstanding at 1 january", "exercised during",
                             "forfeited during", "granted during"]):
        return "DISC.SHARE_BASED"
    if any(w in col_kw for w in ["number of options", "weighted- average exercis"]):
        return "DISC.SHARE_BASED"

    # Investment property fair value
    if any(w in kw for w in ["income-generating property", "vacant property"]):
        return "DISC.INV_PROP"

    # Supplier finance arrangements
    if "supplier finance" in kw:
        return "DISC.BORROWINGS"

    # Goodwill CGU assumptions
    if any(w in kw for w in ["discount rate", "terminal value growth",
                             "ebitda growth rate"]):
        return "DISC.GOODWILL"

    # Equity investments detail
    if any(w in kw for w in ["equity securities", "consumer markets"]):
        return "DISC.FIN_INST"

    # Related party receivables
    if "trade receivables" in kw and "related parties" in kw:
        return "DISC.RELATED_PARTIES"

    # Restatement
    if "correction of error" in col_kw or "restatement" in col_kw:
        return "DISC.RESTATEMENT"

    # Biological assets (column)
    if any(w in col_kw for w in ["biological", "bearer", "consumable"]):
        return "DISC.BIOLOGICAL_ASSETS"

    # Dividends per share
    if any(w in kw for w in ["cents per qualifying", "cents per non-redeemable"]):
        return "DISC.DIVIDENDS"

    # Geography/NCA by geography
    if any(w in kw for w in ["country x", "all foreign countries",
                             "foreign countries"]):
        return "DISC.SEGMENTS"

    # Share-based payment liabilities
    if any(w in kw for w in ["carrying amount of liabilities for",
                             "intrinsic value of liabilities for"]):
        return "DISC.SHARE_BASED"

    # Biological asset fair value
    if any(w in kw for w in ["change in fair value (realised)",
                             "change in fair value (unrealised)"]):
        return "DISC.BIOLOGICAL_ASSETS"

    # PPE depreciation impact
    if "depreciation" in kw and "expense" in kw:
        return "DISC.PPE"

    # Investment at fair value (column)
    if any(w in col_kw for w in ["fair value at 31 december",
                                 "dividend income recognise"]):
        return "DISC.FIN_INST"

    # UGB Anlagenspiegel (fixed asset schedule)
    if any(w in kw for w in ["anlagenspiegel", "anschaffungskosten",
                             "kumulierte abschreibung"]):
        return "DISC.PPE"

    # UGB Beteiligungsliste (list of subsidiaries)
    if any(w in kw for w in ["beteiligungsliste", "anteil am kapital"]):
        return "DISC.ASSOCIATES"

    return None
