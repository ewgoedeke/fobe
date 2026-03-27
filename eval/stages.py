#!/usr/bin/env python3
"""
stages.py -- Stage implementations for the gated FOBE pipeline.

Each stage wraps existing eval modules and adds a quality gate.
Stages mutate DocumentState in place and return GateResult from gate().
"""

from __future__ import annotations

import copy
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline import DocumentState, GateResult, PipelineConfig

# Lazy imports to avoid circular deps — done inside methods.

PRIMARY_STATEMENTS = {"PNL", "SFP", "OCI", "CFS", "SOCIE"}


# ── Stage 1: Load Tables ────────────────────────────────────────

class Stage1_LoadTables:
    name = "stage1"

    def execute(self, state: DocumentState, config: PipelineConfig) -> None:
        with open(state.tg_path) as f:
            data = json.load(f)
        state.tables = data.get("tables", [])

    def gate(self, state: DocumentState, config: PipelineConfig) -> GateResult:
        count = len(state.tables)
        passed = count >= 1
        findings = [] if passed else [
            {"type": "no_tables", "detail": f"File contains {count} tables"}
        ]
        return GateResult(
            passed=passed,
            stage=self.name,
            findings=findings,
            metrics={"table_count": count},
        )


# ── Stage 2: Structure Extraction ───────────────────────────────

class Stage2_StructureExtraction:
    name = "stage2"

    def execute(self, state: DocumentState, config: PipelineConfig) -> None:
        from classify_tables import classify_document
        from generate_document_meta import generate_meta

        # Classification — dry_run=False when reclassifying so the file is
        # updated on disk for downstream stages that re-read it.
        dry_run = not config.reclassify
        classification = classify_document(
            state.tg_path, dry_run=dry_run,
            verbose=config.verbose, use_llm=config.use_llm,
            reclassify=config.reclassify,
        )
        state.classification = classification

        # Reload tables after classification (classify_document may have
        # modified them in memory if dry_run=False, but with dry_run=True
        # we need to re-read to get the classified version)
        # Actually, classify_document with dry_run=True does NOT write, so
        # the on-disk file is unchanged. We need to classify in-memory.
        # For now, re-read and classify non-dry to get classified tables.
        # TODO: refactor classify_document to accept tables directly.
        #
        # Workaround: classify again non-dry so on-disk file is updated,
        # then re-read. This is what run_eval.py currently does (it calls
        # classify dry_run=True, then analyze_document reads the file).
        # The current flow: classify_document dry_run=True returns stats,
        # but does NOT update tables. analyze_document then calls
        # structural_cascade which reads the file again.
        # We'll follow the same pattern: keep classification stats, let
        # downstream stages re-read the file.

        # Meta extraction
        meta = generate_meta(state.tg_path, verbose=config.verbose)
        state.meta = meta

        # Collect per-table classification for gate check
        with open(state.tg_path) as f:
            data = json.load(f)
        state.tables = data.get("tables", [])

    def gate(self, state: DocumentState, config: PipelineConfig) -> GateResult:
        # Count distinct statement types across classified tables
        classified_types: Counter = Counter()
        unclassified = 0
        for table in state.tables:
            sc = table.get("metadata", {}).get("statementComponent")
            if sc:
                classified_types[sc] += 1
            else:
                unclassified += 1

        primary_types = {t for t in classified_types if t in PRIMARY_STATEMENTS}
        distinct_primary = len(primary_types)
        has_pnl = "PNL" in primary_types
        has_sfp = "SFP" in primary_types

        min_distinct = config.threshold("stage2", "min_distinct_statements") or 2
        require_pnl = config.threshold("stage2", "require_pnl") or False
        require_sfp = config.threshold("stage2", "require_sfp") or False
        max_per_primary = config.threshold("stage2", "max_per_primary_type") or 8

        # Per-type counts for primary statements
        primary_counts = {t: classified_types[t] for t in PRIMARY_STATEMENTS
                          if classified_types[t] > 0}

        findings = []
        passed = True

        if distinct_primary < min_distinct:
            passed = False
            findings.append({
                "type": "toc_unresolved",
                "detail": (f"Only {distinct_primary} primary statement types "
                           f"found: {sorted(primary_types)}. "
                           f"Need >= {min_distinct}."),
            })

        if require_pnl and not has_pnl:
            passed = False
            findings.append({
                "type": "missing_pnl",
                "detail": "No table classified as PNL",
            })

        if require_sfp and not has_sfp:
            passed = False
            findings.append({
                "type": "missing_sfp",
                "detail": "No table classified as SFP",
            })

        # Check for inflated primary statement counts — a real annual report
        # has 1-2 tables per primary type, never 15+ SFP or 20+ PNL.
        inflated = {t: n for t, n in primary_counts.items()
                    if n > max_per_primary}
        if inflated:
            passed = False
            for stmt_type, count in inflated.items():
                findings.append({
                    "type": "inflated_primary",
                    "detail": (f"{count} tables classified as {stmt_type} "
                               f"(max {max_per_primary}). "
                               f"Classification is likely broken."),
                })

        return GateResult(
            passed=passed,
            stage=self.name,
            findings=findings,
            metrics={
                "distinct_primary_statements": distinct_primary,
                "primary_types": sorted(primary_types),
                "primary_counts": primary_counts,
                "classified_by_type": dict(classified_types.most_common()),
                "unclassified": unclassified,
                "total_tables": len(state.tables),
            },
        )


# ── Stage 3: Numeric Conversion ─────────────────────────────────

class Stage3_NumericConversion:
    name = "stage3"

    def execute(self, state: DocumentState, config: PipelineConfig) -> None:
        # Docling already populates parsedValue for most cells.
        # This stage validates and fills gaps.
        for table in state.tables:
            for row in table.get("rows", []):
                for cell in row.get("cells", []):
                    if cell.get("parsedValue") is not None:
                        continue
                    text = (cell.get("text") or "").strip()
                    if not text:
                        continue
                    parsed = _try_parse_value(text)
                    if parsed is not None:
                        cell["parsedValue"] = parsed

    def gate(self, state: DocumentState, config: PipelineConfig) -> GateResult:
        total_value_cells = 0
        parsed_cells = 0

        for table in state.tables:
            value_col_indices = {
                c["colIdx"] for c in table.get("columns", [])
                if c.get("role") == "VALUE"
            }
            for row in table.get("rows", []):
                for cell in row.get("cells", []):
                    if cell.get("colIdx") in value_col_indices:
                        text = (cell.get("text") or "").strip()
                        if not text:
                            continue  # skip legitimately empty cells
                        total_value_cells += 1
                        if cell.get("parsedValue") is not None:
                            parsed_cells += 1

        parse_rate = parsed_cells / total_value_cells if total_value_cells else 1.0
        min_rate = config.threshold("stage3", "min_parse_rate") or 0.80
        passed = parse_rate >= min_rate

        findings = []
        if not passed:
            findings.append({
                "type": "low_parse_rate",
                "detail": (f"Parse rate {parse_rate:.1%} < {min_rate:.0%} "
                           f"({parsed_cells}/{total_value_cells} value cells)"),
            })

        return GateResult(
            passed=passed,
            stage=self.name,
            findings=findings,
            metrics={
                "total_value_cells": total_value_cells,
                "parsed_cells": parsed_cells,
                "parse_rate": round(parse_rate, 4),
            },
        )


def _try_parse_value(text: str) -> float | None:
    """Attempt to parse a text value that Docling missed."""
    s = text.strip()
    if not s or s in ("-", "–", "—", "n/a", "n.a.", "N/A"):
        return 0.0 if s in ("-", "–", "—") else None

    # Handle parenthetical negatives: (123) → -123
    neg = False
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
        neg = True
    elif s.startswith("-") or s.startswith("−"):
        s = s[1:].strip()
        neg = True

    # Remove thousand separators and normalize decimal
    # European: 1.234.567,89 → 1234567.89
    # English:  1,234,567.89 → 1234567.89
    if "," in s and "." in s:
        # Determine which is the decimal separator (last one)
        last_comma = s.rfind(",")
        last_dot = s.rfind(".")
        if last_comma > last_dot:
            # European: dots are thousands, comma is decimal
            s = s.replace(".", "").replace(",", ".")
        else:
            # English: commas are thousands, dot is decimal
            s = s.replace(",", "")
    elif "," in s:
        # Could be European decimal or English thousands
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            # Likely decimal: 123,45
            s = s.replace(",", ".")
        else:
            # Likely thousands: 1,234
            s = s.replace(",", "")
    elif "." in s:
        parts = s.split(".")
        if len(parts) > 2:
            # Multiple dots = European thousands: 1.234.567
            s = s.replace(".", "")

    # Remove any remaining whitespace, % signs
    s = s.replace(" ", "").replace("\u00a0", "").rstrip("%")

    try:
        val = float(s)
        return -val if neg else val
    except ValueError:
        return None


# ── Stage 4: Table Structure Extraction ──────────────────────────

class Stage4_TableStructure:
    name = "stage4"

    def execute(self, state: DocumentState, config: PipelineConfig) -> None:
        from structural_inference import cascade as structural_cascade

        # Run structural inference on a copy (don't modify state.tables yet,
        # let cascade build the hierarchy)
        tables_copy = copy.deepcopy(state.tables)
        iterations, tags = structural_cascade(
            tables_copy, config.ontology_root,
            verbose=config.verbose,
        )
        # Store results for downstream use
        state._structural_iterations = iterations
        state._structural_tags = tags
        # Update tables with hierarchy info from the cascade
        state.tables = tables_copy

    def gate(self, state: DocumentState, config: PipelineConfig) -> GateResult:
        # Check parent-child summation consistency
        from table_arithmetic import pass0_table_arithmetic

        results = pass0_table_arithmetic(state.tables)
        total_checks = len(results)
        passed_checks = sum(1 for r in results if r.passed)

        consistency_rate = passed_checks / total_checks if total_checks else 1.0
        min_rate = config.threshold("stage4", "min_consistency_rate") or 0.70
        passed = consistency_rate >= min_rate

        findings = []
        if not passed:
            findings.append({
                "type": "low_consistency",
                "detail": (f"Hierarchy consistency {consistency_rate:.1%} < "
                           f"{min_rate:.0%} ({passed_checks}/{total_checks})"),
            })

        return GateResult(
            passed=passed,
            stage=self.name,
            findings=findings,
            metrics={
                "summation_checks": total_checks,
                "summation_passed": passed_checks,
                "consistency_rate": round(consistency_rate, 4),
                "structural_iterations": getattr(state, "_structural_iterations", 0),
                "structural_tags": len(getattr(state, "_structural_tags", [])),
            },
        )


# ── Stage 5: Fact Tagging ────────────────────────────────────────

class Stage5_FactTagging:
    name = "stage5"

    def execute(self, state: DocumentState, config: PipelineConfig) -> None:
        from pretag_all import pretag_document
        from structural_inference import cascade as structural_cascade
        from run_corpus import analyze_document

        # Step 1: Label-based pre-tagging (writes tags to disk)
        pretag_document(state.tg_path, dry_run=False)

        # Step 2: Structural inference on re-read tables
        with open(state.tg_path) as f:
            tables = json.load(f).get("tables", [])
        tables_copy = copy.deepcopy(tables)
        structural_cascade(tables_copy, config.ontology_root,
                           verbose=config.verbose)

        # Step 3: LLM tagging with GAAP filter (#49)
        if config.use_llm:
            from llm_tagger import tag_document, _build_concept_index
            concept_index = _build_concept_index(config.ontology_root)
            gaap = state.meta.get("gaap") if state.meta else None
            if config.verbose:
                print(f"  LLM tagger: gaap={gaap}",
                      file=__import__("sys").stderr)
            tag_document(
                state.tg_path,
                concept_index,
                gaap=gaap,
                verbose=config.verbose,
            )

        # Step 4: Analyze results (facts, consistency, scoring)
        result = analyze_document(state.tg_path, config.ontology_root)

        # Store tagging stats
        state.tagging = {
            "name": result["name"],
            "tables": result["tables"],
            "total_rows": result["total_rows"],
            "data_rows": result["data_rows"],
            "pretagged_rows": result["pretagged_rows"],
            "label_matched_rows": result["label_matched_rows"],
            "structural_inferred": result["structural_inferred"],
            "structural_by_rule": result["structural_by_rule"],
            "structural_iterations": result["structural_iterations"],
            "indexed_facts": result["indexed_facts"],
            "unique_concepts": result["unique_concepts"],
            "concept_list": result["concept_list"],
            "classified_tables": result["classified_tables"],
            "fact_sources": result["fact_sources"],
        }

        # Store consistency and corroboration for Stage 6
        state._analysis_result = result

    def gate(self, state: DocumentState, config: PipelineConfig) -> GateResult:
        data_rows = state.tagging.get("data_rows", 0)
        pretagged = state.tagging.get("pretagged_rows", 0)

        tag_rate = pretagged / data_rows if data_rows else 0.0
        min_rate = config.threshold("stage5", "min_tag_rate") or 0.50
        passed = tag_rate >= min_rate

        findings = []
        if not passed:
            findings.append({
                "type": "low_tag_rate",
                "detail": (f"Tag rate {tag_rate:.1%} < {min_rate:.0%} "
                           f"({pretagged}/{data_rows} data rows)"),
            })

        return GateResult(
            passed=passed,
            stage=self.name,
            findings=findings,
            metrics={
                "data_rows": data_rows,
                "pretagged_rows": pretagged,
                "tag_rate": round(tag_rate, 4),
                "structural_inferred": state.tagging.get("structural_inferred", 0),
                "indexed_facts": state.tagging.get("indexed_facts", 0),
                "unique_concepts": state.tagging.get("unique_concepts", 0),
            },
        )


# ── Stage 6: Validation & Scoring ───────────────────────────────

class Stage6_Validation:
    name = "stage6"

    def execute(self, state: DocumentState, config: PipelineConfig) -> None:
        from check_classification import check_table

        result = getattr(state, "_analysis_result", None)
        if result is None:
            # Stage 5 didn't run or failed — run analysis now
            from run_corpus import analyze_document
            result = analyze_document(state.tg_path, config.ontology_root)

        # Classification checks
        all_issues = []
        for table in state.tables:
            all_issues.extend(check_table(table))
        by_severity = Counter(i["severity"] for i in all_issues)

        state.consistency = {
            "name": result["name"],
            "findings_count": result["findings_count"],
            "by_category": result["by_category"],
            "by_edge": result["by_edge"],
            "classification_check": {
                "tables_checked": len(state.tables),
                "issues": all_issues,
                "summary": dict(by_severity),
            },
            "findings": result["findings"],
        }

        state.corroboration = {
            "name": result["name"],
            "corroboration": result["corroboration"],
            "fact_scores": result["fact_scores"],
            "confirmed_concepts": result["confirmed_concepts"],
            "contradicted_concepts": result["contradicted_concepts"],
            "unconfirmed_concepts": result["unconfirmed_concepts"],
        }

    def gate(self, state: DocumentState, config: PipelineConfig) -> GateResult:
        # Terminal stage — always passes
        fact_scores = state.corroboration.get("fact_scores", {})
        return GateResult(
            passed=True,
            stage=self.name,
            findings=[],
            metrics={
                "findings_count": state.consistency.get("findings_count", 0),
                "fact_scores": fact_scores,
                "by_category": state.consistency.get("by_category", {}),
            },
        )


# ── Factory ──────────────────────────────────────────────────────

def build_default_stages() -> list:
    """Create the default 6-stage pipeline."""
    return [
        Stage1_LoadTables(),
        Stage2_StructureExtraction(),
        Stage3_NumericConversion(),
        Stage4_TableStructure(),
        Stage5_FactTagging(),
        Stage6_Validation(),
    ]
