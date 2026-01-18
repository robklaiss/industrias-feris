#!/usr/bin/env python3
"""Test script to verify gCamFuFD duplication fix"""

import sys
from pathlib import Path

# Test with a real XML file that has the duplication issue
print("Testing gCamFuFD duplication fix on existing file...")

# Check the artifacts directory for a test file
test_file = Path("artifacts/_stage_01_input.xml")
if not test_file.exists():
    print(f"❌ Test file not found: {test_file}")
    sys.exit(1)

# Count gCamFuFD in the file
from tools.assert_no_dup_gcamfufd import count_gcamfufd

count = count_gcamfufd(str(test_file))
print(f"gCamFuFD count in {test_file}: {count}")

if count == 2:
    print("✅ Found duplication issue as expected")
    print("The fix should prevent this from reaching the final payload")
elif count == 1:
    print("✅ No duplication found")
else:
    print(f"⚠️  Unexpected count: {count}")

# Now check the final payload
final_file = Path("artifacts/last_lote_from_payload.xml")
if final_file.exists():
    final_count = count_gcamfufd(str(final_file))
    print(f"gCamFuFD count in final payload: {final_count}")
    
    if final_count == 1:
        print("✅ SUCCESS: Final payload has exactly 1 gCamFuFD")
        sys.exit(0)
    else:
        print(f"❌ FAILURE: Final payload has {final_count} gCamFuFD, expected 1")
        sys.exit(1)
else:
    print(f"⚠️  Final payload file not found: {final_file}")
    print("Please run a test first to generate the payload")
    sys.exit(0)
