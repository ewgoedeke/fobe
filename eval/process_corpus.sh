#!/bin/bash
# process_corpus.sh — Batch process all PDFs through Docling → preprocess → fixtures
#
# Runs ingest_docling.py for each PDF in sources/ugb/, which:
#   1. Converts PDF → Docling JSON + tables_raw.jsonl
#   2. Auto-calls preprocess.py → table_graphs.json
#   3. Copies table_graphs.json to eval/fixtures/{name}/
#
# Usage:
#   bash eval/process_corpus.sh              # process all PDFs
#   bash eval/process_corpus.sh --skip-existing  # skip already-processed
#   bash eval/process_corpus.sh omv strabag  # process specific ones

set -euo pipefail

FOBE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOC_TAG="${DOC_TAG_ROOT:-/tmp/doc_tag}"
WORK_DIR="/tmp/fobe_corpus"

SKIP_EXISTING=false
SPECIFIC=()

# Parse args
for arg in "$@"; do
    if [ "$arg" = "--skip-existing" ]; then
        SKIP_EXISTING=true
    else
        SPECIFIC+=("$arg")
    fi
done

# Verify doc_tag exists
if [ ! -f "$DOC_TAG/ingest_docling.py" ]; then
    echo "ERROR: doc_tag not found at $DOC_TAG"
    echo "Set DOC_TAG_ROOT env var or clone to /tmp/doc_tag"
    exit 1
fi

# Verify Docling is available
python3 -c "from docling.document_converter import DocumentConverter" 2>/dev/null || {
    echo "ERROR: Docling not available. Install with: pip install docling"
    echo "Or run this script on the server where Docling is installed."
    exit 1
}

mkdir -p "$WORK_DIR"

PROCESSED=0
FAILED=0
SKIPPED=0

echo "=========================================="
echo "FOBE Corpus Processing"
echo "=========================================="
echo "Source: $FOBE_ROOT/sources/ugb/"
echo "Work:   $WORK_DIR"
echo "Doc_tag: $DOC_TAG"
echo ""

for pdf in "$FOBE_ROOT"/sources/ugb/*.pdf; do
    name=$(basename "$pdf" .pdf)

    # Filter by specific names if provided
    if [ ${#SPECIFIC[@]} -gt 0 ]; then
        match=false
        for s in "${SPECIFIC[@]}"; do
            if [[ "$name" == *"$s"* ]]; then
                match=true
                break
            fi
        done
        if [ "$match" = false ]; then
            continue
        fi
    fi

    fixture_dir="$FOBE_ROOT/eval/fixtures/$name"
    fixture_file="$fixture_dir/table_graphs.json"

    # Skip if already processed
    if [ "$SKIP_EXISTING" = true ] && [ -f "$fixture_file" ]; then
        echo "SKIP: $name (fixture exists)"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    echo "──────────────────────────────────────────"
    echo "Processing: $name"
    echo "  PDF: $pdf ($(du -h "$pdf" | cut -f1))"

    doc_dir="$WORK_DIR/$name"
    mkdir -p "$doc_dir"

    # Run ingest_docling.py (auto-calls preprocess.py)
    if python3 "$DOC_TAG/ingest_docling.py" \
        --pdf "$pdf" \
        --doc-dir "$doc_dir" \
        --display-name "$name" 2>&1; then

        # Find table_graphs.json in output
        tg=$(find "$doc_dir" -name "table_graphs.json" -type f | head -1)

        if [ -n "$tg" ]; then
            mkdir -p "$fixture_dir"
            cp "$tg" "$fixture_file"

            # Count tables and rows
            tables=$(python3 -c "import json; d=json.load(open('$fixture_file')); print(len(d.get('tables',[])))" 2>/dev/null || echo "?")
            rows=$(python3 -c "import json; d=json.load(open('$fixture_file')); print(sum(len(t.get('rows',[])) for t in d.get('tables',[])))" 2>/dev/null || echo "?")

            echo "  ✅ $name: $tables tables, $rows rows → $fixture_file"
            PROCESSED=$((PROCESSED + 1))
        else
            echo "  ❌ $name: no table_graphs.json produced"
            FAILED=$((FAILED + 1))
        fi
    else
        echo "  ❌ $name: ingest_docling.py failed"
        FAILED=$((FAILED + 1))
    fi
done

echo ""
echo "=========================================="
echo "SUMMARY"
echo "=========================================="
echo "  Processed: $PROCESSED"
echo "  Failed:    $FAILED"
echo "  Skipped:   $SKIPPED"
echo "  Total PDFs: $(ls "$FOBE_ROOT"/sources/ugb/*.pdf | wc -l)"

# Run consistency engine if any were processed
if [ $PROCESSED -gt 0 ]; then
    echo ""
    echo "Running consistency engine on new fixtures..."
    cd "$FOBE_ROOT"
    for fixture_dir in eval/fixtures/*/; do
        tg="$fixture_dir/table_graphs.json"
        if [ -f "$tg" ]; then
            name=$(basename "$fixture_dir")
            result=$(python3 eval/check_consistency.py "$tg" 2>&1 | grep "findings" | head -1)
            echo "  $name: $result"
        fi
    done
fi
