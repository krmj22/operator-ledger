#!/usr/bin/env python3
"""
Agent Bootstrap Context Printer

Solves the cold-start problem. When opening a new chat, agents paste ONE block
of output and immediately know who you are, what you're doing, and how to assist.

Usage:
  python agent_bootstrap.py              # Default compact output (<2000 chars)
  python agent_bootstrap.py --compact    # Minimal version (~500 chars)
  python agent_bootstrap.py --full       # Verbose version (all skills, all projects)
  python agent_bootstrap.py --focus "Python task"  # Filter to relevant context
"""

import sys
import argparse
from pathlib import Path
import yaml
from datetime import datetime, timedelta


def load_yaml(filepath):
    """Load YAML file and return parsed data."""
    try:
        with open(filepath, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return None
    except yaml.YAMLError as e:
        print(f"Error parsing {filepath}: {e}", file=sys.stderr)
        sys.exit(1)


def get_top_skills(skills_data, count=8):
    """Extract top N skills by level and frequency."""
    all_skills = []

    # Flatten all skill categories
    for category_name, category_data in skills_data.get('skills', {}).items():
        if isinstance(category_data, dict):
            # Handle nested structure (e.g., tech_stack.frameworks)
            for subcategory_name, subcategory_data in category_data.items():
                if isinstance(subcategory_data, list):
                    for skill in subcategory_data:
                        if isinstance(skill, dict) and 'skill' in skill:
                            all_skills.append({
                                'name': skill['skill'],
                                'level': skill.get('level', 0),
                                'last_seen': skill.get('temporal_metadata', {}).get('last_seen', ''),
                                'frequency': skill.get('temporal_metadata', {}).get('frequency', 'unknown')
                            })
        elif isinstance(category_data, list):
            for skill in category_data:
                if isinstance(skill, dict) and 'skill' in skill:
                    all_skills.append({
                        'name': skill['skill'],
                        'level': skill.get('level', 0),
                        'last_seen': skill.get('temporal_metadata', {}).get('last_seen', ''),
                        'frequency': skill.get('temporal_metadata', {}).get('frequency', 'unknown')
                    })

    # Handle tech_stack and orchestration categories
    for top_category in ['tech_stack', 'orchestration']:
        top_data = skills_data.get(top_category, {})
        if isinstance(top_data, dict):
            for subcategory_name, subcategory_data in top_data.items():
                items = subcategory_data.get('items', []) if isinstance(subcategory_data, dict) else []
                for skill in items:
                    if isinstance(skill, dict) and 'skill' in skill:
                        all_skills.append({
                            'name': skill['skill'],
                            'level': skill.get('level', 0),
                            'last_seen': skill.get('temporal_metadata', {}).get('last_seen', ''),
                            'frequency': skill.get('temporal_metadata', {}).get('frequency', 'unknown')
                        })
        elif isinstance(top_data, list):
            for skill in top_data:
                if isinstance(skill, dict) and 'skill' in skill:
                    all_skills.append({
                        'name': skill['skill'],
                        'level': skill.get('level', 0),
                        'last_seen': skill.get('temporal_metadata', {}).get('last_seen', ''),
                        'frequency': skill.get('temporal_metadata', {}).get('frequency', 'unknown')
                    })

    # Sort by level (desc), then frequency
    freq_order = {'frequent': 3, 'regular': 2, 'occasional': 1, 'unknown': 0}
    all_skills.sort(key=lambda s: (s['level'], freq_order.get(s['frequency'], 0)), reverse=True)

    return all_skills[:count]


def load_commit_activity(ledger_dir):
    """Load recent commit activity for context."""
    commit_activity_path = ledger_dir / 'commit_activity.yaml'
    data = load_yaml(commit_activity_path)

    if not data:
        return None

    return {
        'last_7_days': data.get('activity_windows', {}).get('last_7_days', {}),
        'recent_decisions': data.get('recent_decisions', [])[:3]  # Top 3
    }


def get_active_projects(projects_data, mode='compact'):
    """Extract active/in-progress projects."""
    projects = projects_data.get('projects', [])
    active = []

    for project in projects:
        stage = project.get('stage', '')
        status = project.get('status', '')

        # Consider phase-1, phase-2, phase-3 as active; skip research/archived
        if stage in ['phase-1', 'phase-2', 'phase-3'] and status not in ['archived', 'planning']:
            active.append({
                'name': project.get('name', 'Unknown'),
                'objective': project.get('objective', ''),
                'stage': stage
            })

    if mode == 'full':
        return active
    return active[:3]  # Top 3 for compact mode


def get_recent_decisions(decisions_data, count=2):
    """Extract most recent decisions."""
    decisions = decisions_data.get('decisions', [])

    # Sort by date (most recent first)
    sorted_decisions = sorted(
        decisions,
        key=lambda d: d.get('date', ''),
        reverse=True
    )

    return sorted_decisions[:count]


def calculate_recent_activity(sessions_data, days=7):
    """Calculate activity metrics from sessions data."""
    if not sessions_data or 'sessions' not in sessions_data:
        return {
            'commits': 'N/A',
            'sessions': 0,
            'focus': 'Operator ledger system'
        }

    cutoff_date = datetime.now() - timedelta(days=days)
    recent_sessions = 0

    sessions = sessions_data.get('sessions', [])
    for session in sessions:
        session_date_str = session.get('date', '')
        try:
            session_date = datetime.strptime(session_date_str, '%Y-%m-%d')
            if session_date >= cutoff_date:
                recent_sessions += 1
        except (ValueError, TypeError):
            pass

    return {
        'commits': 'N/A',  # Would need GitHub integration (#68)
        'sessions': recent_sessions,
        'focus': 'Operator ledger system'
    }


def print_compact_bootstrap(ledger_dir):
    """Print minimal bootstrap context (~500 chars)."""
    # Load minimal data
    trajectory = load_yaml(ledger_dir / 'trajectory.yaml')
    status = load_yaml(ledger_dir / 'status.yaml')

    if not trajectory or not status:
        print("Error: Required files missing", file=sys.stderr)
        sys.exit(1)

    traj = trajectory.get('trajectory', {})
    stat = status.get('status', {})

    print("=== OPERATOR CONTEXT (COMPACT) ===\n")
    print(f"FOCUS: {traj.get('current_focus', 'N/A')}")
    print(f"ETHOS: >95% confidence, brutal simplicity, fail fast")
    print(f"LEVEL: {traj.get('learning_path', {}).get('current_level', 'N/A')}")

    print("\nACTIVE:")
    for project in stat.get('in_progress', [])[:2]:
        print(f"  - {project.get('project', 'Unknown')}")

    print("\nNEXT: GitHub integration → Agent validation → Decision logging")


def print_full_bootstrap(ledger_dir):
    """Print verbose bootstrap context (all skills, all projects)."""
    # Load all data
    skills = load_yaml(ledger_dir / 'skills_active.yaml')
    projects = load_yaml(ledger_dir / 'projects.yaml')
    trajectory = load_yaml(ledger_dir / 'trajectory.yaml')
    status = load_yaml(ledger_dir / 'status.yaml')
    decisions = load_yaml(ledger_dir / 'decisions.yaml')
    sessions = load_yaml(ledger_dir / 'sessions.yaml')

    if not all([skills, projects, trajectory, status]):
        print("Error: Required files missing", file=sys.stderr)
        sys.exit(1)

    print("=== OPERATOR CONTEXT BOOTSTRAP (FULL) ===\n")

    # 1. All skills
    all_skills = get_top_skills(skills, count=999)  # Get all
    print(f"ACTIVE SKILLS (All {len(all_skills)} skills):")
    for skill in all_skills:
        print(f"- {skill['name']} (Level {skill['level']}, {skill['frequency']})")
    print()

    # 2. All projects
    all_projects = get_active_projects(projects, mode='full')
    print(f"ACTIVE PROJECTS (All {len(all_projects)} projects):")
    for project in all_projects:
        print(f"- {project['name']}: {project['objective'][:80]}...")
    print()

    # Continue with remaining sections (same as default)
    print_default_sections(trajectory, status, decisions, sessions, ledger_dir)


def print_focused_bootstrap(ledger_dir, focus_task):
    """Print bootstrap context filtered to focus task."""
    # Load data
    skills = load_yaml(ledger_dir / 'skills_active.yaml')
    projects = load_yaml(ledger_dir / 'projects.yaml')

    if not all([skills, projects]):
        print("Error: Required files missing", file=sys.stderr)
        sys.exit(1)

    print(f"=== OPERATOR CONTEXT (FOCUS: {focus_task}) ===\n")

    # Filter skills by focus task (simple keyword matching)
    all_skills = get_top_skills(skills, count=999)
    relevant_skills = [s for s in all_skills if focus_task.lower() in s['name'].lower()]

    if relevant_skills:
        print("RELEVANT SKILLS:")
        for skill in relevant_skills[:5]:
            print(f"- {skill['name']} (Level {skill['level']})")
    else:
        print("RELEVANT SKILLS: None found (showing top 3 general skills)")
        for skill in all_skills[:3]:
            print(f"- {skill['name']} (Level {skill['level']})")

    print(f"\nSUGGESTION: For '{focus_task}', see skills_active.yaml and projects.yaml")


def print_default_sections(trajectory, status, decisions, sessions, ledger_dir):
    """Print shared sections for default/full modes."""
    traj = trajectory.get('trajectory', {})
    stat = status.get('status', {})

    # 3. Philosophy & Approach
    print("PHILOSOPHY:")
    print("- >95% confidence, brutal simplicity, fail fast")
    print("- CRISP-E framework (see .agents/ETHOS.md)")
    print()

    # 4. Recent Work (from GitHub commits)
    commit_activity = load_commit_activity(ledger_dir)
    if commit_activity:
        window = commit_activity['last_7_days']
        print("RECENT WORK (7d):")
        print(f"- {window.get('commits', 0)} commits across {window.get('repos_active', 0)} repos")
        if window.get('top_skills'):
            print(f"- Skills: {', '.join(window['top_skills'][:3])}")
        if commit_activity['recent_decisions']:
            print(f"- Recent decision: {commit_activity['recent_decisions'][0]['decision'][:50]}...")
        print()
    else:
        # Fallback to session-based activity
        activity = calculate_recent_activity(sessions, days=7)
        print("RECENT ACTIVITY (7d):")
        print(f"- {activity['sessions']} sessions, focus: {activity['focus']}")
        print()

    # 5. Decision Context
    if decisions:
        recent_decisions = get_recent_decisions(decisions, count=1)
        print("LATEST DECISION:")
        for dec in recent_decisions:
            print(f"- {dec.get('decision', 'Unknown')} ({dec.get('date', 'N/A')})")
    print()

    # 6. Next Focus
    print("NEXT FOCUS:")
    for goal in traj.get('goals', {}).get('90_day', [])[:2]:
        print(f"- {goal.get('skill', 'Unknown')}: {goal.get('reasoning', 'N/A')[:50]}...")
    print()

    # 7. Learning Path
    learning = traj.get('learning_path', {})
    print("LEARNING:")
    print(f"- Ready: {', '.join(learning.get('ready_to_learn', [])[:2])}")
    print(f"- Avoid: {', '.join(learning.get('explicitly_avoid', [])[:2])}")
    print()

    # 8. Command Reference
    print("COMMANDS:")
    print("- python analysis/scripts/query_sessions.py --skill \"<name>\"")
    print("- cat ledger/skills_active.yaml")


def print_default_bootstrap(ledger_dir):
    """Print default bootstrap context (<2000 chars)."""
    # Load all data
    skills = load_yaml(ledger_dir / 'skills_active.yaml')
    projects = load_yaml(ledger_dir / 'projects.yaml')
    trajectory = load_yaml(ledger_dir / 'trajectory.yaml')
    status = load_yaml(ledger_dir / 'status.yaml')
    decisions = load_yaml(ledger_dir / 'decisions.yaml')
    sessions = load_yaml(ledger_dir / 'sessions.yaml')

    if not all([skills, projects, trajectory, status]):
        print("Error: Required files missing", file=sys.stderr)
        sys.exit(1)

    print("=== OPERATOR CONTEXT BOOTSTRAP ===\n")

    # 1. Active Skills (Top 8)
    top_skills = get_top_skills(skills, count=8)
    print("ACTIVE SKILLS (Top 8):")
    for skill in top_skills:
        print(f"- {skill['name']} (L{skill['level']}, {skill['last_seen']}) [skills_active.yaml]")
    print()

    # 2. Active Projects
    active_projects = get_active_projects(projects, mode='compact')
    print("ACTIVE PROJECTS:")
    for project in active_projects:
        print(f"- {project['name']}: {project['objective'][:50]}... [projects.yaml]")
    print()

    # Remaining sections
    print_default_sections(trajectory, status, decisions, sessions, ledger_dir)


def main():
    parser = argparse.ArgumentParser(
        description='Agent Bootstrap Context Printer - Eliminates cold-start problem'
    )
    parser.add_argument(
        '--compact',
        action='store_true',
        help='Minimal version (~500 chars)'
    )
    parser.add_argument(
        '--full',
        action='store_true',
        help='Verbose version (all skills, all projects)'
    )
    parser.add_argument(
        '--focus',
        type=str,
        metavar='TASK',
        help='Filter to relevant skills/projects for task'
    )

    args = parser.parse_args()

    # Determine ledger directory
    script_dir = Path(__file__).parent
    ledger_dir = script_dir.parent.parent / 'packages' / 'ledger'

    if not ledger_dir.exists():
        print(f"Error: Ledger directory not found: {ledger_dir}", file=sys.stderr)
        sys.exit(1)

    # Route to appropriate output mode
    if args.compact:
        print_compact_bootstrap(ledger_dir)
    elif args.full:
        print_full_bootstrap(ledger_dir)
    elif args.focus:
        print_focused_bootstrap(ledger_dir, args.focus)
    else:
        print_default_bootstrap(ledger_dir)


if __name__ == '__main__':
    main()
