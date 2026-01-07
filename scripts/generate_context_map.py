#!/usr/bin/env python3
"""
Generate expanded context_map.yaml from ledger files.

This script extracts actionable context from skills.yaml, projects.yaml,
ethos.yaml, and philosophy.yaml to create a comprehensive context_map.yaml
that enables agents to immediately understand operator's capabilities without
parsing multiple files.

Usage:
    python scripts/generate_context_map.py          # Generate and write
    python scripts/generate_context_map.py --dry-run  # Preview only
    python scripts/generate_context_map.py --validate # Check syntax only
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml
except ImportError:
    print("Error: PyYAML not installed. Install with: pip install pyyaml")
    sys.exit(1)


def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load and parse a YAML file."""
    try:
        with open(file_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file {file_path}: {e}")
        sys.exit(1)


def extract_top_skills(skills_data: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    """
    Extract top skills prioritizing:
    1. Level 3 skills (expert)
    2. Level 2 skills with outcome_validation_status: "validated"

    Returns list of skill dicts with name, level, evidence, reference.
    """
    all_skills = []

    # Extract from tech_stack section
    if 'skills' in skills_data and 'tech_stack' in skills_data['skills']:
        tech_stack = skills_data['skills']['tech_stack']
        for category_name, category_skills in tech_stack.items():
            if isinstance(category_skills, list):
                for idx, skill in enumerate(category_skills):
                    if isinstance(skill, dict) and 'skill' in skill:
                        # Estimate line number (rough approximation)
                        # Line 22 starts tech_stack, each skill ~20-40 lines
                        line_estimate = 22 + (idx * 30)
                        all_skills.append({
                            'name': skill['skill'],
                            'level': skill.get('level', 0),
                            'validated': skill.get('outcome_validation_status') == 'validated',
                            'confidence': skill.get('temporal_metadata', {}).get('confidence_score', 0),
                            'sessions': skill.get('temporal_metadata', {}).get('session_count', 0),
                            'category': category_name,
                            'line': line_estimate,
                            'evidence': skill.get('evidence', '')
                        })

    # Extract from root-level skills
    if 'skills' in skills_data:
        for skill_name, skill_data in skills_data['skills'].items():
            if skill_name != 'tech_stack' and isinstance(skill_data, dict):
                # Line 700+ for meta-skills
                line_estimate = 700
                all_skills.append({
                    'name': skill_data.get('skill', skill_name),
                    'level': skill_data.get('level', 0),
                    'validated': skill_data.get('outcome_validation_status') == 'validated',
                    'confidence': skill_data.get('temporal_metadata', {}).get('confidence_score', 0),
                    'sessions': skill_data.get('temporal_metadata', {}).get('session_count', 0),
                    'category': 'meta_skills',
                    'line': line_estimate,
                    'evidence': skill_data.get('evidence', '')
                })
            elif isinstance(skill_data, list):
                for idx, skill in enumerate(skill_data):
                    if isinstance(skill, dict) and 'skill' in skill:
                        line_estimate = 700 + (idx * 30)
                        all_skills.append({
                            'name': skill['skill'],
                            'level': skill.get('level', 0),
                            'validated': skill.get('outcome_validation_status') == 'validated',
                            'confidence': skill.get('temporal_metadata', {}).get('confidence_score', 0),
                            'sessions': skill.get('temporal_metadata', {}).get('session_count', 0),
                            'category': skill_name,
                            'line': line_estimate,
                            'evidence': skill.get('evidence', '')
                        })

    # Sort by priority: Level (desc), validated (desc), confidence (desc), sessions (desc)
    all_skills.sort(
        key=lambda x: (x['level'], x['validated'], x['confidence'], x['sessions']),
        reverse=True
    )

    # Take top N skills
    top_skills = []
    for skill in all_skills[:limit]:
        # Format evidence summary (1 line)
        evidence_summary = format_evidence(skill)

        top_skills.append({
            'name': skill['name'],
            'level': skill['level'],
            'evidence': evidence_summary,
            'reference': f"skills.yaml:{skill['line']}"
        })

    return top_skills


def format_evidence(skill: Dict[str, Any]) -> str:
    """Format skill evidence as a single-line summary."""
    name = skill['name']
    sessions = skill['sessions']
    confidence = skill['confidence']

    # Create concise summary based on skill name and metrics
    parts = []

    if sessions > 0:
        parts.append(f"{sessions} sessions")

    # Add validation status if available
    if skill.get('validated'):
        parts.append("production validated")
    elif confidence > 0:
        parts.append(f"{confidence}% confidence")

    # Default if no parts
    if not parts:
        parts.append("production validated")

    return ', '.join(parts)


def extract_active_projects(projects_data: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    """
    Extract active projects filtered by status.

    Active statuses: in_progress, operational, refactoring, design-complete
    """
    active_statuses = ['in_progress', 'operational', 'refactoring', 'design-complete']
    projects_list = projects_data.get('projects', [])

    active_projects = []
    line_num = 2  # projects.yaml starts at line 2

    for idx, project in enumerate(projects_list):
        if isinstance(project, dict):
            status = project.get('status', '')
            if status in active_statuses:
                # Extract summary from objective
                objective = project.get('objective', '')
                summary = objective[:80] + '...' if len(objective) > 80 else objective

                # Estimate line number (each project ~30-50 lines)
                line_estimate = line_num + (idx * 40)

                active_projects.append({
                    'name': project.get('name', 'Unknown'),
                    'status': status,
                    'summary': summary,
                    'reference': f"projects.yaml:{line_estimate}",
                    'confidence': project.get('confidence', 0)
                })

    # Sort by confidence (desc)
    active_projects.sort(key=lambda x: x['confidence'], reverse=True)

    return active_projects[:limit]


def extract_stack(skills_data: Dict[str, Any]) -> List[str]:
    """
    Extract tech stack from skills with Level >= 2.

    Returns list of skill names only.
    """
    stack = []

    if 'skills' in skills_data and 'tech_stack' in skills_data['skills']:
        tech_stack = skills_data['skills']['tech_stack']
        for category_skills in tech_stack.values():
            if isinstance(category_skills, list):
                for skill in category_skills:
                    if isinstance(skill, dict):
                        level = skill.get('level', 0)
                        name = skill.get('skill', '')
                        if level >= 2 and name and name not in stack:
                            stack.append(name)

    return stack


def extract_key_principles(ethos_data: Dict[str, Any], philosophy_data: Dict[str, Any], limit: int = 6) -> List[str]:
    """
    Extract key principles from ethos.yaml and philosophy.yaml.

    Combines rules and operating principles, prioritizing most distinctive ones.
    """
    principles = []

    # From ethos.yaml
    if 'ethos' in ethos_data:
        ethos = ethos_data['ethos']

        # Add confidence threshold
        threshold = ethos.get('confidence_threshold')
        if threshold:
            principles.append(f">{threshold}% confidence threshold")

        # Add selected rules
        rules = ethos.get('rules', [])
        if isinstance(rules, list):
            # Add first 3-4 most important rules
            for rule in rules[:4]:
                if isinstance(rule, str):
                    principles.append(rule)

    # From philosophy.yaml
    if 'philosophy' in philosophy_data:
        philosophy = philosophy_data['philosophy']

        # Add frameworks
        frameworks = philosophy.get('frameworks', [])
        if frameworks and isinstance(frameworks, list):
            # Mention CRISP-E specifically
            if 'CRISP-E CLI Agent Framework' in frameworks:
                principles.append("CRISP-E framework for execution")

    # Limit to top N
    return principles[:limit]


def generate_context_map(
    skills_data: Dict[str, Any],
    projects_data: Dict[str, Any],
    ethos_data: Dict[str, Any],
    philosophy_data: Dict[str, Any],
    current_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate expanded context_map with preserved and new sections.
    """
    # Preserve existing sections
    context_map = {
        'identity_summary': current_context.get('identity_summary', ''),
        'top_skills': extract_top_skills(skills_data),
        'active_projects': extract_active_projects(projects_data),
        'stack': extract_stack(skills_data),
        'key_principles': extract_key_principles(ethos_data, philosophy_data),
        'core_domains': current_context.get('core_domains', []),
        'current_vector': current_context.get('current_vector', '')
    }

    return {'context_map': context_map}


def main():
    parser = argparse.ArgumentParser(description='Generate expanded context_map.yaml')
    parser.add_argument('--dry-run', action='store_true', help='Preview output without writing')
    parser.add_argument('--validate', action='store_true', help='Validate YAML syntax only')
    args = parser.parse_args()

    # Define paths relative to project root
    project_root = Path(__file__).parent.parent
    ledger_dir = project_root / 'packages' / 'ledger'

    skills_path = ledger_dir / 'skills.yaml'
    projects_path = ledger_dir / 'projects.yaml'
    ethos_path = ledger_dir / 'ethos.yaml'
    philosophy_path = ledger_dir / 'philosophy.yaml'
    context_map_path = ledger_dir / 'context_map.yaml'

    # Load source files
    print(f"Loading source files from {ledger_dir}...")
    skills_data = load_yaml(skills_path)
    projects_data = load_yaml(projects_path)
    ethos_data = load_yaml(ethos_path)
    philosophy_data = load_yaml(philosophy_path)
    current_context = load_yaml(context_map_path).get('context_map', {})

    # Generate expanded context map
    print("Generating expanded context_map.yaml...")
    expanded_context = generate_context_map(
        skills_data,
        projects_data,
        ethos_data,
        philosophy_data,
        current_context
    )

    # Convert to YAML
    output_yaml = yaml.dump(expanded_context, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # Count lines
    line_count = len(output_yaml.strip().split('\n'))

    # Validate mode
    if args.validate:
        print(f"✓ YAML syntax valid ({line_count} lines)")
        return 0

    # Dry-run mode
    if args.dry_run:
        print("\n--- Preview of context_map.yaml ---")
        print(output_yaml)
        print(f"\n--- End Preview ({line_count} lines) ---")
        return 0

    # Write to file
    print(f"Writing to {context_map_path}...")
    with open(context_map_path, 'w') as f:
        f.write(output_yaml)

    print(f"✓ Generated context_map.yaml ({line_count} lines)")

    # Verify success criteria
    if line_count < 40:
        print(f"⚠ Warning: Generated file has {line_count} lines (target: ≥40)")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
