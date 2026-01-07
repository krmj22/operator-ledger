#!/usr/bin/env python3
"""
Generate compact commit activity summary from commit_index.yaml and commit_decisions.yaml.

Output: commit_activity.yaml with time-bucketed summaries (<200 lines, <100ms load time)

Usage:
    python3 ledger/scripts/generate_commit_summary.py
"""

import yaml
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any
from collections import defaultdict
import re


def load_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML file and return parsed data."""
    if not path.exists():
        return {}

    with open(path, 'r') as f:
        return yaml.safe_load(f) or {}


def extract_skills_from_message(message: str) -> List[str]:
    """
    Extract skill mentions from commit message.

    Looks for patterns like:
    - "feat: Python Development"
    - "Python Development" in message body
    """
    skills = set()

    # Common skill patterns
    skill_patterns = [
        "Python Development",
        "TypeScript Development",
        "JavaScript Development",
        "Systems Design",
        "PDF Processing",
        "UI Design",
        "Web Development",
        "Database Development",
        "Shell Scripting",
        "Documentation",
        "Configuration Management",
    ]

    for skill in skill_patterns:
        if skill.lower() in message.lower():
            skills.add(skill)

    return sorted(skills)


def calculate_activity_window(commit_index: Dict[str, Any], days: int) -> Dict[str, Any]:
    """
    Calculate activity metrics for a time window.

    Args:
        commit_index: Parsed commit_index.yaml data
        days: Number of days in window

    Returns:
        Dict with repos_active, commits, top_skills, decisions_made
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    repos_active = set()
    commits_in_window = []
    skill_counts = defaultdict(int)

    for repo in commit_index.get("repos", []):
        repo_name = repo.get("name", "")
        has_commits_in_window = False

        for commit in repo.get("commits", []):
            commit_date_str = commit.get("date", "")
            try:
                # Parse ISO format date
                commit_date = datetime.fromisoformat(commit_date_str.replace('Z', '+00:00'))

                if commit_date >= cutoff_date:
                    has_commits_in_window = True
                    commits_in_window.append(commit)

                    # Extract skills from commit message
                    skills = extract_skills_from_message(commit.get("message", ""))
                    for skill in skills:
                        skill_counts[skill] += 1

            except (ValueError, TypeError):
                pass

        if has_commits_in_window:
            repos_active.add(repo_name)

    # Get top skills (sorted by count)
    top_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)
    top_skills = [skill for skill, count in top_skills[:5]]

    return {
        "repos_active": len(repos_active),
        "commits": len(commits_in_window),
        "top_skills": top_skills,
        "decisions_made": 0  # Will be filled by aggregate_decision_activity
    }


def aggregate_decision_activity(commit_decisions: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Aggregate recent decisions with days_since calculation.

    Args:
        commit_decisions: Parsed commit_decisions.yaml data

    Returns:
        List of decision summaries with days_since field
    """
    decisions = []
    today = datetime.now(timezone.utc)

    for decision in commit_decisions.get("decisions", []):
        decision_date_str = decision.get("date", "")
        try:
            # Parse YYYY-MM-DD format
            decision_date = datetime.strptime(decision_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            days_since = (today - decision_date).days

            decisions.append({
                "id": decision.get("id", ""),
                "decision": decision.get("decision", ""),
                "date": decision_date_str,
                "status": decision.get("status", ""),
                "days_since": days_since
            })
        except (ValueError, TypeError):
            pass

    # Sort by date (most recent first)
    decisions.sort(key=lambda d: d["date"], reverse=True)

    return decisions


def aggregate_skill_activity(commit_index: Dict[str, Any], days: int) -> List[Dict[str, Any]]:
    """
    Aggregate skill activity with repo lists and most recent dates.

    Args:
        commit_index: Parsed commit_index.yaml data
        days: Number of days to look back

    Returns:
        List of skill activity summaries
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    skill_data = defaultdict(lambda: {"repos": set(), "commits": 0, "most_recent": None})

    for repo in commit_index.get("repos", []):
        repo_name = repo.get("name", "")

        for commit in repo.get("commits", []):
            commit_date_str = commit.get("date", "")
            try:
                commit_date = datetime.fromisoformat(commit_date_str.replace('Z', '+00:00'))

                if commit_date >= cutoff_date:
                    skills = extract_skills_from_message(commit.get("message", ""))

                    for skill in skills:
                        skill_data[skill]["repos"].add(repo_name)
                        skill_data[skill]["commits"] += 1

                        # Track most recent date
                        if (skill_data[skill]["most_recent"] is None or
                            commit_date > skill_data[skill]["most_recent"]):
                            skill_data[skill]["most_recent"] = commit_date

            except (ValueError, TypeError):
                pass

    # Convert to list format
    skill_activity = []
    for skill_name, data in sorted(skill_data.items()):
        most_recent_str = data["most_recent"].strftime("%Y-%m-%d") if data["most_recent"] else None

        skill_activity.append({
            "skill": skill_name,
            "commits_last_30d": data["commits"],
            "repos": sorted(list(data["repos"])),
            "most_recent": most_recent_str
        })

    # Sort by commit count (descending)
    skill_activity.sort(key=lambda s: s["commits_last_30d"], reverse=True)

    return skill_activity


def count_decisions_in_window(decisions: List[Dict[str, Any]], days: int) -> int:
    """Count decisions made within the specified window."""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    count = 0

    for decision in decisions:
        decision_date_str = decision.get("date", "")
        try:
            decision_date = datetime.strptime(decision_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if decision_date >= cutoff_date:
                count += 1
        except (ValueError, TypeError):
            pass

    return count


def generate_commit_activity_summary(
    commit_index: Dict[str, Any],
    commit_decisions: Dict[str, Any],
    output_path: Path
):
    """
    Generate compact commit_activity.yaml summary.

    Args:
        commit_index: Parsed commit_index.yaml data
        commit_decisions: Parsed commit_decisions.yaml data
        output_path: Path to write commit_activity.yaml
    """
    # Calculate activity windows
    window_7d = calculate_activity_window(commit_index, days=7)
    window_30d = calculate_activity_window(commit_index, days=30)
    window_90d = calculate_activity_window(commit_index, days=90)

    # Get decision activity
    all_decisions = aggregate_decision_activity(commit_decisions)

    # Update decision counts for windows
    window_7d["decisions_made"] = count_decisions_in_window(all_decisions, days=7)
    window_30d["decisions_made"] = count_decisions_in_window(all_decisions, days=30)
    window_90d["decisions_made"] = count_decisions_in_window(all_decisions, days=90)

    # Get skill activity
    skill_activity = aggregate_skill_activity(commit_index, days=30)

    # Assemble output
    output_data = {
        "activity_windows": {
            "last_7_days": window_7d,
            "last_30_days": window_30d,
            "last_90_days": window_90d
        },
        "recent_decisions": all_decisions[:5],  # Top 5 most recent
        "skill_activity": skill_activity
    }

    # Write to YAML
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        yaml.dump(output_data, f, default_flow_style=False, sort_keys=False)


def main():
    """Main entry point."""
    # Determine paths
    script_dir = Path(__file__).parent
    ledger_dir = script_dir.parent

    commit_index_path = ledger_dir / "commit_index.yaml"
    commit_decisions_path = ledger_dir / "commit_decisions.yaml"
    output_path = ledger_dir / "commit_activity.yaml"

    # Load data
    commit_index = load_yaml(commit_index_path)
    commit_decisions = load_yaml(commit_decisions_path)

    # Generate summary
    generate_commit_activity_summary(commit_index, commit_decisions, output_path)

    # Report results
    with open(output_path, 'r') as f:
        lines = len(f.readlines())

    print(f"Generated commit_activity.yaml ({lines} lines)")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
