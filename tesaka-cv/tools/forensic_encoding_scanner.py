#!/usr/bin/env python3
"""
FASE B - Encoding Forensics Scanner
Scans XML for encoding issues, control characters, and malformed content.
"""
import sys
import re
from collections import defaultdict

def scan_encoding(xml_path, output_path):
    """Scan for encoding issues and control characters."""
    
    with open(xml_path, 'rb') as f:
        raw_bytes = f.read()
    
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("ENCODING FORENSICS REPORT - FASE B")
    report_lines.append("=" * 80)
    report_lines.append(f"File: {xml_path}")
    report_lines.append(f"Total size: {len(raw_bytes)} bytes")
    report_lines.append("")
    
    # Check for BOM
    report_lines.append("1. BYTE ORDER MARK (BOM) CHECK")
    if raw_bytes.startswith(b'\xef\xbb\xbf'):
        report_lines.append("   ✗ UTF-8 BOM detected at start (0xEF 0xBB 0xBF)")
    elif raw_bytes.startswith(b'\xff\xfe'):
        report_lines.append("   ✗ UTF-16 LE BOM detected")
    elif raw_bytes.startswith(b'\xfe\xff'):
        report_lines.append("   ✗ UTF-16 BE BOM detected")
    else:
        report_lines.append("   ✓ No BOM detected")
    report_lines.append("")
    
    # Check UTF-8 validity
    report_lines.append("2. UTF-8 ENCODING VALIDATION")
    try:
        text = raw_bytes.decode('utf-8')
        report_lines.append("   ✓ Valid UTF-8 encoding")
    except UnicodeDecodeError as e:
        report_lines.append(f"   ✗ INVALID UTF-8: {e}")
        report_lines.append(f"      Position: {e.start}-{e.end}")
        report_lines.append(f"      Bytes: {raw_bytes[max(0, e.start-10):e.end+10].hex()}")
        text = raw_bytes.decode('utf-8', errors='replace')
    report_lines.append("")
    
    # Check for control characters (0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F)
    report_lines.append("3. CONTROL CHARACTER SCAN")
    control_chars = defaultdict(list)
    
    # Allowed: 0x09 (tab), 0x0A (LF), 0x0D (CR)
    # Forbidden in XML: 0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F
    forbidden_ranges = [
        (0x00, 0x08),
        (0x0B, 0x0B),
        (0x0C, 0x0C),
        (0x0E, 0x1F)
    ]
    
    for i, byte in enumerate(raw_bytes):
        for start, end in forbidden_ranges:
            if start <= byte <= end:
                control_chars[byte].append(i)
    
    if control_chars:
        report_lines.append("   ✗ FORBIDDEN CONTROL CHARACTERS FOUND:")
        for char_code, positions in sorted(control_chars.items()):
            count = len(positions)
            sample_positions = positions[:5]
            report_lines.append(f"      0x{char_code:02X}: {count} occurrence(s) at positions {sample_positions}")
            if count > 5:
                report_lines.append(f"         ... and {count - 5} more")
    else:
        report_lines.append("   ✓ No forbidden control characters")
    report_lines.append("")
    
    # Check line endings
    report_lines.append("4. LINE ENDING ANALYSIS")
    crlf_count = text.count('\r\n')
    lf_only_count = text.count('\n') - crlf_count
    cr_only_count = text.count('\r') - crlf_count
    
    report_lines.append(f"   CRLF (\\r\\n): {crlf_count}")
    report_lines.append(f"   LF only (\\n): {lf_only_count}")
    report_lines.append(f"   CR only (\\r): {cr_only_count}")
    
    if crlf_count > 0 and lf_only_count > 0:
        report_lines.append("   ⚠ MIXED line endings detected (CRLF and LF)")
    elif cr_only_count > 0:
        report_lines.append("   ⚠ Old Mac-style CR line endings detected")
    else:
        report_lines.append("   ✓ Consistent line endings")
    report_lines.append("")
    
    # Check for malformed entities
    report_lines.append("5. ENTITY ESCAPING CHECK")
    
    # Find all text content (between > and <)
    text_content_pattern = re.compile(r'>([^<]+)<')
    issues = []
    
    for match in text_content_pattern.finditer(text):
        content = match.group(1)
        pos = match.start(1)
        
        # Check for unescaped < or >
        if '<' in content or '>' in content:
            issues.append(f"Unescaped < or > at position {pos}: {repr(content[:50])}")
        
        # Check for bare & not part of entity
        bare_amp = re.findall(r'&(?!(?:amp|lt|gt|quot|apos);)', content)
        if bare_amp:
            issues.append(f"Unescaped & at position {pos}: {repr(content[:50])}")
    
    if issues:
        report_lines.append("   ✗ ENTITY ESCAPING ISSUES:")
        for issue in issues[:10]:
            report_lines.append(f"      {issue}")
        if len(issues) > 10:
            report_lines.append(f"      ... and {len(issues) - 10} more")
    else:
        report_lines.append("   ✓ No entity escaping issues detected")
    report_lines.append("")
    
    # Check for unusual whitespace
    report_lines.append("6. WHITESPACE ANALYSIS")
    
    # Count different whitespace types
    tab_count = text.count('\t')
    space_count = text.count(' ')
    newline_count = text.count('\n')
    
    # Check for unusual Unicode whitespace
    unusual_ws = []
    unusual_ws_chars = [
        ('\u00a0', 'NO-BREAK SPACE'),
        ('\u2000', 'EN QUAD'),
        ('\u2001', 'EM QUAD'),
        ('\u2002', 'EN SPACE'),
        ('\u2003', 'EM SPACE'),
        ('\u2004', 'THREE-PER-EM SPACE'),
        ('\u2005', 'FOUR-PER-EM SPACE'),
        ('\u2006', 'SIX-PER-EM SPACE'),
        ('\u2007', 'FIGURE SPACE'),
        ('\u2008', 'PUNCTUATION SPACE'),
        ('\u2009', 'THIN SPACE'),
        ('\u200a', 'HAIR SPACE'),
        ('\u202f', 'NARROW NO-BREAK SPACE'),
        ('\u205f', 'MEDIUM MATHEMATICAL SPACE'),
        ('\u3000', 'IDEOGRAPHIC SPACE'),
    ]
    
    for char, name in unusual_ws_chars:
        count = text.count(char)
        if count > 0:
            unusual_ws.append(f"{name} (U+{ord(char):04X}): {count} occurrence(s)")
    
    report_lines.append(f"   Regular spaces: {space_count}")
    report_lines.append(f"   Tabs: {tab_count}")
    report_lines.append(f"   Newlines: {newline_count}")
    
    if unusual_ws:
        report_lines.append("   ✗ UNUSUAL UNICODE WHITESPACE:")
        for ws in unusual_ws:
            report_lines.append(f"      {ws}")
    else:
        report_lines.append("   ✓ No unusual Unicode whitespace")
    report_lines.append("")
    
    # Check XML declaration
    report_lines.append("7. XML DECLARATION CHECK")
    if text.startswith('<?xml'):
        first_line = text.split('\n')[0] if '\n' in text else text[:200]
        report_lines.append(f"   XML declaration: {first_line}")
        
        if 'encoding=' in first_line.lower():
            if 'UTF-8' in first_line or 'utf-8' in first_line:
                report_lines.append("   ✓ UTF-8 encoding declared")
            else:
                report_lines.append("   ⚠ Non-UTF-8 encoding declared")
        else:
            report_lines.append("   ⚠ No encoding attribute in XML declaration")
    else:
        report_lines.append("   ✗ No XML declaration found")
    report_lines.append("")
    
    # Summary
    report_lines.append("=" * 80)
    report_lines.append("SUMMARY")
    report_lines.append("=" * 80)
    
    critical_issues = []
    warnings = []
    
    if control_chars:
        critical_issues.append(f"Forbidden control characters: {sum(len(v) for v in control_chars.values())} total")
    
    if issues:
        critical_issues.append(f"Entity escaping issues: {len(issues)}")
    
    if unusual_ws:
        warnings.append(f"Unusual Unicode whitespace: {len(unusual_ws)} types")
    
    if crlf_count > 0 and lf_only_count > 0:
        warnings.append("Mixed line endings")
    
    if critical_issues:
        report_lines.append("CRITICAL ISSUES:")
        for issue in critical_issues:
            report_lines.append(f"  ✗ {issue}")
    
    if warnings:
        report_lines.append("")
        report_lines.append("WARNINGS:")
        for warning in warnings:
            report_lines.append(f"  ⚠ {warning}")
    
    if not critical_issues and not warnings:
        report_lines.append("✓ No encoding issues detected")
    
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("END OF REPORT")
    report_lines.append("=" * 80)
    
    report = "\n".join(report_lines)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    return report

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python forensic_encoding_scanner.py <input.xml> <output_report.txt>")
        sys.exit(1)
    
    xml_file = sys.argv[1]
    output_file = sys.argv[2]
    
    report = scan_encoding(xml_file, output_file)
    print(report)
