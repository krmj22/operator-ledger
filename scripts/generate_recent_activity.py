#!/usr/bin/env python3
"""
Generate Recent Activity Summary
Generates recent_activity.yaml from sessions.yaml with time-windowed summaries.

Part of Issue #54: Generate weekly recent_activity.yaml from sessions.
"""

import yaml
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict
from collections import Counter


def load_sessions(sessions_yaml: Path) -> List[Dict]:
    """Load sessions from sessions.yaml."""
    if not sessions_yaml.exists():
        return []

    with open(sessions_yaml, 'r') as f:
        data = yaml.safe_load(f)
        return data.get("sessions", [])


def filter_by_last_n_days(sessions: List[Dict], n: int) -> List[Dict]:
    """Return sessions from the last N days."""
    cutoff_date = datetime.now() - timedelta(days=n)

    filtered = []
    for session in sessions:
        start_time_str = session.get("start_time", "")
        if not start_time_str:
            continue

        try:
            start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            if start_time >= cutoff_date:
                filtered.append(session)
        except Exception:
            continue

    return sorted(filtered, key=lambda s: s.get("start_time", ""), reverse=True)


def extract_project_name(session: Dict) -> str:
    """Extract project name from session, using project_context or working_directory."""
    project_context = session.get("project_context")
    if project_context and project_context.get("project_name"):
        return project_context["project_name"]

    # Fallback to basename of working_directory (deterministic, factual)
    working_dir = session.get("working_directory")
    if working_dir:
        return Path(working_dir).name

    return "unknown"


def extract_accomplishments(activity_summary: str) -> bool:
    """Check if activity summary contains accomplishment indicators (concrete action verbs)."""
    if not activity_summary:
        return False

    # Pattern match for concrete action verbs indicating completion
    accomplishment_patterns = [
        r'\b(completed|finished|done)\b',
        r'\b(implemented|created|built|developed)\b',
        r'\b(fixed|resolved|solved)\b',
        r'\b(deployed|released|shipped)\b',
        r'\b(added|updated|upgraded)\b',
        r'\b(refactored|optimized|improved)\b',
    ]

    summary_lower = activity_summary.lower()
    for pattern in accomplishment_patterns:
        if re.search(pattern, summary_lower):
            return True

    return False


def aggregate_window_data(sessions: List[Dict]) -> Dict:
    """Aggregate sessions into projects, skills, and accomplishments."""
    projects = []
    all_skills = []
    accomplishments = []

    for session in sessions:
        # Extract project
        project = extract_project_name(session)
        if project and project != "unknown":
            projects.append(project)

        # Extract skills
        skills = session.get("skills_demonstrated", [])
        all_skills.extend(skills)

        # Extract accomplishments
        activity_summary = session.get("activity_summary", "")
        if extract_accomplishments(activity_summary):
            accomplishments.append({
                "date": session.get("date", "unknown"),
                "summary": activity_summary[:80]  # Truncate for brevity
            })

    # Count frequencies
    project_counts = Counter(projects)
    skill_counts = Counter(all_skills)

    # Get top items (limit to keep output concise)
    top_projects = [{"name": p, "sessions": c} for p, c in project_counts.most_common(5)]
    top_skills = [{"name": s, "count": c} for s, c in skill_counts.most_common(8)]
    top_accomplishments = accomplishments[:5]  # Most recent 5

    return {
        "total_sessions": len(sessions),
        "projects": top_projects,
        "skills": top_skills,
        "accomplishments": top_accomplishments
    }


def generate_recent_activity(sessions_yaml: Path, output_yaml: Path):
    """Generate recent_activity.yaml from sessions.yaml."""

    # Load all sessions
    all_sessions = load_sessions(sessions_yaml)

    if not all_sessions:
        print(f"⚠️  No sessions found in {sessions_yaml}")
        return

    # Filter by time windows
    last_7_days = filter_by_last_n_days(all_sessions, 7)
    last_30_days = filter_by_last_n_days(all_sessions, 30)
    last_90_days = filter_by_last_n_days(all_sessions, 90)

    # Aggregate data for each window
    data_7d = aggregate_window_data(last_7_days)
    data_30d = aggregate_window_data(last_30_days)
    data_90d = aggregate_window_data(last_90_days)

    # Build output structure
    output = {
        "generated_at": datetime.now().isoformat(),
        "last_7_days": data_7d,
        "last_30_days": data_30d,
        "last_90_days": data_90d
    }

    # Write YAML output
    with open(output_yaml, 'w') as f:
        yaml.dump(output, f, default_flow_style=False, sort_keys=False, width=100)

    # Verify output size
    line_count = sum(1 for _ in open(output_yaml))

    print(f"✓ Generated {output_yaml}")
    print(f"  - Last 7 days: {data_7d['total_sessions']} sessions")
    print(f"  - Last 30 days: {data_30d['total_sessions']} sessions")
    print(f"  - Last 90 days: {data_90d['total_sessions']} sessions")
    print(f"  - Output size: {line_count} lines")

    if line_count > 50:
        print(f"⚠️  Warning: Output exceeds 50 lines ({line_count} lines)")


def main():
    # Auto-detect paths
    script_dir = Path(__file__).parent
    operator_root = script_dir.parent
    sessions_yaml = operator_root / "ledger" / "activity" / "sessions.yaml"
    output_yaml = operator_root / "ledger" / "activity" / "recent_activity.yaml"

    # Validate sessions.yaml exists
    if not sessions_yaml.exists():
        print(f"❌ sessions.yaml not found at {sessions_yaml}")
        print("Run daily_ingestion.sh to populate sessions.yaml")
        return 1

    # Generate recent activity summary
    generate_recent_activity(sessions_yaml, output_yaml)

    return 0


if __name__ == "__main__":
    exit(main())
