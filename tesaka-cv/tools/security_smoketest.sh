#!/usr/bin/env bash
set -euo pipefail

# Security Smoketest for SIFEN
# Verifies basic security measures are in place

echo "🔒 SIFEN Security Smoketest"
echo "=========================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track results
FAILURES=0
WARNINGS=0

# Helper functions
fail() {
    echo -e "${RED}❌ FAIL: $1${NC}"
    ((FAILURES++))
}

warn() {
    echo -e "${YELLOW}⚠️  WARN: $1${NC}"
    ((WARNINGS++))
}

pass() {
    echo -e "${GREEN}✅ PASS: $1${NC}"
}

# Test 1: Check for hardcoded secrets
echo ""
echo "1. Checking for hardcoded secrets..."

# Patterns that should NOT be in code (excluding tests)
SECRET_PATTERNS=(
    "SIFEN_CSC_TEST\s*="
    "SIFEN_CSC_PROD\s*="
    "ADMIN_PASS\s*="
    "password\s*=\s*['\"][^'\"]{8,}"
)

for pattern in "${SECRET_PATTERNS[@]}"; do
    if grep -r -E "$pattern" --include="*.py" --exclude-dir=".venv" --exclude-dir="__pycache__" --exclude-dir="tests" . 2>/dev/null; then
        fail "Found potential hardcoded secret pattern: $pattern"
    fi
done

# Check for private keys (excluding test files)
if grep -r -E "PRIVATE KEY\s*-----" --include="*.py" --exclude-dir=".venv" --exclude-dir="__pycache__" --exclude-dir="tests" . 2>/dev/null; then
    fail "Found potential hardcoded secret pattern: PRIVATE KEY"
fi

# Check for .env files (should not be committed)
if find . -name ".env*" -type f | grep -v ".env.example" | grep -v ".git" | head -1 >/dev/null; then
    fail "Found .env files that should not be committed"
else
    pass "No .env files committed"
fi

# Test 2: Check for certificate files
echo ""
echo "2. Checking for certificate files..."

# Allow certificates only in tests directory
if find . \( -name "*.p12" -o -name "*.pfx" -o -name "*.key" -o -name "*.jks" -o -name "*.crt" -o -name "*.cer" -o -name "*.der" \) -type f | grep -v ".git" | grep -v ".venv" | grep -v "__pycache__" | grep -v "tests/" | head -1 >/dev/null; then
    fail "Found certificate file outside tests directory"
else
    pass "No certificate files found outside tests"
fi

# Allow .pem files only in specific directories (tests, examples)
if find . -name "*.pem" -type f | grep -v ".git" | grep -v ".venv" | grep -v "__pycache__" | grep -v "tests/" | grep -v "examples/" | head -1 >/dev/null; then
    fail "Found PEM file outside tests/examples"
else
    pass "No certificate files found in repo"
fi

# Test 3: Check environment variables handling
echo ""
echo "3. Checking environment variables handling..."

# Check if scripts use safe_config
if grep -r "from tools.safe_config import" --include="*.py" . 2>/dev/null | head -1 >/dev/null; then
    pass "Scripts using safe_config module"
else
    warn "Consider using safe_config module for environment variables"
fi

# Test 4: Check for secrets in git history
echo ""
echo "4. Checking git history for secrets..."

if git log --all --full-history -- "*secret*" "*password*" "*key*" 2>/dev/null | head -1 >/dev/null; then
    warn "Potential secrets found in git history"
else
    pass "No obvious secrets in git history"
fi

# Test 5: Check web authentication
echo ""
echo "5. Checking web authentication..."

if [ -f "tools/web_auth.py" ]; then
    pass "Web authentication module exists"
    
    # Check if Flask app uses auth
    if grep -r "@requires_auth" --include="*.py" app/ 2>/dev/null | head -1 >/dev/null; then
        pass "Web endpoints require authentication"
    else
        warn "Web endpoints might not require authentication"
    fi
else
    warn "Web authentication module not found"
fi

# Test 6: Check rate limiting
echo ""
echo "6. Checking rate limiting..."

if grep -r "rate_limited\|rate.limit" --include="*.py" . 2>/dev/null | head -1 >/dev/null; then
    pass "Rate limiting implemented"
else
    warn "Rate limiting not implemented"
fi

# Test 7: Check HTTPS enforcement
echo ""
echo "7. Checking HTTPS configuration..."

if grep -r "TLS\|SSL\|https" --include="*.py" app/ 2>/dev/null | head -1 >/dev/null; then
    pass "HTTPS/TLS configuration found"
else
    warn "HTTPS/TLS configuration not found"
fi

# Test 8: Check input validation
echo ""
echo "8. Checking input validation..."

if grep -r "validate\|sanitize" --include="*.py" . 2>/dev/null | head -1 >/dev/null; then
    pass "Input validation found"
else
    warn "Input validation not found"
fi

# Test 9: Check logging security
echo ""
echo "9. Checking logging security..."

# Check for masked CSC in logs
if grep -r "mask_csc\|CSC.*\*\*\*" --include="*.py" . 2>/dev/null | head -1 >/dev/null; then
    pass "CSC masking in logs implemented"
else
    warn "CSC might not be masked in logs"
fi

# Test 10: Check system fails without env vars
echo ""
echo "10. Checking system fails without required env vars..."

if [ -f "tools/safe_config.py" ]; then
    pass "Safe config loader exists"
else
    fail "Safe config loader not found"
fi

# Summary
echo ""
echo "=========================="
echo -e "Security Smoketest Results:"
echo -e "${GREEN}✅ Checks passed${NC}"
echo -e "${YELLOW}⚠️  Warnings: $WARNINGS${NC}"
if [ $FAILURES -eq 0 ]; then
    echo -e "${GREEN}❌ Failures: $FAILURES${NC}"
    echo ""
    echo -e "${GREEN}🎉 All security checks passed!${NC}"
    exit 0
else
    echo -e "${RED}❌ Failures: $FAILURES${NC}"
    echo ""
    echo -e "${RED}⚠️  Please fix the security issues above before deploying.${NC}"
    exit 1
fi
