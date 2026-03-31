#!/usr/bin/env python3
"""
test_set.py -- Document sets for pipeline evaluation.

Defines cumulative tiers for both IFRS and UGB:
  IFRS20 ⊂ IFRS50 ⊂ IFRS100 ⊂ IFRS_ALL
  UGB20  ⊂ UGB50  ⊂ UGB100  ⊂ UGB200 ⊂ UGB_ALL
Each larger tier includes all documents from the smaller tier plus more.
"""

import json
from pathlib import Path

_FIXTURE_ROOT = Path(__file__).parent / "fixtures"

# ── IFRS documents ──────────────────────────────────────────

IFRS_TEST_SET = [
    "kapsch_2024",
    "omv_2024",
    "evn_2024",
    "facc_2024",
    "ca_immo_2024_en",
    "icbc_austria_2024",
    "kpmg_ifs_insurance_2024",
    "s_immo_2024",
    "pierer_mobility_2024",
    "marinomed_2024",
]

# ── UGB core (hand-picked, always included) ─────────────────

_UGB_CORE = [
    "mayr_melnhof_ugb_2024",        # 24pp
    "merkur_international_ugb_2023", # 14pp
    "voestalpine_ugb_2025",          # 33pp
    "pke_holding_ugb_2024",          # 25pp
    "gesiba_ugb_2022",               # 19pp
    "agrana_ugb_2025",               # 23pp
    "donau_chemie_ugb_2023",         # 22pp
    "bergbahn_kitzbuehel_ugb_2024",  # 19pp
    "evn_ugb_2025",                  # 33pp
    "kapsch_ugb_2025",               # 35pp
    "borealis_ag_ugb_2023",          # 33pp
    "marinomed_ugb_2024",            # 35pp
]


def _discover_ifrs_fixtures() -> list[str]:
    """Scan fixtures/ for all IFRS (non-UGB) directories, sorted alphabetically."""
    if not _FIXTURE_ROOT.is_dir():
        return []
    return sorted(
        d.name for d in _FIXTURE_ROOT.iterdir()
        if d.is_dir() and "ugb" not in d.name.lower()
        and (d / "table_graphs.json").exists()
        and d.name not in ("saldenliste_gmbh",)  # skip non-IFRS
    )


def _discover_ugb_fixtures() -> list[str]:
    """Scan fixtures/ for all UGB directories, sorted alphabetically."""
    if not _FIXTURE_ROOT.is_dir():
        return []
    return sorted(
        d.name for d in _FIXTURE_ROOT.iterdir()
        if d.is_dir() and "ugb" in d.name.lower()
        and (d / "table_graphs.json").exists()  # must have data
        and d.name not in ("_ugb_2023", "ag_ugb_2023", "aktiengesellschaft_ugb_2023")  # skip broken names
    )


def _build_cumulative(core: list[str], pool: list[str], size: int) -> list[str]:
    """Build a set of `size` documents: core first, then fill from pool."""
    seen = set(core)
    result = list(core)
    for doc_id in pool:
        if len(result) >= size:
            break
        if doc_id not in seen:
            result.append(doc_id)
            seen.add(doc_id)
    return result


# ── Build tiers lazily (computed once on first access) ──────

_all_ifrs: list[str] | None = None
_all_ugb: list[str] | None = None


def _ensure_ifrs():
    global _all_ifrs
    if _all_ifrs is None:
        _all_ifrs = _discover_ifrs_fixtures()


def _ensure_ugb():
    global _all_ugb
    if _all_ugb is None:
        _all_ugb = _discover_ugb_fixtures()


def ifrs_tier(size: int) -> list[str]:
    """Return a cumulative IFRS set of the given size (capped at available)."""
    _ensure_ifrs()
    return _build_cumulative(IFRS_TEST_SET, _all_ifrs, size)


def ugb_tier(size: int) -> list[str]:
    """Return a cumulative UGB set of the given size (capped at available)."""
    _ensure_ugb()
    return _build_cumulative(_UGB_CORE, _all_ugb, size)


# Named IFRS tiers
def IFRS20() -> list[str]:
    return ifrs_tier(20)

def IFRS50() -> list[str]:
    return ifrs_tier(50)

def IFRS100() -> list[str]:
    return ifrs_tier(100)

def IFRS200() -> list[str]:
    return ifrs_tier(200)

def IFRS_ALL() -> list[str]:
    _ensure_ifrs()
    return _build_cumulative(IFRS_TEST_SET, _all_ifrs, len(_all_ifrs) + len(IFRS_TEST_SET))


# Named UGB tiers
def UGB20() -> list[str]:
    return ugb_tier(20)

def UGB50() -> list[str]:
    return ugb_tier(50)

def UGB100() -> list[str]:
    return ugb_tier(100)

def UGB200() -> list[str]:
    return ugb_tier(200)

def UGB500() -> list[str]:
    return ugb_tier(500)

def UGB_ALL() -> list[str]:
    _ensure_ugb()
    return _build_cumulative(_UGB_CORE, _all_ugb, len(_all_ugb) + len(_UGB_CORE))


# ── Legacy compatibility ────────────────────────────────────

UGB_TEST_SET = _UGB_CORE  # original 12

TEST_SET = IFRS_TEST_SET + UGB_TEST_SET


def is_test_set(doc_id: str) -> bool:
    return doc_id in TEST_SET


def get_test_set_info() -> list[dict]:
    """Return info for each test set document."""
    results = []
    for doc_id in TEST_SET:
        fixture_dir = _FIXTURE_ROOT / doc_id
        tg_path = fixture_dir / "table_graphs.json"
        gt_path = fixture_dir / "ground_truth" / "toc.json"

        info = {
            "doc_id": doc_id,
            "gaap": "UGB" if "ugb" in doc_id else "IFRS",
            "has_fixture": tg_path.exists(),
            "has_ground_truth": gt_path.exists(),
            "table_count": 0,
        }

        if tg_path.exists():
            try:
                with open(tg_path) as f:
                    data = json.load(f)
                info["table_count"] = len(data.get("tables", []))
            except (json.JSONDecodeError, OSError):
                pass

        results.append(info)
    return results


if __name__ == "__main__":
    _ensure_ifrs()
    _ensure_ugb()
    total_ifrs = len(_all_ifrs)
    total_ugb = len(_all_ugb)
    print(f"Available IFRS fixtures: {total_ifrs}")
    print(f"Available UGB fixtures:  {total_ugb}")
    print()

    for name, tier_fn in [("IFRS20", IFRS20), ("IFRS50", IFRS50), ("IFRS100", IFRS100),
                           ("IFRS200", IFRS200), ("IFRS_ALL", IFRS_ALL)]:
        docs = tier_fn()
        print(f"{name:10s}: {len(docs)} documents")

    print()
    for name, tier_fn in [("UGB20", UGB20), ("UGB50", UGB50), ("UGB100", UGB100),
                           ("UGB200", UGB200), ("UGB500", UGB500), ("UGB_ALL", UGB_ALL)]:
        docs = tier_fn()
        print(f"{name:10s}: {len(docs)} documents")

    print(f"\nTEST_SET: {len(TEST_SET)} documents ({len(IFRS_TEST_SET)} IFRS, {len(UGB_TEST_SET)} UGB)")
    print()
    for info in get_test_set_info():
        status = []
        if info["has_fixture"]:
            status.append(f"{info['table_count']} tables")
        else:
            status.append("NO FIXTURE")
        if info["has_ground_truth"]:
            status.append("GT")
        print(f"  {info['doc_id']:40s} {info['gaap']:5s} {', '.join(status)}")
