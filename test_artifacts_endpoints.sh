#!/bin/bash

# Test script for artifacts endpoints
# Usage: ./test_artifacts_endpoints.sh

BASE_URL="http://localhost:8000"

echo "=== Testing Artifacts Endpoints ==="
echo ""

# Test 1: Get latest artifacts
echo "1. GET /api/v1/artifacts/latest"
echo "curl -s ${BASE_URL}/api/v1/artifacts/latest | jq ."
curl -s "${BASE_URL}/api/v1/artifacts/latest" | jq .
echo ""

# Extract the latest dId for subsequent tests
LATEST_DID=$(curl -s "${BASE_URL}/api/v1/artifacts/latest" | jq -r '.dId // empty')

if [ -z "$LATEST_DID" ]; then
    echo "❌ No dId found. Make sure there are sent_lote_*.xml files in artifacts/"
    exit 1
fi

echo "✅ Latest dId: $LATEST_DID"
echo ""

# Test 2: Get artifacts info for specific dId
echo "2. GET /api/v1/artifacts/${LATEST_DID}"
echo "curl -s ${BASE_URL}/api/v1/artifacts/${LATEST_DID} | jq ."
curl -s "${BASE_URL}/api/v1/artifacts/${LATEST_DID}" | jq .
echo ""

# Test 3: Download DE XML
echo "3. GET /api/v1/artifacts/${LATEST_DID}/de"
echo "Downloading DE_TAL_CUAL_TRANSMITIDO_${LATEST_DID}.xml..."
curl -s "${BASE_URL}/api/v1/artifacts/${LATEST_DID}/de" -o "downloaded_de_${LATEST_DID}.xml"
if [ -f "downloaded_de_${LATEST_DID}.xml" ]; then
    echo "✅ File downloaded successfully"
    echo "File size: $(wc -c < "downloaded_de_${LATEST_DID}.xml") bytes"
    echo "First 3 lines:"
    head -n 3 "downloaded_de_${LATEST_DID}.xml" | sed 's/^/  /'
else
    echo "❌ Failed to download file"
fi
echo ""

# Test 4: Try to download rechazo (may not exist)
echo "4. GET /api/v1/artifacts/${LATEST_DID}/rechazo"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/v1/artifacts/${LATEST_DID}/rechazo")
if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Rechazo XML exists and downloaded"
elif [ "$HTTP_CODE" = "404" ]; then
    echo "ℹ️  Rechazo XML not found (HTTP 404) - This is normal if there's no rejection"
else
    echo "❌ Unexpected HTTP code: $HTTP_CODE"
fi
echo ""

# Test 5: Try to download metadata (may not exist)
echo "5. GET /api/v1/artifacts/${LATEST_DID}/meta"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/v1/artifacts/${LATEST_DID}/meta")
if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Metadata JSON exists and downloaded"
elif [ "$HTTP_CODE" = "404" ]; then
    echo "ℹ️  Metadata not found (HTTP 404) - This is normal if no metadata was saved"
else
    echo "❌ Unexpected HTTP code: $HTTP_CODE"
fi
echo ""

# Test 6: Test invalid dId
echo "6. GET /api/v1/artifacts/invalid (should return 400)"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/v1/artifacts/invalid")
if [ "$HTTP_CODE" = "400" ]; then
    echo "✅ Correctly returned 400 for invalid dId"
else
    echo "❌ Expected 400, got $HTTP_CODE"
fi
echo ""

# Test 7: Test non-existent dId
echo "7. GET /api/v1/artifacts/9999999999 (should return 404)"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/v1/artifacts/9999999999")
if [ "$HTTP_CODE" = "404" ]; then
    echo "✅ Correctly returned 404 for non-existent dId"
else
    echo "❌ Expected 404, got $HTTP_CODE"
fi
echo ""

# Cleanup
echo "Cleanup..."
rm -f "downloaded_de_${LATEST_DID}.xml"
echo "✅ Test completed!"
