# Migration Guide: PIPELINE_CONTRACT v1 → v2

This guide helps migrate the SIFEN pipeline from contract v1 to v2 to achieve 100% compliance.

## Overview of Changes

| Section | v1 | v2 | Impact |
|---------|----|----|---------|
| 7 | ❌ Missing | ✅ Exit codes table | New validation logic |
| 8 | ⚠️ Partial | ✅ Complete artifact naming | Need iteration numbers |
| 9 | ❌ Missing | ✅ Success criteria | New classification |
| 10 | ❌ Missing | ✅ Timeout behavior | Better error handling |
| 11 | ❌ Missing | ✅ Validation tools | New test suite |

## Step-by-Step Migration

### Step 1: Update Contract File

```bash
# Backup old contract
cp PIPELINE_CONTRACT.md PIPELINE_CONTRACT_v1_BACKUP.md

# Replace with v2
cp PIPELINE_CONTRACT_v2.md PIPELINE_CONTRACT.md
```

### Step 2: Apply Code Changes

#### 2.1 Add fix_summary generation (Section 8)

```bash
cd tesaka-cv
python tools/add_fix_summary.py
```

This patches `auto_fix_0160_loop.py` to generate `fix_summary_N.md` files.

#### 2.2 Add iteration parameter to send_sirecepde.py

Edit `tools/send_sirecepde.py` and add after line 6030:

```python
parser.add_argument(
    "--iteration",
    type=int,
    default=None,
    help="Número de iteración (para naming de artifacts)"
)
```

Then update the timestamp generation around line 5611:

```python
# Add iteration number to timestamp if provided
if args.iteration is not None:
    timestamp = f"{timestamp}_iter{args.iteration}"
```

#### 2.3 Update auto_fix_0160_loop.py to pass iteration

Edit `tools/auto_fix_0160_loop.py` and modify the send command around line 838:

```python
send_cmd = [
    str(py), str(send_py),
    "--env", args.env,
    "--xml", str(current_xml),
    "--bump-doc", "1",
    "--dump-http",
    "--artifacts-dir", str(artifacts_dir),
    "--iteration", str(i)  # ADD THIS LINE
]
```

#### 2.4 Add success validation to auto_fix_0160_loop.py

Add this function after line 150:

```python
def is_success_status(dCodRes: str) -> bool:
    """Check if dCodRes represents success according to PIPELINE_CONTRACT v2"""
    success_codes = {
        "0001", "0002", "0003",  # Sin observaciones
        "0101", "0102", "0103",  # Aprobado
        "0201", "0202"          # Aprobado con observaciones
    }
    return dCodRes in success_codes
```

Then update the success check around line 891:

```python
if st.de_cod and st.de_cod not in ("0160", "0361"):
    if is_success_status(st.de_cod):
        print(f"\n✅ STOP: Éxito - DE aprobado (dCodRes = {st.de_cod})")
        return 0
    else:
        print(f"\n⚠️  STOP: Error de negocio (dCodRes = {st.de_cod})")
        return 0
```

### Step 3: Update Documentation

#### 3.1 Update README files

Add to `tesaka-cv/README.md`:

```markdown
## Pipeline Compliance

This implementation follows PIPELINE_CONTRACT v2.0. See [PIPELINE_CONTRACT.md](PIPELINE_CONTRACT.md) for details.

### Quick Validation

```bash
# Test contract compliance
python -m pytest tests/test_pipeline_contract.py -v

# Validate last response
python tools/validate_success_criteria.py artifacts/response_recepcion_*.json
```
```

#### 3.2 Update usage examples

In `docs/USAGE_SEND_SIRECEPDE.md`, add:

```markdown
### With iteration tracking (v2.0)

```bash
# Manual iteration
python -m tools.send_sirecepde --env prod --xml input.xml --iteration 1

# Via auto_fix_0160_loop.py (automatic)
python -m tools.auto_fix_0160_loop.py --env prod --xml input.xml --max-iter 10
```

### Step 4: Run Validation Tests

```bash
# Run contract compliance tests
cd /Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado
python -m pytest tests/test_pipeline_contract.py -v

# Expected output:
# ============================= test session starts ==============================
# collected 15 items
# 
# tests/test_pipeline_contract.py::TestPipelineContract::test_canonical_command_structure PASSED
# tests/test_pipeline_contract.py::TestPipelineContract::test_follow_lote_polling_behavior PASSED
# ...
# ========================== 15 passed in 2.34s ==============================
```

### Step 5: Verify End-to-End

```bash
cd tesaka-cv

# Test with a real XML (adjust path as needed)
export SIFEN_SIGN_P12_PATH="certs/your_cert.p12"
export SIFEN_SIGN_P12_PASSWORD="your_password"

# Run one iteration to check artifacts
python -m tools.send_sirecepde \
  --env test \
  --xml artifacts/last_lote.xml \
  --iteration 1 \
  --dump-http

# Check new artifacts
ls -la artifacts/*_iter_1.*
ls -la artifacts/fix_summary_1.md  # Should exist after fix
```

## Validation Checklist

- [ ] Contract updated to v2.0
- [ ] fix_summary_N.md generation added
- [ ] Iteration numbers in artifact names
- [ ] Success criteria validation added
- [ ] Exit codes standardized
- [ ] All tests pass
- [ ] Documentation updated
- [ ] End-to-end verification successful

## Troubleshooting

### Issue: Tests fail for missing tools
```bash
# Ensure all tools are executable
chmod +x tesaka-cv/tools/*.py
```

### Issue: fix_summary not generated
```bash
# Re-run the patch script
python tesaka-cv/tools/add_fix_summary.py
```

### Issue: Iteration numbers not appearing
```bash
# Check that --iteration is being passed
grep -n "iteration" tesaka-cv/tools/auto_fix_0160_loop.py
```

## Rollback Plan

If you need to rollback to v1:

```bash
# Restore v1 contract
cp PIPELINE_CONTRACT_v1_BACKUP.md PIPELINE_CONTRACT.md

# Revert auto_fix_0160_loop.py
git checkout HEAD -- tesaka-cv/tools/auto_fix_0160_loop.py

# Remove iteration parameter from send_sirecepde.py
git checkout HEAD -- tesaka-cv/tools/send_sirecepde.py
```

## Support

For questions about the migration:

1. Check the test output: `python -m pytest tests/test_pipeline_contract.py -v`
2. Review the contract: `cat PIPELINE_CONTRACT.md`
3. Check anti-regression rules: `cat tesaka-cv/docs/aprendizajes/anti-regresion.md`

## Benefits of v2

After migration, you'll have:

- ✅ 100% contract compliance
- ✅ Clear success/error criteria
- ✅ Standardized exit codes
- ✅ Complete artifact traceability
- ✅ Better debugging with fix summaries
- ✅ Automated validation suite
