#!/usr/bin/env python3
"""
section_types.py -- Single source of truth for document section hierarchy.

All section type constants, groupings, colors, and rank classes live here.
Frontend mirror: explorer/frontend/src/components/section-hierarchy.js
"""

from __future__ import annotations

# ── Floating types ──────────────────────────────────────────────────────────
# These can appear at any level and inherit context from their position.

FLOATING_TYPES = {"FRONT_MATTER", "TOC"}

# ── Section groups ──────────────────────────────────────────────────────────
# Groups are inferred from surrounding content types, never annotated directly.

SECTION_GROUPS = {
    "GENERAL_REPORTING": {
        "label": "General Reporting",
        "types": [
            "MANAGEMENT_REPORT", "ESG", "CORPORATE_GOVERNANCE",
            "RISK_REPORT", "REMUNERATION_REPORT", "SUPERVISORY_BOARD",
            "AUDITOR_REPORT", "RESPONSIBILITY_STATEMENT", "OTHER",
        ],
    },
    "PRIMARY_FINANCIALS": {
        "label": "Primary Financial Statements",
        "types": ["PNL", "SFP", "OCI", "CFS", "SOCIE"],
    },
    "NOTES": {
        "label": "Notes to the Financial Statements",
        "types": [],  # NOTES is both the group and its sole content type
    },
    "APPENDIX": {
        "label": "Appendix",
        "types": [],  # APPENDIX is both the group and its sole content type
    },
}

# Reverse lookup: content type -> group key
TYPE_TO_GROUP: dict[str, str] = {}
for _group_key, _group_def in SECTION_GROUPS.items():
    for _t in _group_def["types"]:
        TYPE_TO_GROUP[_t] = _group_key
# Self-referencing groups
TYPE_TO_GROUP["NOTES"] = "NOTES"
TYPE_TO_GROUP["APPENDIX"] = "APPENDIX"

# ── Primary statements ──────────────────────────────────────────────────────

PRIMARY_STATEMENTS = frozenset({"PNL", "SFP", "OCI", "CFS", "SOCIE"})

# ── Rank classes (page classifier) ─────────────────────────────────────────

RANK_CLASSES = ["TOC", "PNL", "SFP", "OCI", "CFS", "SOCIE", "NOTES", "OTHER"]

# Map from full section type to rank class (rank_pages.py classifier buckets)
TYPE_TO_RANK_CLASS: dict[str, str] = {
    "TOC": "TOC", "PNL": "PNL", "SFP": "SFP", "OCI": "OCI",
    "CFS": "CFS", "SOCIE": "SOCIE", "NOTES": "NOTES",
    "FRONT_MATTER": "OTHER", "MANAGEMENT_REPORT": "OTHER",
    "AUDITOR_REPORT": "OTHER", "SUPERVISORY_BOARD": "OTHER",
    "APPENDIX": "OTHER", "OTHER": "OTHER",
    "CORPORATE_GOVERNANCE": "OTHER", "ESG": "OTHER",
    "RISK_REPORT": "OTHER", "REMUNERATION_REPORT": "OTHER",
    "RESPONSIBILITY_STATEMENT": "OTHER",
}

# ── All section types with metadata ────────────────────────────────────────

ALL_SECTION_TYPES: dict[str, dict] = {
    # Floating
    "FRONT_MATTER":           {"label": "Front Matter",              "bg": "bg-slate-500/15",   "text": "text-slate-400",  "hex": "#94a3b8"},
    "TOC":                    {"label": "TOC",                       "bg": "bg-slate-500/15",   "text": "text-slate-400",  "hex": "#94a3b8"},
    # Primary financials
    "PNL":                    {"label": "Income Statement (PNL)",    "bg": "bg-red-500/15",     "text": "text-red-400",    "hex": "#f87171"},
    "SFP":                    {"label": "Balance Sheet (SFP)",       "bg": "bg-orange-500/15",  "text": "text-orange-400", "hex": "#fb923c"},
    "OCI":                    {"label": "Other Comprehensive Income","bg": "bg-yellow-500/15",  "text": "text-yellow-400", "hex": "#facc15"},
    "CFS":                    {"label": "Cash Flow Statement",       "bg": "bg-green-500/15",   "text": "text-green-400",  "hex": "#4ade80"},
    "SOCIE":                  {"label": "Changes in Equity",         "bg": "bg-teal-500/15",    "text": "text-teal-400",   "hex": "#2dd4bf"},
    # General reporting
    "MANAGEMENT_REPORT":      {"label": "Management Report",         "bg": "bg-sky-500/15",     "text": "text-sky-400",    "hex": "#38bdf8"},
    "ESG":                    {"label": "ESG / Sustainability",      "bg": "bg-emerald-500/15", "text": "text-emerald-400","hex": "#34d399"},
    "CORPORATE_GOVERNANCE":   {"label": "Corporate Governance",      "bg": "bg-blue-500/15",    "text": "text-blue-400",   "hex": "#60a5fa"},
    "RISK_REPORT":            {"label": "Risk Report",               "bg": "bg-rose-500/15",    "text": "text-rose-400",   "hex": "#fb7185"},
    "REMUNERATION_REPORT":    {"label": "Remuneration Report",       "bg": "bg-pink-500/15",    "text": "text-pink-400",   "hex": "#f472b6"},
    "SUPERVISORY_BOARD":      {"label": "Supervisory Board Report",  "bg": "bg-fuchsia-500/15", "text": "text-fuchsia-400","hex": "#e879f9"},
    "AUDITOR_REPORT":         {"label": "Auditor Report",            "bg": "bg-violet-500/15",  "text": "text-violet-400", "hex": "#a78bfa"},
    "RESPONSIBILITY_STATEMENT":{"label": "Responsibility Statement", "bg": "bg-indigo-500/15",  "text": "text-indigo-400", "hex": "#818cf8"},
    # Notes & appendix
    "NOTES":                  {"label": "Notes",                     "bg": "bg-purple-500/15",  "text": "text-purple-400", "hex": "#c084fc"},
    "APPENDIX":               {"label": "Appendix",                  "bg": "bg-cyan-500/15",    "text": "text-cyan-400",   "hex": "#22d3ee"},
    # Catch-all
    "OTHER":                  {"label": "Other",                     "bg": "bg-zinc-500/15",    "text": "text-zinc-500",   "hex": "#71717a"},
}

# Ordered list for UI display
TYPE_ORDER = [
    "PNL", "SFP", "OCI", "CFS", "SOCIE",
    "FRONT_MATTER", "TOC", "NOTES",
    "MANAGEMENT_REPORT", "ESG", "CORPORATE_GOVERNANCE",
    "RISK_REPORT", "REMUNERATION_REPORT", "SUPERVISORY_BOARD",
    "AUDITOR_REPORT", "RESPONSIBILITY_STATEMENT",
    "APPENDIX", "OTHER",
]

# ── Helpers ─────────────────────────────────────────────────────────────────

def type_label(section_type: str) -> str:
    """Get human-readable label for a section type."""
    info = ALL_SECTION_TYPES.get(section_type)
    return info["label"] if info else section_type


def type_color(section_type: str) -> str:
    """Get hex color for a section type."""
    info = ALL_SECTION_TYPES.get(section_type)
    return info["hex"] if info else "#71717a"


def is_floating(section_type: str) -> bool:
    """Whether this type inherits context from surrounding sections."""
    return section_type in FLOATING_TYPES


def group_for_type(section_type: str) -> str | None:
    """Get the group key for a section type, or None if floating/unknown."""
    return TYPE_TO_GROUP.get(section_type)
