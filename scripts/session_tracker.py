#!/usr/bin/env python3
"""
Session Activity Tracker
Extracts session-level metadata from CLI transcripts and updates sessions.yaml.

Part of Issue #45: Add session activity tracking to ledger.
"""

import json
import yaml
import re
import os
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple


def parse_history_jsonl(history_path: Path) -> Dict[str, List[Dict]]:
    """Parse history.jsonl and group by session ID."""
    sessions = {}
    try:
        with open(history_path, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                session_id = entry.get("sessionId")
                if session_id:
                    if session_id not in sessions:
                        sessions[session_id] = []
                    sessions[session_id].append(entry)
    except Exception as e:
        print(f"❌ Error parsing {history_path}: {e}")
        return {}
    return sessions


def convert_history_session_to_transcript(session_id: str, entries: List[Dict]) -> Dict:
    """Convert history.jsonl session entries to transcript format."""
    if not entries:
        return {}

    # Sort by timestamp
    sorted_entries = sorted(entries, key=lambda x: x.get("timestamp", 0))

    # Extract timestamps (in milliseconds)
    timestamps = [e.get("timestamp", 0) for e in sorted_entries if e.get("timestamp")]
    start_time = datetime.fromtimestamp(timestamps[0] / 1000).isoformat() if timestamps else ""
    end_time = datetime.fromtimestamp(timestamps[-1] / 1000).isoformat() if timestamps else None

    # Convert entries to interactions format
    interactions = []
    for entry in sorted_entries:
        interactions.append({
            "content": entry.get("display", ""),
            "timestamp": entry.get("timestamp", 0),
            "working_dir": entry.get("project", "")
        })

    return {
        "session_id": session_id,
        "start_time": start_time,
        "end_time": end_time,
        "interactions": interactions
    }


def parse_transcript(transcript_path: Path) -> Optional[Dict]:
    """Parse a single transcript JSON file."""
    try:
        with open(transcript_path, 'r') as f:
            data = json.load(f)

        # Validate required fields per AGENTS.md session contract
        if not all(key in data for key in ["session_id", "start_time", "interactions"]):
            print(f"⚠️  Missing required fields in {transcript_path.name}")
            return None

        return data
    except Exception as e:
        print(f"❌ Error parsing {transcript_path.name}: {e}")
        return None


def extract_working_directory(interactions: List[Dict]) -> Optional[str]:
    """Extract working directory from interaction content."""
    # First check if working_dir is directly available (from history.jsonl)
    for interaction in interactions:
        working_dir = interaction.get("working_dir")
        if working_dir:
            return working_dir

    # Fall back to pattern matching in content
    patterns = [
        r"Working directory:\s*([^\n]+)",
        r"cwd:\s*([^\n]+)",
        r"pwd:\s*([^\n]+)",
        r"cd\s+([^\s\n]+)",
        r"directory:\s*([^\n]+)",
    ]

    for interaction in interactions:
        content = interaction.get("content", "")
        if not content:
            continue

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                wd = match.group(1).strip()
                # Clean up common artifacts
                wd = wd.replace("`", "").replace("\"", "").replace("'", "")
                if os.path.isabs(wd):
                    return wd

    return None


def match_project_from_directory(working_dir: Optional[str], projects: List[Dict]) -> Optional[Dict]:
    """Match working directory to a project from projects.yaml."""
    if not working_dir:
        return None

    # Try exact match first
    for project in projects:
        name = project.get("name", "")
        alias = project.get("alias", "")

        # Check if working dir contains project name or alias
        if name.lower() in working_dir.lower() or (alias and alias.lower() in working_dir.lower()):
            return {
                "project_id": alias if alias else name,
                "project_name": name,
                "inferred_from": "working_directory_match"
            }

    # Try partial path matching
    for project in projects:
        name = project.get("name", "")
        # Extract key words from project name (remove parentheses content)
        key_words = re.sub(r'\([^)]*\)', '', name).strip().lower()

        if key_words and key_words in working_dir.lower():
            return {
                "project_id": project.get("alias", name),
                "project_name": name,
                "inferred_from": "working_directory_partial_match"
            }

    return None


def detect_skills_in_session(interactions: List[Dict]) -> List[str]:
    """Detect skills demonstrated in session using simplified pattern matching."""
    # Simplified skill patterns (subset of skill_ingestion.py patterns)
    skill_patterns = {
        "Project Management": [
            r"issue\s+\d+",
            r"GitHub\s+issue",
            r"tracking\s+progress",
            r"todo\s+list",
            r"milestone",
        ],
        "Critical Thinking & Evaluation": [
            r"analyze\s+options",
            r"evaluate\s+approach",
            r"trade[-\s]?offs?",
            r"consider\s+alternatives",
        ],
        "GitHub MCP Integration": [
            r"gh\s+issue",
            r"gh\s+pr",
            r"github\s+api",
            r"create\s+issue",
        ],
        "Pattern Recognition": [
            r"recurring\s+pattern",
            r"common\s+pattern",
            r"identify\s+pattern",
        ],
        "Documentation & Knowledge Capture": [
            r"document(?:ing|ed)",
            r"write\s+(?:readme|docs?|guide)",
            r"update\s+documentation",
        ],
    }

    detected_skills = set()
    combined_content = " ".join([
        interaction.get("content", "")
        for interaction in interactions
        if interaction.get("type") == "user_prompt"  # Per AGENTS.md contract
    ])

    for skill_name, patterns in skill_patterns.items():
        for pattern in patterns:
            if re.search(pattern, combined_content, re.IGNORECASE):
                detected_skills.add(skill_name)
                break  # One match per skill is enough

    return sorted(list(detected_skills))


def generate_activity_summary(interactions: List[Dict], skills: List[str]) -> str:
    """Generate human-readable activity summary."""
    if not interactions:
        return "Empty session (no interactions)"

    # Extract first few user prompts for context
    user_prompts = [
        interaction.get("content", "")[:100]  # First 100 chars
        for interaction in interactions[:5]  # First 5 interactions
        if interaction.get("type") == "user_prompt"
    ]

    if not user_prompts:
        return f"{len(interactions)} interactions recorded"

    # Create summary from first prompt + skill list
    first_prompt = user_prompts[0].strip()
    if len(first_prompt) > 80:
        first_prompt = first_prompt[:77] + "..."

    if skills:
        return f"{first_prompt} | Skills: {', '.join(skills[:3])}"
    else:
        return first_prompt


def calculate_duration(start_time: str, end_time: Optional[str]) -> float:
    """Calculate session duration in minutes."""
    if not end_time:
        return 0.0

    try:
        start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        duration_seconds = (end - start).total_seconds()
        return round(duration_seconds / 60, 1)
    except Exception:
        return 0.0


def load_sessions_yaml(sessions_path: Path) -> Dict:
    """Load existing sessions.yaml file."""
    if not sessions_path.exists():
        # Create default structure
        return {"sessions": []}

    with open(sessions_path, 'r') as f:
        data = yaml.safe_load(f)
        if not data or "sessions" not in data:
            return {"sessions": []}
        return data


def save_sessions_yaml(sessions_path: Path, data: Dict):
    """Save sessions.yaml with proper formatting."""
    with open(sessions_path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def session_exists(sessions: List[Dict], session_id: str) -> bool:
    """Check if session_id already exists in sessions list."""
    return any(session.get("session_id") == session_id for session in sessions)


def find_session(sessions: List[Dict], session_id: str) -> Optional[Dict]:
    """Find and return session by session_id."""
    for session in sessions:
        if session.get("session_id") == session_id:
            return session
    return None


def filenames_similar(filename1: str, filename2: str) -> bool:
    """Check if two transcript filenames are similar enough to indicate continuation."""
    # Extract base patterns from filenames
    # Examples: TerminalSavedOutput_YYMMDD-HHMMSS.json, Terminal Saved Output.json

    # Remove extensions
    base1 = Path(filename1).stem
    base2 = Path(filename2).stem

    # Extract date patterns (YYMMDD or YYYYMMDD)
    date_pattern = r'(\d{6,8})'
    date1 = re.search(date_pattern, base1)
    date2 = re.search(date_pattern, base2)

    # If both have dates, compare them (same date = similar)
    if date1 and date2:
        return date1.group(1)[:6] == date2.group(1)[:6]  # Compare first 6 digits (YYMMDD)

    # Otherwise, check if base names are similar (fuzzy match)
    # Remove all non-alphanumeric chars and compare
    clean1 = re.sub(r'[^a-zA-Z0-9]', '', base1.lower())
    clean2 = re.sub(r'[^a-zA-Z0-9]', '', base2.lower())

    # Similar if one contains the other or they share significant prefix
    return (clean1 in clean2 or clean2 in clean1 or
            (len(clean1) > 10 and len(clean2) > 10 and clean1[:10] == clean2[:10]))


def detect_continuation(new_session: Dict, existing_sessions: List[Dict]) -> Optional[str]:
    """
    Detect if new_session is a continuation of an existing session.
    Returns the session_id of the base session if continuation detected, None otherwise.

    Detection strategies:
    1. Interaction ID overlap (>50% threshold)
    2. Temporal proximity + filename similarity + working directory match
    """
    new_interactions = new_session.get("interactions", [])
    new_start_time = new_session.get("start_time", "")
    new_filename = new_session.get("transcript_path", "")
    new_working_dir = new_session.get("working_directory")

    if not new_interactions or not new_start_time:
        return None

    # Extract interaction IDs from new session
    new_ids = set()
    for interaction in new_interactions:
        interaction_id = interaction.get("id")
        if interaction_id:
            new_ids.add(interaction_id)

    # Parse new session start time
    try:
        new_start = datetime.fromisoformat(new_start_time.replace('Z', '+00:00'))
    except Exception:
        return None

    # Check each existing session for continuation indicators
    for existing in existing_sessions:
        existing_interactions = existing.get("interactions", [])
        existing_start_time = existing.get("start_time", "")
        existing_filename = existing.get("transcript_path", "")
        existing_working_dir = existing.get("working_directory")

        if not existing_interactions or not existing_start_time:
            continue

        # Strategy 1: Check for overlapping interaction IDs
        existing_ids = set()
        for interaction in existing_interactions:
            interaction_id = interaction.get("id")
            if interaction_id:
                existing_ids.add(interaction_id)

        if new_ids and existing_ids:
            overlap = new_ids & existing_ids
            overlap_ratio = len(overlap) / len(new_ids)

            # If >50% of new interactions overlap with existing, it's a continuation
            if overlap_ratio > 0.5:
                return existing.get("session_id")

        # Strategy 2: Temporal proximity + filename similarity + working directory match
        try:
            existing_start = datetime.fromisoformat(existing_start_time.replace('Z', '+00:00'))
            time_diff_seconds = abs((new_start - existing_start).total_seconds())

            # Within 4 hours (14400 seconds)
            if time_diff_seconds < 14400:
                # Check filename similarity
                if filenames_similar(new_filename, existing_filename):
                    # If we have working directories, they should match
                    if new_working_dir and existing_working_dir:
                        if new_working_dir == existing_working_dir:
                            return existing.get("session_id")
                    else:
                        # No working dir info, rely on time + filename
                        return existing.get("session_id")
        except Exception:
            continue

    return None


def merge_session_continuation(base_session: Dict, continuation_data: Dict) -> Dict:
    """
    Merge continuation session data into base session.
    Strategy: Keep the most complete version (highest interaction count).

    Updates:
    - end_time: Use latest
    - interaction_count: Use highest
    - skills_demonstrated: Union of both sets
    - activity_summary: Use continuation's summary
    - continuation_metadata: Track all transcript paths
    """
    # Use latest end_time
    continuation_end = continuation_data.get("end_time")
    if continuation_end:
        base_session["end_time"] = continuation_end

    # Recalculate duration with new end_time
    base_session["duration_minutes"] = calculate_duration(
        base_session.get("start_time", ""),
        base_session.get("end_time")
    )

    # Use highest interaction count
    new_count = continuation_data.get("interaction_count", 0)
    old_count = base_session.get("interaction_count", 0)
    if new_count > old_count:
        base_session["interaction_count"] = new_count

    # Merge skills (union)
    base_skills = set(base_session.get("skills_demonstrated", []))
    new_skills = set(continuation_data.get("skills_demonstrated", []))
    merged_skills = sorted(list(base_skills | new_skills))
    base_session["skills_demonstrated"] = merged_skills

    # Update activity summary to latest
    base_session["activity_summary"] = continuation_data.get("activity_summary",
                                                             base_session.get("activity_summary", ""))

    # Initialize or update continuation_metadata
    if "continuation_metadata" not in base_session:
        base_session["continuation_metadata"] = {
            "continued_from": [base_session.get("transcript_path", "")],
            "continuation_count": 0
        }

    # Add new transcript path to continuation list
    new_transcript = continuation_data.get("transcript_path", "")
    if new_transcript and new_transcript not in base_session["continuation_metadata"]["continued_from"]:
        base_session["continuation_metadata"]["continued_from"].append(new_transcript)
        base_session["continuation_metadata"]["continuation_count"] += 1

    # Update ingestion metadata
    base_session["ingestion_metadata"]["ingested_at"] = datetime.now().isoformat()

    return base_session


def process_transcript(
    transcript_path: Path,
    projects: List[Dict],
    sessions_yaml_path: Path,
    data_dir: Path
) -> bool:
    """Process a single transcript and update sessions.yaml."""

    # Parse transcript
    transcript_data = parse_transcript(transcript_path)
    if not transcript_data:
        return False

    session_id = transcript_data["session_id"]

    # Load existing sessions
    sessions_data = load_sessions_yaml(sessions_yaml_path)

    # Check for exact duplicates
    if session_exists(sessions_data["sessions"], session_id):
        print(f"⏭️  Skipping {transcript_path.name} (already ingested)")
        return False

    # Extract metadata
    start_time = transcript_data.get("start_time", "")
    end_time = transcript_data.get("end_time")
    interactions = transcript_data.get("interactions", [])

    date = start_time[:10] if start_time else "unknown"
    duration_minutes = calculate_duration(start_time, end_time)
    interaction_count = len(interactions)

    # Extract working directory and match project
    working_dir = extract_working_directory(interactions)
    project_context = match_project_from_directory(working_dir, projects)

    # Detect skills
    skills_demonstrated = detect_skills_in_session(interactions)

    # Generate activity summary
    activity_summary = generate_activity_summary(interactions, skills_demonstrated)

    # Calculate relative transcript path (relative to data dir)
    try:
        relative_path = str(transcript_path.relative_to(data_dir))
    except ValueError:
        relative_path = str(transcript_path)

    # Create session entry (needed for both new sessions and continuation detection)
    session_entry = {
        "session_id": session_id,
        "date": date,
        "start_time": start_time,
        "end_time": end_time if end_time else None,
        "duration_minutes": duration_minutes,
        "interaction_count": interaction_count,
        "working_directory": working_dir,
        "project_context": project_context,
        "activity_summary": activity_summary,
        "skills_demonstrated": skills_demonstrated,
        "transcript_path": relative_path,
        "interactions": interactions,  # Include for continuation detection
        "ingestion_metadata": {
            "ingested_at": datetime.now().isoformat(),
            "confidence": 90  # Conservative confidence score
        }
    }

    # Check for session continuation
    continuation_of = detect_continuation(session_entry, sessions_data["sessions"])
    if continuation_of:
        print(f"🔗 Detected continuation of session {continuation_of[:8]}...")
        base_session = find_session(sessions_data["sessions"], continuation_of)
        if base_session:
            merge_session_continuation(base_session, session_entry)
            save_sessions_yaml(sessions_yaml_path, sessions_data)
            print(f"✅ Merged continuation from {transcript_path.name}")
            return True
        else:
            # Should never happen, but fallback to adding as new session
            print(f"⚠️  Continuation detected but base session not found, adding as new")

    # Remove interactions from session_entry before saving (not needed in YAML)
    session_entry.pop("interactions", None)

    # Append to sessions
    sessions_data["sessions"].append(session_entry)

    # Save back to file
    save_sessions_yaml(sessions_yaml_path, sessions_data)

    print(f"✅ Ingested session {session_id[:8]}... from {transcript_path.name}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Track session activity and update sessions.yaml")
    parser.add_argument("--transcript-dir", type=Path, help="Directory containing transcript JSON files")
    parser.add_argument("--projects-yaml", type=Path, help="Path to projects.yaml")
    parser.add_argument("--sessions-yaml", type=Path, help="Path to sessions.yaml (output)")
    parser.add_argument("--transcript", type=Path, help="Single transcript file to process")

    args = parser.parse_args()

    # Get paths from environment or arguments
    operator_root = Path(__file__).parent.parent

    transcript_dir = args.transcript_dir or Path(os.getenv("OPERATOR_DATA_DIR", operator_root / "data"))
    projects_yaml = args.projects_yaml or operator_root / "ledger" / "projects" / "repos.yaml"
    sessions_yaml = args.sessions_yaml or operator_root / "ledger" / "activity" / "sessions.yaml"

    # Validate paths
    if not projects_yaml.exists():
        print(f"❌ projects.yaml not found at {projects_yaml}")
        return 1

    # Load projects
    with open(projects_yaml, 'r') as f:
        projects_data = yaml.safe_load(f)
        projects = projects_data.get("repositories", [])

    print(f"📂 Transcript directory: {transcript_dir}")
    print(f"📋 Projects loaded: {len(projects)}")
    print(f"📝 Sessions file: {sessions_yaml}")
    print()

    # Process transcripts
    if args.transcript:
        # Single transcript mode
        success = process_transcript(args.transcript, projects, sessions_yaml, transcript_dir)
        return 0 if success else 1
    else:
        # Batch mode - check for history.jsonl first
        history_file = transcript_dir / "history.jsonl"

        if history_file.exists():
            print(f"📚 Processing history.jsonl...")
            sessions_dict = parse_history_jsonl(history_file)
            print(f"Found {len(sessions_dict)} unique sessions\n")

            ingested_count = 0
            for session_id, entries in sessions_dict.items():
                # Convert to transcript format
                transcript_data = convert_history_session_to_transcript(session_id, entries)
                if not transcript_data:
                    continue

                # Load existing sessions
                sessions_data = load_sessions_yaml(sessions_yaml)

                # Check for duplicates
                if session_exists(sessions_data["sessions"], session_id):
                    print(f"⏭️  Skipping session {session_id[:8]}... (already ingested)")
                    continue

                # Extract metadata
                start_time = transcript_data.get("start_time", "")
                end_time = transcript_data.get("end_time")
                interactions = transcript_data.get("interactions", [])

                date = start_time[:10] if start_time else "unknown"
                duration_minutes = calculate_duration(start_time, end_time)
                interaction_count = len(interactions)

                # Extract working directory and match project
                working_dir = extract_working_directory(interactions)
                project_context = match_project_from_directory(working_dir, projects)

                # Build minimal session entry for history.jsonl
                session_entry = {
                    "session_id": session_id,
                    "date": date,
                    "start_time": start_time,
                    "end_time": end_time if end_time else None,
                    "duration_minutes": duration_minutes,
                    "interaction_count": interaction_count,
                    "working_directory": working_dir,
                    "project_context": project_context,
                    "activity_summary": "Session tracked from history.jsonl",
                    "skills_demonstrated": [],
                    "transcript_path": "history.jsonl",
                    "ingestion_metadata": {
                        "ingested_at": datetime.now().isoformat(),
                        "source": "history.jsonl",
                        "confidence": 70  # Lower confidence for history.jsonl sessions
                    }
                }

                # Append to sessions
                sessions_data["sessions"].append(session_entry)
                save_sessions_yaml(sessions_yaml, sessions_data)

                project_name = project_context.get('name', 'Unknown') if project_context else 'Unknown'
                print(f"✅ {session_id[:8]}... | {date} | {project_name} ({interaction_count} interactions)")
                ingested_count += 1

            print(f"\n✨ Ingested {ingested_count} new sessions from history.jsonl")
            return 0

        # Fall back to legacy TerminalSavedOutput_*.json files
        json_files = sorted(transcript_dir.glob("TerminalSavedOutput_*.json"))

        if not json_files:
            print(f"⚠️  No transcript files found in {transcript_dir}")
            return 1

        print(f"Found {len(json_files)} transcript files\n")

        ingested_count = 0
        for json_file in json_files:
            if process_transcript(json_file, projects, sessions_yaml, transcript_dir):
                ingested_count += 1

        print(f"\n✨ Ingested {ingested_count} new sessions")
        return 0


if __name__ == "__main__":
    exit(main())
