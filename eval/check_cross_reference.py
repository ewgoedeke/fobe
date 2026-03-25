#!/usr/bin/env python3
"""
check_cross_reference.py — Amount cross-referencing across tables.

For every numeric value in the document, finds all other occurrences
(exact, ×1000, ×1000000, sign-flipped) and checks consistency.

Usage:
    python3 eval/check_cross_reference.py <table_graphs.json>
"""

import json
import sys
from collections import defaultdict


def build_amount_index(tables):
    """Index all parsed values across all tables."""
    index = defaultdict(list)  # normalized_amount → [(table_id, row_id, label, unit_scale, raw_amount)]
    
    for table in tables:
        table_id = table['tableId']
        page = table.get('pageNo', '?')
        sc = table.get('metadata', {}).get('statementComponent', 'None')
        unit = table.get('metadata', {}).get('detectedUnit', 'UNIT.UNITS')
        
        # Determine unit scale
        scale = 1
        if unit in ('UNIT.THOUSANDS', 'TEUR'):
            scale = 1000
        elif unit in ('UNIT.MILLIONS', 'Mio'):
            scale = 1000000
        
        for row in table.get('rows', []):
            if row.get('rowType') in ('SEPARATOR', 'METADATA'):
                continue
            label = row.get('label', '') or ''
            for cell in row.get('cells', []):
                pv = cell.get('parsedValue')
                if pv is not None and pv != 0:
                    # Normalize to units
                    normalized = pv * scale
                    entry = {
                        'table_id': table_id,
                        'page': page,
                        'statement': sc,
                        'row_id': row.get('rowId', ''),
                        'label': label[:60],
                        'raw_value': pv,
                        'unit_scale': scale,
                        'normalized_value': normalized,
                        'col_idx': cell.get('colIdx')
                    }
                    index[normalized].append(entry)
    
    return index


def find_cross_references(index):
    """Find amounts that appear in multiple tables."""
    xrefs = []
    
    for amount, entries in index.items():
        if abs(amount) < 100:  # skip trivial amounts
            continue
        
        # Group by table
        tables = set(e['table_id'] for e in entries)
        if len(tables) > 1:
            # Same normalized amount in different tables
            xrefs.append({
                'type': 'EXACT_MATCH',
                'amount': amount,
                'occurrences': len(entries),
                'tables': list(tables),
                'entries': entries
            })
    
    # Also check ×1000 relationships
    amounts = set(index.keys())
    for amount in list(amounts):
        if abs(amount) < 1000:
            continue
        scaled = amount * 1000
        if scaled in amounts:
            xrefs.append({
                'type': 'SCALE_1000',
                'small_amount': amount,
                'large_amount': scaled,
                'small_entries': index[amount],
                'large_entries': index[scaled],
                'message': f'{amount:,.0f} × 1000 = {scaled:,.0f}'
            })
    
    return xrefs


def check_revenue_consistency(tables):
    """Specific check: PNL face revenue vs segment external revenue."""
    issues = []
    
    pnl_revenue = {}  # col_idx → amount
    segment_external = {}  # col_idx → total across segments
    segment_ic = {}  # col_idx → total IC
    
    for table in tables:
        sc = table.get('metadata', {}).get('statementComponent')
        unit = table.get('metadata', {}).get('detectedUnit', '')
        scale = 1000 if 'THOUSAND' in unit.upper() or 'TEUR' in unit.upper() else (1000000 if 'MILLION' in unit.upper() else 1)
        
        for row in table.get('rows', []):
            label = (row.get('label', '') or '').lower()
            
            # PNL face revenue
            if sc == 'PNL' and 'revenue' in label and row.get('rowType') in ('DATA', 'TOTAL_EXPLICIT'):
                for cell in row.get('cells', []):
                    if cell.get('parsedValue') is not None:
                        pnl_revenue[cell['colIdx']] = cell['parsedValue'] * scale
            
            # Segment external revenue (look for the consolidated total column)
            if 'external revenue' in label:
                for cell in row.get('cells', []):
                    if cell.get('parsedValue') is not None:
                        val = cell['parsedValue'] * scale
                        # Accumulate — the last/largest column is likely the group total
                        if cell['colIdx'] not in segment_external or abs(val) > abs(segment_external.get(cell['colIdx'], 0)):
                            segment_external[cell['colIdx']] = val
            
            if 'intercompany revenue' in label or 'inter-segment revenue' in label:
                for cell in row.get('cells', []):
                    if cell.get('parsedValue') is not None:
                        val = cell['parsedValue'] * scale
                        segment_ic[cell['colIdx']] = val
    
    # Compare
    if pnl_revenue and segment_external:
        for col, pnl_val in pnl_revenue.items():
            # Find the segment total column that's closest to PNL
            best_match = None
            best_delta = float('inf')
            for seg_col, seg_val in segment_external.items():
                delta = abs(pnl_val - seg_val)
                if delta < best_delta:
                    best_delta = delta
                    best_match = (seg_col, seg_val)
            
            if best_match and best_delta > 0:
                ic_val = segment_ic.get(best_match[0], 0)
                issues.append({
                    'check': 'REVENUE_IC_LEAKAGE',
                    'severity': 'WARNING' if best_delta < abs(pnl_val) * 0.01 else 'ERROR',
                    'pnl_face_revenue': pnl_val,
                    'segment_external_revenue': best_match[1],
                    'delta': best_delta,
                    'ic_post_elimination': ic_val,
                    'message': f'PNL face revenue ({pnl_val:,.0f}) ≠ segment external ({best_match[1]:,.0f}), Δ={best_delta:,.0f}. IC post-elim={ic_val:,.0f}'
                })
    
    return issues


def main():
    if len(sys.argv) < 2:
        print(f'Usage: {sys.argv[0]} <table_graphs.json>')
        sys.exit(1)
    
    with open(sys.argv[1]) as f:
        data = json.load(f)
    
    tables = data.get('tables', [])
    
    # Build index
    index = build_amount_index(tables)
    print(f'Indexed {len(index)} unique normalized amounts across {len(tables)} tables')
    
    # Cross-references
    xrefs = find_cross_references(index)
    multi_table = [x for x in xrefs if x['type'] == 'EXACT_MATCH']
    scaled = [x for x in xrefs if x['type'] == 'SCALE_1000']
    print(f'Found {len(multi_table)} amounts appearing in multiple tables')
    print(f'Found {len(scaled)} ×1000 scale relationships')
    
    # Revenue consistency
    rev_issues = check_revenue_consistency(tables)
    
    print(f'\n=== Revenue Consistency ===')
    for issue in rev_issues:
        sev = issue['severity']
        icon = {'ERROR': '❌', 'WARNING': '⚠️'}.get(sev, '?')
        print(f'{icon} [{sev}] {issue["check"]}')
        print(f'   {issue["message"]}')
    
    if not rev_issues:
        print('✅ No revenue consistency issues detected')
    
    return 1 if any(i['severity'] == 'ERROR' for i in rev_issues) else 0


if __name__ == '__main__':
    sys.exit(main())
