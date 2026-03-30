#!/usr/bin/env python3
"""
test_set.py -- 20-document ground truth test set for pipeline evaluation.

10 IFRS (from existing fixtures) + 10 UGB (from sources/ugb/).
"""

# IFRS documents (existing fixtures)
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

# UGB documents (from sources/ugb/, need Docling parse except andritz)
UGB_TEST_SET = [
    "mayr_melnhof_ugb_2024",
    "merkur_international_ugb_2023",
    "verbund_ugb_2024",
    "voestalpine_ugb_2025",
    "strabag_ugb_2024",
    "pke_holding_ugb_2024",
    "gesiba_ugb_2022",
    "flughafen_wien_ugb_2024",
    "agrana_ugb_2025",
    "andritz_ugb_2024",
    "donau_chemie_ugb_2023",
    "bergbahn_kitzbuehel_ugb_2024",
]

TEST_SET = IFRS_TEST_SET + UGB_TEST_SET


def is_test_set(doc_id: str) -> bool:
    return doc_id in TEST_SET


def get_test_set_info() -> list[dict]:
    """Return info for each test set document."""
    import json
    from pathlib import Path

    fixture_root = Path(__file__).parent / "fixtures"
    results = []
    for doc_id in TEST_SET:
        fixture_dir = fixture_root / doc_id
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
    print(f"Test set: {len(TEST_SET)} documents ({len(IFRS_TEST_SET)} IFRS, {len(UGB_TEST_SET)} UGB)\n")
    for info in get_test_set_info():
        status = []
        if info["has_fixture"]:
            status.append(f"{info['table_count']} tables")
        else:
            status.append("NO FIXTURE")
        if info["has_ground_truth"]:
            status.append("GT")
        print(f"  {info['doc_id']:40s} {info['gaap']:5s} {', '.join(status)}")
