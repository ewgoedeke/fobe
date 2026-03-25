#!/usr/bin/env python3
"""
check_classification.py — Pre-tagging table classification validation.

Checks whether each table's statementComponent is consistent with its row labels.
Detects misclassified tables (e.g., associate summary tagged as OCI).

Usage:
    python3 eval/check_classification.py <table_graphs.json>
"""

import json
import sys
import re
from collections import Counter

# Row labels that indicate a PNL-structure table
PNL_INDICATORS = re.compile(
    r'\b(revenue|revenues|umsatz|erlös|cost of (sales|goods)|gross profit|'
    r'ebitda|ebit|operating (profit|result|loss)|betriebsergebnis|'
    r'profit before tax|ergebnis vor steuern|income tax|ertragsteuer|'
    r'net profit|jahresüberschuss|selling expenses|admin|verwaltung)\b',
    re.IGNORECASE
)

# Row labels that indicate an SFP-structure table
SFP_INDICATORS = re.compile(
    r'\b(total assets|summe aktiva|total equity|eigenkapital|'
    r'non-current (assets|liabilities)|current (assets|liabilities)|'
    r'anlagevermögen|umlaufvermögen|verbindlichkeiten|rückstellung)\b',
    re.IGNORECASE
)

# Row labels that indicate OCI-specific content
OCI_INDICATORS = re.compile(
    r'\b(other comprehensive|sonstiges ergebnis|'
    r'translation|hedging|remeasurement|fvoci)\b',
    re.IGNORECASE
)

# Labels that should NEVER appear in OCI
OCI_FORBIDDEN = re.compile(
    r'\b(revenue|revenues|cost of (sales|goods)|gross profit|ebitda|'
    r'selling expenses|admin expenses)\b',
    re.IGNORECASE
)


def check_table(table):
    """Check a single table for classification issues."""
    issues = []
    table_id = table['tableId']
    page = table.get('pageNo', '?')
    sc = table.get('metadata', {}).get('statementComponent')
    rows = table.get('rows', [])
    
    if not rows:
        return issues
    
    labels = [r.get('label', '') or '' for r in rows]
    data_rows = [r for r in rows if r.get('rowType') in ('DATA', 'TOTAL_EXPLICIT', 'TOTAL_IMPLICIT')]
    
    # Count indicator matches
    pnl_matches = sum(1 for l in labels if PNL_INDICATORS.search(l))
    sfp_matches = sum(1 for l in labels if SFP_INDICATORS.search(l))
    oci_matches = sum(1 for l in labels if OCI_INDICATORS.search(l))
    
    # Check 1: OCI table with PNL-structure rows
    if sc == 'OCI':
        forbidden = [l for l in labels if OCI_FORBIDDEN.search(l)]
        if forbidden:
            issues.append({
                'check': 'OCI_HAS_PNL_STRUCTURE',
                'severity': 'ERROR',
                'table_id': table_id,
                'page': page,
                'message': f'Table classified as OCI but contains PNL-structure rows: {forbidden[:3]}',
                'suggestion': 'Likely IAS 28 associate summary or segment P&L — reclassify'
            })
    
    # Check 2: Associate/JV summary detection
    if len(data_rows) <= 8 and pnl_matches >= 2 and sfp_matches >= 1:
        # Small table with both PNL and SFP structure → likely associate summary
        if sc not in ('DISC.ASSOCIATES', None):
            issues.append({
                'check': 'ASSOCIATE_SUMMARY_DETECTED',
                'severity': 'WARNING',
                'table_id': table_id,
                'page': page,
                'message': f'Small table ({len(data_rows)} data rows) with PNL + SFP structure — likely IAS 28 associate/JV summary',
                'current_classification': sc,
                'suggested_context': 'DISC.ASSOCIATES'
            })
    
    # Check 3: PNL table without revenue
    if sc == 'PNL' and pnl_matches == 0:
        issues.append({
            'check': 'PNL_NO_REVENUE',
            'severity': 'WARNING',
            'table_id': table_id,
            'page': page,
            'message': 'Table classified as PNL but no revenue/profit-related labels found'
        })
    
    # Check 4: Unclassified table with strong signal
    if sc is None:
        if pnl_matches >= 3 and sfp_matches == 0:
            issues.append({
                'check': 'UNCLASSIFIED_LIKELY_PNL',
                'severity': 'INFO',
                'table_id': table_id,
                'page': page,
                'message': f'Unclassified table with {pnl_matches} PNL-indicator rows — consider classifying as PNL or DISC.*'
            })
        elif sfp_matches >= 3 and pnl_matches == 0:
            issues.append({
                'check': 'UNCLASSIFIED_LIKELY_SFP',
                'severity': 'INFO',
                'table_id': table_id,
                'page': page,
                'message': f'Unclassified table with {sfp_matches} SFP-indicator rows — consider classifying as SFP or DISC.*'
            })
    
    return issues


def main():
    if len(sys.argv) < 2:
        print(f'Usage: {sys.argv[0]} <table_graphs.json>')
        sys.exit(1)
    
    with open(sys.argv[1]) as f:
        data = json.load(f)
    
    tables = data.get('tables', [])
    all_issues = []
    
    for table in tables:
        issues = check_table(table)
        all_issues.extend(issues)
    
    # Summary
    by_severity = Counter(i['severity'] for i in all_issues)
    print(f'\n=== Classification Check: {len(tables)} tables, {len(all_issues)} issues ===')
    print(f'  ERRORS:   {by_severity.get("ERROR", 0)}')
    print(f'  WARNINGS: {by_severity.get("WARNING", 0)}')
    print(f'  INFO:     {by_severity.get("INFO", 0)}')
    
    for issue in all_issues:
        sev = issue['severity']
        icon = {'ERROR': '❌', 'WARNING': '⚠️', 'INFO': 'ℹ️'}.get(sev, '?')
        print(f'\n{icon} [{sev}] {issue["check"]}')
        print(f'   Table: {issue["table_id"]} (page {issue["page"]})')
        print(f'   {issue["message"]}')
        if 'suggestion' in issue:
            print(f'   Suggestion: {issue["suggestion"]}')
        if 'suggested_context' in issue:
            print(f'   Suggested context: {issue["suggested_context"]}')
    
    # Output JSON
    output = {
        'tables_checked': len(tables),
        'issues': all_issues,
        'summary': dict(by_severity)
    }
    
    json_path = sys.argv[1].replace('table_graphs.json', 'classification_check.json')
    with open(json_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f'\nResults written to: {json_path}')
    
    return 1 if by_severity.get('ERROR', 0) > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
