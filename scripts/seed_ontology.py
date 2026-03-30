#!/usr/bin/env python3
"""
seed_ontology.py — Load YAML concept definitions into Supabase Postgres.

Reads:
  concepts/*.yaml          → concepts table
  concepts/disc/*.yaml     → concepts table
  industry/*.yaml          → concepts table
  gaap/*.yaml              → concept_gaap_labels table
  aliases.yaml             → concept_aliases table

Usage:
  python scripts/seed_ontology.py [--dry-run] [--supabase-url URL] [--supabase-key KEY]

Environment variables (alternative to CLI flags):
  SUPABASE_URL, SUPABASE_SECRET_KEY
"""

import argparse
import os
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_concepts_from_yaml(yaml_path: Path) -> list[dict]:
    """Parse a concepts YAML file and return normalized concept dicts."""
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    if not data or "concepts" not in data:
        return []

    results = []
    for c in data["concepts"]:
        concept_id = c.get("id")
        if not concept_id:
            continue

        # Derive context from concept ID: FS.PNL.REVENUE → PNL, DISC.PPE.COST_OPENING → DISC.PPE
        parts = concept_id.split(".")
        if parts[0] == "FS" and len(parts) >= 3:
            # FS.PNL.REVENUE → PNL, FS.PNL.BANK.X → PNL
            context = parts[1]
        elif parts[0] == "DISC" and len(parts) >= 3:
            # DISC.PPE.COST_OPENING → DISC.PPE, DISC.BANK.ECL_STAGE1 → DISC.BANK
            context = f"{parts[0]}.{parts[1]}"
        else:
            context = parts[0]

        results.append({
            "id": concept_id,
            "label": c.get("label", concept_id),
            "context": context,
            "balance_type": c.get("balance_type"),
            "period_type": c.get("period_type"),
            "unit_type": c.get("unit_type"),
            "is_total": c.get("is_total", False),
            "mappable": c.get("mappable", True),
        })
    return results


def load_gaap_labels(yaml_path: Path) -> list[dict]:
    """Parse a GAAP labels YAML file (gaap/ugb.yaml etc)."""
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    if not data or "labels" not in data:
        return []

    gaap = yaml_path.stem.upper()  # ugb.yaml → UGB
    results = []
    for concept_id, label_info in data["labels"].items():
        if isinstance(label_info, dict):
            for lang, label_text in label_info.items():
                if lang == "ref":
                    continue
                results.append({
                    "concept_id": concept_id,
                    "gaap": gaap,
                    "label": label_text,
                    "language": lang,
                })
        elif isinstance(label_info, str):
            results.append({
                "concept_id": concept_id,
                "gaap": gaap,
                "label": label_info,
                "language": "en",
            })
    return results


def load_aliases(yaml_path: Path) -> list[dict]:
    """Parse aliases.yaml → concept_aliases rows."""
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    if not data or "aliases" not in data:
        return []

    results = []
    for concept_id, alias_list in data["aliases"].items():
        if not isinstance(alias_list, list):
            continue
        for alias in alias_list:
            # Heuristic: German aliases contain umlauts or common German words
            lang = "de" if any(c in alias for c in "äöüß") else "en"
            results.append({
                "concept_id": concept_id,
                "alias": alias,
                "language": lang,
            })
    return results


def collect_all(repo_root: Path) -> tuple[list[dict], list[dict], list[dict]]:
    """Collect all ontology data from YAML files."""
    concepts = []
    gaap_labels = []
    aliases = []

    # Primary statement concepts
    for yaml_file in sorted((repo_root / "concepts").glob("*.yaml")):
        concepts.extend(load_concepts_from_yaml(yaml_file))

    # Disclosure concepts
    disc_dir = repo_root / "concepts" / "disc"
    if disc_dir.exists():
        for yaml_file in sorted(disc_dir.glob("*.yaml")):
            concepts.extend(load_concepts_from_yaml(yaml_file))

    # Industry concepts
    industry_dir = repo_root / "industry"
    if industry_dir.exists():
        for yaml_file in sorted(industry_dir.glob("*.yaml")):
            concepts.extend(load_concepts_from_yaml(yaml_file))

    # GAAP labels
    gaap_dir = repo_root / "gaap"
    if gaap_dir.exists():
        for yaml_file in sorted(gaap_dir.glob("*.yaml")):
            if yaml_file.stat().st_size > 0:
                gaap_labels.extend(load_gaap_labels(yaml_file))

    # Aliases
    aliases_file = repo_root / "aliases.yaml"
    if aliases_file.exists():
        aliases = load_aliases(aliases_file)

    return concepts, gaap_labels, aliases


def seed_supabase(concepts: list[dict], gaap_labels: list[dict], aliases: list[dict],
                  supabase_url: str, supabase_key: str) -> dict:
    """Upsert ontology data into Supabase."""
    from supabase import create_client

    sb = create_client(supabase_url, supabase_key)
    stats = {"concepts": 0, "gaap_labels": 0, "aliases": 0, "skipped_labels": 0, "skipped_aliases": 0}

    # Upsert concepts
    if concepts:
        sb.table("concepts").upsert(concepts, on_conflict="id").execute()
        stats["concepts"] = len(concepts)

    # Collect valid concept IDs for FK validation
    valid_ids = {c["id"] for c in concepts}

    # Upsert GAAP labels (only for concepts that exist)
    valid_labels = [l for l in gaap_labels if l["concept_id"] in valid_ids]
    stats["skipped_labels"] = len(gaap_labels) - len(valid_labels)
    if valid_labels:
        sb.table("concept_gaap_labels").upsert(
            valid_labels,
            on_conflict="concept_id,gaap,label,language"
        ).execute()
        stats["gaap_labels"] = len(valid_labels)

    # Upsert aliases (only for concepts that exist)
    valid_aliases = [a for a in aliases if a["concept_id"] in valid_ids]
    stats["skipped_aliases"] = len(aliases) - len(valid_aliases)
    if valid_aliases:
        sb.table("concept_aliases").upsert(
            valid_aliases,
            on_conflict="concept_id,alias,language"
        ).execute()
        stats["aliases"] = len(valid_aliases)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Seed FOBE ontology into Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing to DB")
    parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    parser.add_argument("--supabase-key", default=os.environ.get("SUPABASE_SECRET_KEY"))
    args = parser.parse_args()

    concepts, gaap_labels, aliases = collect_all(REPO_ROOT)

    print(f"Collected from YAML files:")
    print(f"  Concepts:    {len(concepts)}")
    print(f"  GAAP labels: {len(gaap_labels)}")
    print(f"  Aliases:     {len(aliases)}")

    # Show context breakdown
    contexts = {}
    for c in concepts:
        ctx = c["context"]
        contexts[ctx] = contexts.get(ctx, 0) + 1
    print(f"\nConcepts by context:")
    for ctx in sorted(contexts):
        print(f"  {ctx}: {contexts[ctx]}")

    if args.dry_run:
        print("\n[dry-run] No data written.")
        return

    if not args.supabase_url or not args.supabase_key:
        print("\nError: --supabase-url and --supabase-key required (or set SUPABASE_URL / SUPABASE_SECRET_KEY)")
        sys.exit(1)

    stats = seed_supabase(concepts, gaap_labels, aliases, args.supabase_url, args.supabase_key)
    print(f"\nSeeded to Supabase:")
    print(f"  Concepts:       {stats['concepts']}")
    print(f"  GAAP labels:    {stats['gaap_labels']} (skipped {stats['skipped_labels']} with missing concept)")
    print(f"  Aliases:        {stats['aliases']} (skipped {stats['skipped_aliases']} with missing concept)")


if __name__ == "__main__":
    main()
