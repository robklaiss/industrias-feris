# Fix for gCamFuFD Duplication Bug (Error 0160)

## Problem
SIFEN was returning error 0160 "XML Mal Formado" because the XML contained 2 gCamFuFD elements instead of 1.

## Root Cause
The input XML already contained 2 gCamFuFD elements as children of rDE. The passthrough flow was not checking for or eliminating duplicates.

## Solution Implemented

### 1. Fixed Guardrail in normalize_rde_before_sign()
- Fixed `_find_direct()` which returns a list, not a single element
- Added `_find_direct_single()` helper function
- Changed guardrail from `if _find_direct(rde, "gCamFuFD"):` to `if _find_direct_single(rde, "gCamFuFD") is not None:`

### 2. Added Deduplication in Passthrough Flow
In `build_lote_passthrough_signed()`:
- Added detection of multiple gCamFuFD elements
- Keep only the first occurrence
- Remove duplicates and re-serialize

### 3. Added Fail-Hard Guardrail
Before ZIP creation:
- Count gCamFuFD elements in the final lote.xml
- Raise RuntimeError if count != 1
- Save XML for debugging when error occurs

## Files Modified
- `tools/send_sirecepde.py`: Main fix implementation

## Testing
```bash
# Verify fix
python3 tools/assert_no_dup_gcamfufd.py artifacts/last_lote_from_payload.xml
# Should output: gCamFuFD count: 1
```

## Anti-Regression
The fail-hard guardrail ensures that any future duplication will be caught immediately with a clear error message, preventing invalid XML from being sent to SIFEN.
