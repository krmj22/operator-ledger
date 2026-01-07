#!/usr/bin/env python3
"""
Tests for generate_commit_summary.py

Tests verify:
1. Time-bucketed summary generation (7d, 30d, 90d)
2. Compact output format (<200 lines)
3. Decision aggregation with days_since calculation
4. Skill activity aggregation by time window
"""

import pytest
import yaml
from pathlib import Path
from datetime import datetime, timedelta, timezone
from generate_commit_summary import (
    calculate_activity_window,
    aggregate_decision_activity,
    aggregate_skill_activity,
    generate_commit_activity_summary
)


@pytest.fixture
def sample_commit_index():
    """Create sample commit index data for testing."""
    today = datetime.now(timezone.utc)

    return {
        "indexed_at": today.isoformat(),
        "repos": [
            {
                "name": "operator",
                "url": "https://github.com/user/operator",
                "commits": [
                    {
                        "sha": "abc123",
                        "message": "feat(ledger): add skill validation\n\nfeat: Python Development\nfeat: Systems Design",
                        "author": "user@example.com",
                        "date": (today - timedelta(days=3)).isoformat(),
                        "files_changed": 5,
                        "additions": 100,
                        "deletions": 20
                    },
                    {
                        "sha": "def456",
                        "message": "fix(parser): handle edge case\n\nfeat: Python Development",
                        "author": "user@example.com",
                        "date": (today - timedelta(days=10)).isoformat(),
                        "files_changed": 2,
                        "additions": 30,
                        "deletions": 10
                    },
                    {
                        "sha": "ghi789",
                        "message": "docs: update README",
                        "author": "user@example.com",
                        "date": (today - timedelta(days=50)).isoformat(),
                        "files_changed": 1,
                        "additions": 15,
                        "deletions": 5
                    }
                ]
            },
            {
                "name": "test-repo",
                "url": "https://github.com/user/test-repo",
                "commits": [
                    {
                        "sha": "xyz999",
                        "message": "feat: implement UI\n\nfeat: TypeScript Development",
                        "author": "user@example.com",
                        "date": (today - timedelta(days=5)).isoformat(),
                        "files_changed": 8,
                        "additions": 200,
                        "deletions": 50
                    }
                ]
            }
        ]
    }


@pytest.fixture
def sample_commit_decisions():
    """Create sample commit decisions data for testing."""
    today = datetime.now(timezone.utc)

    return {
        "decisions": [
            {
                "id": "DEC-GH-001",
                "decision": "Use vanilla HTML/Canvas",
                "date": (today - timedelta(days=25)).strftime("%Y-%m-%d"),
                "status": "active"
            },
            {
                "id": "DEC-GH-002",
                "decision": "Implement TDD protocol",
                "date": (today - timedelta(days=10)).strftime("%Y-%m-%d"),
                "status": "active"
            }
        ],
        "skill_evidence": []
    }


def test_calculate_activity_window_7_days(sample_commit_index):
    """Test 7-day activity window calculation."""
    window = calculate_activity_window(sample_commit_index, days=7)

    assert window["repos_active"] == 2  # operator and test-repo
    assert window["commits"] == 2  # abc123 and xyz999 (within 7 days)
    assert "top_skills" in window
    assert isinstance(window["top_skills"], list)


def test_calculate_activity_window_30_days(sample_commit_index):
    """Test 30-day activity window calculation."""
    window = calculate_activity_window(sample_commit_index, days=30)

    assert window["repos_active"] == 2
    assert window["commits"] == 3  # abc123, def456, xyz999
    assert len(window["top_skills"]) > 0


def test_calculate_activity_window_90_days(sample_commit_index):
    """Test 90-day activity window calculation."""
    window = calculate_activity_window(sample_commit_index, days=90)

    assert window["repos_active"] == 2
    assert window["commits"] == 4  # All commits


def test_aggregate_decision_activity(sample_commit_decisions):
    """Test decision activity aggregation with days_since calculation."""
    decisions = aggregate_decision_activity(sample_commit_decisions)

    assert len(decisions) >= 1
    assert "id" in decisions[0]
    assert "decision" in decisions[0]
    assert "date" in decisions[0]
    assert "status" in decisions[0]
    assert "days_since" in decisions[0]
    assert decisions[0]["days_since"] >= 0


def test_aggregate_skill_activity(sample_commit_index):
    """Test skill activity aggregation with repo lists and recent dates."""
    skills = aggregate_skill_activity(sample_commit_index, days=30)

    assert len(skills) > 0
    assert "skill" in skills[0]
    assert "commits_last_30d" in skills[0]
    assert "repos" in skills[0]
    assert "most_recent" in skills[0]
    assert isinstance(skills[0]["repos"], list)


def test_generate_commit_activity_summary_structure(sample_commit_index, sample_commit_decisions, tmp_path):
    """Test that generated summary has correct structure."""
    output_path = tmp_path / "commit_activity.yaml"

    generate_commit_activity_summary(
        sample_commit_index,
        sample_commit_decisions,
        output_path
    )

    # Load and verify structure
    with open(output_path, 'r') as f:
        data = yaml.safe_load(f)

    assert "activity_windows" in data
    assert "last_7_days" in data["activity_windows"]
    assert "last_30_days" in data["activity_windows"]
    assert "last_90_days" in data["activity_windows"]

    # Verify window structure
    for window_name in ["last_7_days", "last_30_days", "last_90_days"]:
        window = data["activity_windows"][window_name]
        assert "repos_active" in window
        assert "commits" in window
        assert "top_skills" in window
        assert "decisions_made" in window

    assert "recent_decisions" in data
    assert "skill_activity" in data


def test_generate_commit_activity_summary_size(sample_commit_index, sample_commit_decisions, tmp_path):
    """Test that generated summary is <200 lines."""
    output_path = tmp_path / "commit_activity.yaml"

    generate_commit_activity_summary(
        sample_commit_index,
        sample_commit_decisions,
        output_path
    )

    # Count lines
    with open(output_path, 'r') as f:
        lines = f.readlines()

    assert len(lines) < 200, f"Output has {len(lines)} lines, expected <200"


def test_decision_days_since_calculation(sample_commit_decisions):
    """Test that days_since is calculated correctly for decisions."""
    decisions = aggregate_decision_activity(sample_commit_decisions)

    # First decision should be ~25 days ago
    assert decisions[0]["days_since"] >= 24 and decisions[0]["days_since"] <= 26

    # Second decision should be ~10 days ago
    if len(decisions) > 1:
        assert decisions[1]["days_since"] >= 9 and decisions[1]["days_since"] <= 11


def test_skill_activity_repo_aggregation(sample_commit_index):
    """Test that skill activity correctly aggregates repos."""
    skills = aggregate_skill_activity(sample_commit_index, days=30)

    # Find Python Development skill
    python_skill = next((s for s in skills if s["skill"] == "Python Development"), None)
    assert python_skill is not None
    assert "operator" in python_skill["repos"]
    assert python_skill["commits_last_30d"] >= 2


def test_determinism():
    """Test that generation is deterministic across multiple runs."""
    # Create fixed test data
    fixed_date = datetime(2025, 12, 1, tzinfo=timezone.utc)

    test_index = {
        "indexed_at": fixed_date.isoformat(),
        "repos": [
            {
                "name": "test",
                "url": "https://github.com/user/test",
                "commits": [
                    {
                        "sha": "abc123",
                        "message": "feat: test\n\nfeat: Python Development",
                        "author": "user@example.com",
                        "date": fixed_date.isoformat(),
                        "files_changed": 1,
                        "additions": 10,
                        "deletions": 0
                    }
                ]
            }
        ]
    }

    test_decisions = {"decisions": [], "skill_evidence": []}

    # Generate 3 times
    results = []
    for i in range(3):
        from io import StringIO
        import sys

        # Capture output
        output = StringIO()

        # Would need to modify function to accept StringIO or return data
        # For now, verify data structure is deterministic
        window = calculate_activity_window(test_index, days=7)
        results.append(str(window))

    # All results should be identical
    assert results[0] == results[1] == results[2], "Results are not deterministic"
