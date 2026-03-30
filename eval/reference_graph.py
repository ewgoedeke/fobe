#!/usr/bin/env python3
"""
reference_graph.py — Build a document-level reference graph from table_graphs.json.

Extracts cross-references between tables by analysing:
  1. TOC entries that map note numbers to page ranges
  2. Note/Anhang columns in primary statement tables (role=NOTES)
  3. Inline note references in row labels (e.g. "see Note 12")

The graph connects primary-statement rows to their disclosure notes,
enabling downstream classification and concept-candidate filtering.

Pipeline position:
    reference_graph.py is consumed by classify_tables.py, pretag_all.py, llm_tagger.py
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ── ParsedLabel ──────────────────────────────────────────────────────────────

@dataclass
class ParsedLabel:
    """A row label with footnote markers and inline note references stripped."""
    raw: str
    clean: str                  # label with footnotes/note refs removed
    footnote_letters: list[str] = field(default_factory=list)   # e.g. ['d', 'e']
    note_number: Optional[str] = None    # e.g. "21", "9(C)", "28(C)-(D)"

    @property
    def has_note(self) -> bool:
        return self.note_number is not None


# Trailing footnote letters: single lowercase a-o, possibly comma-separated
# e.g. "Revenue c,d" → footnotes ['c','d'], "Investment property d" → ['d']
_TRAILING_FOOTNOTE_RE = re.compile(
    r"\s+([a-o](?:\s*,\s*[a-o])*)\s*$"
)

# Inline note references: "see Note 12", "(Note 5.1)", "(note 22)"
_INLINE_NOTE_RE = re.compile(
    r"\(?\s*(?:see\s+)?(?:note|anhang|anmerkung)\s+(\d+(?:[.\-()A-Za-z]*)?)\s*\)?"
    , re.IGNORECASE
)

# Superscript digits used as footnote markers
_SUPERSCRIPT_RE = re.compile(r"\s*[¹²³⁴⁵⁶⁷⁸⁹⁰]+\s*$")

# Trailing asterisks
_TRAILING_STAR_RE = re.compile(r"\s*\*+\s*$")


def parse_label(raw_label: str) -> ParsedLabel:
    """Parse a row label, stripping footnote letters and inline note refs."""
    text = raw_label.strip()
    footnote_letters: list[str] = []
    note_number: str | None = None

    # 1. Strip trailing superscript footnote markers
    text = _SUPERSCRIPT_RE.sub("", text)
    text = _TRAILING_STAR_RE.sub("", text)

    # 2. Strip trailing footnote letters (a-o)
    m = _TRAILING_FOOTNOTE_RE.search(text)
    if m:
        letters_str = m.group(1)
        footnote_letters = [ch.strip() for ch in letters_str.split(",") if ch.strip()]
        text = text[:m.start()].rstrip()

    # 3. Extract inline note references
    m = _INLINE_NOTE_RE.search(text)
    if m:
        note_number = m.group(1)
        text = text[:m.start()].rstrip() + text[m.end():]
        text = text.strip()

    # 4. Clean up parenthetical note refs like "(1)" at end
    text = re.sub(r"\s*\(\d+\)\s*$", "", text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return ParsedLabel(
        raw=raw_label,
        clean=text,
        footnote_letters=footnote_letters,
        note_number=note_number,
    )


# ── DocumentRefGraph ─────────────────────────────────────────────────────────

@dataclass
class NoteEntry:
    """A single note reference extracted from a table."""
    note_number: str            # e.g. "21", "9(C)"
    note_number_base: int       # just the leading integer, e.g. 21, 9
    source_table_id: str        # tableId of the table containing the note column
    source_row_idx: int
    source_label: str           # the row label this note is attached to
    source_context: str         # statementComponent of the source table (e.g. "SFP")


@dataclass
class DocumentRefGraph:
    """Cross-reference graph for a single document.

    Maps note numbers to:
      - The rows they were referenced from (in primary statements)
      - The disclosure context they likely correspond to (from TOC or keywords)
    """
    # note_base_number (int) → list of NoteEntry
    note_entries: dict[int, list[NoteEntry]] = field(default_factory=dict)

    # note_base_number (int) → inferred disclosure context (e.g. "DISC.PPE")
    note_to_context: dict[int, str] = field(default_factory=dict)

    # tableId → list of note_base_numbers referenced by that table
    table_notes: dict[str, list[int]] = field(default_factory=dict)

    def context_for_note(self, note_num: int) -> Optional[str]:
        """Return the disclosure context for a note number, if known."""
        return self.note_to_context.get(note_num)

    def notes_for_table(self, table_id: str) -> list[int]:
        """Return note numbers referenced by a specific table."""
        return self.table_notes.get(table_id, [])

    def labels_for_note(self, note_num: int) -> list[str]:
        """Return the source labels that reference this note number."""
        return [e.source_label for e in self.note_entries.get(note_num, [])]


# Note number → disclosure context heuristics (matches _NOTE_PATTERNS in classify_tables.py)
_NOTE_CONTEXT_PATTERNS = [
    (re.compile(r"segment", re.I), "DISC.SEGMENTS"),
    (re.compile(r"revenue|umsatz|erlös", re.I), "DISC.REVENUE"),
    (re.compile(r"property.+plant|sachanlag|ppe", re.I), "DISC.PPE"),
    (re.compile(r"intangible|immateriell", re.I), "DISC.INTANGIBLES"),
    (re.compile(r"goodwill|firmenwert", re.I), "DISC.GOODWILL"),
    (re.compile(r"investment property|als finanzinvestition", re.I), "DISC.INV_PROP"),
    (re.compile(r"lease|leasing|nutzungsrecht", re.I), "DISC.LEASES"),
    (re.compile(r"provision|rückstellung", re.I), "DISC.PROVISIONS"),
    (re.compile(r"tax|steuer", re.I), "DISC.TAX"),
    (re.compile(r"employee.+benefit|pension|abfertigung|personal", re.I), "DISC.EMPLOYEE_BENEFITS"),
    (re.compile(r"earnings per share|ergebnis je aktie", re.I), "DISC.EPS"),
    (re.compile(r"share.+based|aktienbasiert", re.I), "DISC.SHARE_BASED"),
    (re.compile(r"business combination|unternehmenserwerb|akquisition", re.I), "DISC.BCA"),
    (re.compile(r"financial instrument|finanzinstrument", re.I), "DISC.FIN_INST"),
    (re.compile(r"fair value|beizulegender zeitwert", re.I), "DISC.FAIR_VALUE"),
    (re.compile(r"inventor|vorräte|vorrat", re.I), "DISC.INVENTORIES"),
    (re.compile(r"borrowing|anleihe|darlehen", re.I), "DISC.BORROWINGS"),
    (re.compile(r"related part|nahestehend", re.I), "DISC.RELATED_PARTIES"),
    (re.compile(r"contingent|eventual", re.I), "DISC.CONTINGENCIES"),
    (re.compile(r"held for sale|discontinued|aufgegeben", re.I), "DISC.HELD_FOR_SALE"),
    (re.compile(r"hedge|sicherung", re.I), "DISC.HEDGE"),
    (re.compile(r"credit risk|kreditrisiko", re.I), "DISC.CREDIT_RISK"),
    (re.compile(r"biological|biologisch", re.I), "DISC.BIOLOGICAL_ASSETS"),
    (re.compile(r"government grant|zuwendung", re.I), "DISC.GOV_GRANTS"),
    (re.compile(r"dividend|dividende", re.I), "DISC.DIVIDENDS"),
    (re.compile(r"associate|joint venture|assoziiert|gemeinschaft", re.I), "DISC.ASSOCIATES"),
    (re.compile(r"impairment|wertminderung", re.I), "DISC.IMPAIRMENT"),
    (re.compile(r"depreciation|amortisation|abschreibung", re.I), "DISC.PPE"),
    (re.compile(r"capital|eigenkapital", re.I), "DISC.EQUITY"),
    (re.compile(r"operating expense|material|materialaufwand", re.I), "DISC.EXPENSES"),
    (re.compile(r"(?:right.of.use|rou)\s*asset", re.I), "DISC.LEASES"),
    (re.compile(r"trade.+receiv|forderung", re.I), "DISC.TRADE_RECEIVABLES"),
    (re.compile(r"trade.+payab|verbindlichkeit", re.I), "DISC.TRADE_PAYABLES"),
    (re.compile(r"share\s*capital|grundkapital|aktienkapital", re.I), "DISC.EQUITY"),
    (re.compile(r"cash|zahlungsmittel", re.I), "DISC.CASH"),
]

# Extract the base integer from a note number string like "21", "9(C)", "28(C)-(D)"
_NOTE_BASE_RE = re.compile(r"^(\d+)")


def _extract_note_base(note_str: str) -> Optional[int]:
    """Extract the leading integer from a note number string."""
    m = _NOTE_BASE_RE.match(note_str.strip())
    return int(m.group(1)) if m else None


def _infer_note_context(label: str) -> Optional[str]:
    """Try to infer a disclosure context from a row label via keyword matching."""
    for pattern, ctx in _NOTE_CONTEXT_PATTERNS:
        if pattern.search(label):
            return ctx
    return None


# ── Source 1: Note column extraction ─────────────────────────────────────────

def _extract_note_columns(tables: list[dict], graph: DocumentRefGraph) -> None:
    """Extract note references from columns with role=NOTES."""
    for table in tables:
        table_id = table.get("tableId", "")
        ctx = table.get("metadata", {}).get("statementComponent", "")
        columns = table.get("columns", [])

        # Find NOTES columns
        note_col_indices = set()
        for col in columns:
            if col.get("role") == "NOTES":
                note_col_indices.add(col["colIdx"])
            elif "note" in col.get("headerLabel", "").lower():
                note_col_indices.add(col["colIdx"])

        if not note_col_indices:
            continue

        table_note_bases: list[int] = []

        for row in table.get("rows", []):
            label = row.get("label", "").strip()
            if not label:
                continue

            # Find note value in the note column
            for cell in row.get("cells", []):
                if cell.get("colIdx") not in note_col_indices:
                    continue
                note_text = cell.get("text", "").strip()
                if not note_text:
                    continue

                note_base = _extract_note_base(note_text)
                if note_base is None:
                    continue

                entry = NoteEntry(
                    note_number=note_text,
                    note_number_base=note_base,
                    source_table_id=table_id,
                    source_row_idx=row.get("rowIdx", 0),
                    source_label=label,
                    source_context=ctx,
                )
                graph.note_entries.setdefault(note_base, []).append(entry)
                if note_base not in table_note_bases:
                    table_note_bases.append(note_base)

                # Try to infer disclosure context from the label
                inferred = _infer_note_context(label)
                if inferred and note_base not in graph.note_to_context:
                    graph.note_to_context[note_base] = inferred

        if table_note_bases:
            graph.table_notes[table_id] = table_note_bases


# ── Source 2: Inline note references in labels ───────────────────────────────

def _extract_inline_refs(tables: list[dict], graph: DocumentRefGraph) -> None:
    """Extract inline note references from row labels (e.g. 'see Note 12')."""
    for table in tables:
        table_id = table.get("tableId", "")
        ctx = table.get("metadata", {}).get("statementComponent", "")

        for row in table.get("rows", []):
            label = row.get("label", "").strip()
            if not label:
                continue

            m = _INLINE_NOTE_RE.search(label)
            if not m:
                continue

            note_text = m.group(1)
            note_base = _extract_note_base(note_text)
            if note_base is None:
                continue

            # Don't duplicate entries already captured via note columns
            existing = graph.note_entries.get(note_base, [])
            already = any(
                e.source_table_id == table_id and e.source_row_idx == row.get("rowIdx", 0)
                for e in existing
            )
            if already:
                continue

            entry = NoteEntry(
                note_number=note_text,
                note_number_base=note_base,
                source_table_id=table_id,
                source_row_idx=row.get("rowIdx", 0),
                source_label=label,
                source_context=ctx,
            )
            graph.note_entries.setdefault(note_base, []).append(entry)

            # Infer context
            clean_label = label[:m.start()].strip()
            inferred = _infer_note_context(clean_label)
            if inferred and note_base not in graph.note_to_context:
                graph.note_to_context[note_base] = inferred


# ── Source 3: TOC-based note→context mapping ────────────────────────────────

_TOC_NOTE_ENTRY_RE = re.compile(
    r"^\s*(\d+)\s*[.)]\s+(.+)", re.IGNORECASE
)


def _extract_toc_note_contexts(tables: list[dict], graph: DocumentRefGraph) -> None:
    """Scan TOC-like tables for note number → topic mappings.

    Looks for patterns like "21. Property, plant and equipment ... 45"
    in TOC tables, and maps note 21 → DISC.PPE.
    """
    for table in tables[:20]:
        rows = table.get("rows", [])
        if len(rows) < 3:
            continue

        # Check if this looks like a TOC (has page numbers)
        value_cols = [c for c in table.get("columns", []) if c.get("role") == "VALUE"]
        if len(value_cols) > 2:
            continue

        entries_with_notes = []
        for row in rows:
            label = row.get("label", "").strip()
            m = _TOC_NOTE_ENTRY_RE.match(label)
            if m:
                note_num = int(m.group(1))
                topic = m.group(2).strip()
                entries_with_notes.append((note_num, topic))

        # Need at least a few note entries to consider this a notes TOC
        if len(entries_with_notes) < 3:
            continue

        for note_num, topic in entries_with_notes:
            if note_num in graph.note_to_context:
                continue
            ctx = _infer_note_context(topic)
            if ctx:
                graph.note_to_context[note_num] = ctx


# ── Main entry point ─────────────────────────────────────────────────────────

def build_reference_graph(tables: list[dict]) -> DocumentRefGraph:
    """Build a document reference graph from all tables.

    Analyses three sources:
      1. Note columns (role=NOTES) in primary statement tables
      2. Inline note references in row labels
      3. TOC entries mapping note numbers to topics

    Args:
        tables: list of table dicts from table_graphs.json

    Returns:
        DocumentRefGraph with note references and inferred contexts
    """
    graph = DocumentRefGraph()

    # Source 1: Note columns (highest quality — explicit note numbers)
    _extract_note_columns(tables, graph)

    # Source 2: Inline references in labels
    _extract_inline_refs(tables, graph)

    # Source 3: TOC note→context mapping
    _extract_toc_note_contexts(tables, graph)

    return graph


def has_note_column(table: dict) -> bool:
    """Check if a table has a Note/Anhang column."""
    for col in table.get("columns", []):
        if col.get("role") == "NOTES":
            return True
        header = col.get("headerLabel", "").lower().strip()
        if header in ("note", "notes", "anhang", "anmerkung", "anmerkungen"):
            return True
    return False
