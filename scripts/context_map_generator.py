#!/usr/bin/env python3
"""
Context Map Generator - Smart Ledger Assembly
Generates optimized agent context that loads only what's needed for a specific task.

Usage:
    python context_map_generator.py --task "Python development"
    python context_map_generator.py --task "Plan Q1 2026" --format yaml
    python context_map_generator.py --task "Python work" --skills-only
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Set

import yaml


def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load YAML file with error handling."""
    try:
        with open(file_path, 'r') as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as e:
        print(f"Error loading {file_path}: {e}", file=sys.stderr)
        return {}


def find_yaml_line(file_path: Path, key_path: List[str]) -> int:
    """Find line number for a key path in YAML file."""
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()

        # Simple heuristic: find first line containing the last key
        target_key = key_path[-1]
        for i, line in enumerate(lines, 1):
            if target_key in line and ':' in line:
                return i
        return 1
    except FileNotFoundError:
        return 1


def extract_skills_from_yaml(skills_data: Dict[str, Any], file_path: Path) -> List[Dict[str, Any]]:
    """Extract all skills from skills_active.yaml with file:line references."""
    skills = []

    def process_skill_list(items: List[Dict], category: str):
        """Process a list of skill items."""
        for item in items:
            if isinstance(item, dict) and 'skill' in item:
                line_num = find_yaml_line(file_path, [item['skill']])
                skills.append({
                    'name': item['skill'],
                    'level': item.get('level', 1),
                    'category': category,
                    'validation': item.get('validation', 'agent-assessed'),
                    'file_ref': f"{file_path.name}:{line_num}",
                    'temporal_metadata': item.get('temporal_metadata', {}),
                })

    def traverse(data: Any, category_path: str = ''):
        """Recursively traverse the YAML structure."""
        if isinstance(data, dict):
            for key, value in data.items():
                new_path = f"{category_path}/{key}" if category_path else key

                # Check if this dict has 'items' key
                if 'items' in value and isinstance(value['items'], list):
                    process_skill_list(value['items'], new_path)
                else:
                    traverse(value, new_path)
        elif isinstance(data, list):
            process_skill_list(data, category_path)

    # Traverse the entire structure
    traverse(skills_data)

    return skills


def extract_projects(projects_data: Dict[str, Any], file_path: Path, active_only: bool = False) -> List[Dict[str, Any]]:
    """Extract projects from projects.yaml with file:line references."""
    projects = []

    projects_list = projects_data.get('projects', [])
    for i, project in enumerate(projects_list):
        if not isinstance(project, dict):
            continue

        status = project.get('status', '')
        stage = project.get('stage', '')

        # Filter active projects
        if active_only and status not in ['operational', 'prototype', 'design-complete', 'design', 'refactoring']:
            continue

        line_num = find_yaml_line(file_path, ['projects', project.get('name', '')])
        projects.append({
            'name': project.get('name', 'Unknown'),
            'alias': project.get('alias', ''),
            'status': status,
            'stage': stage,
            'objective': project.get('objective', ''),
            'last_update': project.get('last_update', ''),
            'dependencies': project.get('dependencies', []),
            'skills_demonstrated': project.get('skills_demonstrated', []),
            'file_ref': f"{file_path.name}:{line_num}",
        })

    return projects


def fuzzy_match(query: str, targets: List[str]) -> Set[str]:
    """Fuzzy match query against target strings."""
    query_lower = query.lower()
    query_tokens = re.split(r'\W+', query_lower)

    matches = set()
    for target in targets:
        target_lower = target.lower()
        # Exact substring match
        if query_lower in target_lower:
            matches.add(target)
            continue
        # Token match
        for token in query_tokens:
            if token and len(token) > 2 and token in target_lower:
                matches.add(target)
                break

    return matches


def filter_skills(skills: List[Dict[str, Any]], task: str) -> List[Dict[str, Any]]:
    """Filter skills relevant to task."""
    if not task:
        return skills

    # Extract skill names for fuzzy matching
    skill_names = [s['name'] for s in skills]
    matched_names = fuzzy_match(task, skill_names)

    # Filter by matched names or category
    filtered = []
    for skill in skills:
        if skill['name'] in matched_names:
            filtered.append(skill)
        elif fuzzy_match(task, [skill['category']]):
            filtered.append(skill)

    # Sort by level (descending) and name
    filtered.sort(key=lambda s: (-s['level'], s['name']))

    return filtered


def filter_projects(projects: List[Dict[str, Any]], task: str) -> List[Dict[str, Any]]:
    """Filter projects relevant to task."""
    if not task:
        return projects

    # Extract project names and objectives for fuzzy matching
    project_texts = [f"{p['name']} {p['objective']}" for p in projects]

    filtered = []
    for i, project in enumerate(projects):
        # Check dependencies (handle both str and dict items)
        deps = project['dependencies']
        deps_list = [d if isinstance(d, str) else str(d) for d in deps]
        deps_str = ' '.join(deps_list)
        if fuzzy_match(task, [project['name'], project['objective'], deps_str]):
            filtered.append(project)

    # Sort by last_update (most recent first)
    filtered.sort(key=lambda p: p.get('last_update', ''), reverse=True)

    return filtered


def extract_philosophy(trajectory_data: Dict[str, Any]) -> List[str]:
    """Extract core philosophy principles."""
    principles = []

    # Career direction
    career = trajectory_data.get('trajectory', {}).get('career_direction', '')
    if career:
        principles.append(career.strip())

    # Explicitly avoid
    avoid = trajectory_data.get('trajectory', {}).get('learning_path', {}).get('explicitly_avoid', [])
    if avoid:
        principles.append(f"Avoid: {', '.join(avoid)}")

    return principles


def calculate_recent_activity(skills: List[Dict[str, Any]], time_window_days: int) -> Dict[str, Any]:
    """Calculate activity metrics for matched skills."""
    cutoff_date = datetime.now() - timedelta(days=time_window_days)

    total_sessions = 0
    categories = set()

    for skill in skills:
        metadata = skill.get('temporal_metadata', {})
        session_count = metadata.get('session_count', 0)
        last_seen = metadata.get('last_seen', '')

        # Parse last_seen date
        try:
            if last_seen:
                last_date = datetime.strptime(last_seen, '%Y-%m-%d')
                if last_date >= cutoff_date:
                    total_sessions += session_count
        except ValueError:
            pass

        categories.add(skill['category'])

    return {
        'total_sessions': total_sessions,
        'categories': list(categories),
        'days': time_window_days,
    }


def format_text_output(context: Dict[str, Any]) -> str:
    """Format context as human-readable text."""
    lines = []

    # Header
    task = context['task']
    lines.append(f"═══ CONTEXT MAP: {task} ═══")
    lines.append("")

    # Skills
    skills = context.get('skills', [])
    if skills:
        lines.append(f"RELEVANT SKILLS (matching \"{task}\"):")
        for skill in skills[:10]:  # Limit to top 10
            name = skill['name']
            level = skill['level']
            ref = skill['file_ref']
            lines.append(f"- {name} (Level {level}) [{ref}]")
        lines.append("")

    # Projects
    projects = context.get('projects', [])
    if projects:
        lines.append(f"ACTIVE PROJECTS (involves {task}):")
        for project in projects[:5]:  # Limit to top 5
            name = project['name']
            status = project['status']
            last = project.get('last_update', 'unknown')
            lines.append(f"- {name} ({status}, last active {last})")
        lines.append("")

    # Philosophy
    philosophy = context.get('philosophy', [])
    if philosophy:
        lines.append("PHILOSOPHY:")
        for principle in philosophy[:3]:  # Limit to 3
            lines.append(f"- {principle}")
        lines.append("")

    # Activity
    activity = context.get('activity', {})
    if activity:
        sessions = activity.get('total_sessions', 0)
        days = activity.get('days', 30)
        lines.append(f"RECENT ACTIVITY:")
        lines.append(f"- {sessions} sessions in last {days} days")
        lines.append("")

    # Footer
    lines.append("═" * 39)

    # Calculate total size
    output_text = '\n'.join(lines)
    char_count = len(output_text)
    lines.append(f"Total context: {char_count} characters")

    return '\n'.join(lines)


def format_json_output(context: Dict[str, Any]) -> str:
    """Format context as JSON."""
    return json.dumps(context, indent=2)


def format_yaml_output(context: Dict[str, Any]) -> str:
    """Format context as YAML."""
    return yaml.dump(context, default_flow_style=False, sort_keys=False)


def generate_context_map(
    task: str,
    time_window: int = 30,
    format_type: str = 'text',
    active_only: bool = False,
    skills_only: bool = False,
    include_decisions: bool = False,
) -> str:
    """Generate context map for task."""

    # Locate ledger directory
    ledger_dir = Path(__file__).parent.parent.parent / 'packages' / 'ledger'

    # Load ledger files
    skills_data = load_yaml(ledger_dir / 'skills_active.yaml')
    projects_data = load_yaml(ledger_dir / 'projects.yaml')
    trajectory_data = load_yaml(ledger_dir / 'trajectory.yaml')
    status_data = load_yaml(ledger_dir / 'status.yaml')

    # Extract and filter skills
    all_skills = extract_skills_from_yaml(skills_data, ledger_dir / 'skills_active.yaml')
    filtered_skills = filter_skills(all_skills, task)

    # Build context
    context = {
        'task': task,
        'skills': filtered_skills,
    }

    # Add projects unless skills-only
    if not skills_only:
        all_projects = extract_projects(projects_data, ledger_dir / 'projects.yaml', active_only)
        filtered_projects = filter_projects(all_projects, task)
        context['projects'] = filtered_projects

        # Add philosophy
        philosophy = extract_philosophy(trajectory_data)
        context['philosophy'] = philosophy

        # Add activity metrics
        activity = calculate_recent_activity(filtered_skills, time_window)
        context['activity'] = activity

    # Add decisions if requested
    if include_decisions:
        recent_decisions = status_data.get('status', {}).get('recent_decisions', [])
        context['recent_decisions'] = recent_decisions

    # Format output
    if format_type == 'json':
        return format_json_output(context)
    elif format_type == 'yaml':
        return format_yaml_output(context)
    else:
        return format_text_output(context)


def main():
    parser = argparse.ArgumentParser(
        description='Generate optimized agent context for specific tasks',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python context_map_generator.py --task "Python development"
  python context_map_generator.py --task "Plan Q1 2026" --format yaml
  python context_map_generator.py --task "Python work" --skills-only
        """
    )

    parser.add_argument(
        '--task',
        type=str,
        required=True,
        help='Task description to filter relevant context'
    )
    parser.add_argument(
        '--time-window',
        type=int,
        default=30,
        help='Recent activity window in days (default: 30)'
    )
    parser.add_argument(
        '--format',
        type=str,
        choices=['text', 'json', 'yaml'],
        default='text',
        help='Output format (default: text)'
    )
    parser.add_argument(
        '--active-only',
        action='store_true',
        help='Exclude paused projects'
    )
    parser.add_argument(
        '--skills-only',
        action='store_true',
        help='Return skills context only'
    )
    parser.add_argument(
        '--decisions',
        action='store_true',
        help='Include recent decisions'
    )

    args = parser.parse_args()

    # Generate and print context map
    output = generate_context_map(
        task=args.task,
        time_window=args.time_window,
        format_type=args.format,
        active_only=args.active_only,
        skills_only=args.skills_only,
        include_decisions=args.decisions,
    )

    print(output)


if __name__ == '__main__':
    main()
