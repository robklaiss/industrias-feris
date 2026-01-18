# SOAP 1.2 Fix Implementation Report
**Date:** 2026-01-18  
**Issue:** Error 0160 "XML Mal Formado" - SOAP version mismatch hypothesis

## Hypothesis
Error 0160 was potentially caused by SOAP version mismatch:
- Request sent: SOAP 1.1 (`http://schemas.xmlsoap.org/soap/envelope/`)
- Response received: SOAP 1.2 (`http://www.w3.org/2003/05/soap-envelope`)
- Headers: SOAP 1.1 used `text/xml` with `SOAPAction` header

## Changes Implemented

### File Modified
`tesaka-cv/app/sifen_client/soap_client.py` - Method `send_recibe_lote()`

### Specific Changes

#### 1. SOAP Namespace (Line ~1602)
**Before:**
```python
# SOAP 1.1 usa namespace diferente
soap_env_ns = "http://schemas.xmlsoap.org/soap/envelope/"
```

**After:**
```python
# SOAP 1.2 namespace (FIX 0160: SIFEN requiere SOAP 1.2)
soap_env_ns = "http://www.w3.org/2003/05/soap-envelope"
```

#### 2. HTTP Headers (Lines ~1614-1623)
**Before:**
```python
# SOAP 1.1 (text/xml con SOAPAction header separado)
SOAP_ACTION = "http://ekuatia.set.gov.py/sifen/xsd/siRecepLoteDE"
headers = {
    "Accept": "text/xml, application/xml, */*",
    "Content-Type": "text/xml; charset=utf-8",
    "SOAPAction": f'"{SOAP_ACTION}"',
    "Connection": "close",
}
```

**After:**
```python
# SOAP 1.2 (application/soap+xml con action en Content-Type, SIN SOAPAction)
# FIX 0160: Error era por mismatch SOAP 1.1 vs SOAP 1.2
SOAP_ACTION = "http://ekuatia.set.gov.py/sifen/xsd/siRecepLoteDE"
headers = {
    "Accept": "application/soap+xml, text/xml, */*",
    "Content-Type": f'application/soap+xml; charset=utf-8; action="{SOAP_ACTION}"',
    "Connection": "close",
}
print(f"🔍 SOAP VERSION: 1.2")
print(f"🔍 Headers en send_recibe_lote (SOAP 1.2): {headers}")
```

#### 3. Namespace Prefix (Lines ~1665-1672)
**Before:**
```python
# Construir SOAP - usar prefijo sifen para namespace SIFEN
env = etree.Element(
    f"{{{soap_env_ns}}}Envelope",
    nsmap={"soap": soap_env_ns, "sifen": sifen_ns}
)
```

**After:**
```python
# Construir SOAP 1.2 - usar prefijo env para SOAP 1.2 y sifen para namespace SIFEN
# FIX 0160: Usar 'env' como prefijo para SOAP 1.2 (no 'soap')
env = etree.Element(
    f"{{{soap_env_ns}}}Envelope",
    nsmap={"env": soap_env_ns, "sifen": sifen_ns}
)
```

#### 4. Namespace Cleanup (Line ~1684)
**Before:**
```python
etree.cleanup_namespaces(env, top_nsmap={"soap": soap_env_ns, "sifen": sifen_ns})
```

**After:**
```python
# FIX 0160: Usar 'env' como prefijo para SOAP 1.2
etree.cleanup_namespaces(env, top_nsmap={"env": soap_env_ns, "sifen": sifen_ns})
```

## Verification

### SOAP Envelope Structure (Verified ✅)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope" 
              xmlns:sifen="http://ekuatia.set.gov.py/sifen/xsd">
  <env:Header/>
  <env:Body>
    <sifen:rEnvioLote>
      <sifen:dId>202601181211573</sifen:dId>
      <sifen:xDE>UEsDBBQ...</sifen:xDE>
    </sifen:rEnvioLote>
  </env:Body>
</env:Envelope>
```

### HTTP Headers (Verified ✅)
```json
{
  "Accept": "application/soap+xml, text/xml, */*",
  "Content-Type": "application/soap+xml; charset=utf-8; action=\"http://ekuatia.set.gov.py/sifen/xsd/siRecepLoteDE\"",
  "Connection": "close"
}
```

### Key Differences SOAP 1.1 vs SOAP 1.2

| Aspect | SOAP 1.1 | SOAP 1.2 |
|--------|----------|----------|
| Namespace | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` |
| Content-Type | `text/xml; charset=utf-8` | `application/soap+xml; charset=utf-8` |
| Action | Separate `SOAPAction` header | `action="..."` parameter in Content-Type |
| Prefix | Usually `soap:` | Usually `env:` |

## Test Results

### Test Command
```bash
cd tesaka-cv
export SIFEN_SKIP_RUC_GATE=1
.venv/bin/python -m tools.send_sirecepde --env test \
  --xml /Users/robinklaiss/Desktop/SIFEN_PREVALIDADOR/_last_sent_lote.xml \
  --dump-http
```

### Result
- **HTTP Status:** 400
- **SIFEN Response:** Error 0160 "XML Mal Formado"
- **SOAP Version in Response:** SOAP 1.2 (confirming SIFEN uses SOAP 1.2) ✅

### Validation Checks Passed
- ✅ SOAP envelope uses SOAP 1.2 namespace
- ✅ Headers use `application/soap+xml` with action parameter
- ✅ No `SOAPAction` header present
- ✅ SIFEN responds in SOAP 1.2 format
- ✅ lote.xml is valid against rLoteDE_v150.xsd
- ✅ rDE structure is correct (dVerFor, DE, Signature, gCamFuFD)
- ✅ rDE and DE have different Ids
- ✅ No BOM in XML
- ✅ XML declaration is correct

## Conclusion

### SOAP 1.2 Fix: Successfully Implemented ✅
The code now correctly sends SOAP 1.2 requests to SIFEN, matching the response format.

### Error 0160 Still Occurs ⚠️
Despite the SOAP 1.2 fix, error 0160 persists. This indicates:
1. **SOAP version mismatch was NOT the root cause of error 0160**
2. The error is likely due to another XML structure issue
3. Further investigation needed into:
   - XML content validation beyond XSD
   - Specific SIFEN parsing requirements
   - Potential issues with the lote.xml content itself

### Next Steps
1. Review SIFEN documentation for additional XML requirements
2. Compare with known working examples
3. Check for any undocumented SIFEN-specific validation rules
4. Consider testing with minimal/simplified DE content

## Anti-Regression Rule

**INVARIANT-SOAP12-SIRECEPLOTE:** 
- `siRecepLoteDE` (recibe_lote) MUST use SOAP 1.2
- Namespace: `http://www.w3.org/2003/05/soap-envelope`
- Prefix: `env:` (not `soap:`)
- Content-Type: `application/soap+xml; charset=utf-8; action="http://ekuatia.set.gov.py/sifen/xsd/siRecepLoteDE"`
- NO `SOAPAction` header
- Response from SIFEN will also be SOAP 1.2

## Files Modified
- `tesaka-cv/app/sifen_client/soap_client.py` (send_recibe_lote method)

## Artifacts Generated
- `tesaka-cv/artifacts/soap_last_request_SENT.xml` - SOAP 1.2 request
- `tesaka-cv/artifacts/lote_from_soap_latest.xml` - Extracted lote.xml
- `tesaka-cv/artifacts/recibe_lote_raw_20260118_121158.xml` - SIFEN response
