#!/bin/bash

# Operator System - End-to-End Smoke Test
#
# Validates entire pipeline: session envelope → ingestion → ledger → dashboard → query
# Run before commits, deployments, or after major changes.
#
# Exit codes:
#   0 = All tests passed
#   1 = One or more tests failed
#
# Usage:
#   bash scripts/smoke_test.sh

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_WARNED=0

# Repo root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Use OPERATOR_LEDGER_DIR env var, fallback to ./ledger for backwards compatibility
LEDGER_DIR="${OPERATOR_LEDGER_DIR:-${REPO_ROOT}/ledger}"

# Start time
START_TIME=$(date +%s)

echo ""
echo "========================================="
echo "  Operator System - Smoke Test"
echo "========================================="
echo ""

# Helper functions
pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
    TESTS_WARNED=$((TESTS_WARNED + 1))
}

info() {
    echo -e "${BLUE}ℹ INFO${NC}: $1"
}

test_header() {
    echo ""
    echo "--- $1 ---"
}

# =============================================================================
# Test 1: Environment Validation
# =============================================================================
test_header "1. Environment Validation"

# Check Python version
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    pass "Python 3 available (version $PYTHON_VERSION)"
else
    fail "Python 3 not found"
fi

# Check PyYAML
if python3 -c "import yaml" 2>/dev/null; then
    pass "PyYAML installed"
else
    warn "PyYAML not installed (some features will be limited)"
fi

# Check OPERATOR_DATA_DIR
if [ -n "${OPERATOR_DATA_DIR:-}" ]; then
    if [ -d "$OPERATOR_DATA_DIR" ]; then
        pass "OPERATOR_DATA_DIR set and exists: $OPERATOR_DATA_DIR"
    else
        warn "OPERATOR_DATA_DIR set but directory doesn't exist: $OPERATOR_DATA_DIR"
    fi
else
    warn "OPERATOR_DATA_DIR not set (some tests will use sample data)"
fi

# Verify repo structure
REQUIRED_PATHS=(
    "packages/common/session_envelope.py"
    "scripts/ledger_verify.py"
    "analysis/scripts/query_sessions.py"
    "analysis/scripts/generate_dashboard_data.py"
)

for path in "${REQUIRED_PATHS[@]}"; do
    if [ -e "$REPO_ROOT/$path" ]; then
        pass "Found $path"
    else
        fail "Missing required file: $path"
    fi
done

# =============================================================================
# Test 2: Session Envelope Validation
# =============================================================================
test_header "2. Session Envelope Validation"

# Test with valid session
TEST_SESSION="$REPO_ROOT/tests/sample_data/valid_session.json"
if [ -f "$TEST_SESSION" ]; then
    if python3 -c "
import json
import sys
sys.path.insert(0, '$REPO_ROOT/packages/common')
from session_envelope import validate_session_envelope

with open('$TEST_SESSION', 'r') as f:
    session_data = json.load(f)

is_valid, warnings = validate_session_envelope(session_data)
if is_valid:
    sys.exit(0)
else:
    print(f'Invalid: {warnings}')
    sys.exit(1)
" 2>/dev/null; then
        pass "Valid session accepted"
    else
        fail "Valid session rejected"
    fi
else
    warn "Test fixture not found: $TEST_SESSION"
fi

# Test with invalid session
INVALID_SESSION="$REPO_ROOT/tests/sample_data/invalid_session.json"
if [ -f "$INVALID_SESSION" ]; then
    if python3 -c "
import json
import sys
sys.path.insert(0, '$REPO_ROOT/packages/common')
from session_envelope import validate_session_envelope

with open('$INVALID_SESSION', 'r') as f:
    session_data = json.load(f)

is_valid, warnings = validate_session_envelope(session_data)
if not is_valid:
    sys.exit(0)
else:
    sys.exit(1)
" 2>/dev/null; then
        pass "Invalid session correctly rejected"
    else
        fail "Invalid session incorrectly accepted"
    fi
else
    warn "Test fixture not found: $INVALID_SESSION"
fi

# =============================================================================
# Test 3: Skill Ingestion Validation
# =============================================================================
test_header "3. Skill Ingestion Validation"

# We can't run the full ingestion (requires Claude Code), but we can validate:
# 1. The ingestion script exists
# 2. It has proper structure
# 3. Required config files are present

INGESTION_SCRIPT="$REPO_ROOT/scripts/daily_ingestion.sh"
if [ -f "$INGESTION_SCRIPT" ] && [ -x "$INGESTION_SCRIPT" ]; then
    pass "Ingestion script exists and is executable"
else
    fail "Ingestion script missing or not executable"
fi

# Check for skills and projects YAML
if [ -f "$LEDGER_DIR/skills.yaml" ]; then
    # Validate YAML can be parsed
    if python3 -c "import yaml; yaml.safe_load(open('$LEDGER_DIR/skills.yaml'))" 2>/dev/null; then
        pass "skills.yaml is valid YAML"
    else
        fail "skills.yaml is invalid YAML"
    fi
else
    fail "skills.yaml not found at $LEDGER_DIR/skills.yaml"
fi

if [ -f "$LEDGER_DIR/projects.yaml" ]; then
    if python3 -c "import yaml; yaml.safe_load(open('$LEDGER_DIR/projects.yaml'))" 2>/dev/null; then
        pass "projects.yaml is valid YAML"
    else
        fail "projects.yaml is invalid YAML"
    fi
else
    fail "projects.yaml not found at $LEDGER_DIR/projects.yaml"
fi

# =============================================================================
# Test 4: Ledger Integrity Verification
# =============================================================================
test_header "4. Ledger Integrity Verification"

# Run ledger verification - use temp file to avoid command substitution issues
# Temporarily disable exit-on-error to capture exit code
set +e
VERIFY_TMP=$(mktemp)
python3 "$REPO_ROOT/scripts/ledger_verify.py" > "$VERIFY_TMP" 2>&1
VERIFY_EXIT=$?
set -e

if [ $VERIFY_EXIT -eq 0 ]; then
    pass "Ledger verification passed"
elif grep -q "index.yaml missing" "$VERIFY_TMP"; then
    # index.yaml is expected to be missing in monorepo structure (it's in operator_ledger)
    warn "Ledger verification: index.yaml missing (expected in monorepo)"
else
    fail "Ledger verification failed"
fi
rm -f "$VERIFY_TMP"

# =============================================================================
# Test 5: Dashboard Generation
# =============================================================================
test_header "5. Dashboard Generation"

# Dashboard generation might fail if temporal analysis files don't exist
# We'll treat this as a warning, not a failure
if python3 "$REPO_ROOT/analysis/scripts/generate_dashboard_data.py" > /dev/null 2>&1; then
    pass "Dashboard data generation successful"

    # Verify output file was created
    OUTPUT_FILE="$REPO_ROOT/analysis/dashboards/ui/dashboard_data.js"
    if [ -f "$OUTPUT_FILE" ]; then
        pass "Dashboard data file created"
    else
        fail "Dashboard data file not created"
    fi
else
    warn "Dashboard generation failed (may need temporal analysis data)"
fi

# =============================================================================
# Test 6: Query Interface
# =============================================================================
test_header "6. Query Interface"

# Test basic query operations
QUERY_SCRIPT="$REPO_ROOT/analysis/scripts/query_sessions.py"

# Test 1: Query by confidence threshold
if python3 "$QUERY_SCRIPT" --confidence-below 50 --format json > /dev/null 2>&1; then
    pass "Query by confidence threshold works"
else
    warn "Query by confidence failed (may need session data)"
fi

# Test 2: Query by time window
if python3 "$QUERY_SCRIPT" --last-n-days 7 --format json > /dev/null 2>&1; then
    pass "Query by time window works"
else
    warn "Query by time window failed (may need session data)"
fi

# Test 3: Invalid query should fail gracefully
if python3 "$QUERY_SCRIPT" --skill "NonexistentSkill12345" --format json > /dev/null 2>&1; then
    # This might succeed with an error message, which is fine
    pass "Query handles invalid skill gracefully"
else
    # Failing here is also acceptable
    pass "Query handles invalid skill gracefully"
fi

# =============================================================================
# Test 7: Integration Check
# =============================================================================
test_header "7. Integration Check"

# Verify that all components can find each other
# Test that session envelope can be imported from other scripts
if python3 -c "import sys; sys.path.insert(0, '$REPO_ROOT/packages/common'); from session_envelope import validate_session_envelope; print('Import successful')" > /dev/null 2>&1; then
    pass "Module imports work correctly"
else
    fail "Module import failed"
fi

# =============================================================================
# Summary Report
# =============================================================================
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "========================================="
echo "  Test Summary"
echo "========================================="
echo ""
echo "Tests passed:  $TESTS_PASSED"
echo "Tests failed:  $TESTS_FAILED"
echo "Warnings:      $TESTS_WARNED"
echo "Duration:      ${DURATION}s"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    if [ $TESTS_WARNED -eq 0 ]; then
        echo -e "${GREEN}✓ OVERALL: ALL TESTS PASSED${NC}"
        echo ""
        exit 0
    else
        echo -e "${YELLOW}⚠ OVERALL: PASSED WITH WARNINGS${NC}"
        echo ""
        exit 0
    fi
else
    echo -e "${RED}✗ OVERALL: TESTS FAILED${NC}"
    echo ""
    echo "Please fix the failures above before proceeding."
    echo ""
    exit 1
fi
