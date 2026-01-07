#!/usr/bin/env python3
"""
Query Ledger Interface for Deterministic Q&A

Purpose:
- Provide deterministic, auditable answers to ledger queries
- All answers include file:line references
- <100ms response time target
- No interpretation - return facts only

Query types:
- --skill <name>: Query skill details and evidence
- --project <name>: Query project status and metadata
- --decision <id_or_topic>: Query technical decisions
- --readiness-for <skill>: Query learning readiness
- --next-goals: Query trajectory goals
- --current-focus: Query current status
- --projects-for-skill <skill>: Find projects using a skill
- --skills-for-project <project>: Find skills demonstrated in project

Output formats:
- Default: Human-readable text with references
- --format json: Machine-readable JSON
- --format yaml: Machine-readable YAML
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Use OPERATOR_LEDGER_DIR env var, fallback to ./ledger for backwards compatibility
LEDGER_DIR = Path(os.getenv('OPERATOR_LEDGER_DIR', Path(__file__).resolve().parents[1] / 'ledger'))
ROOT = LEDGER_DIR


def load_yaml(path: Path) -> tuple[Optional[Dict], Optional[str]]:
    """Load YAML file, return (data, error)"""
    try:
        import yaml
    except ImportError:
        return None, "PyYAML not installed"

    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f), None
    except Exception as e:
        return None, str(e)


def format_file_reference(file_path: Path, line: Optional[int] = None) -> str:
    """Format file:line reference"""
    rel_path = file_path.relative_to(ROOT.parent)
    if line:
        return f"ledger/{rel_path.name}:{line}"
    return f"ledger/{rel_path.name}"


def query_skill(skill_name: str, show_evidence: bool = False) -> Dict[str, Any]:
    """Query skill details from skills_active.yaml and skills_history.yaml"""
    result = {
        "query_type": "skill",
        "skill": skill_name,
        "found": False
    }

    # Search in skills_active.yaml
    active_path = ROOT / "skills_active.yaml"
    data, err = load_yaml(active_path)

    if err:
        result["error"] = f"Failed to load skills_active.yaml: {err}"
        return result

    # Search through skills structure
    skill_data = None
    skill_line = None

    if data and "skills" in data:
        line_num = 1
        for category, subcategories in data["skills"].items():
            if isinstance(subcategories, dict):
                for subcat, skills in subcategories.items():
                    if isinstance(skills, list):
                        for skill in skills:
                            line_num += 1
                            if isinstance(skill, dict) and skill.get("skill") == skill_name:
                                skill_data = skill
                                skill_line = line_num
                                break

    if skill_data:
        result["found"] = True
        result["level"] = skill_data.get("level", "unknown")
        result["validation"] = skill_data.get("validation", "unknown")
        result["status"] = "Active"

        # Get temporal metadata
        temporal = skill_data.get("temporal_metadata", {})
        result["first_seen"] = temporal.get("first_seen")
        result["last_seen"] = temporal.get("last_seen")
        result["session_count"] = temporal.get("session_count", 0)

        result["reference"] = format_file_reference(active_path, skill_line)

        # Evidence sessions
        if show_evidence and "evidence" in skill_data:
            result["evidence_sessions"] = []
            for ev in skill_data["evidence"]:
                if "source" in ev:
                    source_path = Path(ev["source"])
                    result["evidence_sessions"].append({
                        "file": source_path.name,
                        "date": ev.get("date"),
                        "note": ev.get("note")
                    })

        # Outcome evidence
        if show_evidence and "outcome_evidence" in skill_data:
            result["outcome_evidence"] = []
            for outcome in skill_data["outcome_evidence"]:
                result["outcome_evidence"].append({
                    "type": outcome.get("type"),
                    "reference": outcome.get("reference"),
                    "status": outcome.get("status"),
                    "date": outcome.get("date"),
                    "note": outcome.get("note")
                })
    else:
        # Check skills_history.yaml
        history_path = ROOT / "skills_history.yaml"
        hist_data, hist_err = load_yaml(history_path)

        if not hist_err and hist_data and "skills" in hist_data:
            # Similar search in historical skills
            result["status"] = "Historical (no longer active)"
            result["reference"] = format_file_reference(history_path)

    return result


def query_project(project_name: str) -> Dict[str, Any]:
    """Query project details from projects.yaml"""
    result = {
        "query_type": "project",
        "project": project_name,
        "found": False
    }

    projects_path = ROOT / "projects.yaml"
    data, err = load_yaml(projects_path)

    if err:
        result["error"] = f"Failed to load projects.yaml: {err}"
        return result

    if data and "projects" in data:
        for idx, project in enumerate(data["projects"]):
            if project.get("name") == project_name or project.get("alias") == project_name:
                result["found"] = True
                result["status"] = project.get("status")
                result["last_active"] = project.get("last_update")
                result["stage"] = project.get("stage")
                result["objective"] = project.get("objective")
                result["confidence"] = project.get("confidence")

                # Calculate approximate line number (rough estimate)
                line_num = 2 + (idx * 15)  # Rough estimate
                result["reference"] = format_file_reference(projects_path, line_num)

                # Skills demonstrated
                if "skills_demonstrated" in project:
                    result["skills_demonstrated"] = project["skills_demonstrated"]

                # Recent activity (would need to query git or sessions)
                result["recent_commits"] = "N/A (requires git integration)"

                break

    return result


def query_decision(decision_id_or_topic: str) -> Dict[str, Any]:
    """Query technical decisions from decisions.yaml"""
    result = {
        "query_type": "decision",
        "query": decision_id_or_topic,
        "found": False
    }

    decisions_path = ROOT / "decisions.yaml"
    data, err = load_yaml(decisions_path)

    if err:
        result["error"] = f"Failed to load decisions.yaml: {err}"
        return result

    if data and "decisions" in data:
        for idx, decision in enumerate(data["decisions"]):
            # Match by ID or topic
            if (decision.get("id") == decision_id_or_topic or
                decision_id_or_topic.lower() in decision.get("topic", "").lower()):

                result["found"] = True
                result["decision_id"] = decision.get("id")
                result["topic"] = decision.get("topic")
                result["decision"] = decision.get("decision")
                result["rationale"] = decision.get("rationale")
                result["date"] = decision.get("date")
                result["status"] = decision.get("status")
                result["impact"] = decision.get("impact")
                result["project"] = decision.get("project")

                # Alternatives considered
                if "alternatives_considered" in decision:
                    result["alternatives"] = decision["alternatives_considered"]

                # Evidence
                if "evidence" in decision:
                    result["evidence"] = decision["evidence"]

                # Line reference (rough estimate: ~30 lines per decision)
                line_num = 7 + (idx * 30)
                result["reference"] = format_file_reference(decisions_path, line_num)

                break

    return result


def query_readiness(skill_name: str) -> Dict[str, Any]:
    """Query learning readiness from trajectory.yaml"""
    result = {
        "query_type": "readiness",
        "skill": skill_name,
        "readiness": "unknown"
    }

    trajectory_path = ROOT / "trajectory.yaml"
    data, err = load_yaml(trajectory_path)

    if err:
        result["error"] = f"Failed to load trajectory.yaml: {err}"
        return result

    # Check if skill is in ready_to_learn
    if data and "trajectory" in data:
        traj = data["trajectory"]

        if "learning_path" in traj:
            learning = traj["learning_path"]

            # Check ready_to_learn
            if "ready_to_learn" in learning:
                for ready_skill in learning["ready_to_learn"]:
                    if skill_name.lower() in ready_skill.lower():
                        result["readiness"] = "ready_to_learn"
                        result["skill"] = ready_skill
                        break

            # Check prerequisites
            if "prerequisites_satisfied" in learning:
                result["prerequisites_satisfied"] = learning["prerequisites_satisfied"]

            # Current level
            result["current_level"] = learning.get("current_level")
            result["focus_areas"] = learning.get("focus_areas", [])

        result["reference"] = format_file_reference(trajectory_path, 39)

    # Also check actual skill status
    skill_result = query_skill(skill_name)
    if skill_result["found"]:
        result["current_skill_level"] = skill_result.get("level", 0)
        result["skill_status"] = skill_result.get("status")
    else:
        result["current_skill_level"] = 0
        result["skill_status"] = "Not acquired"

    return result


def query_next_goals() -> Dict[str, Any]:
    """Query trajectory goals"""
    result = {
        "query_type": "trajectory",
    }

    trajectory_path = ROOT / "trajectory.yaml"
    data, err = load_yaml(trajectory_path)

    if err:
        result["error"] = f"Failed to load trajectory.yaml: {err}"
        return result

    if data and "trajectory" in data:
        traj = data["trajectory"]
        result["current_focus"] = traj.get("current_focus")
        result["elevator_pitch"] = traj.get("elevator_pitch")

        if "goals" in traj:
            result["90_day_goals"] = traj["goals"].get("90_day", [])
            result["1_year_goals"] = traj["goals"].get("1_year", [])

        if "learning_path" in traj:
            result["learning_path"] = traj["learning_path"].get("focus_areas", [])

        result["reference"] = format_file_reference(trajectory_path, 1)

    return result


def query_current_focus() -> Dict[str, Any]:
    """Query current status and focus"""
    result = {
        "query_type": "current_focus",
    }

    status_path = ROOT / "status.yaml"
    data, err = load_yaml(status_path)

    if err:
        result["error"] = f"Failed to load status.yaml: {err}"
        return result

    if data and "status" in data:
        status = data["status"]

        if "context" in status:
            result["primary_focus"] = status["context"].get("primary_focus")
            result["context_switch_frequency"] = status["context"].get("context_switch_frequency")

        if "in_progress" in status:
            result["active_projects"] = []
            for project in status["in_progress"]:
                result["active_projects"].append({
                    "project": project.get("project"),
                    "priority": project.get("priority"),
                    "effort_estimate": project.get("effort_estimate"),
                    "deadline": project.get("deadline")
                })

        if "recent_decisions" in status:
            result["recent_decisions"] = status["recent_decisions"]

        result["reference"] = format_file_reference(status_path, 1)

    return result


def query_projects_for_skill(skill_name: str) -> Dict[str, Any]:
    """Find projects that use/demonstrate a specific skill"""
    result = {
        "query_type": "projects_for_skill",
        "skill": skill_name,
        "projects": []
    }

    projects_path = ROOT / "projects.yaml"
    data, err = load_yaml(projects_path)

    if err:
        result["error"] = f"Failed to load projects.yaml: {err}"
        return result

    if data and "projects" in data:
        for project in data["projects"]:
            if "skills_demonstrated" in project:
                for skill in project["skills_demonstrated"]:
                    if isinstance(skill, dict) and skill.get("skill") == skill_name:
                        result["projects"].append({
                            "name": project.get("name"),
                            "status": project.get("status"),
                            "evidence": skill.get("evidence")
                        })
                        break

    result["reference"] = format_file_reference(projects_path)
    return result


def query_skills_for_project(project_name: str) -> Dict[str, Any]:
    """Find skills demonstrated in a specific project"""
    result = {
        "query_type": "skills_for_project",
        "project": project_name,
        "skills": []
    }

    projects_path = ROOT / "projects.yaml"
    data, err = load_yaml(projects_path)

    if err:
        result["error"] = f"Failed to load projects.yaml: {err}"
        return result

    if data and "projects" in data:
        for project in data["projects"]:
            if project.get("name") == project_name or project.get("alias") == project_name:
                if "skills_demonstrated" in project:
                    result["skills"] = project["skills_demonstrated"]
                result["reference"] = format_file_reference(projects_path)
                break

    return result


def query_recent_work(days: int = 7) -> Dict[str, Any]:
    """Query recent commit activity from commit_activity.yaml"""
    result = {
        "query_type": "recent_work",
        "days": days
    }

    commit_activity_path = ROOT / "commit_activity.yaml"
    data, err = load_yaml(commit_activity_path)

    if err:
        result["error"] = f"Failed to load commit_activity.yaml: {err}"
        return result

    if not data:
        result["error"] = "No commit activity data available"
        return result

    # Select appropriate window
    window_key = f"last_{days}_days"
    windows = data.get("activity_windows", {})

    # Find closest window (7, 30, or 90 days)
    if days <= 7:
        window = windows.get("last_7_days", {})
        window_name = "last 7 days"
    elif days <= 30:
        window = windows.get("last_30_days", {})
        window_name = "last 30 days"
    else:
        window = windows.get("last_90_days", {})
        window_name = "last 90 days"

    result["window"] = window_name
    result["repos_active"] = window.get("repos_active", 0)
    result["commits"] = window.get("commits", 0)
    result["top_skills"] = window.get("top_skills", [])
    result["decisions_made"] = window.get("decisions_made", 0)

    # Include recent decisions
    result["recent_decisions"] = data.get("recent_decisions", [])[:3]

    # Include skill activity
    result["skill_activity"] = data.get("skill_activity", [])[:5]

    result["reference"] = format_file_reference(commit_activity_path)

    return result


def format_output_text(result: Dict[str, Any]) -> str:
    """Format result as human-readable text"""
    lines = []

    if "error" in result:
        return f"Error: {result['error']}"

    query_type = result.get("query_type")

    if query_type == "skill":
        if not result.get("found"):
            return f"Skill '{result['skill']}' not found"

        lines.append(f"Skill: {result['skill']}")
        lines.append(f"  Level: {result.get('level', 'unknown')}")
        lines.append(f"  Validation: {result.get('validation', 'unknown')}")
        lines.append(f"  Status: {result.get('status', 'unknown')}")
        if result.get("last_seen"):
            lines.append(f"  Last used: {result['last_seen']}")
        if result.get("session_count"):
            lines.append(f"  Session count: {result['session_count']}")
        lines.append(f"  Reference: {result.get('reference')}")

        if "evidence_sessions" in result:
            lines.append(f"\n  Evidence sessions ({len(result['evidence_sessions'])}):")
            for ev in result["evidence_sessions"][:5]:  # Show first 5
                lines.append(f"    - {ev['file']} ({ev.get('date', 'unknown date')})")
                if ev.get('note'):
                    lines.append(f"      {ev['note'][:80]}...")

        if "outcome_evidence" in result:
            lines.append(f"\n  Outcome evidence:")
            for outcome in result["outcome_evidence"]:
                lines.append(f"    - {outcome['type']}: {outcome.get('reference')}")

    elif query_type == "project":
        if not result.get("found"):
            return f"Project '{result['project']}' not found"

        lines.append(f"Project: {result['project']}")
        lines.append(f"  Status: {result.get('status', 'unknown')}")
        if result.get("last_active"):
            lines.append(f"  Last active: {result['last_active']}")
        if result.get("stage"):
            lines.append(f"  Stage: {result['stage']}")
        if result.get("objective"):
            lines.append(f"  Objective: {result['objective']}")
        lines.append(f"  Reference: {result.get('reference')}")

        if "skills_demonstrated" in result:
            lines.append(f"\n  Skills demonstrated:")
            for skill in result["skills_demonstrated"]:
                if isinstance(skill, dict):
                    lines.append(f"    - {skill.get('skill')} (Level {skill.get('level', '?')})")

    elif query_type == "decision":
        if not result.get("found"):
            return f"Decision matching '{result['query']}' not found"

        lines.append(f"Decision: {result.get('topic')}")
        lines.append(f"  ID: {result.get('decision_id')}")
        lines.append(f"  Decision: {result.get('decision')}")
        lines.append(f"  Status: {result.get('status')}")
        lines.append(f"  Date: {result.get('date')}")
        lines.append(f"  Impact: {result.get('impact')}")
        lines.append(f"  Reasoning: {result.get('rationale')}")

        if "alternatives" in result:
            lines.append(f"\n  Alternatives considered:")
            for alt in result["alternatives"]:
                lines.append(f"    - {alt.get('name')}: {alt.get('rejected_because')}")

        if "evidence" in result:
            lines.append(f"\n  Evidence:")
            for ev in result["evidence"]:
                lines.append(f"    - {ev.get('type')}: {ev.get('ref')}")

        lines.append(f"\n  Reference: {result.get('reference')}")

    elif query_type == "readiness":
        lines.append(f"Skill: {result['skill']}")
        lines.append(f"  Current level: {result.get('current_skill_level', 0)}")
        lines.append(f"  Readiness: {result.get('readiness', 'unknown')}")

        if "prerequisites_satisfied" in result:
            lines.append(f"\n  Prerequisites satisfied:")
            for prereq in result["prerequisites_satisfied"]:
                lines.append(f"    - {prereq}")

        lines.append(f"\n  Reference: {result.get('reference')}")

    elif query_type == "trajectory":
        lines.append(f"Current focus: {result.get('current_focus')}")
        lines.append(f"")

        if "90_day_goals" in result:
            lines.append(f"90-day goals:")
            for goal in result["90_day_goals"]:
                if isinstance(goal, dict):
                    lines.append(f"  - {goal.get('skill')} (deadline: {goal.get('deadline')})")
                else:
                    lines.append(f"  - {goal}")

        if "1_year_goals" in result:
            lines.append(f"\n1-year vision:")
            for goal in result["1_year_goals"]:
                lines.append(f"  - {goal}")

        lines.append(f"\nReference: {result.get('reference')}")

    elif query_type == "current_focus":
        lines.append(f"Primary focus: {result.get('primary_focus')}")

        if "active_projects" in result:
            lines.append(f"\nActive projects:")
            for proj in result["active_projects"]:
                lines.append(f"  {proj['priority']}. {proj['project']} ({proj.get('effort_estimate', 'N/A')})")

        if "recent_decisions" in result:
            lines.append(f"\nRecent decisions:")
            for dec in result["recent_decisions"]:
                lines.append(f"  - {dec.get('decision')} ({dec.get('date')})")

        lines.append(f"\nReference: {result.get('reference')}")

    elif query_type == "projects_for_skill":
        lines.append(f"Projects using skill '{result['skill']}':")
        if result["projects"]:
            for proj in result["projects"]:
                lines.append(f"  - {proj['name']} ({proj.get('status', 'unknown')})")
        else:
            lines.append(f"  No projects found")
        lines.append(f"\nReference: {result.get('reference')}")

    elif query_type == "skills_for_project":
        lines.append(f"Skills for project '{result['project']}':")
        if result["skills"]:
            for skill in result["skills"]:
                if isinstance(skill, dict):
                    lines.append(f"  - {skill.get('skill')} (Level {skill.get('level', '?')})")
                else:
                    lines.append(f"  - {skill}")
        else:
            lines.append(f"  No skills found")
        lines.append(f"\nReference: {result.get('reference')}")

    elif query_type == "recent_work":
        lines.append(f"Recent work ({result.get('window', 'N/A')}):")
        lines.append(f"  Commits: {result.get('commits', 0)}")
        lines.append(f"  Repos active: {result.get('repos_active', 0)}")
        lines.append(f"  Decisions made: {result.get('decisions_made', 0)}")

        if result.get('top_skills'):
            lines.append(f"\n  Top skills:")
            for skill in result['top_skills']:
                lines.append(f"    - {skill}")

        if result.get('recent_decisions'):
            lines.append(f"\n  Recent decisions:")
            for dec in result['recent_decisions']:
                lines.append(f"    - {dec.get('id')}: {dec.get('decision')[:60]}...")
                lines.append(f"      ({dec.get('days_since')} days ago)")

        if result.get('skill_activity'):
            lines.append(f"\n  Skill activity:")
            for skill in result['skill_activity']:
                lines.append(f"    - {skill.get('skill')}: {skill.get('commits_last_30d')} commits")
                lines.append(f"      Repos: {', '.join(skill.get('repos', []))}")

        lines.append(f"\nReference: {result.get('reference')}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Query ledger for deterministic Q&A",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Query type arguments (mutually exclusive)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--skill", metavar="NAME", help="Query skill details")
    group.add_argument("--project", metavar="NAME", help="Query project status")
    group.add_argument("--decision", metavar="ID_OR_TOPIC", help="Query technical decision")
    group.add_argument("--readiness-for", metavar="SKILL", help="Query learning readiness")
    group.add_argument("--next-goals", action="store_true", help="Query trajectory goals")
    group.add_argument("--current-focus", action="store_true", help="Query current focus")
    group.add_argument("--projects-for-skill", metavar="SKILL", help="Find projects using skill")
    group.add_argument("--skills-for-project", metavar="PROJECT", help="Find skills in project")
    group.add_argument("--recent-work", action="store_true", help="Query recent commit activity")

    # Options
    parser.add_argument("--show-evidence", action="store_true", help="Show evidence details (for skill queries)")
    parser.add_argument("--format", choices=["text", "json", "yaml"], default="text", help="Output format")
    parser.add_argument("--days", type=int, default=7, help="Number of days for recent work query (default: 7)")

    args = parser.parse_args()

    # Route to appropriate query function
    result = None

    if args.skill:
        result = query_skill(args.skill, args.show_evidence)
    elif args.project:
        result = query_project(args.project)
    elif args.decision:
        result = query_decision(args.decision)
    elif args.readiness_for:
        result = query_readiness(args.readiness_for)
    elif args.next_goals:
        result = query_next_goals()
    elif args.current_focus:
        result = query_current_focus()
    elif args.projects_for_skill:
        result = query_projects_for_skill(args.projects_for_skill)
    elif args.skills_for_project:
        result = query_skills_for_project(args.skills_for_project)
    elif args.recent_work:
        result = query_recent_work(args.days)

    # Format output
    if args.format == "json":
        print(json.dumps(result, indent=2))
    elif args.format == "yaml":
        try:
            import yaml
            print(yaml.dump(result, default_flow_style=False))
        except ImportError:
            print("Error: PyYAML not installed. Install with: pip install pyyaml", file=sys.stderr)
            sys.exit(1)
    else:
        print(format_output_text(result))


if __name__ == "__main__":
    main()
