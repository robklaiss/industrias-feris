#!/bin/bash

echo "=== Verification script for artifacts API fix ==="
echo

# 1. Kill any existing uvicorn process
echo "1. Killing existing uvicorn processes..."
pkill -f uvicorn || true
sleep 1

# 2. Start the server
echo "2. Starting server..."
cd /Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/tesaka-cv
SIFEN_ENV=test SIFEN_DEBUG=1 python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/uvicorn.log 2>&1 &
SERVER_PID=$!
sleep 3

# Check if server started
if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "❌ Server failed to start. Check /tmp/uvicorn.log"
    exit 1
fi

echo "✅ Server started with PID $SERVER_PID"

# 3. Test endpoints
echo
echo "3. Testing endpoints..."

echo -n "  Testing /api/v1/artifacts/4554737-820260124_225655 ... "
RESPONSE=$(curl -s http://127.0.0.1:8000/api/v1/artifacts/4554737-820260124_225655)
if echo "$RESPONSE" | jq -e '.dId == "4554737-820260124_225655"' > /dev/null 2>&1; then
    echo "✅ OK"
else
    echo "❌ FAILED"
    echo "$RESPONSE"
fi

echo -n "  Testing /api/v1/artifacts/4554737-820260124_225655/de ... "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/v1/artifacts/4554737-820260124_225655/de)
if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ OK (HTTP $HTTP_CODE)"
else
    echo "❌ FAILED (HTTP $HTTP_CODE)"
fi

echo -n "  Testing /api/v1/artifacts/latest ... "
RESPONSE=$(curl -s http://127.0.0.1:8000/api/v1/artifacts/latest)
if echo "$RESPONSE" | jq -e '.dId' > /dev/null 2>&1; then
    echo "✅ OK"
    echo "    Latest dId: $(echo "$RESPONSE" | jq -r '.dId')"
else
    echo "❌ FAILED"
    echo "$RESPONSE"
fi

# 4. Test with debug output
echo
echo "4. Testing with SIFEN_DEBUG=1 (check server logs)..."
curl -s http://127.0.0.1:8000/api/v1/artifacts/4554737-820260124_225655 > /dev/null
echo "  Check debug output in /tmp/uvicorn.log"

# 5. Cleanup
echo
echo "5. Cleaning up..."
kill $SERVER_PID
sleep 1

echo
echo "=== Verification complete ==="
echo
echo "Manual commands to test:"
echo "1. Start server: cd tesaka-cv && SIFEN_ENV=test python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
echo "2. Test: curl -s http://127.0.0.1:8000/api/v1/artifacts/4554737-820260124_225655 | jq ."
echo "3. Test DE: curl -s http://127.0.0.1:8000/api/v1/artifacts/4554737-820260124_225655/de | head -20"
echo "4. Test latest: curl -s http://127.0.0.1:8000/api/v1/artifacts/latest | jq ."
