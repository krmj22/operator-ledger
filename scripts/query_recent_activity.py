#!/usr/bin/env python3
"""
Query Recent Activity
Query sessions.yaml for recent session activity and generate human-readable reports.

Part of Issue #45: Add session activity tracking to ledger.
"""

import yaml
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json


def load_sessions(sessions_yaml: Path) -> List[Dict]:
    """Load sessions from sessions.yaml."""
    if not sessions_yaml.exists():
        return []

    with open(sessions_yaml, 'r') as f:
        data = yaml.safe_load(f)
        return data.get("sessions", [])


def filter_by_last_n_sessions(sessions: List[Dict], n: int) -> List[Dict]:
    """Return the last N sessions, sorted by date descending."""
    # Sort by start_time descending (most recent first)
    sorted_sessions = sorted(
        sessions,
        key=lambda s: s.get("start_time", ""),
        reverse=True
    )
    return sorted_sessions[:n]


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

    # Sort by start_time descending
    return sorted(filtered, key=lambda s: s.get("start_time", ""), reverse=True)


def filter_by_project(sessions: List[Dict], project: str) -> List[Dict]:
    """Filter sessions by project name or alias."""
    filtered = []
    project_lower = project.lower()

    for session in sessions:
        project_context = session.get("project_context")
        if not project_context:
            continue

        project_id = project_context.get("project_id", "").lower()
        project_name = project_context.get("project_name", "").lower()

        if project_lower in project_id or project_lower in project_name:
            filtered.append(session)

    return filtered


def format_session_markdown(session: Dict, index: int) -> str:
    """Format a single session as markdown."""
    session_id = session.get("session_id", "unknown")[:8]
    date = session.get("date", "unknown")
    start_time = session.get("start_time", "")[:16]  # YYYY-MM-DDTHH:MM
    duration = session.get("duration_minutes", 0)
    interaction_count = session.get("interaction_count", 0)

    project_context = session.get("project_context")
    if project_context:
        project_name = project_context.get("project_name", "Unknown")
        project_id = project_context.get("project_id", "unknown")
        project_str = f"{project_name} ({project_id})"
    else:
        working_dir = session.get("working_directory", "unknown")
        project_str = f"Working dir: {working_dir}"

    activity_summary = session.get("activity_summary", "No summary available")
    skills = session.get("skills_demonstrated", [])
    skills_str = ", ".join(skills) if skills else "None detected"

    output = f"""
### {index}. Session {session_id} - {date}

**Time:** {start_time} | **Duration:** {duration:.1f} min | **Interactions:** {interaction_count}
**Project:** {project_str}
**Activity:** {activity_summary}
**Skills:** {skills_str}
"""
    return output.strip()


def format_session_table(session: Dict) -> str:
    """Format a single session as a table row."""
    session_id = session.get("session_id", "unknown")[:8]
    date = session.get("date", "unknown")
    duration = session.get("duration_minutes", 0)

    project_context = session.get("project_context")
    if project_context:
        project_str = project_context.get("project_id", "unknown")
    else:
        project_str = "unknown"

    skills = session.get("skills_demonstrated", [])
    skills_str = ", ".join(skills[:2]) if skills else "none"
    if len(skills) > 2:
        skills_str += f" +{len(skills) - 2}"

    return f"| {session_id} | {date} | {duration:4.1f} | {project_str:20} | {skills_str} |"


def output_markdown(sessions: List[Dict]):
    """Output sessions in markdown format."""
    if not sessions:
        print("No sessions found matching criteria.")
        return

    print(f"# Recent Session Activity\n")
    print(f"**Total sessions:** {len(sessions)}\n")

    for i, session in enumerate(sessions, 1):
        print(format_session_markdown(session, i))
        print()


def output_table(sessions: List[Dict]):
    """Output sessions in table format."""
    if not sessions:
        print("No sessions found matching criteria.")
        return

    print(f"\nRecent Session Activity ({len(sessions)} sessions)\n")
    print("| Session  | Date       | Duration | Project              | Skills |")
    print("|----------|------------|----------|----------------------|--------|")

    for session in sessions:
        print(format_session_table(session))


def output_json(sessions: List[Dict]):
    """Output sessions in JSON format."""
    print(json.dumps(sessions, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Query recent session activity from sessions.yaml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show last 3 sessions
  %(prog)s --last-n-sessions 3

  # Show sessions from last 7 days
  %(prog)s --last-n-days 7

  # Show sessions for specific project
  %(prog)s --project "Accounting OS"

  # Combine filters
  %(prog)s --last-n-days 30 --project BSP --format markdown
        """
    )

    parser.add_argument(
        "--last-n-sessions",
        type=int,
        metavar="N",
        help="Show last N sessions"
    )
    parser.add_argument(
        "--last-n-days",
        type=int,
        metavar="N",
        help="Show sessions from last N days"
    )
    parser.add_argument(
        "--project",
        type=str,
        metavar="PROJECT",
        help="Filter by project name or alias"
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "table", "json"],
        default="markdown",
        help="Output format (default: markdown)"
    )
    parser.add_argument(
        "--sessions-yaml",
        type=Path,
        help="Path to sessions.yaml (default: auto-detect)"
    )

    args = parser.parse_args()

    # Auto-detect sessions.yaml path
    if args.sessions_yaml:
        sessions_yaml = args.sessions_yaml
    else:
        # Assume script is in analysis/scripts/
        script_dir = Path(__file__).parent
        operator_root = script_dir.parent.parent
        sessions_yaml = operator_root / "packages" / "ledger" / "sessions.yaml"

    # Validate sessions.yaml exists
    if not sessions_yaml.exists():
        print(f"❌ sessions.yaml not found at {sessions_yaml}")
        print("Run daily_ingestion.sh to populate sessions.yaml")
        return 1

    # Load sessions
    all_sessions = load_sessions(sessions_yaml)

    if not all_sessions:
        print("No sessions found in sessions.yaml")
        return 0

    # Apply filters
    filtered_sessions = all_sessions

    if args.last_n_sessions:
        filtered_sessions = filter_by_last_n_sessions(filtered_sessions, args.last_n_sessions)

    if args.last_n_days:
        filtered_sessions = filter_by_last_n_days(filtered_sessions, args.last_n_days)

    if args.project:
        filtered_sessions = filter_by_project(filtered_sessions, args.project)

    # If no specific filters, default to last 10 sessions
    if not any([args.last_n_sessions, args.last_n_days, args.project]):
        filtered_sessions = filter_by_last_n_sessions(filtered_sessions, 10)

    # Output in requested format
    if args.format == "markdown":
        output_markdown(filtered_sessions)
    elif args.format == "table":
        output_table(filtered_sessions)
    elif args.format == "json":
        output_json(filtered_sessions)

    return 0


if __name__ == "__main__":
    exit(main())
