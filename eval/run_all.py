#!/usr/bin/env python3
"""
run_all.py — Run all FOBE evaluation checks on a document.

Usage:
    python3 eval/run_all.py <table_graphs.json>
"""

import subprocess
import sys
import os

CHECKS = [
    ('Classification', 'eval/check_classification.py'),
    ('Consistency', 'eval/check_consistency.py'),
]


def main():
    if len(sys.argv) < 2:
        print(f'Usage: {sys.argv[0]} <table_graphs.json>')
        sys.exit(1)
    
    doc_path = sys.argv[1]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    
    print(f'FOBE Evaluation Suite')
    print(f'Document: {doc_path}')
    print(f'=' * 60)
    
    results = {}
    for name, script in CHECKS:
        script_path = os.path.join(repo_root, script)
        print(f'\n{"─" * 60}')
        print(f'Running: {name}')
        print(f'{"─" * 60}')
        
        result = subprocess.run(
            [sys.executable, script_path, doc_path],
            capture_output=False
        )
        results[name] = 'PASS' if result.returncode == 0 else 'FAIL'
    
    print(f'\n{"=" * 60}')
    print(f'SUMMARY')
    print(f'{"=" * 60}')
    for name, status in results.items():
        icon = '✅' if status == 'PASS' else '❌'
        print(f'  {icon} {name}: {status}')


if __name__ == '__main__':
    main()
