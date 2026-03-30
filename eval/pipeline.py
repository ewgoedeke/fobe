#!/usr/bin/env python3
"""
pipeline.py -- Gated pipeline framework for FOBE document processing.

Orchestrates 6 stages with quality gates between them. If a gate fails,
processing halts for that document and findings are persisted.

Data classes:
    GateResult    -- outcome of a gate check (passed/failed + metrics + findings)
    DocumentState -- mutable state bag passed through stages
    PipelineConfig -- configurable thresholds, stage selection, flags

Stage protocol:
    Each stage has execute(state) and gate(state) -> GateResult.
"""

from __future__ import annotations

import json
import os
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


# ── Data classes ─────────────────────────────────────────────────

@dataclass
class GateResult:
    """Outcome of a stage gate check."""
    passed: bool
    stage: str
    findings: list[dict] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentState:
    """Mutable state bag passed through pipeline stages."""
    tg_path: str
    doc_name: str = ""
    tables: list[dict] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    classification: dict[str, Any] = field(default_factory=dict)
    tagging: dict[str, Any] = field(default_factory=dict)
    consistency: dict[str, Any] = field(default_factory=dict)
    corroboration: dict[str, Any] = field(default_factory=dict)
    review_needed: dict[str, Any] | None = None
    gate_results: dict[str, GateResult] = field(default_factory=dict)
    stage_results: list[dict] = field(default_factory=list)
    status: str = "running"          # running | completed | halted_at_gate | error
    halted_at: str | None = None
    error: str | None = None
    error_traceback: str | None = None

    def __post_init__(self):
        if not self.doc_name:
            self.doc_name = Path(self.tg_path).parent.name


@dataclass
class PipelineConfig:
    """Pipeline configuration: stage selection, gate thresholds, flags."""
    stages_to_run: list[str] | None = None  # None = all stages
    gate_thresholds: dict[str, dict] = field(default_factory=dict)
    use_llm: bool = True
    reclassify: bool = False
    use_ground_truth: bool = False
    verbose: bool = False
    output_dir: str | None = None
    ontology_root: str = ""

    # Default gate thresholds (overridden by gate_thresholds)
    # Tuned on 39-doc corpus (27032026EVAL007): aim for ≥80% pass rate.
    # Stage 5 tag_rate is the main bottleneck (median ~28% without LLM
    # classification); will tighten as classification coverage improves.
    DEFAULT_THRESHOLDS = {
        "stage2": {
            "min_distinct_statements": 1,
            "require_pnl": False,
            "require_sfp": False,
            "max_per_primary_type": 8,
        },
        "stage3": {
            "min_parse_rate": 0.60,
        },
        "stage4": {
            "min_consistency_rate": 0.50,
        },
        "stage5": {
            "min_tag_rate": 0.10,
        },
    }

    def threshold(self, stage: str, key: str) -> Any:
        """Get a gate threshold, with user overrides taking precedence."""
        overrides = self.gate_thresholds.get(stage, {})
        if key in overrides:
            return overrides[key]
        defaults = self.DEFAULT_THRESHOLDS.get(stage, {})
        return defaults.get(key)


# ── Stage protocol ───────────────────────────────────────────────

class Stage(Protocol):
    """Protocol for pipeline stages."""
    name: str

    def execute(self, state: DocumentState, config: PipelineConfig) -> None:
        """Run the stage, mutating state in place."""
        ...

    def gate(self, state: DocumentState, config: PipelineConfig) -> GateResult:
        """Evaluate the quality gate after execution."""
        ...


# ── Pipeline ─────────────────────────────────────────────────────

class Pipeline:
    """Orchestrates stages with quality gates."""

    def __init__(self, config: PipelineConfig, stages: list[Stage] | None = None):
        self.config = config
        self.stages: list[Stage] = stages or []

    def add_stage(self, stage: Stage) -> None:
        self.stages.append(stage)

    def run(self, tg_path: str) -> DocumentState:
        """Run the pipeline on a single document. Returns final state."""
        state = DocumentState(tg_path=tg_path)
        stages_run = []

        for stage in self.stages:
            # Skip stages not in the run list
            if (self.config.stages_to_run is not None
                    and stage.name not in self.config.stages_to_run):
                continue

            t0 = time.monotonic()
            try:
                stage.execute(state, self.config)
                gate_result = stage.gate(state, self.config)
            except Exception as e:
                state.status = "error"
                state.error = str(e)
                state.error_traceback = traceback.format_exc()
                stages_run.append(stage.name)
                break

            elapsed = time.monotonic() - t0
            state.gate_results[stage.name] = gate_result
            state.stage_results.append({
                "stage": stage.name,
                "elapsed_seconds": round(elapsed, 2),
                "gate_passed": gate_result.passed,
            })
            stages_run.append(stage.name)

            if self.config.verbose:
                status = "PASS" if gate_result.passed else "HALT"
                print(f"  [{stage.name}] {status}  "
                      f"({elapsed:.1f}s)  {gate_result.metrics}",
                      file=__import__("sys").stderr)

            if not gate_result.passed:
                state.status = "halted_at_gate"
                state.halted_at = stage.name
                break
        else:
            # All stages completed successfully
            state.status = "completed"

        return state

    def persist(self, state: DocumentState, doc_dir: str) -> None:
        """Write pipeline results to the run output directory."""
        os.makedirs(doc_dir, exist_ok=True)

        # Always write pipeline.json
        pipeline_data = {
            "status": state.status,
            "halted_at": state.halted_at,
            "stages_run": [sr["stage"] for sr in state.stage_results],
            "stage_results": state.stage_results,
            "gate_results": {
                name: {
                    "passed": gr.passed,
                    "metrics": gr.metrics,
                    "findings": gr.findings,
                }
                for name, gr in state.gate_results.items()
            },
        }
        if state.error:
            pipeline_data["error"] = state.error
            pipeline_data["error_traceback"] = state.error_traceback

        _write_json(os.path.join(doc_dir, "pipeline.json"), pipeline_data)

        # Write per-concern files if they exist
        if state.meta:
            _write_json(os.path.join(doc_dir, "meta.json"), state.meta)
        if state.classification:
            _write_json(os.path.join(doc_dir, "classification.json"),
                        state.classification)
        if state.tagging:
            _write_json(os.path.join(doc_dir, "tagging.json"), state.tagging)
        if state.consistency:
            _write_json(os.path.join(doc_dir, "consistency.json"),
                        state.consistency)
        if state.corroboration:
            _write_json(os.path.join(doc_dir, "corroboration.json"),
                        state.corroboration)

        # Write error.json on failure
        if state.status == "error":
            _write_json(os.path.join(doc_dir, "error.json"), {
                "document": state.doc_name,
                "path": state.tg_path,
                "error": state.error,
                "traceback": state.error_traceback,
            })


def _write_json(path: str, data: Any) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
