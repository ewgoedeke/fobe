#!/usr/bin/env python3
"""
generate_document_meta.py — Extract document metadata from table_graphs.json.

Produces a document_meta.json per fixture containing:
  - Entity identity (name, jurisdiction, GAAP, industry)
  - Reporting framework (currency, unit, sign convention)
  - Period map (detected years/periods from column headers)
  - Document-specific axis members:
      AXIS.SEGMENT_DOC   — operating segments
      AXIS.PPE_CLASS_DOC — PPE classes
      AXIS.GEOGRAPHY_DOC — geographic regions

Entity-specific labels (segment names, PPE classes) are stored here,
NOT in aliases.yaml. This ensures they are applied consistently for the
same entity across periods and available for cross-entity comparison.

Usage:
    python3 eval/generate_document_meta.py <table_graphs.json> [--verbose]
    python3 eval/generate_document_meta.py --all
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ── Entity name extraction ────────────────────────────────────────

def _extract_entity_name(fixture_name: str) -> str:
    """Derive entity name from fixture directory name."""
    name = fixture_name.replace("_tables_stitched", "")
    # Remove year suffix
    name = re.sub(r'_(\d{4}(_\d{4})?)(_full)?$', '', name)
    # Remove format suffixes
    name = re.sub(r'_(ugb|ifrs|afr|en)$', '', name)
    # Clean up
    name = name.replace("_", " ").title()
    return name


# ── GAAP detection ────────────────────────────────────────────────

_GAAP_KEYWORDS = {
    "IFRS": ["ifrs", "international financial reporting", "ias "],
    "UGB": ["ugb", "§ 224", "§224", "§ 231", "§231", "§ 236", "unternehmensgesetzbuch",
            "jahresabschluss", "bilanz zum", "gewinn- und verlustrechnung für"],
    "HGB": ["hgb", "handelsgesetzbuch"],
    "US_GAAP": ["us gaap", "asc ", "fasb"],
}


def _detect_gaap(tables: list[dict], fixture_name: str) -> str:
    """Detect reporting framework from labels and fixture name."""
    # Fixture name hints
    if "ugb" in fixture_name.lower():
        return "UGB"

    # Scan first 20 tables for GAAP keywords
    text = ""
    for t in tables[:20]:
        for r in t.get("rows", [])[:10]:
            text += " " + r.get("label", "").lower()
        for c in t.get("columns", []):
            text += " " + c.get("headerLabel", "").lower()

    scores = {}
    for gaap, keywords in _GAAP_KEYWORDS.items():
        scores[gaap] = sum(1 for kw in keywords if kw in text)

    if scores:
        best = max(scores, key=scores.get)
        if scores[best] > 0:
            return best

    return "IFRS"  # default for Austrian listed companies


# ── Currency / Unit detection ─────────────────────────────────────

def _detect_currency_unit(tables: list[dict]) -> tuple[str, str]:
    """Extract primary currency and unit from table metadata."""
    currencies = Counter()
    units = Counter()

    for t in tables:
        m = t.get("metadata", {})
        c = m.get("detectedCurrency")
        u = m.get("detectedUnit")
        if c and c != "None":
            currencies[c] += 1
        if u and u != "None" and u not in ("UNIT.PERCENT", "UNIT.PER_SHARE"):
            units[u] += 1

    currency = currencies.most_common(1)[0][0] if currencies else "CURRENCY.EUR"
    unit = units.most_common(1)[0][0] if units else "UNIT.THOUSANDS"
    return currency, unit


# ── Period detection ──────────────────────────────────────────────

def _detect_periods(tables: list[dict]) -> dict[str, dict]:
    """Extract period definitions from column headers."""
    periods = {}
    for t in tables:
        for c in t.get("columns", []):
            axes = c.get("detectedAxes", {})
            period_key = axes.get("AXIS.PERIOD")
            if not period_key:
                continue
            header = c.get("headerLabel", "")

            # Extract year from header
            year_match = re.search(r'20\d{2}', header)
            year = int(year_match.group()) if year_match else None

            if period_key not in periods:
                periods[period_key] = {
                    "label": header.strip(),
                    "year": year,
                }

    return periods


# ── Axis member extraction ────────────────────────────────────────

def _extract_segment_members(tables: list[dict]) -> dict[str, str]:
    """Extract operating segment names from segment tables."""
    segments = {}
    seg_counter = 0

    for t in tables:
        sc = t.get("metadata", {}).get("statementComponent")
        if sc != "DISC.SEGMENTS":
            continue

        # Segments can be in column headers (multi-segment tables)
        for c in t.get("columns", []):
            header = c.get("headerLabel", "").strip()
            if not header or c.get("role") != "VALUE":
                continue
            # Strip year/period suffixes
            seg_name = re.sub(r'\.\s*\d{4}$', '', header).strip()
            seg_name = re.sub(r'\s*\(restated\).*$', '', seg_name, flags=re.IGNORECASE).strip()
            # Skip years, periods, generic headers, metrics, and accounting labels
            seg_lower = seg_name.lower()
            skip = seg_lower in (
                "total", "note", "in thousands of eur", "in millions of eur",
                "adjustments", "consolidated totals", "eliminations",
                "group", "consolidated", "unallocated",
                "2025", "2024", "2023", "2022", "2021",
            ) or re.match(r'^\d{4}', seg_name) or "restated" in seg_lower
            # Filter out metric/KPI columns and non-segment headers
            skip = skip or any(w in seg_lower for w in [
                "change", "delta", "in %", "margin", "growth",
                "variance", "prior year", "vs.", "yoy",
                "total segment", "summe", " total",
                "ebitda", "ebit", "revenue", "profit", "loss",
                "eur million", "eur thousand", "in eur", "in teur",
                "management report", "group management",
            ])
            # Skip if contains a pipe with year (e.g. "AMAG total | 2024")
            skip = skip or bool(re.search(r'\|\s*\d{4}', seg_name))
            # Skip entity name + "total" patterns
            skip = skip or "total" in seg_lower
            # Max label length: real segments are concise names
            skip = skip or len(seg_name) > 60
            if seg_name and len(seg_name) > 3 and not skip:
                if seg_name not in segments.values():
                    seg_counter += 1
                    segments[f"SEG.{seg_counter:03d}"] = seg_name

        # Segments can also be in row labels for geographic/product breakdown
        # but only if the table has segment-named columns already found
        # (avoids picking up random data rows as segments)

    return segments


def _extract_ppe_classes(tables: list[dict]) -> dict[str, str]:
    """Extract PPE class names from PPE rollforward tables."""
    classes = {}
    cls_counter = 0

    for t in tables:
        sc = t.get("metadata", {}).get("statementComponent")
        if sc != "DISC.PPE":
            continue

        # PPE classes are typically in column headers
        for c in t.get("columns", []):
            header = c.get("headerLabel", "").strip()
            if not header or c.get("role") != "VALUE":
                continue
            header = re.sub(r'\.\s*\d{4}$', '', header).strip()
            hdr_lower = header.lower()
            # Normalize soft hyphens and line breaks
            hdr_norm = re.sub(r'[-\u00ad]\s*', '', hdr_lower)
            skip_ppe = hdr_lower in (
                "total", "note", "in thousands of eur", "in millions of eur",
            ) or re.match(r'^\d{4}', header) or "restated" in hdr_lower
            # Skip date-only headers (e.g. "30.09", "31.12.2024")
            skip_ppe = skip_ppe or bool(re.match(r'^[\d.]+(\s*(eur|teur))?$', hdr_lower.strip()))
            # Filter out movement/non-class labels (check normalized form too)
            movement_keywords = [
                "before tax", "net of tax", "tax (expense", "later",
                # Movement keywords (German + English)
                "zugänge", "abgänge", "abschreibung", "zuschreibung",
                "umbuchung", "umgliederung", "nutzungsdauer", "buchwert",
                "anschaffungskosten", "kumulierte", "herstellungskosten",
                "additions", "disposals", "depreciation", "amortisation",
                "impairment", "transfers", "carrying amount", "cost",
                "accumulated", "reclassification",
                # Position indicators
                "stand ", "bw ",
            ]
            skip_ppe = skip_ppe or any(w in hdr_lower for w in movement_keywords)
            skip_ppe = skip_ppe or any(w.replace('-', '') in hdr_norm for w in movement_keywords)
            # Max length filter for PPE class names
            skip_ppe = skip_ppe or len(header) > 60
            if header and len(header) > 3 and not skip_ppe:
                if header not in classes.values():
                    cls_counter += 1
                    classes[f"PPEDOC.{cls_counter:03d}"] = header

    return classes


def _extract_geography(tables: list[dict]) -> dict[str, str]:
    """Extract geographic region names from revenue/segment tables."""
    regions = {}
    reg_counter = 0

    for t in tables:
        sc = t.get("metadata", {}).get("statementComponent", "")
        if sc not in ("DISC.SEGMENTS", "DISC.REVENUE"):
            continue

        for r in t.get("rows", []):
            label = r.get("label", "").strip()
            if not label or len(label) > 40:
                continue  # skip paragraph-length labels
            label_lower = label.lower()
            # Geography patterns: country names, region names
            # Only match if the label IS a geography (not contains one as substring)
            geo_keywords = [
                "europe", "america", "asia", "africa", "middle east",
                "austria", "germany", "uk", "usa", "china", "japan",
                "domestic", "foreign", "rest of",
                "österreich", "deutschland", "europa",
                "north america", "south america", "latin america",
                "apac", "emea", "americas", "cee",
            ]
            is_geo = any(w in label_lower for w in geo_keywords)
            # Reject labels that are clearly not geography names
            if is_geo and any(w in label_lower for w in [
                "margin", "indicator", "revenue from", "income from",
                "balance", "total", "note",
            ]):
                is_geo = False
            if is_geo:
                if label not in regions.values():
                    reg_counter += 1
                    regions[f"GEO.{reg_counter:03d}"] = label

    return regions


# ── Industry detection ────────────────────────────────────────────

_INDUSTRY_KEYWORDS = {
    "BANKING": ["net interest income", "credit risk", "loan", "deposit",
                "cet1", "tier 1", "zinserträge", "kreditrisiko"],
    "INSURANCE": ["insurance revenue", "insurance service", "csr", "csm",
                  "versicherung", "prämien"],
    "UTILITIES": ["electricity", "generation", "grid", "strom", "energie",
                  "erzeugung", "netz"],
    "TELECOM": ["subscriber", "arpu", "mobile", "broadband", "teilnehmer"],
    "REAL_ESTATE": ["investment property", "rental income", "occupancy",
                    "immobilien", "mieterlöse"],
    "OIL_GAS": ["exploration", "refining", "upstream", "downstream",
                "barrel", "boe"],
    "MANUFACTURING": ["production", "plant", "raw material", "inventory",
                      "produktion", "rohstoff"],
    "CONSTRUCTION": ["contract", "project", "backlog", "auftrag",
                     "bauauftrag"],
    "AVIATION": ["flight", "passenger", "aircraft", "flug"],
    "PHARMA": ["clinical", "pipeline", "drug", "patent"],
}


def _detect_industry(tables: list[dict], fixture_name: str) -> str:
    """Detect industry from table content."""
    text = ""
    for t in tables[:30]:
        for r in t.get("rows", [])[:20]:
            text += " " + r.get("label", "").lower()

    scores = {}
    for industry, keywords in _INDUSTRY_KEYWORDS.items():
        scores[industry] = sum(1 for kw in keywords if kw in text)

    if scores:
        best = max(scores, key=scores.get)
        if scores[best] >= 2:
            return best

    return "MANUFACTURING"  # default for Austrian industrial companies


# ── Main ──────────────────────────────────────────────────────────

def generate_meta(tg_path: str, verbose: bool = False) -> dict:
    """Generate basic document metadata (entity, GAAP, currency, industry).

    This extracts metadata that does NOT depend on validated classifications.
    Axis members (segments, PPE classes, geography) are deferred to
    extract_axes() which should run after the Stage 2 gate passes.
    """
    with open(tg_path) as f:
        data = json.load(f)
    tables = data.get("tables", [])

    fixture_name = Path(tg_path).parent.name
    entity_name = _extract_entity_name(fixture_name)
    gaap = _detect_gaap(tables, fixture_name)
    currency, unit = _detect_currency_unit(tables)
    periods = _detect_periods(tables)
    industry = _detect_industry(tables, fixture_name)

    meta = {
        "document_id": fixture_name,
        "entity_name": entity_name,
        "gaap": gaap,
        "industry": industry,
        "jurisdiction": "AT",  # all current fixtures are Austrian
        "currency": currency,
        "unit": unit,
        "periods": periods,
        "document_axes": {},
    }

    if verbose:
        print(f"  Entity: {entity_name}")
        print(f"  GAAP: {gaap}, Industry: {industry}")
        print(f"  Currency: {currency}, Unit: {unit}")
        print(f"  Periods: {list(periods.keys())}")

    return meta


def extract_axes(tables: list[dict], meta: dict,
                 verbose: bool = False) -> dict:
    """Extract axis members from validated/classified tables.

    Should be called AFTER the Stage 2 gate passes so that axis members
    are only extracted from correctly-classified tables. Mutates meta
    in place and returns it.
    """
    segments = _extract_segment_members(tables)
    ppe_classes = _extract_ppe_classes(tables)
    geography = _extract_geography(tables)

    if segments:
        meta["document_axes"]["AXIS.SEGMENT_DOC"] = segments
    if ppe_classes:
        meta["document_axes"]["AXIS.PPE_CLASS_DOC"] = ppe_classes
    if geography:
        meta["document_axes"]["AXIS.GEOGRAPHY_DOC"] = geography

    if verbose:
        if segments:
            print(f"  Segments ({len(segments)}): {list(segments.values())[:5]}")
        if ppe_classes:
            print(f"  PPE classes ({len(ppe_classes)}): {list(ppe_classes.values())[:5]}")
        if geography:
            print(f"  Geography ({len(geography)}): {list(geography.values())[:5]}")

    return meta


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    dry_run = "--dry-run" in sys.argv

    if "--all" in sys.argv:
        paths = sorted(Path("eval/fixtures").glob("*/table_graphs.json"))
    else:
        paths = [Path(a) for a in sys.argv[1:] if not a.startswith("-")]

    for path in paths:
        if not path.exists():
            print(f"Error: {path} not found")
            continue

        name = path.parent.name
        print(f"\n{name}:")
        meta = generate_meta(str(path), verbose=verbose)
        # When run standalone, extract axes immediately (no gate)
        with open(path) as f:
            tables = json.load(f).get("tables", [])
        extract_axes(tables, meta, verbose=verbose)

        out_path = path.parent / "document_meta.json"
        if not dry_run:
            with open(out_path, "w") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
            print(f"  Written: {out_path}")
        else:
            print(f"  [DRY RUN] Would write: {out_path}")
            if verbose:
                print(json.dumps(meta, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
