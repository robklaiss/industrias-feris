#!/usr/bin/env python3
"""
Add fix_summary_N.md generation to auto_fix_0160_loop.py

This script patches auto_fix_0160_loop.py to generate markdown summaries
for each iteration, as required by PIPELINE_CONTRACT section 8.
"""

import re
from pathlib import Path

def add_fix_summary_generation():
    """Add fix summary generation after line 1029 in auto_fix_0160_loop.py"""
    
    auto_fix_file = Path(__file__).parent / "auto_fix_0160_loop.py"
    
    if not auto_fix_file.exists():
        print(f"❌ File not found: {auto_fix_file}")
        return 1
    
    # Read the file
    content = auto_fix_file.read_text(encoding="utf-8")
    lines = content.splitlines()
    
    # Find the line after "✅ wrote OK"
    insert_idx = None
    for i, line in enumerate(lines):
        if line.strip() == 'print("✅ wrote OK")':
            insert_idx = i + 1
            break
    
    if insert_idx is None:
        print("❌ Could not find insertion point")
        return 1
    
    # Generate the fix summary code to insert
    fix_summary_code = '''        
        # Generate fix summary markdown (PIPELINE_CONTRACT section 8)
        fix_summary_file = artifacts_dir / f"fix_summary_{i}.md"
        fix_summary_content = f"""# Fix Summary - Iteration {i}

## Applied Fixes:
{chr(10).join(f"- {fx}" for fx in fixes_applied)}

## Files:
- Input: {current_xml.name}
- Output: {out_xml.name}

## Status:
- dCodRes: {st.de_cod or 'N/A'}
- Message: {st.de_msg[:200] + '...' if st.de_msg and len(st.de_msg) > 200 else st.de_msg or 'N/A'}
"""
        try:
            fix_summary_file.write_text(fix_summary_content, encoding="utf-8")
            print(f"📝 Fix summary saved: {fix_summary_file.name}")
        except Exception as e:
            print(f"⚠️  Warning: Could not write fix summary: {e}")
'''
    
    # Insert the code
    lines.insert(insert_idx, fix_summary_code)
    
    # Write back the file
    auto_fix_file.write_text("\n".join(lines), encoding="utf-8")
    
    print(f"✅ Added fix summary generation to {auto_fix_file}")
    return 0

if __name__ == "__main__":
    exit(add_fix_summary_generation())
