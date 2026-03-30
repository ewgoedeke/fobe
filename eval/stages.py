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
        from human_review import load_human_review, apply_overrides, is_review_stale

        # Check for ground truth TOC — if present and config says use it,
        # apply ground truth page map before classification
        gt_applied = False
        if getattr(config, "use_ground_truth", False):
            from ground_truth import load_toc_gt, toc_gt_to_page_map
            from classify_tables import _classify_by_page
            fixture_dir = str(Path(state.tg_path).parent)
            gt = load_toc_gt(fixture_dir)
            if gt and gt.sections:
                page_map = toc_gt_to_page_map(gt)
                with open(state.tg_path) as f:
                    data = json.load(f)
                tables = data.get("tables", [])
                classified = 0
                for t in tables:
                    result = _classify_by_page(t, page_map)
                    if result:
                        t.setdefault("metadata", {})["statementComponent"] = result
                        t["metadata"]["classification_method"] = "ground_truth"
                        t["metadata"]["classification_confidence"] = "high"
                        classified += 1
                with open(state.tg_path, "w") as f:
                    json.dump(data, f, indent=2, default=str)
                gt_applied = True
                if config.verbose:
                    print(f"  [stage2] Applied ground truth TOC: {classified}/{len(tables)} "
                          f"tables classified from {len(page_map)} page entries",
                          file=__import__("sys").stderr)

        # Classification — dry_run=False when reclassifying OR when no tables
        # have existing classification (first run on new fixtures).
        has_existing = any(
            t.get("metadata", {}).get("statementComponent")
            for t in state.tables
        )
        dry_run = not config.reclassify and has_existing
        classification = classify_document(
            state.tg_path, dry_run=dry_run,
            verbose=config.verbose, use_llm=config.use_llm,
            reclassify=config.reclassify if not gt_applied else False,
        )
        state.classification = classification

        # Meta extraction
        meta = generate_meta(state.tg_path, verbose=config.verbose)
        state.meta = meta

        # Collect per-table classification for gate check
        with open(state.tg_path) as f:
            data = json.load(f)
        state.tables = data.get("tables", [])

        # Apply human review overrides if available
        fixture_dir = str(Path(state.tg_path).parent)
        review = load_human_review(fixture_dir)
        if review:
            stale, missing = is_review_stale(review, state.tables)
            if stale and config.verbose:
                print(f"  [stage2] WARNING: human_review.json references "
                      f"missing tableIds: {missing}", file=__import__("sys").stderr)

            state.tables, apply_stats = apply_overrides(state.tables, review)
            state.classification["human_review_applied"] = apply_stats
            state.classification["human_review_stale"] = stale

            # Write updated tables back to disk for downstream stages
            data["tables"] = state.tables
            with open(state.tg_path, "w") as f:
                json.dump(data, f, indent=2, default=str)

            if config.verbose:
                total = apply_stats.get("total_applied", 0)
                print(f"  [stage2] Applied {total} human review overrides "
                      f"({apply_stats})", file=__import__("sys").stderr)

            # Store gate_override flag for gate() to check
            state.classification["_gate_override"] = review.get(
                "gate_override", False)

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

        # Check for gate_override from human review
        gate_override = state.classification.get("_gate_override", False)
        human_review_applied = "human_review_applied" in state.classification

        if gate_override and not passed:
            passed = True
            findings.append({
                "type": "gate_override",
                "detail": "Gate forced to pass by human_review.json gate_override=true",
            })

        metrics = {
            "distinct_primary_statements": distinct_primary,
            "primary_types": sorted(primary_types),
            "primary_counts": primary_counts,
            "classified_by_type": dict(classified_types.most_common()),
            "unclassified": unclassified,
            "total_tables": len(state.tables),
        }

        # Generate review manifest if gate fails
        if not passed:
            from human_review import (generate_review_manifest,
                                      write_review_manifest)
            from classify_tables import _detect_toc

            # Get TOC info for the manifest
            toc_info = None
            try:
                toc_info = _detect_toc(state.tables)
            except Exception:
                pass

            manifest = generate_review_manifest(
                state.tables,
                # Pass a temporary GateResult with current findings
                type("_GR", (), {"findings": findings, "metrics": metrics})(),
                toc_info,
                state.doc_name,
            )
            fixture_dir = str(Path(state.tg_path).parent)
            manifest_path = write_review_manifest(fixture_dir, manifest)
            state.review_needed = manifest

            metrics["needs_review"] = True

            if human_review_applied:
                findings.append({
                    "type": "review_insufficient",
                    "detail": ("human_review.json was applied but gate still "
                               f"fails. Updated review_needed.json at "
                               f"{manifest_path}"),
                })
            else:
                findings.append({
                    "type": "needs_review",
                    "detail": f"Review manifest written to {manifest_path}",
                })

        # Axis extraction moved to Stage 4 (post-hierarchy) where
        # cross-column arithmetic can validate segment/geo columns.

        return GateResult(
            passed=passed,
            stage=self.name,
            findings=findings,
            metrics=metrics,
        )


# ── Stage 3: Numeric Conversion ─────────────────────────────────

class Stage3_NumericConversion:
    name = "stage3"

    # Scale multipliers for detected units
    _SCALE_FACTORS = {
        "UNIT.THOUSANDS": 1_000,
        "UNIT.MILLIONS": 1_000_000,
        "UNIT.BILLIONS": 1_000_000_000,
    }

    def execute(self, state: DocumentState, config: PipelineConfig) -> None:
        for table in state.tables:
            # Step 1: Fill gaps in parsedValue
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

            # Step 2: Detect and store scale factor per table
            unit = table.get("metadata", {}).get("detectedUnit")
            scale = self._SCALE_FACTORS.get(unit, 1)
            if scale != 1:
                table.setdefault("metadata", {})["scaleFactor"] = scale

            # Step 3: Detect per-column scale from header text
            # (handles mixed scales within one table, e.g. "in TEUR" vs "in %")
            col_scales = {}
            for col in table.get("columns", []):
                if col.get("role") != "VALUE":
                    continue
                header = (col.get("headerLabel") or "").lower()
                col_scale = _detect_header_scale(header)
                if col_scale:
                    col_scales[col["colIdx"]] = col_scale

            # Step 4: Apply scaledValue = parsedValue * scale
            # Use per-column scale if available, else table-level scale
            value_col_indices = {
                c["colIdx"] for c in table.get("columns", [])
                if c.get("role") == "VALUE"
            }
            for row in table.get("rows", []):
                for cell in row.get("cells", []):
                    pv = cell.get("parsedValue")
                    if pv is None:
                        continue
                    ci = cell.get("colIdx")
                    if ci not in value_col_indices:
                        continue
                    # Per-column scale takes precedence over table-level
                    effective_scale = col_scales.get(ci, scale)
                    # Don't scale percentages or per-share values
                    col_unit = _col_unit(table, ci)
                    if col_unit in ("UNIT.PERCENT", "UNIT.PER_SHARE"):
                        effective_scale = 1
                    if effective_scale != 1:
                        cell["scaledValue"] = pv * effective_scale
                    else:
                        cell["scaledValue"] = pv

        # Step 5: Structural quality assessment
        from table_quality import assess_structure
        assess_structure(state.tables, verbose=config.verbose)

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


import re as _re

_HEADER_SCALE_PATTERNS = [
    (_re.compile(r"(?i)\b(teur|t\s*eur|in\s+tausend|in\s+thousands|tsd)\b"), 1_000),
    (_re.compile(r"(?i)\b(meur|m\s*eur|mio|in\s+million|in\s+millions)\b"), 1_000_000),
    (_re.compile(r"(?i)\b(mrd|in\s+billion|in\s+billions)\b"), 1_000_000_000),
]


def _detect_header_scale(header: str) -> int | None:
    """Detect scale factor from column header text."""
    for pattern, scale in _HEADER_SCALE_PATTERNS:
        if pattern.search(header):
            return scale
    return None


def _col_unit(table: dict, col_idx: int) -> str | None:
    """Get the detected unit for a specific column, if any."""
    for col in table.get("columns", []):
        if col.get("colIdx") == col_idx:
            axes = col.get("detectedAxes", {})
            return axes.get("AXIS.VALUE_TYPE") or None
    # Fall back to table-level unit
    return table.get("metadata", {}).get("detectedUnit")


# ── Stage 4: Table Structure Extraction ──────────────────────────

class Stage4_TableStructure:
    name = "stage4"

    def execute(self, state: DocumentState, config: PipelineConfig) -> None:
        from structural_inference import cascade as structural_cascade
        from table_stitching import stitch_tables

        # Step 4a: Multipage table stitching
        merged = stitch_tables(state.tables, verbose=config.verbose)
        state._stitched_count = merged

        # Step 4b: Run structural inference (hierarchy + summation detection)
        tables_copy = copy.deepcopy(state.tables)
        iterations, tags = structural_cascade(
            tables_copy, config.ontology_root,
            verbose=config.verbose,
        )
        state._structural_iterations = iterations
        state._structural_tags = tags
        state.tables = tables_copy

        # Step 4c: Hierarchy-informed axis extraction
        # Now that hierarchy is built, extract axes with validation
        from generate_document_meta import extract_axes
        extract_axes(state.tables, state.meta, verbose=config.verbose)

        # Apply cross-column arithmetic to validate segment columns
        from column_arithmetic import classify_columns
        seg_axes = state.meta.get("document_axes", {}).get("segments", {})
        if seg_axes:
            for table in state.tables:
                sc = table.get("metadata", {}).get("statementComponent") or ""
                if "SEGMENT" in sc:
                    result = classify_columns(table)
                    if result.additive_cols:
                        table.setdefault("metadata", {})["columnClassification"] = {
                            "additive": result.additive_cols,
                            "total": result.total_col,
                            "derived": result.derived_cols,
                            "confidence": result.confidence,
                        }

    def gate(self, state: DocumentState, config: PipelineConfig) -> GateResult:
        # Hierarchy quality scoring
        from table_quality import assess_hierarchy
        assess_hierarchy(state.tables)

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
                "stitched_tables": getattr(state, "_stitched_count", 0),
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

        # Step 3: LLM tagging (API) or prompt generation (IDE)
        from llm_tagger import _build_concept_index
        concept_index = _build_concept_index(config.ontology_root)
        gaap = state.meta.get("gaap") if state.meta else None

        if config.use_llm:
            # Direct API call (batch automation)
            from llm_tagger import tag_document
            if config.verbose:
                print(f"  LLM tagger: gaap={gaap}",
                      file=__import__("sys").stderr)
            tag_document(
                state.tg_path,
                concept_index,
                gaap=gaap,
                verbose=config.verbose,
            )
        else:
            # Generate prompt files for IDE sessions (cost-free)
            from prompt_generator import generate_document_prompts
            prompt_dir = config.output_dir
            prompts = generate_document_prompts(
                state.tg_path, concept_index, gaap=gaap,
                output_dir=prompt_dir,
            )
            if prompts and config.verbose:
                print(f"  Generated {len(prompts)} prompt file(s) for IDE tagging",
                      file=__import__("sys").stderr)

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
