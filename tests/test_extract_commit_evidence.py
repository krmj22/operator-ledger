"""
Test extract_commit_evidence.py script.

Tests decision extraction, skill evidence generation, and error handling.
"""

import yaml
import sys
from pathlib import Path

# Add parent directory to path to import the script
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from extract_commit_evidence import (
    parse_decision_from_message,
    extract_decision_from_pattern,
    extract_skill_from_files,
    generate_commit_decisions,
)


def test_parse_decision_from_message_with_metadata():
    """Test parsing commit message with full decision metadata."""
    message = """feat(pdf-redactor): implement vanilla HTML/Canvas UI

Decision: Use vanilla HTML/Canvas instead of React
Reasoning: Simplicity > features, no build step overhead
Alternatives: React (rejected), Vue (rejected)
Transcript: TerminalSavedOutput_251120.json:msg_45
Outcome: Direct canvas manipulation without framework abstraction
"""

    result = parse_decision_from_message(message)

    assert result is not None
    assert result["decision"] == "Use vanilla HTML/Canvas instead of React"
    assert result["reasoning"] == "Simplicity > features, no build step overhead"
    assert len(result["alternatives"]) == 2
    assert result["alternatives"][0]["name"] == "React"
    assert result["alternatives"][0]["rejected_because"] == "rejected"
    assert result["transcript_ref"] == "TerminalSavedOutput_251120.json:msg_45"
    assert result["outcome"] == "Direct canvas manipulation without framework abstraction"


def test_parse_decision_from_message_without_metadata():
    """Test parsing commit message without decision metadata - should return None."""
    message = """feat(ledger): add query_ledger interface

Basic feature without decision metadata.
"""

    result = parse_decision_from_message(message)
    assert result is None


def test_extract_skill_from_files_python():
    """Test skill extraction from Python files."""
    files = ["src/parser.py", "tests/test_parser.py", "utils/helper.py"]

    skills = extract_skill_from_files(files)

    assert "Python Development" in skills


def test_extract_skill_from_files_typescript():
    """Test skill extraction from TypeScript files."""
    files = ["src/app.ts", "src/components.tsx"]

    skills = extract_skill_from_files(files)

    assert "TypeScript Development" in skills


def test_extract_skill_from_files_multiple():
    """Test skill extraction from multiple file types."""
    files = ["src/app.py", "src/util.js", "README.md"]

    skills = extract_skill_from_files(files)

    assert "Python Development" in skills
    assert "JavaScript Development" in skills
    assert "Documentation" in skills


def test_generate_commit_decisions_structure():
    """Test that generate_commit_decisions creates valid YAML structure."""
    # Create minimal test data
    test_commits = [
        {
            "sha": "abc123",
            "message": """feat(test): test feature

Decision: Use approach A
Reasoning: Because B
Alternatives: C (rejected)
Outcome: Success
""",
            "date": "2025-12-15T00:00:00Z",
            "files": ["test.py"]
        }
    ]

    result = generate_commit_decisions(test_commits)

    # Check structure
    assert "decisions" in result
    assert "skill_evidence" in result

    # Check decision structure
    decisions = result["decisions"]
    assert len(decisions) >= 1

    decision = decisions[0]
    assert "id" in decision
    assert "decision" in decision
    assert "reasoning" in decision
    assert "commit_sha" in decision
    assert "commit_date" in decision
    assert "status" in decision

    # Check skill evidence structure
    skill_evidence = result["skill_evidence"]
    assert len(skill_evidence) >= 1

    evidence = skill_evidence[0]
    assert "skill" in evidence
    assert "commits" in evidence
    assert "confidence" in evidence
    assert "evidence_type" in evidence


def test_script_handles_no_decisions_gracefully():
    """Test that script handles commits without decisions without errors."""
    test_commits = [
        {
            "sha": "xyz789",
            "message": "fix: simple bug fix\n\nNo decision metadata here.",
            "date": "2025-12-15T00:00:00Z",
            "files": ["src/app.py"]
        }
    ]

    result = generate_commit_decisions(test_commits)

    # Should still generate structure
    assert "decisions" in result
    assert "skill_evidence" in result

    # Decisions should be empty
    assert len(result["decisions"]) == 0

    # Skill evidence should still be generated
    assert len(result["skill_evidence"]) >= 1


# ============================================
# Pattern Detection Tests (Phase 5 - Issue #93)
# ============================================

def test_pattern_use_instead_of():
    """Test 'use X instead of Y' pattern detection."""
    message = "feat: use GitHub instead of PyPI for private distribution"

    result = extract_decision_from_pattern(message)

    assert result is not None
    assert "github" in result["decision"].lower()
    assert result["confidence"] >= 0.8
    assert result["extraction_method"] == "pattern"


def test_pattern_switch_from_to():
    """Test 'switch from X to Y' pattern detection."""
    message = "refactor: switch from React to vanilla HTML for simplicity"

    result = extract_decision_from_pattern(message)

    assert result is not None
    assert "vanilla" in result["decision"].lower() or "html" in result["decision"].lower()
    assert result["confidence"] >= 0.8


def test_pattern_before_after():
    """Test BEFORE/AFTER structure detection."""
    message = """refactor: consolidate deployment

BEFORE:
- Separate deployment folder
- Multiple packages

AFTER:
- Single unified package
- All materials in one place
"""

    result = extract_decision_from_pattern(message)

    assert result is not None
    assert result["confidence"] >= 0.6


def test_pattern_remove_with_reasoning():
    """Test 'remove X' pattern with reasoning."""
    message = "refactor: remove enterprise bloat - single machine use"

    result = extract_decision_from_pattern(message)

    assert result is not None
    assert "remove" in result["decision"].lower()
    assert result["confidence"] >= 0.7


def test_pattern_why_explanation():
    """Test 'Why:' explanation extraction."""
    message = """feat: create self-contained demo package

Why: Private repo sharing with accountant, no PyPI needed
What: Demo package with embedded source
"""

    result = extract_decision_from_pattern(message)

    assert result is not None
    assert "reasoning" in result
    assert "private" in result["reasoning"].lower() or "pypi" in result["reasoning"].lower()


def test_pattern_adr_reference():
    """Test ADR reference detection (high confidence)."""
    message = "docs: add ADR 0005 for GitHub distribution strategy"

    result = extract_decision_from_pattern(message)

    assert result is not None
    assert "ADR" in result["decision"]
    assert result["confidence"] >= 0.9


def test_pattern_refactor_consolidate():
    """Test refactoring keywords detection."""
    message = "refactor: consolidate deployment into demo package"

    result = extract_decision_from_pattern(message)

    assert result is not None
    assert result["confidence"] >= 0.6


def test_pattern_no_decision_in_simple_fix():
    """Test that simple fixes don't trigger false positives."""
    message = "fix: typo in README"

    result = extract_decision_from_pattern(message)

    # Should not extract a decision from a simple typo fix
    assert result is None


def test_pattern_confidence_threshold():
    """Test that low-confidence patterns are rejected."""
    message = "chore: update dependencies"

    result = extract_decision_from_pattern(message)

    # Generic chores shouldn't be detected as decisions
    assert result is None


def test_structured_takes_precedence():
    """Test that structured format takes precedence over pattern detection."""
    message = """feat: implement new feature

Decision: Use approach A over approach B
Reasoning: Better performance and maintainability
Alternatives: Approach B (rejected)
"""

    result = parse_decision_from_message(message)

    assert result is not None
    assert result["extraction_method"] == "structured"
    assert result["confidence"] == 1.0


def test_decision_includes_confidence():
    """Test that extracted decisions include confidence scores."""
    test_commits = [
        {
            "sha": "abc123",
            "message": "refactor: switch from React to vanilla JS",
            "date": "2025-12-15T00:00:00Z",
            "files": ["src/app.js"]
        }
    ]

    result = generate_commit_decisions(test_commits)

    assert len(result["decisions"]) >= 1
    decision = result["decisions"][0]
    assert "confidence" in decision
    assert "extraction_method" in decision
    assert decision["confidence"] >= 0.6
