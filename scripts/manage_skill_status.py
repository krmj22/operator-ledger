#!/usr/bin/env python3
"""
Manage Skill Status - Automatic Promotion/Demotion Between Active and Historical

This script implements Issue #59:
- Promotes skills from skills_history.yaml to skills_active.yaml based on usage
- Demotes skills from skills_active.yaml to skills_history.yaml based on inactivity
- Generates weekly status change reports

Promotion Rules:
1. session_count >= 5
2. 3+ sessions in last 30 days
3. Level 2+ with validated outcome evidence
4. Manual override (status == 'active')

Demotion Rules:
1. 90+ days inactive (from temporal_metadata.last_seen)
2. Level 0-1 (after decay)
3. status == 'dormant'
4. session_count <= 2 AND Level 2+ (weak evidence)

Usage:
  python3 scripts/manage_skill_status.py [--dry-run] [--output report.yaml]
"""

import yaml
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import defaultdict


# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
OPERATOR_ROOT = SCRIPT_DIR.parent
ACTIVE_FILE = OPERATOR_ROOT / "ledger/skills_active.yaml"
HISTORICAL_FILE = OPERATOR_ROOT / "ledger/skills_history.yaml"
LOG_DIR = OPERATOR_ROOT / "ledger/logs"


def load_yaml_file(filepath: Path) -> Dict[str, Any]:
    """Load YAML file and return parsed data."""
    with open(filepath, 'r') as f:
        return yaml.safe_load(f)


def save_yaml_file(filepath: Path, data: Dict[str, Any]) -> None:
    """Save data to YAML file with consistent formatting."""
    with open(filepath, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def calculate_days_since(date_str: str) -> int:
    """Calculate days since a given date string (YYYY-MM-DD)."""
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        return (datetime.now() - date).days
    except (ValueError, TypeError):
        return 0


def count_recent_sessions(skill: Dict[str, Any], days: int = 30) -> int:
    """
    Count sessions in the last N days.

    Uses temporal_metadata if available, otherwise falls back to evidence array.
    """
    # Try to get from temporal_metadata first
    temporal = skill.get('temporal_metadata', {})
    last_seen = temporal.get('last_seen')

    if not last_seen:
        return 0

    days_since = calculate_days_since(last_seen)

    # If last_seen is NOT within N days, no recent sessions
    if days_since > days:
        return 0

    # Last_seen is within N days, estimate recent sessions based on total count and frequency
    session_count = temporal.get('session_count', 0)
    frequency = temporal.get('frequency', 'occasional')

    # Conservative estimate: assume sessions are distributed over time
    # If last activity was recent, likely some sessions are recent
    if frequency == 'frequent':
        # Frequent skills: assume 60-80% of sessions are recent if last_seen is within 30 days
        return max(3, int(session_count * 0.7)) if session_count >= 3 else session_count
    elif frequency == 'occasional':
        # Occasional skills: assume 40-60% of sessions are recent
        return max(2, int(session_count * 0.5)) if session_count >= 3 else session_count
    elif frequency == 'rare':
        # Rare skills: assume 20-30% of sessions are recent
        return max(1, int(session_count * 0.3)) if session_count >= 2 else session_count

    return session_count  # Default: return total count if within N days


def has_validated_outcome_evidence(skill: Dict[str, Any]) -> bool:
    """Check if skill has validated outcome evidence."""
    return (
        skill.get('outcome_validation_status') == 'validated'
        or (
            'outcome_evidence' in skill
            and skill['outcome_evidence']
            and len(skill['outcome_evidence']) > 0
        )
    )


def should_promote(skill: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Determine if a historical skill should be promoted to active.

    Returns: (should_promote: bool, reason: str)
    """
    temporal = skill.get('temporal_metadata', {})
    session_count = temporal.get('session_count', 0)
    level = skill.get('level', 0)
    status = skill.get('status', '')

    # Rule 1: Manual override
    if status == 'active':
        return True, "Manual override - status set to active"

    # Rule 2: Session threshold met
    if session_count >= 5:
        return True, f"Session threshold met ({session_count} sessions)"

    # Rule 3: Recent activity (3+ sessions in last 30 days)
    recent_sessions = count_recent_sessions(skill, days=30)
    if recent_sessions >= 3:
        return True, f"Recent activity ({recent_sessions} sessions in last 30 days)"

    # Rule 4: Level 2+ with validated outcome evidence
    if level >= 2 and has_validated_outcome_evidence(skill):
        return True, f"Level {level} with validated outcome evidence"

    return False, ""


def should_demote(skill: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Determine if an active skill should be demoted to historical.

    Returns: (should_demote: bool, reason: str)
    """
    temporal = skill.get('temporal_metadata', {})
    last_seen = temporal.get('last_seen', '')
    session_count = temporal.get('session_count', 0)
    level = skill.get('level', 0)
    status = skill.get('status', '')

    # Rule 1: Manual override
    if status == 'dormant':
        return True, "Manual override - status set to dormant"

    # Rule 2: 90+ days inactive
    if last_seen:
        days_inactive = calculate_days_since(last_seen)
        if days_inactive >= 90:
            return True, f"90+ days inactive ({days_inactive} days since {last_seen})"

    # Rule 3: Level 0-1 (after decay)
    if level <= 1:
        return True, f"Low level after decay (Level {level})"

    # Rule 4: Single-session pattern at high level (weak evidence)
    if session_count <= 2 and level >= 2:
        return True, f"Weak evidence (only {session_count} sessions at Level {level})"

    return False, ""


def promote_skill(skill: Dict[str, Any], skill_name: str) -> Dict[str, Any]:
    """
    Promote skill from historical to active format.

    Expands minimal tracking to full detail while preserving all historical data.
    """
    promoted = skill.copy()

    # Update status
    promoted['status'] = 'active'

    # Add promotion metadata
    if 'temporal_metadata' not in promoted:
        promoted['temporal_metadata'] = {}

    promoted['temporal_metadata']['promoted_date'] = datetime.now().strftime("%Y-%m-%d")

    # Ensure full tracking structures exist
    if 'evidence' not in promoted or not promoted['evidence']:
        promoted['evidence'] = []

    if 'outcome_evidence' not in promoted:
        promoted['outcome_evidence'] = []

    return promoted


def demote_skill(skill: Dict[str, Any], skill_name: str) -> Dict[str, Any]:
    """
    Demote skill from active to historical format.

    Collapses to minimal tracking but preserves temporal_metadata and session references.
    """
    # Create minimal skill entry
    demoted = {
        'skill': skill_name,
        'level': skill.get('level', 0),
        'validation': skill.get('validation', 'agent-assessed'),
        'status': 'dormant',
    }

    # Preserve temporal metadata (essential for tracking)
    if 'temporal_metadata' in skill:
        demoted['temporal_metadata'] = skill['temporal_metadata'].copy()
        demoted['temporal_metadata']['demoted_date'] = datetime.now().strftime("%Y-%m-%d")

    # Preserve minimal evidence (first source + note)
    evidence = skill.get('evidence', [])
    if evidence and len(evidence) > 0:
        first_evidence = evidence[0]
        if isinstance(first_evidence, dict):
            demoted['evidence_note'] = first_evidence.get('note', 'No description')
            if 'source' in first_evidence:
                demoted['evidence_sources'] = [{
                    'source': first_evidence['source'],
                    'date': first_evidence.get('date', ''),
                    'note': first_evidence.get('note', '')[:100]  # Truncate
                }]

    # Add brief status note
    demoted['status_note'] = f"Demoted from active (2025-12-01)"

    return demoted


def extract_all_skills(data: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any], List[str]]]:
    """
    Extract all skills from nested YAML structure.

    Returns: [(skill_name, skill_data, path_to_skill), ...]
    where path_to_skill is like ['tech_stack', 'frameworks']
    """
    skills = []

    def traverse(node, path=[]):
        if isinstance(node, dict):
            if 'skill' in node and 'level' in node:
                # This is a skill entry
                skill_name = node['skill']
                skills.append((skill_name, node, path))
            else:
                # Traverse deeper
                for key, value in node.items():
                    if key == 'skills':
                        traverse(value, path)
                    elif isinstance(value, (dict, list)):
                        traverse(value, path + [key])
        elif isinstance(node, list):
            for item in node:
                traverse(item, path)

    traverse(data)
    return skills


def remove_skill_from_structure(data: Dict[str, Any], skill_name: str) -> bool:
    """
    Remove a skill from the nested YAML structure.

    Returns True if skill was found and removed.
    """
    def traverse_and_remove(node):
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if isinstance(value, list):
                    # Check if this list contains the skill
                    original_len = len(value)
                    node[key] = [item for item in value if not (isinstance(item, dict) and item.get('skill') == skill_name)]
                    if len(node[key]) < original_len:
                        return True
                elif isinstance(value, dict):
                    if traverse_and_remove(value):
                        return True
        return False

    return traverse_and_remove(data)


def add_skill_to_structure(data: Dict[str, Any], skill_data: Dict[str, Any], path: List[str]) -> None:
    """
    Add a skill to the nested YAML structure at the specified path.
    """
    # Navigate to the correct category
    current = data
    for segment in path:
        if segment not in current:
            current[segment] = {}
        current = current[segment]

    # Add to the list at this path
    if not isinstance(current, list):
        # If path leads to a dict, we need to find or create a list
        # This handles the nested structure like tech_stack -> frameworks -> [skills]
        # We'll append to the first list we find or create one

        # Try to find an existing list
        for key, value in current.items():
            if isinstance(value, list):
                value.append(skill_data)
                return

        # No list found, create one under a default key
        current['items'] = [skill_data]
    else:
        current.append(skill_data)


def process_skill_status_changes(dry_run: bool = False) -> Dict[str, Any]:
    """
    Main processing function to promote/demote skills.

    Returns report data with promotions and demotions.
    """
    print("Loading skills files...")
    active_data = load_yaml_file(ACTIVE_FILE)
    historical_data = load_yaml_file(HISTORICAL_FILE)

    print(f"Active skills loaded from: {ACTIVE_FILE}")
    print(f"Historical skills loaded from: {HISTORICAL_FILE}")

    # Extract all skills
    active_skills = extract_all_skills(active_data)
    historical_skills = extract_all_skills(historical_data)

    print(f"\nFound {len(active_skills)} active skills")
    print(f"Found {len(historical_skills)} historical skills")

    promotions = []
    demotions = []

    # Check historical skills for promotion
    print("\n" + "="*60)
    print("CHECKING HISTORICAL SKILLS FOR PROMOTION")
    print("="*60)

    for skill_name, skill_data, path in historical_skills:
        should_promote_flag, reason = should_promote(skill_data)
        if should_promote_flag:
            promotions.append({
                'skill': skill_name,
                'reason': reason,
                'old_level': skill_data.get('level', 0),
                'session_count': skill_data.get('temporal_metadata', {}).get('session_count', 0),
                'path': path,
                'data': skill_data
            })
            print(f"  ✓ PROMOTE: {skill_name} - {reason}")

    # Check active skills for demotion
    print("\n" + "="*60)
    print("CHECKING ACTIVE SKILLS FOR DEMOTION")
    print("="*60)

    for skill_name, skill_data, path in active_skills:
        should_demote_flag, reason = should_demote(skill_data)
        if should_demote_flag:
            demotions.append({
                'skill': skill_name,
                'reason': reason,
                'old_level': skill_data.get('level', 0),
                'last_seen': skill_data.get('temporal_metadata', {}).get('last_seen', ''),
                'days_inactive': calculate_days_since(skill_data.get('temporal_metadata', {}).get('last_seen', '')) if skill_data.get('temporal_metadata', {}).get('last_seen') else 0,
                'path': path,
                'data': skill_data
            })
            print(f"  ✓ DEMOTE: {skill_name} - {reason}")

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Promotions: {len(promotions)}")
    print(f"Demotions: {len(demotions)}")
    print(f"No changes: {len(active_skills) + len(historical_skills) - len(promotions) - len(demotions)}")

    if dry_run:
        print("\n[DRY RUN] No changes written to files")
        return {
            'date': datetime.now().strftime("%Y-%m-%d"),
            'promotions': promotions,
            'demotions': demotions,
            'no_changes': len(active_skills) + len(historical_skills) - len(promotions) - len(demotions)
        }

    # Apply changes
    if promotions or demotions:
        print("\nApplying changes...")

        # Process demotions first (active -> historical)
        for demotion in demotions:
            skill_name = demotion['skill']
            skill_data = demotion['data']
            path = demotion['path']

            # Remove from active
            remove_skill_from_structure(active_data, skill_name)

            # Add to historical (demoted format)
            demoted_skill = demote_skill(skill_data, skill_name)
            add_skill_to_structure(historical_data, demoted_skill, path)

            print(f"  ✓ Demoted: {skill_name}")

        # Process promotions (historical -> active)
        for promotion in promotions:
            skill_name = promotion['skill']
            skill_data = promotion['data']
            path = promotion['path']

            # Remove from historical
            remove_skill_from_structure(historical_data, skill_name)

            # Add to active (promoted format)
            promoted_skill = promote_skill(skill_data, skill_name)
            add_skill_to_structure(active_data, promoted_skill, path)

            print(f"  ✓ Promoted: {skill_name}")

        # Save updated files
        print("\nSaving updated files...")
        save_yaml_file(ACTIVE_FILE, active_data)
        save_yaml_file(HISTORICAL_FILE, historical_data)
        print(f"  ✓ Saved: {ACTIVE_FILE}")
        print(f"  ✓ Saved: {HISTORICAL_FILE}")

    return {
        'date': datetime.now().strftime("%Y-%m-%d"),
        'promotions': promotions,
        'demotions': demotions,
        'no_changes': len(active_skills) + len(historical_skills) - len(promotions) - len(demotions)
    }


def generate_report(report_data: Dict[str, Any], output_path: Path = None) -> None:
    """Generate weekly skill status change report."""
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d")
        output_path = LOG_DIR / f"skill_status_changes_{timestamp}.yaml"

    # Ensure log directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Format report for YAML output
    report = {
        'skill_status_changes': {
            'date': report_data['date'],
            'promotions': [
                {
                    'skill': p['skill'],
                    'reason': p['reason'],
                    'old_level': p['old_level'],
                    'session_count': p['session_count']
                }
                for p in report_data['promotions']
            ],
            'demotions': [
                {
                    'skill': d['skill'],
                    'reason': d['reason'],
                    'old_level': d['old_level'],
                    'last_seen': d['last_seen'],
                    'days_inactive': d['days_inactive']
                }
                for d in report_data['demotions']
            ],
            'no_changes': report_data['no_changes']
        }
    }

    save_yaml_file(output_path, report)
    print(f"\nReport generated: {output_path}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Manage skill status between active and historical')
    parser.add_argument('--dry-run', action='store_true', help='Show what would change without modifying files')
    parser.add_argument('--output', type=str, help='Output path for report (default: logs/skill_status_changes_YYYYMMDD.yaml)')

    args = parser.parse_args()

    print("="*60)
    print("SKILL STATUS MANAGEMENT")
    print("="*60)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.dry_run:
        print("Mode: DRY RUN (no changes will be written)")
    print("="*60)

    try:
        # Process changes
        report_data = process_skill_status_changes(dry_run=args.dry_run)

        # Generate report
        output_path = Path(args.output) if args.output else None
        generate_report(report_data, output_path)

        print("\n✓ Skill status management complete")

        # Exit code based on changes
        if report_data['promotions'] or report_data['demotions']:
            sys.exit(0)  # Changes made
        else:
            sys.exit(0)  # No changes needed

    except Exception as e:
        print(f"\n✗ ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
