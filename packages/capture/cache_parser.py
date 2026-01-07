"""
Cache Parser: Parse agent session cache files into session envelope format.

Supports multiple agent formats:
- Claude Code: JSONL format (~/.claude/projects/)
- Codex: JSONL format with session_meta
- Gemini: JSON format (~/.gemini/tmp/*/chats/session-*.json)

All formats are auto-detected and converted to unified session envelope schema.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any


def parse_cache_session(cache_file: Path) -> Dict[str, Any]:
    """
    Parse cache session file (Claude Code, Codex JSONL, or Gemini JSON) into session envelope format.

    Args:
        cache_file: Path to cache file (.jsonl for Claude/Codex, .json for Gemini)

    Returns:
        Session envelope dict with extracted metadata
    """
    # Check if file is Gemini JSON format (single object vs JSONL)
    with open(cache_file, 'r') as f:
        content = f.read()

    # Try to parse as single JSON object (Gemini format)
    try:
        data = json.loads(content)
        if "sessionId" in data and "messages" in data and "projectHash" in data:
            # Gemini format detected
            return _parse_gemini_session(data, cache_file)
    except json.JSONDecodeError:
        pass  # Not a single JSON object, try JSONL parsing

    # Parse as JSONL (Claude Code or Codex)
    summary = ""
    session_id = ""
    project_path = ""
    git_branch = ""
    start_time = None
    end_time = None
    timestamps = []
    source_type = None  # Auto-detect: "claude-code-cache" or "codex-cache"

    for line in content.split('\n'):
        if not line.strip():
            continue

        entry = json.loads(line)
        entry_type = entry.get("type")

        # Codex format: session_meta contains metadata
        if entry_type == "session_meta":
            source_type = "codex-cache"
            payload = entry.get("payload", {})

            if not session_id:
                session_id = payload.get("id", "")

            if not project_path:
                project_path = payload.get("cwd", "")

            if not git_branch:
                git_info = payload.get("git", {})
                git_branch = git_info.get("branch", "")

        # Claude Code format: summary line
        if entry_type == "summary":
            source_type = "claude-code-cache"
            summary = entry.get("summary", "")

        # Claude Code format: user/assistant messages
        if entry_type in ("user", "assistant"):
            source_type = "claude-code-cache"

            if not session_id and "sessionId" in entry:
                session_id = entry["sessionId"]

            if not project_path and "cwd" in entry:
                project_path = entry["cwd"]

            if not git_branch and "gitBranch" in entry:
                git_branch = entry["gitBranch"]

            if "timestamp" in entry:
                timestamps.append(entry["timestamp"])

        # Both formats: collect timestamps
        if "timestamp" in entry and entry["timestamp"]:
            timestamps.append(entry["timestamp"])

    # Calculate start/end times from timestamps
    if timestamps:
        timestamps.sort()
        start_time = timestamps[0]
        end_time = timestamps[-1]

    # Default to claude-code-cache if not detected
    if not source_type:
        source_type = "claude-code-cache"

    return {
        "session_id": session_id,
        "summary": summary,
        "start_time": start_time,
        "end_time": end_time,
        "project_path": project_path,
        "git_branch": git_branch,
        "source": source_type,
        "source_path": str(cache_file)
    }


def _parse_gemini_session(data: Dict[str, Any], cache_file: Path) -> Dict[str, Any]:
    """
    Parse Gemini JSON session format.

    Args:
        data: Parsed JSON object from Gemini session file
        cache_file: Path to source file

    Returns:
        Session envelope dict
    """
    session_id = data.get("sessionId", "")
    project_hash = data.get("projectHash", "")
    start_time = data.get("startTime", "")
    end_time = data.get("lastUpdated", "")

    # Gemini doesn't have a summary field - generate one from first user message
    summary = ""
    messages = data.get("messages", [])
    if messages:
        for msg in messages:
            if msg.get("type") == "user":
                content = msg.get("content", "")
                # Use first 100 chars of first user message as summary
                summary = content[:100] + "..." if len(content) > 100 else content
                break

    return {
        "session_id": session_id,
        "summary": summary,
        "start_time": start_time,
        "end_time": end_time,
        "project_path": project_hash,  # Gemini uses project hash instead of path
        "git_branch": "",  # Gemini doesn't store git branch in session
        "source": "gemini-cache",
        "source_path": str(cache_file)
    }
