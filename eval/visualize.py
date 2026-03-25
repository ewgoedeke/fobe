#!/usr/bin/env python3
"""
visualize.py — Generate Mermaid diagrams of ontology reporting hierarchies.

Shows how facts flow from primary statements through disclosure notes,
with corroboration checks at each junction.

Usage:
    python3 eval/visualize.py ppe          # PPE hierarchy
    python3 eval/visualize.py revenue      # Revenue hierarchy
    python3 eval/visualize.py full         # Full statement map
    python3 eval/visualize.py <doc.json>   # Scored document overlay
"""

import json
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_ontology(root: str) -> dict:
    """Load concepts, counterparts, and axes."""
    concepts = {}
    for f in sorted(Path(root, "concepts").glob("*.yaml")) + sorted(Path(root, "concepts/disc").glob("*.yaml")):
        data = yaml.safe_load(open(f))
        if data and "concepts" in data:
            for c in data["concepts"]:
                concepts[c["id"]] = c

    cp = yaml.safe_load(open(Path(root, "counterparts.yaml")))
    return {"concepts": concepts, "counterparts": cp}


def mermaid_ppe(onto: dict) -> str:
    """Generate Mermaid diagram for PPE reporting hierarchy."""
    lines = [
        "graph TD",
        '    classDef face fill:#2563eb,color:white,stroke:none',
        '    classDef note fill:#7c3aed,color:white,stroke:none',
        '    classDef roll fill:#059669,color:white,stroke:none',
        '    classDef check fill:#f59e0b,color:black,stroke:none,stroke-dasharray:5',
        '    classDef axis fill:#6b7280,color:white,stroke:none',
        "",
        "    %% Primary statement",
        '    SFP_PPE["FS.SFP.PPE_NET<br/>Property, plant and equipment<br/><i>SFP face line</i>"]:::face',
        "",
        "    %% Checks",
        '    CHK_FACE_NOTE{{"note = face?"}}:::check',
        '    CHK_DISAGG{{"SUM(classes) = total?"}}:::check',
        '    CHK_ROLL_COST{{"opening + movements = closing?"}}:::check',
        '    CHK_ROLL_DEPR{{"opening + movements = closing?"}}:::check',
        '    CHK_NET{{"cost − depr = carrying?"}}:::check',
        "",
        "    %% Note total",
        '    PPE_CARRYING["DISC.PPE.CARRYING_AMOUNT<br/>Carrying amount (net)<br/><i>Note total per class</i>"]:::note',
        "",
        "    %% PPE classes (axis)",
        '    AXIS["AXIS.PPE_CLASS_DOC<br/>Land & buildings | Plant | Fixtures | Under construction"]:::axis',
        "",
        "    %% Rollforward — Cost",
        '    COST_OPEN["COST_OPENING<br/>Cost — opening"]:::roll',
        '    COST_ADD["COST_ADDITIONS<br/>+ Additions"]:::roll',
        '    COST_BCA["COST_BCA<br/>+ Business combinations"]:::roll',
        '    COST_DISP["COST_DISPOSALS<br/>− Disposals"]:::roll',
        '    COST_FX["COST_FX_EFFECT<br/>± FX effect"]:::roll',
        '    COST_CLOSE["COST_CLOSING<br/>Cost — closing"]:::roll',
        "",
        "    %% Rollforward — Accumulated depreciation",
        '    DEPR_OPEN["ACCUM_DEPR_OPENING<br/>Accum depr — opening"]:::roll',
        '    DEPR_CHG["ACCUM_DEPR_CHARGE<br/>+ Charge for year"]:::roll',
        '    DEPR_IMP["ACCUM_DEPR_IMPAIRMENT<br/>+ Impairment"]:::roll',
        '    DEPR_DISP["ACCUM_DEPR_DISPOSALS<br/>− Disposals"]:::roll',
        '    DEPR_FX["ACCUM_DEPR_FX_EFFECT<br/>± FX effect"]:::roll',
        '    DEPR_CLOSE["ACCUM_DEPR_CLOSING<br/>Accum depr — closing"]:::roll',
        "",
        "    %% PNL cross-reference",
        '    PNL_DA["FS.PNL.DEPRECIATION_AMORTISATION<br/>D&A on PNL face"]:::face',
        "",
        "    %% Edges",
        "    SFP_PPE --> CHK_FACE_NOTE --> PPE_CARRYING",
        "    PPE_CARRYING --> AXIS",
        "    AXIS --> CHK_DISAGG",
        "    CHK_DISAGG --> PPE_CARRYING",
        "",
        "    PPE_CARRYING --> CHK_NET",
        "    COST_CLOSE --> CHK_NET",
        "    DEPR_CLOSE --> CHK_NET",
        "",
        "    COST_OPEN --> CHK_ROLL_COST",
        "    COST_ADD --> CHK_ROLL_COST",
        "    COST_BCA --> CHK_ROLL_COST",
        "    COST_DISP --> CHK_ROLL_COST",
        "    COST_FX --> CHK_ROLL_COST",
        "    CHK_ROLL_COST --> COST_CLOSE",
        "",
        "    DEPR_OPEN --> CHK_ROLL_DEPR",
        "    DEPR_CHG --> CHK_ROLL_DEPR",
        "    DEPR_IMP --> CHK_ROLL_DEPR",
        "    DEPR_DISP --> CHK_ROLL_DEPR",
        "    DEPR_FX --> CHK_ROLL_DEPR",
        "    CHK_ROLL_DEPR --> DEPR_CLOSE",
        "",
        "    DEPR_CHG -.->|cross-ref| PNL_DA",
    ]
    return "\n".join(lines)


def mermaid_revenue(onto: dict) -> str:
    """Generate Mermaid diagram for Revenue reporting hierarchy."""
    lines = [
        "graph TD",
        '    classDef face fill:#2563eb,color:white,stroke:none',
        '    classDef note fill:#7c3aed,color:white,stroke:none',
        '    classDef seg fill:#dc2626,color:white,stroke:none',
        '    classDef check fill:#f59e0b,color:black,stroke:none',
        '    classDef ic fill:#ef4444,color:white,stroke:none',
        "",
        '    PNL_REV["FS.PNL.REVENUE<br/>Revenue<br/><i>PNL face</i>"]:::face',
        "",
        "    %% Segment disaggregation",
        '    CHK_SEG{{"face = SUM(external) + IC?"}}:::check',
        '    SEG_EXT["DISC.SEGMENTS.EXTERNAL_REVENUE<br/>External revenue per segment"]:::seg',
        '    SEG_IC["DISC.SEGMENTS.INTERSEGMENT_REVENUE<br/>Intercompany revenue"]:::ic',
        '    SEG_TOTAL["DISC.SEGMENTS.TOTAL_REVENUE<br/>Segment total"]:::seg',
        "",
        "    %% IFRS 15 disaggregation",
        '    CHK_TIMING{{"face ≥ SUM(timing)?"}}:::check',
        '    REV_POINT["DISC.REVENUE.GOODS_TRANSFERRED_POINT<br/>Point in time"]:::note',
        '    REV_OVER["DISC.REVENUE.GOODS_TRANSFERRED_OVERTIME<br/>Over time"]:::note',
        '    REV_TOTAL["DISC.REVENUE.TOTAL_REVENUE<br/>IFRS 15 total"]:::note',
        "",
        "    %% Note-to-face",
        '    CHK_NOTE{{"face ≥ note total?<br/><i>IFRS 15 scope</i>"}}:::check',
        "",
        "    %% CFS cross-reference",
        '    CFS_PROFIT["FS.CFS.PROFIT_FOR_PERIOD<br/>CFS starting point"]:::face',
        '    PNL_NP["FS.PNL.NET_PROFIT<br/>Net profit"]:::face',
        "",
        "    %% Edges",
        "    PNL_REV --> CHK_SEG",
        "    CHK_SEG --> SEG_EXT",
        "    CHK_SEG --> SEG_IC",
        "    SEG_EXT --> SEG_TOTAL",
        "    SEG_IC --> SEG_TOTAL",
        "",
        "    PNL_REV --> CHK_NOTE --> REV_TOTAL",
        "    REV_TOTAL --> CHK_TIMING",
        "    REV_POINT --> CHK_TIMING",
        "    REV_OVER --> CHK_TIMING",
        "",
        "    PNL_NP -.->|cross-statement tie| CFS_PROFIT",
    ]
    return "\n".join(lines)


def mermaid_full(onto: dict) -> str:
    """Generate Mermaid diagram showing all cross-statement ties."""
    lines = [
        "graph LR",
        '    classDef pnl fill:#2563eb,color:white,stroke:none',
        '    classDef sfp fill:#059669,color:white,stroke:none',
        '    classDef oci fill:#7c3aed,color:white,stroke:none',
        '    classDef cfs fill:#dc2626,color:white,stroke:none',
        '    classDef socie fill:#ea580c,color:white,stroke:none',
        '    classDef check fill:#f59e0b,color:black,stroke:none',
        '    classDef disc fill:#6b7280,color:white,stroke:none',
        "",
        "    subgraph PNL[Income Statement]",
        '        REV["Revenue"]:::pnl',
        '        COGS["Cost of sales"]:::pnl',
        '        GP["Gross profit"]:::pnl',
        '        OPEX["Operating expenses"]:::pnl',
        '        EBIT["Operating profit"]:::pnl',
        '        FIN["Financial result"]:::pnl',
        '        PBT["Profit before tax"]:::pnl',
        '        TAX["Income tax"]:::pnl',
        '        NP["Net profit"]:::pnl',
        "    end",
        "",
        "    subgraph OCI[Other Comprehensive Income]",
        '        OCI_ITEMS["OCI items"]:::oci',
        '        TOTAL_OCI["Total OCI"]:::oci',
        '        TCI["Total comprehensive income"]:::oci',
        "    end",
        "",
        "    subgraph SOCIE[Changes in Equity]",
        '        SOCIE_OPEN["Opening equity"]:::socie',
        '        SOCIE_PROFIT["Profit for period"]:::socie',
        '        SOCIE_OCI["OCI for period"]:::socie',
        '        SOCIE_DIV["Dividends"]:::socie',
        '        SOCIE_CLOSE["Closing equity"]:::socie',
        "    end",
        "",
        "    subgraph SFP[Balance Sheet]",
        '        ASSETS["Total assets"]:::sfp',
        '        EQUITY["Total equity"]:::sfp',
        '        LIAB["Total liabilities"]:::sfp',
        '        EQ_LIAB["Equity + Liabilities"]:::sfp',
        "    end",
        "",
        "    subgraph CFS[Cash Flow Statement]",
        '        CFS_PROFIT["Profit for period"]:::cfs',
        '        CFS_OPS["Operating cash"]:::cfs',
        '        CFS_INV["Investing cash"]:::cfs',
        '        CFS_FIN["Financing cash"]:::cfs',
        '        CFS_CLOSE["Closing cash"]:::cfs',
        "    end",
        "",
        "    subgraph DISC[Disclosure Notes]",
        '        DISC_SEG["Segments"]:::disc',
        '        DISC_PPE["PPE rollforward"]:::disc',
        '        DISC_TAX["Tax note"]:::disc',
        '        DISC_REV["Revenue note"]:::disc',
        "    end",
        "",
        "    %% Summation trees (within statements)",
        "    REV --> GP",
        "    COGS --> GP",
        "    GP --> EBIT",
        "    OPEX --> EBIT",
        "    EBIT --> PBT",
        "    FIN --> PBT",
        "    PBT --> NP",
        "    TAX --> NP",
        "    NP --> TCI",
        "    TOTAL_OCI --> TCI",
        "    ASSETS ===|must equal| EQ_LIAB",
        "",
        "    %% Cross-statement ties",
        '    NP ==>|"equals"| SOCIE_PROFIT',
        '    TOTAL_OCI ==>|"equals"| SOCIE_OCI',
        '    SOCIE_CLOSE ==>|"equals"| EQUITY',
        '    CFS_CLOSE ==>|"equals"| SFP_CASH',
        '    NP ==>|"equals"| CFS_PROFIT',
        "",
        '    SFP_CASH["Cash (SFP)"]:::sfp',
        "",
        "    %% Note-to-face ties",
        '    REV -.->|"face ≥ note"| DISC_REV',
        '    REV -.->|"face = Σseg"| DISC_SEG',
        '    TAX -.->|"face = note"| DISC_TAX',
        '    ASSETS -.->|"face = Σclass"| DISC_PPE',
    ]
    return "\n".join(lines)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    onto = load_ontology(root)

    if len(sys.argv) < 2:
        print("Usage: python3 eval/visualize.py [ppe|revenue|full]")
        sys.exit(1)

    view = sys.argv[1].lower()
    if view == "ppe":
        diagram = mermaid_ppe(onto)
    elif view == "revenue":
        diagram = mermaid_revenue(onto)
    elif view == "full":
        diagram = mermaid_full(onto)
    else:
        print(f"Unknown view: {view}")
        sys.exit(1)

    print(diagram)

    # Also write to file
    out_path = os.path.join(root, "docs", f"diagram_{view}.md")
    with open(out_path, "w") as f:
        f.write(f"# {view.upper()} Reporting Hierarchy\n\n")
        f.write(f"```mermaid\n{diagram}\n```\n")
    print(f"\nWritten to: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
