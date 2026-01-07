#!/usr/bin/env python3
"""
Apply Approved Skill Updates
Reads skill_ingestion_report.yaml and applies only approved updates to skills.yaml

IAW Issue #44 - Human review workflow
"""

import yaml
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any


def load_report(report_path: Path) -> Dict:
    """Load the skill ingestion report."""
    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")

    with open(report_path, 'r') as f:
        return yaml.safe_load(f)


def load_skills(skills_path: Path) -> tuple:
    """
    Load skills from BOTH skills_active.yaml and skills_history.yaml.

    IAW Issue #58: Skills are split into active (high-signal) and historical (dormant).
    This function loads both files separately (NOT merged) to allow targeted updates.

    Returns:
        Tuple of (active_data, history_data, active_path, history_path, use_legacy)
    """
    ledger_dir = skills_path.parent
    active_path = ledger_dir / "skills" / "active.yaml"
    history_path = ledger_dir / "skills" / "history.yaml"
    legacy_path = skills_path  # Use the provided path as legacy fallback

    # Try to load from new split structure first
    if active_path.exists() and history_path.exists():
        print(f"   Loading from split structure (active + history)")
        with open(active_path, 'r') as f:
            active_data = yaml.safe_load(f)
        with open(history_path, 'r') as f:
            history_data = yaml.safe_load(f)
        return (active_data, history_data, active_path, history_path, False)

    # Fallback to legacy single file
    elif legacy_path.exists():
        print(f"   Loading from legacy skills.yaml")
        with open(legacy_path, 'r') as f:
            legacy_data = yaml.safe_load(f)
        return (legacy_data, None, legacy_path, None, True)

    else:
        raise FileNotFoundError(
            f"Skills files not found. Expected either:\n"
            f"  - {active_path} AND {history_path}\n"
            f"  - {legacy_path}"
        )


def find_skill_in_ledger(skills_data: Dict, skill_name: str) -> tuple:
    """
    Find a skill in the ledger structure.
    Returns (category, index, skill_dict) tuple or (None, None, None) if not found.

    IAW Issue #58: Works with both split and legacy structures.
    """
    # Check tech_stack skills
    if "skills" in skills_data and "tech_stack" in skills_data["skills"]:
        for category, category_skills in skills_data["skills"]["tech_stack"].items():
            if isinstance(category_skills, list):
                for idx, skill in enumerate(category_skills):
                    if skill.get("skill") == skill_name or skill_name.endswith(f".{skill.get('skill')}"):
                        return (f"tech_stack.{category}", idx, skill)

    # Check orchestration skills
    if "skills" in skills_data and "orchestration" in skills_data["skills"]:
        for idx, skill in enumerate(skills_data["skills"]["orchestration"]):
            if skill.get("skill") == skill_name:
                return ("orchestration", idx, skill)

    # Check top-level skills (new structure from split)
    if "skills" in skills_data:
        for idx, skill in enumerate(skills_data.get("skills", [])):
            if isinstance(skill, dict) and skill.get("skill") == skill_name:
                return ("skills", idx, skill)

    return (None, None, None)


def apply_update(skills_data: Dict, update: Dict) -> bool:
    """
    Apply a single approved update to the skills data.

    IAW Issue #58: Works with both split and legacy structures.
    IAW Issue #71: Adds evidence_sessions for transcript drill-down.
    The skill dict is modified in-place, so changes are reflected in skills_data.

    Returns True if update was applied, False if skill not found.
    """
    skill_name = update.get("skill_name")
    category, idx, skill = find_skill_in_ledger(skills_data, skill_name)

    if category is None:
        print(f"   ⚠️  Skill not found in ledger: {skill_name}")
        print(f"      This is a new skill - consider adding manually first")
        return False

    # Update temporal metadata if provided
    if "temporal_metadata" in update:
        if "temporal_metadata" not in skill:
            skill["temporal_metadata"] = {}

        for key, value in update["temporal_metadata"].items():
            skill["temporal_metadata"][key] = value

    # Add evidence samples as new evidence entries
    if "evidence_samples" in update and update["evidence_samples"]:
        if "evidence" not in skill:
            skill["evidence"] = []
        elif isinstance(skill["evidence"], str):
            # Convert string evidence to list format
            old_evidence = skill["evidence"]
            skill["evidence"] = [{"note": old_evidence}]

        # Add new evidence from samples
        for sample in update["evidence_samples"]:
            evidence_entry = {
                "source_file": sample.get("source_file", ""),
                "interaction_id": sample.get("interaction_id", ""),
                "note": sample.get("content", "")[:200]  # Truncate to 200 chars
            }

            # Check for duplicate evidence
            is_duplicate = any(
                e.get("source_file") == evidence_entry["source_file"] and
                e.get("interaction_id") == evidence_entry["interaction_id"]
                for e in skill["evidence"]
                if isinstance(e, dict)
            )

            if not is_duplicate:
                skill["evidence"].append(evidence_entry)

    # Add evidence_sessions if provided (IAW Issue #71)
    if "evidence_sessions" in update and update["evidence_sessions"]:
        if "evidence_sessions" not in skill:
            skill["evidence_sessions"] = []

        # Add new evidence_sessions entries
        for session in update["evidence_sessions"]:
            session_entry = {
                "session_file": session.get("session_file", ""),
                "session_id": session.get("session_id", ""),
                "date": session.get("date", ""),
                "interaction_id": session.get("interaction_id", ""),
                "snippet": session.get("snippet", "")
            }

            # Check for duplicate evidence_sessions (by session_file + interaction_id)
            is_duplicate = any(
                e.get("session_file") == session_entry["session_file"] and
                e.get("interaction_id") == session_entry["interaction_id"]
                for e in skill["evidence_sessions"]
                if isinstance(e, dict)
            )

            if not is_duplicate:
                skill["evidence_sessions"].append(session_entry)

    return True


def save_skills(skills_data: Dict, skills_path: Path):
    """Save the updated skills.yaml file."""
    with open(skills_path, 'w') as f:
        yaml.dump(skills_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def main():
    parser = argparse.ArgumentParser(description="Apply approved skill updates to ledger")

    # Use script location to find operator repo root
    script_dir = Path(__file__).resolve().parent
    operator_root = script_dir.parent  # scripts -> operator

    # Use OPERATOR_LEDGER_DIR env var, fallback to ./ledger for backwards compatibility
    ledger_dir = Path(os.getenv('OPERATOR_LEDGER_DIR', operator_root / 'ledger'))

    parser.add_argument(
        "--report",
        type=Path,
        default=ledger_dir / "skill_ingestion_report.yaml",
        help="Path to skill ingestion report"
    )
    parser.add_argument(
        "--skills",
        type=Path,
        default=ledger_dir / "skills.yaml",
        help="Path to skills.yaml"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be applied without making changes"
    )

    args = parser.parse_args()

    print("📋 Applying Approved Skill Updates")
    print(f"   Report: {args.report}")
    print(f"   Skills: {args.skills}")

    if args.dry_run:
        print("   Mode: DRY RUN (no changes will be made)")

    try:
        report = load_report(args.report)
    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
        return 1

    try:
        active_data, history_data, active_path, history_path, use_legacy = load_skills(args.skills)
    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
        return 1

    # Filter for approved updates
    suggested_updates = report.get("suggested_updates", [])
    approved_updates = [u for u in suggested_updates if u.get("approved") is True]

    print(f"\n📊 Update Summary:")
    print(f"   Total suggested: {len(suggested_updates)}")
    print(f"   Approved: {len(approved_updates)}")
    print(f"   Pending review: {len(suggested_updates) - len(approved_updates)}")

    if len(approved_updates) == 0:
        print(f"\n✅ No approved updates to apply")
        print(f"   Set 'approved: true' in {args.report} to approve updates")
        return 0

    # Apply approved updates
    print(f"\n🔧 Applying {len(approved_updates)} approved updates...")

    applied_count = 0
    skipped_count = 0
    active_modified = False
    history_modified = False

    for update in approved_updates:
        skill_name = update.get("skill_name")
        confidence = update.get("confidence", 0)

        print(f"\n   • {skill_name} (confidence: {confidence}%)")

        if args.dry_run:
            print(f"      [DRY RUN] Would apply update")
            applied_count += 1
        else:
            # Try to apply to active file first
            if apply_update(active_data, update):
                print(f"      ✅ Applied (active)")
                applied_count += 1
                active_modified = True
            # If not in active, try historical file (if split structure)
            elif not use_legacy and history_data and apply_update(history_data, update):
                print(f"      ✅ Applied (historical)")
                applied_count += 1
                history_modified = True
            else:
                print(f"      ⏭️  Skipped (not found in ledger)")
                skipped_count += 1

    # Save changes
    if not args.dry_run and applied_count > 0:
        if use_legacy:
            # Legacy mode: save single file
            print(f"\n💾 Saving changes to {args.skills}...")
            save_skills(active_data, args.skills)
            print(f"✅ Changes saved")
        else:
            # Split mode: save modified files only
            if active_modified:
                print(f"\n💾 Saving changes to {active_path}...")
                save_skills(active_data, active_path)
                print(f"✅ Active skills saved")
            if history_modified:
                print(f"\n💾 Saving changes to {history_path}...")
                save_skills(history_data, history_path)
                print(f"✅ Historical skills saved")

    # Summary
    print(f"\n📈 Results:")
    print(f"   Applied: {applied_count}")
    print(f"   Skipped: {skipped_count}")

    if applied_count > 0 and not args.dry_run:
        print(f"\n✅ Next steps:")
        if use_legacy:
            print(f"   1. Review changes: git diff {args.skills}")
        else:
            print(f"   1. Review changes: git diff {active_path} {history_path}")
        print(f"   2. Verify ledger: python scripts/ledger_verify.py")
        print(f"   3. Commit changes if satisfied")

    return 0


if __name__ == "__main__":
    sys.exit(main())
