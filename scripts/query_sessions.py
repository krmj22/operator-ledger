#!/usr/bin/env python3
"""
Query Sessions by Skill, Project, Confidence, or Time Window

Drill down from ledger skills to specific session evidence. Answers questions like:
- Which sessions demonstrated "Risk Analysis"?
- What sessions happened in the last 7 days?
- Which skills have low confidence (<50)?

Examples:
    python query_sessions.py --skill "Project Management"
    python query_sessions.py --skill "Python Development" --with-ref
    python query_sessions.py --confidence-below 50 --with-ref --format table
    python query_sessions.py --last-n-days 7 --skill "Verification"
    python query_sessions.py --project "Voice Pipeline" --format table

The --with-ref flag adds file:line references showing where skills are defined
in the YAML ledger files, making it easy to jump to the source.
"""

import argparse
import json
import os
import re
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional


def load_skills(ledger_path: Path, active_only: bool = False) -> Tuple[Dict, Path]:
    """Load skills.yaml from ledger. Returns (skills_data, skills_file_path)."""
    # Prefer skills_active.yaml if it exists, fallback to skills.yaml
    if active_only:
        skills_file = ledger_path / "packages" / "ledger" / "skills_active.yaml"
    else:
        skills_file = ledger_path / "packages" / "ledger" / "skills_active.yaml"
        if not skills_file.exists():
            skills_file = ledger_path / "packages" / "ledger" / "skills.yaml"

    if not skills_file.exists():
        raise FileNotFoundError(f"Skills file not found: {skills_file}")

    with open(skills_file, 'r') as f:
        return yaml.safe_load(f), skills_file


def load_transcripts_index(transcripts_path: Path) -> Dict:
    """Load transcripts_index.json from data directory."""
    # Check multiple possible locations
    possible_paths = [
        transcripts_path.parent / "transcripts_index.json",
        transcripts_path / "transcripts_index.json"
    ]

    for index_path in possible_paths:
        if index_path.exists():
            with open(index_path, 'r') as f:
                return json.load(f)

    raise FileNotFoundError(f"transcripts_index.json not found in any expected location: {possible_paths}")


def build_skill_line_references(yaml_file_path: Path) -> Dict[str, Dict]:
    """
    Build a mapping of skill names to their line numbers in the YAML file.

    Returns:
        Dict mapping skill_name -> {
            'file': relative path from repo root,
            'definition_line': line where '- skill: Name' appears,
            'evidence_start': line where 'evidence:' array starts,
            'evidence_end': line where evidence array ends
        }
    """
    references = {}

    with open(yaml_file_path, 'r') as f:
        lines = f.readlines()

    current_skill = None
    skill_start_line = None
    skill_base_indent = None
    evidence_start_line = None
    evidence_base_indent = None

    for i, line in enumerate(lines, start=1):
        # Match skill definition: "- skill: <name>" or "  - skill: <name>"
        skill_match = re.match(r'^(\s*)- skill:\s*(.+)$', line)
        if skill_match:
            # Save previous skill's evidence end if we were tracking one
            if current_skill and evidence_start_line:
                references[current_skill]['evidence_end'] = i - 1

            skill_base_indent = len(skill_match.group(1))
            skill_name = skill_match.group(2).strip()
            current_skill = skill_name
            skill_start_line = i
            evidence_start_line = None
            evidence_base_indent = None

            references[skill_name] = {
                'file': f"ledger/{yaml_file_path.name}",
                'definition_line': skill_start_line,
                'evidence_start': None,
                'evidence_end': None
            }
            continue

        # Match evidence array start: "evidence:" or "  evidence:"
        # Note: evidence can be a string (single line) or array (multi-line)
        if current_skill and re.match(r'^(\s+)evidence:\s*$', line):
            evidence_match = re.match(r'^(\s+)evidence:\s*$', line)
            evidence_base_indent = len(evidence_match.group(1))
            evidence_start_line = i
            references[current_skill]['evidence_start'] = evidence_start_line
            continue

        # Check if we've moved to a new skill property at the same level or moved to next skill
        if evidence_start_line and evidence_base_indent is not None:
            # Get leading spaces of current line
            leading_spaces_match = re.match(r'^(\s*)', line)
            leading_spaces = len(leading_spaces_match.group(1)) if leading_spaces_match else 0

            # If line is non-empty and at same or lower indent than evidence:, we've left the array
            if line.strip() and leading_spaces <= evidence_base_indent:
                # Check if it's not just continuation of a multi-line string
                if not line.lstrip().startswith('- '):  # Not a list item
                    references[current_skill]['evidence_end'] = i - 1
                    evidence_start_line = None
                    evidence_base_indent = None

    # Handle last skill if it had evidence
    if current_skill and evidence_start_line:
        references[current_skill]['evidence_end'] = len(lines)

    return references


def extract_all_skills(skills_data: Dict) -> List[Dict]:
    """Extract all skills from nested structure with their metadata."""
    all_skills = []

    if 'skills' not in skills_data:
        return all_skills

    def process_skill_list(skill_list, category, subcategory=None):
        """Helper to process a list of skills."""
        for skill_entry in skill_list:
            if isinstance(skill_entry, dict) and 'skill' in skill_entry:
                skill_info = {
                    'name': skill_entry['skill'],
                    'category': f"{category}/{subcategory}" if subcategory else category,
                    'level': skill_entry.get('level', 0),
                    'evidence': skill_entry.get('evidence', ''),
                    'evidence_sessions': skill_entry.get('evidence_sessions', []),  # IAW Issue #71
                    'temporal_metadata': skill_entry.get('temporal_metadata', {})
                }
                all_skills.append(skill_info)

    # Iterate through categories
    for category, category_data in skills_data['skills'].items():
        if isinstance(category_data, list):
            # Direct list of skills (e.g., orchestration)
            process_skill_list(category_data, category)
        elif isinstance(category_data, dict):
            # Nested structure with subcategories (e.g., tech_stack -> frameworks)
            for subcategory, skill_list in category_data.items():
                if isinstance(skill_list, list):
                    process_skill_list(skill_list, category, subcategory)

    return all_skills


def query_by_skill(skill_name: str, skills_data: Dict, transcripts_index: Dict,
                   line_references: Optional[Dict] = None, with_evidence_sessions: bool = False) -> Dict:
    """
    Find all sessions for a specific skill.

    Args:
        skill_name: Name of the skill to query
        skills_data: Loaded skills YAML data
        transcripts_index: Loaded transcripts index (not currently used)
        line_references: Optional file:line references to YAML sources
        with_evidence_sessions: If True, include evidence_sessions in results (IAW Issue #71)
    """
    all_skills = extract_all_skills(skills_data)

    # Find matching skill (case-insensitive)
    matching_skill = None
    for skill in all_skills:
        if skill['name'].lower() == skill_name.lower():
            matching_skill = skill
            break

    if not matching_skill:
        return {
            'error': f"Skill '{skill_name}' not found in ledger",
            'available_skills': [s['name'] for s in all_skills[:10]]  # Show first 10 as hint
        }

    temporal_meta = matching_skill.get('temporal_metadata', {})
    confidence = temporal_meta.get('confidence_score', 0)
    trend = temporal_meta.get('trend', 'unknown')
    session_count = temporal_meta.get('session_count', 0)

    # Extract evidence_sessions if available (IAW Issue #71)
    evidence_sessions = matching_skill.get('evidence_sessions', [])

    result = {
        'query': {
            'type': 'skill',
            'skill': skill_name,
            'filters': {}
        },
        'results': {
            'skill_confidence': confidence,
            'skill_trend': trend,
            'skill_level': matching_skill['level'],
            'skill_category': matching_skill['category'],
            'session_count': session_count,
            'sessions': evidence_sessions if with_evidence_sessions else [],
            'evidence': matching_skill['evidence']
        }
    }

    # Add evidence_sessions to results if requested (IAW Issue #71)
    if with_evidence_sessions and evidence_sessions:
        result['results']['evidence_sessions'] = evidence_sessions
        result['results']['evidence_sessions_count'] = len(evidence_sessions)

    # Add line references if available
    if line_references and matching_skill['name'] in line_references:
        ref = line_references[matching_skill['name']]
        result['results']['references'] = {
            'definition': f"{ref['file']}:{ref['definition_line']}",
            'evidence_source': None
        }
        if ref['evidence_start'] and ref['evidence_end']:
            result['results']['references']['evidence_source'] = \
                f"{ref['file']}:{ref['evidence_start']}-{ref['evidence_end']}"

    return result


def query_by_confidence(threshold: int, skills_data: Dict,
                       line_references: Optional[Dict] = None) -> Dict:
    """Find all skills below confidence threshold."""
    all_skills = extract_all_skills(skills_data)

    low_confidence_skills = []
    for skill in all_skills:
        temporal_meta = skill.get('temporal_metadata', {})
        confidence = temporal_meta.get('confidence_score', 0)

        if confidence < threshold and confidence > 0:  # Exclude 0 (no data)
            skill_entry = {
                'skill_name': skill['name'],
                'confidence': confidence,
                'level': skill['level'],
                'category': skill['category'],
                'trend': temporal_meta.get('trend', 'unknown'),
                'session_count': temporal_meta.get('session_count', 0),
                'evidence_quality': temporal_meta.get('evidence_quality', 'unknown')
            }

            # Add line references if available
            if line_references and skill['name'] in line_references:
                ref = line_references[skill['name']]
                skill_entry['references'] = {
                    'definition': f"{ref['file']}:{ref['definition_line']}",
                    'evidence_source': None
                }
                if ref['evidence_start'] and ref['evidence_end']:
                    skill_entry['references']['evidence_source'] = \
                        f"{ref['file']}:{ref['evidence_start']}-{ref['evidence_end']}"

            low_confidence_skills.append(skill_entry)

    # Sort by confidence (lowest first)
    low_confidence_skills.sort(key=lambda x: x['confidence'])

    return {
        'query': {
            'type': 'confidence_filter',
            'threshold': threshold,
            'filters': {}
        },
        'results': {
            'matching_skills_count': len(low_confidence_skills),
            'skills': low_confidence_skills
        },
        'recommendations': [
            f"Found {len(low_confidence_skills)} skills below {threshold}% confidence",
            "Focus on skills with 'weak' evidence_quality for improvement"
        ]
    }


def query_by_project(project_name: str, transcripts_index: Dict) -> Dict:
    """Find all sessions for a specific project."""
    matching_sessions = []

    for entry in transcripts_index.get('index', []):
        tags = entry.get('tags', {})
        project_id = tags.get('project_id', '')

        # Simple substring match for now
        if project_name.lower() in project_id.lower():
            matching_sessions.append({
                'session_id': entry.get('session_id', ''),
                'date': entry.get('created_date', ''),
                'file_path': entry.get('file_path', ''),
                'project_id': project_id,
                'workflows': tags.get('workflow', []),
                'technical_tags': tags.get('technical', [])
            })

    return {
        'query': {
            'type': 'project',
            'project': project_name,
            'filters': {}
        },
        'results': {
            'session_count': len(matching_sessions),
            'sessions': matching_sessions
        }
    }


def filter_by_time_window(results: Dict, days: int) -> Dict:
    """Filter sessions to last N days."""
    cutoff_date = datetime.now() - timedelta(days=days)

    if 'results' in results and 'sessions' in results['results']:
        filtered_sessions = []
        for session in results['results']['sessions']:
            session_date_str = session.get('date', '')
            if session_date_str:
                try:
                    # Parse ISO8601 timestamp
                    session_date = datetime.fromisoformat(session_date_str.replace('Z', '+00:00'))
                    if session_date >= cutoff_date:
                        filtered_sessions.append(session)
                except (ValueError, AttributeError):
                    continue

        results['results']['sessions'] = filtered_sessions
        results['results']['session_count'] = len(filtered_sessions)
        results['query']['filters']['last_n_days'] = days

    return results


def format_as_json(results: Dict) -> str:
    """Format results as pretty JSON."""
    return json.dumps(results, indent=2)


def format_as_table(results: Dict) -> str:
    """Format results as ASCII table."""
    try:
        from tabulate import tabulate
    except ImportError:
        return "Error: tabulate not installed. Run: pip install tabulate\n" + format_as_json(results)

    if 'error' in results:
        return f"Error: {results['error']}\n"

    query_type = results.get('query', {}).get('type', 'unknown')

    if query_type == 'confidence_filter':
        skills = results.get('results', {}).get('skills', [])
        if not skills:
            return "No skills found matching criteria.\n"

        headers = ['Skill', 'Confidence', 'Level', 'Category', 'Sessions', 'Trend']
        rows = [
            [
                s['skill_name'],
                f"{s['confidence']}%",
                s['level'],
                s['category'],
                s['session_count'],
                s['trend']
            ]
            for s in skills
        ]
        return tabulate(rows, headers=headers, tablefmt='grid')

    elif query_type == 'skill':
        info = results.get('results', {})
        output = [
            f"Skill: {results['query']['skill']}",
            f"Confidence: {info.get('skill_confidence', 0)}%",
            f"Level: {info.get('skill_level', 0)}",
            f"Trend: {info.get('skill_trend', 'unknown')}",
            f"Sessions: {info.get('session_count', 0)}",
        ]

        # Add references if available
        if 'references' in info:
            refs = info['references']
            output.append(f"\nReferences:")
            output.append(f"  Definition: {refs['definition']}")
            if refs.get('evidence_source'):
                output.append(f"  Evidence source: {refs['evidence_source']}")

        # Add evidence_sessions if available (IAW Issue #71)
        if 'evidence_sessions' in info and info['evidence_sessions']:
            output.append(f"\nEvidence Sessions ({info.get('evidence_sessions_count', 0)} total):")
            for session in info['evidence_sessions']:
                output.append(f"  - {session.get('session_file', 'N/A')} ({session.get('date', 'N/A')})")
                output.append(f"    Interaction: {session.get('interaction_id', 'N/A')}")
                output.append(f"    Snippet: {session.get('snippet', 'N/A')}")

        output.append(f"\nEvidence: {info.get('evidence', 'N/A')}")
        return '\n'.join(output)

    else:
        sessions = results.get('results', {}).get('sessions', [])
        if not sessions:
            return "No sessions found.\n"

        headers = ['Session ID', 'Date', 'Workflows']
        rows = [
            [
                s.get('session_id', '')[:12] + '...',
                s.get('date', ''),
                ', '.join(s.get('workflows', []))
            ]
            for s in sessions
        ]
        return tabulate(rows, headers=headers, tablefmt='grid')


def format_as_markdown(results: Dict) -> str:
    """Format results as Markdown."""
    if 'error' in results:
        return f"## Error\n\n{results['error']}\n"

    query_type = results.get('query', {}).get('type', 'unknown')
    output = [f"# Query Results\n"]

    if query_type == 'confidence_filter':
        threshold = results['query']['threshold']
        skills = results.get('results', {}).get('skills', [])
        output.append(f"## Low Confidence Skills (<{threshold}%)\n")
        output.append(f"Found {len(skills)} skills\n")

        for skill in skills:
            output.append(f"### {skill['skill_name']} ({skill['confidence']}%)")
            output.append(f"- **Level:** {skill['level']}")
            output.append(f"- **Category:** {skill['category']}")
            output.append(f"- **Sessions:** {skill['session_count']}")
            output.append(f"- **Trend:** {skill['trend']}")
            output.append("")

    elif query_type == 'skill':
        info = results.get('results', {})
        output.append(f"## Skill: {results['query']['skill']}\n")
        output.append(f"- **Confidence:** {info.get('skill_confidence', 0)}%")
        output.append(f"- **Level:** {info.get('skill_level', 0)}")
        output.append(f"- **Trend:** {info.get('skill_trend', 'unknown')}")
        output.append(f"- **Sessions:** {info.get('session_count', 0)}")

        # Add references if available
        if 'references' in info:
            refs = info['references']
            output.append(f"\n### References")
            output.append(f"- **Definition:** `{refs['definition']}`")
            if refs.get('evidence_source'):
                output.append(f"- **Evidence source:** `{refs['evidence_source']}`")

        # Add evidence_sessions if available (IAW Issue #71)
        if 'evidence_sessions' in info and info['evidence_sessions']:
            output.append(f"\n### Evidence Sessions ({info.get('evidence_sessions_count', 0)} total)\n")
            for session in info['evidence_sessions']:
                output.append(f"- **{session.get('session_file', 'N/A')}** ({session.get('date', 'N/A')})")
                output.append(f"  - Interaction: `{session.get('interaction_id', 'N/A')}`")
                output.append(f"  - Snippet: {session.get('snippet', 'N/A')}")
                output.append("")

        output.append(f"\n**Evidence:** {info.get('evidence', 'N/A')}\n")

    return '\n'.join(output)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--skill', help='Skill name to query')
    parser.add_argument('--project', help='Project name to query')
    parser.add_argument('--confidence-below', type=int, metavar='THRESHOLD',
                       help='Find skills below confidence threshold (0-100)')
    parser.add_argument('--last-n-days', type=int, metavar='N',
                       help='Filter to sessions in last N days')
    parser.add_argument('--format', choices=['json', 'table', 'markdown'],
                       default='json', help='Output format (default: json)')
    parser.add_argument('--with-ref', action='store_true',
                       help='Include file:line references to YAML sources')
    parser.add_argument('--with-evidence-sessions', action='store_true',
                       help='Include evidence_sessions in output (IAW Issue #71)')

    args = parser.parse_args()

    # Validate at least one query parameter provided
    if not any([args.skill, args.project, args.confidence_below]):
        parser.error("Must specify at least one query: --skill, --project, or --confidence-below")

    # Get paths from environment
    operator_data_dir = os.getenv('OPERATOR_DATA_DIR')
    if not operator_data_dir:
        print("Error: OPERATOR_DATA_DIR environment variable not set")
        print("Run: source scripts/bootstrap.sh")
        return 1

    transcripts_path = Path(operator_data_dir)
    # Use script location to find operator repo root
    script_dir = Path(__file__).resolve().parent
    ledger_path = script_dir.parent.parent  # analysis/scripts -> operator root

    try:
        # Load data sources
        skills_data, skills_file = load_skills(ledger_path)
        # transcripts_index is optional and may not exist yet
        try:
            transcripts_index = load_transcripts_index(transcripts_path)
        except FileNotFoundError:
            transcripts_index = {}  # Use empty dict if not found

        # Build line references if requested
        line_references = None
        if args.with_ref:
            line_references = build_skill_line_references(skills_file)

        # Execute query
        if args.skill:
            results = query_by_skill(args.skill, skills_data, transcripts_index,
                                    line_references, args.with_evidence_sessions)
        elif args.project:
            results = query_by_project(args.project, transcripts_index)
        elif args.confidence_below:
            results = query_by_confidence(args.confidence_below, skills_data, line_references)
        else:
            results = {'error': 'No valid query specified'}

        # Apply time window filter if requested
        if args.last_n_days:
            results = filter_by_time_window(results, args.last_n_days)

        # Format and print output
        if args.format == 'json':
            print(format_as_json(results))
        elif args.format == 'table':
            print(format_as_table(results))
        elif args.format == 'markdown':
            print(format_as_markdown(results))

        # Exit code based on whether we found results
        if 'error' in results:
            return 1
        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == '__main__':
    exit(main())
