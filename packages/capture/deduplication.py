"""
Deduplication System: Prevent duplicate evidence entries.

Track processed sessions via session_id to avoid re-ingesting same session
from multiple sources (cache + manual transcripts).
"""

import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List


def load_ingestion_history(history_file: Path) -> Dict[str, List[Dict]]:
    """
    Load ingestion history from YAML file.

    Args:
        history_file: Path to ingestion_history.yaml

    Returns:
        History dict with processed_sessions list
    """
    if not history_file.exists():
        return {"processed_sessions": []}

    with open(history_file, 'r') as f:
        content = f.read().strip()
        if not content:
            return {"processed_sessions": []}
        return yaml.safe_load(content) or {"processed_sessions": []}


def save_ingestion_history(history: Dict[str, List[Dict]], history_file: Path) -> None:
    """
    Save ingestion history to YAML file.

    Args:
        history: History dict with processed_sessions
        history_file: Path to ingestion_history.yaml
    """
    history_file.parent.mkdir(parents=True, exist_ok=True)

    with open(history_file, 'w') as f:
        yaml.dump(history, f, default_flow_style=False, sort_keys=False)


def is_session_processed(history: Dict[str, List[Dict]], session_id: str) -> bool:
    """
    Check if session_id already exists in history.

    Args:
        history: Ingestion history dict
        session_id: Session ID to check

    Returns:
        True if session already processed, False otherwise
    """
    for entry in history.get("processed_sessions", []):
        if entry.get("session_id") == session_id:
            return True
    return False


def mark_session_processed(
    history: Dict[str, List[Dict]],
    session_id: str,
    source: str,
    source_path: str,
    timestamp: str = None,
    project_path: str = None
) -> None:
    """
    Add session to processed history (prevents duplicates).

    Args:
        history: Ingestion history dict (modified in-place)
        session_id: Unique session identifier
        source: Source type (e.g., "claude-code-cache", "manual-transcript")
        source_path: Path to source file
        timestamp: Optional ISO 8601 timestamp for fallback matching
        project_path: Optional project path for fallback matching
    """
    # Check if session already exists
    if is_session_processed(history, session_id):
        return  # Skip - already processed

    entry = {
        "session_id": session_id,
        "source": source,
        "source_path": source_path,
        "ingestion_date": datetime.now().strftime("%Y-%m-%d")
    }

    # Add optional fields for fallback matching
    if timestamp:
        entry["timestamp"] = timestamp
    if project_path:
        entry["project_path"] = project_path

    history.setdefault("processed_sessions", []).append(entry)


def extract_session_id_from_cache(cache_file: Path) -> str:
    """
    Extract sessionId from cache file (JSONL for Claude/Codex, JSON for Gemini).

    Args:
        cache_file: Path to cache file (.jsonl or .json)

    Returns:
        Session ID string
    """
    with open(cache_file, 'r') as f:
        content = f.read()

    # Try Gemini JSON format (single object)
    try:
        data = json.loads(content)
        if "sessionId" in data and "messages" in data:
            # Gemini format
            return data["sessionId"]
    except json.JSONDecodeError:
        pass  # Not single JSON, try JSONL

    # Parse as JSONL (Claude Code or Codex)
    for line in content.split('\n'):
        if not line.strip():
            continue

        entry = json.loads(line)

        # Claude Code: sessionId is in user/assistant messages
        if entry.get("type") in ("user", "assistant"):
            if "sessionId" in entry:
                return entry["sessionId"]

        # Codex: session_id is in session_meta.payload.id
        if entry.get("type") == "session_meta":
            payload = entry.get("payload", {})
            if "id" in payload:
                return payload["id"]

    return ""


def extract_session_id_from_manual_transcript(transcript_file: Path) -> str:
    """
    Extract session_id from manual transcript JSON file.

    Args:
        transcript_file: Path to manual transcript JSON

    Returns:
        Session ID string
    """
    with open(transcript_file, 'r') as f:
        data = json.load(f)
        return data.get("session_id", "")


def is_duplicate_by_timestamp_and_project(
    history: Dict[str, List[Dict]],
    timestamp: str,
    project_path: str
) -> bool:
    """
    Fallback duplicate detection using timestamp proximity + project path.

    Used when session_id is missing/malformed.

    Args:
        history: Ingestion history dict
        timestamp: ISO 8601 timestamp string
        project_path: Absolute path to project directory

    Returns:
        True if likely duplicate (same project, timestamps within 5 minutes)
    """
    from dateutil import parser as date_parser

    try:
        target_time = date_parser.isoparse(timestamp)
    except Exception:
        return False

    # Check each processed session
    for entry in history.get("processed_sessions", []):
        entry_timestamp = entry.get("timestamp")
        entry_project = entry.get("project_path")

        if not entry_timestamp or not entry_project:
            continue

        # Must be same project
        if entry_project != project_path:
            continue

        # Check timestamp proximity (within 5 minutes)
        try:
            entry_time = date_parser.isoparse(entry_timestamp)
            time_diff = abs((target_time - entry_time).total_seconds())

            if time_diff <= 300:  # 5 minutes = 300 seconds
                return True
        except Exception:
            continue

    return False
