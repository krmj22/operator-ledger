#!/usr/bin/env python3
"""
Generate Project-Skill Bidirectional Mappings

Purpose:
- Analyze session transcripts to extract skill usage per project
- Generate bidirectional mappings between projects.yaml and skills.yaml
- Output suggested mappings for manual review and curation

IAW Issue #52 - Bidirectional refs (connects data)

Usage:
    python scripts/generate_project_skill_mapping.py [--dry-run]

Outputs:
- project_skill_mappings.yaml - Suggested mappings for review
- Does NOT modify projects.yaml or skills.yaml directly (manual curation required)
"""

import sys
import yaml
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = ROOT / "packages" / "ledger"

def load_yaml_file(file_path: Path) -> Dict[str, Any]:
    """Load and parse a YAML file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Failed to load {file_path}: {e}")
        sys.exit(1)

def load_sessions() -> List[Dict[str, Any]]:
    """Load sessions.yaml to understand which skills were used in which projects."""
    sessions_file = PACKAGES_DIR / "sessions.yaml"
    if not sessions_file.exists():
        print("ERROR: sessions.yaml not found. Run daily_ingestion.sh first.")
        sys.exit(1)

    data = load_yaml_file(sessions_file)
    return data.get("sessions", [])

def load_projects() -> List[Dict[str, Any]]:
    """Load projects.yaml to get project definitions."""
    projects_file = PACKAGES_DIR / "projects.yaml"
    if not projects_file.exists():
        print("ERROR: projects.yaml not found")
        sys.exit(1)

    data = load_yaml_file(projects_file)
    return data.get("projects", [])

def load_skills() -> Dict[str, Any]:
    """Load skills.yaml to get skill definitions."""
    skills_file = PACKAGES_DIR / "skills.yaml"
    if not skills_file.exists():
        print("ERROR: skills.yaml not found")
        sys.exit(1)

    return load_yaml_file(skills_file)

def map_working_dir_to_project(working_dir: str, projects: List[Dict[str, Any]]) -> str:
    """Map a session working directory to a project name."""
    if not working_dir:
        return None

    working_dir_lower = working_dir.lower()

    # Try exact repo_path match first
    for project in projects:
        if "repo_path" in project:
            if working_dir == project["repo_path"]:
                return project["name"]

    # Try fuzzy match on project name or alias
    for project in projects:
        project_name_lower = project["name"].lower()
        alias_lower = project.get("alias", "").lower()

        if project_name_lower in working_dir_lower or alias_lower in working_dir_lower:
            return project["name"]

        # Check for specific keywords
        if "voice-transcription" in working_dir_lower and "voice" in project_name_lower:
            return project["name"]
        if "json transcription" in working_dir_lower and "json" in project_name_lower:
            return project["name"]
        if "accounting" in working_dir_lower and "accounting" in project_name_lower:
            return project["name"]

    return None

def get_skill_level(skill_name: str, skills_data: Dict[str, Any]) -> int:
    """Get the current level for a skill from skills.yaml."""
    skills_section = skills_data.get("skills", {})

    # Check tech_stack
    tech_stack = skills_section.get("tech_stack", {})
    for category, skill_list in tech_stack.items():
        if isinstance(skill_list, list):
            for skill in skill_list:
                if isinstance(skill, dict) and skill.get("skill") == skill_name:
                    return skill.get("level", 0)

    # Check orchestration
    orchestration = skills_section.get("orchestration", [])
    for skill in orchestration:
        if isinstance(skill, dict) and skill.get("skill") == skill_name:
            return skill.get("level", 0)

    return None

def generate_mappings() -> Dict[str, Any]:
    """Generate bidirectional project-skill mappings from session data."""
    print("Loading data files...")
    sessions = load_sessions()
    projects = load_projects()
    skills_data = load_skills()

    print(f"Loaded {len(sessions)} sessions, {len(projects)} projects")

    # Build mapping: project_name -> {skill_name: session_count}
    project_to_skills = defaultdict(lambda: defaultdict(int))
    skill_to_projects = defaultdict(lambda: defaultdict(int))

    sessions_mapped = 0
    sessions_unmapped = 0

    for session in sessions:
        working_dir = session.get("working_directory")
        skills_demonstrated = session.get("skills_demonstrated", [])

        if not skills_demonstrated:
            continue

        project_name = map_working_dir_to_project(working_dir, projects)

        if project_name:
            sessions_mapped += 1
            for skill in skills_demonstrated:
                project_to_skills[project_name][skill] += 1
                skill_to_projects[skill][project_name] += 1
        else:
            sessions_unmapped += 1

    print(f"Mapped {sessions_mapped} sessions to projects")
    print(f"Unmapped: {sessions_unmapped} sessions")

    # Generate suggested mappings
    mappings = {
        "project_skill_mappings": {
            "generated_at": "2025-12-01",
            "note": "Review and manually curate before applying to projects.yaml and skills.yaml",
            "projects": {},
            "skills": {}
        }
    }

    # For each project, suggest skills_demonstrated
    for project_name, skill_counts in project_to_skills.items():
        # Sort by session count, take top skills
        sorted_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)

        skills_list = []
        for skill_name, session_count in sorted_skills:
            skill_level = get_skill_level(skill_name, skills_data)
            if skill_level is not None and skill_level >= 1:
                skills_list.append({
                    "skill": skill_name,
                    "level": skill_level,
                    "evidence": f"Used in {session_count} sessions for this project",
                    "session_count": session_count
                })

        if skills_list:
            mappings["project_skill_mappings"]["projects"][project_name] = {
                "skills_demonstrated": skills_list
            }

    # For each skill (Level 2+), suggest projects_applied
    for skill_name, project_counts in skill_to_projects.items():
        skill_level = get_skill_level(skill_name, skills_data)

        # Only suggest for Level 2+ skills
        if skill_level is not None and skill_level >= 2:
            sorted_projects = sorted(project_counts.items(), key=lambda x: x[1], reverse=True)

            projects_list = []
            for project_name, session_count in sorted_projects:
                projects_list.append({
                    "project": project_name,
                    "contribution": f"Applied in {session_count} sessions",
                    "session_count": session_count
                })

            if projects_list:
                mappings["project_skill_mappings"]["skills"][skill_name] = {
                    "level": skill_level,
                    "projects_applied": projects_list
                }

    return mappings

def main():
    dry_run = "--dry-run" in sys.argv

    print("Generating project-skill mappings from session data...")
    print("=" * 60)

    mappings = generate_mappings()

    # Output suggested mappings
    output_file = ROOT / "project_skill_mappings.yaml"

    if dry_run:
        print("\nDRY RUN - would write to:", output_file)
        print("\nSuggested mappings:")
        print(yaml.dump(mappings, default_flow_style=False, sort_keys=False))
    else:
        with open(output_file, 'w', encoding='utf-8') as f:
            yaml.dump(mappings, f, default_flow_style=False, sort_keys=False)
        print(f"\nSuggested mappings written to: {output_file}")
        print("\nNext steps:")
        print("1. Review project_skill_mappings.yaml")
        print("2. Manually curate and refine the suggestions")
        print("3. Apply approved mappings to projects.yaml and skills.yaml")
        print("4. Run ledger_verify.py to validate cross-references")

    # Print summary
    projects_count = len(mappings["project_skill_mappings"]["projects"])
    skills_count = len(mappings["project_skill_mappings"]["skills"])

    print("\n" + "=" * 60)
    print(f"Summary:")
    print(f"  Projects with suggested skills: {projects_count}")
    print(f"  Skills with suggested projects: {skills_count}")
    print("=" * 60)

if __name__ == "__main__":
    main()
