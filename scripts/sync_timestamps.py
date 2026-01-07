#!/usr/bin/env python3
"""
Timestamp Synchronization Script
IAW Issue #53 - Synchronize timestamps across ledger files for deterministic operations.

Purpose:
- Identify timestamp drift between related entities (projects and skills)
- Determine canonical timestamps using semantic matching
- Update projects.yaml and skills.yaml to synchronized timestamps
- Generate report of corrections made

Strategy:
1. Find semantic relationships between projects and skills (name matching, evidence refs)
2. For each relationship, use the most recent timestamp as canonical
3. Sync both entities to canonical timestamp if drift >7 days
4. Report all changes made

Tolerance: 7 days - only sync if drift >7 days

Note: This approach uses semantic matching rather than session data because:
- Session working_directory paths may not match project repo_path exactly
- Skills may be used across multiple projects
- The goal is to sync timestamps for semantically related entities
"""

from __future__ import annotations
import sys
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Set
from collections import defaultdict

# Paths
LEDGER_ROOT = Path(__file__).resolve().parents[1] / "packages" / "ledger"
PROJECTS_FILE = LEDGER_ROOT / "projects.yaml"
SKILLS_FILE = LEDGER_ROOT / "skills.yaml"
SKILLS_ACTIVE_FILE = LEDGER_ROOT / "skills_active.yaml"
SESSIONS_FILE = LEDGER_ROOT / "sessions.yaml"

# Tolerance window
DRIFT_TOLERANCE_DAYS = 7

# Dry run mode
DRY_RUN = "--dry-run" in sys.argv


def load_yaml_file(path: Path) -> dict:
    """Load YAML file safely."""
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml_file(path: Path, data: dict):
    """Save YAML file with proper formatting."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def find_semantic_matches(project_name: str, skill_name: str) -> bool:
    """
    Determine if a project and skill are semantically related.

    Matches on:
    - Skill name appears in project name (case-insensitive)
    - Project name appears in skill name (case-insensitive)
    - Common keywords (JSON, Python, Rust, etc.)
    """
    project_lower = project_name.lower()
    skill_lower = skill_name.lower()

    # Direct substring match
    if skill_lower in project_lower or project_lower in skill_lower:
        return True

    # Check for common keywords
    keywords = ["json", "python", "rust", "yaml", "cli", "api", "web", "tauri"]
    for keyword in keywords:
        if keyword in project_lower and keyword in skill_lower:
            return True

    return False


def extract_project_info(projects_data: dict) -> List[Dict]:
    """Extract project name and timestamp info."""
    projects = []

    for project in projects_data.get("projects", []):
        if not isinstance(project, dict):
            continue

        name = project.get("name")
        last_update = project.get("last_update")

        if name and last_update:
            projects.append({
                "name": name,
                "timestamp": last_update,
                "data": project
            })

    return projects


def extract_skill_info(skills_data: dict) -> List[Dict]:
    """Extract skill name and timestamp info."""
    skills = []
    skills_section = skills_data.get("skills", {})

    # Tech stack skills
    tech_stack = skills_section.get("tech_stack", {})
    for category, skill_list in tech_stack.items():
        if not isinstance(skill_list, list):
            continue

        for skill in skill_list:
            if not isinstance(skill, dict):
                continue

            name = skill.get("skill")
            temporal = skill.get("temporal_metadata", {})
            last_seen = temporal.get("last_seen")

            if name and last_seen:
                skills.append({
                    "name": name,
                    "timestamp": last_seen,
                    "data": skill,
                    "category": category
                })

    # Orchestration skills
    orchestration = skills_section.get("orchestration", [])
    for skill in orchestration:
        if not isinstance(skill, dict):
            continue

        name = skill.get("skill")
        temporal = skill.get("temporal_metadata", {})
        last_seen = temporal.get("last_seen")

        if name and last_seen:
            skills.append({
                "name": name,
                "timestamp": last_seen,
                "data": skill,
                "category": "orchestration"
            })

    return skills


def find_timestamp_drifts(projects: List[Dict], skills: List[Dict]) -> List[Tuple]:
    """
    Find semantically related project-skill pairs with timestamp drift >7 days.

    Returns: List of (project_info, skill_info, drift_days, canonical_timestamp) tuples
    """
    drifts = []

    for project in projects:
        for skill in skills:
            # Check if semantically related
            if not find_semantic_matches(project["name"], skill["name"]):
                continue

            # Parse timestamps
            try:
                project_dt = datetime.fromisoformat(str(project["timestamp"]))
                skill_dt = datetime.fromisoformat(str(skill["timestamp"]))
            except Exception:
                continue

            # Calculate drift
            drift_days = abs((project_dt - skill_dt).days)

            if drift_days > DRIFT_TOLERANCE_DAYS:
                # Use most recent as canonical
                canonical = max(project_dt, skill_dt).date().isoformat()
                drifts.append((project, skill, drift_days, canonical))

    return drifts


def apply_timestamp_syncs(drifts: List[Tuple]) -> Tuple[List[Tuple], List[Tuple]]:
    """
    Apply timestamp syncs to project and skill data.

    Returns: (project_changes, skill_changes) where each is a list of
    (name, old_timestamp, new_timestamp, drift_days) tuples
    """
    project_changes = []
    skill_changes = []

    for project_info, skill_info, drift_days, canonical in drifts:
        project = project_info["data"]
        skill = skill_info["data"]

        old_project_timestamp = project["last_update"]
        old_skill_timestamp = skill.get("temporal_metadata", {}).get("last_seen")

        # Update project
        project["last_update"] = canonical
        project_changes.append((
            project_info["name"],
            old_project_timestamp,
            canonical,
            drift_days
        ))

        # Update skill
        if "temporal_metadata" not in skill:
            skill["temporal_metadata"] = {}
        skill["temporal_metadata"]["last_seen"] = canonical
        skill_changes.append((
            skill_info["name"],
            old_skill_timestamp,
            canonical,
            drift_days
        ))

    return project_changes, skill_changes


def main():
    print("Timestamp Synchronization Script")
    print("=" * 60)

    if DRY_RUN:
        print("[DRY RUN MODE - No changes will be written]\n")

    # Load data
    print("Loading ledger files...")
    projects_data = load_yaml_file(PROJECTS_FILE)

    # Determine which skills file to use
    if SKILLS_ACTIVE_FILE.exists():
        skills_file = SKILLS_ACTIVE_FILE
        print(f"Using split structure: {skills_file.name}")
    else:
        skills_file = SKILLS_FILE
        print(f"Using legacy structure: {skills_file.name}")

    skills_data = load_yaml_file(skills_file)

    if not projects_data or not skills_data:
        print("ERROR: Could not load projects.yaml or skills file")
        sys.exit(1)

    # Extract info
    print("\nExtracting project and skill data...")
    projects = extract_project_info(projects_data)
    skills = extract_skill_info(skills_data)

    print(f"  Found {len(projects)} projects with timestamps")
    print(f"  Found {len(skills)} skills with timestamps")

    # Find drifts
    print("\nAnalyzing timestamp consistency...")
    drifts = find_timestamp_drifts(projects, skills)

    if not drifts:
        print("\n✓ All related entity timestamps within 7-day window")
        print("  No synchronization needed")
        sys.exit(0)

    print(f"  Found {len(drifts)} project-skill pairs with >7 day drift")

    # Apply syncs
    print("\nSynchronizing timestamps...")
    project_changes, skill_changes = apply_timestamp_syncs(drifts)

    # Report changes
    print("\n" + "=" * 60)
    print("TIMESTAMP SYNC REPORT")
    print("=" * 60)

    print(f"\nDetected {len(drifts)} timestamp drift(s) between related entities:\n")

    for project_info, skill_info, drift_days, canonical in drifts:
        print(f"  {project_info['name']} ↔ {skill_info['name']}")
        print(f"    Project: {project_info['timestamp']} → {canonical}")
        print(f"    Skill:   {skill_info['timestamp']} → {canonical}")
        print(f"    Drift:   {drift_days} days")
        print()

    total_entities = len(project_changes) + len(skill_changes)

    # Write changes
    if not DRY_RUN:
        print(f"Writing changes to disk...")
        save_yaml_file(PROJECTS_FILE, projects_data)
        print(f"  ✓ Updated {PROJECTS_FILE.name}")

        save_yaml_file(skills_file, skills_data)
        print(f"  ✓ Updated {skills_file.name}")

        print(f"\n✓ Synchronized {len(drifts)} relationship(s), updated {total_entities} entities")
    else:
        print(f"[DRY RUN - Would synchronize {len(drifts)} relationship(s), updating {total_entities} entities]")

    sys.exit(0)


if __name__ == "__main__":
    main()
