#!/usr/bin/env python3
"""
Parse commit_index.yaml and extract:
1. Decision records from commit messages
2. Skill evidence from file extensions + commit types
3. Generate commit_decisions.yaml + skill evidence suggestions
"""

import yaml
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict


def extract_decision_from_pattern(message: str) -> Optional[Dict[str, Any]]:
    """
    Extract decisions from natural language commit messages using pattern detection.

    Detects:
    - "use X instead of Y" / "switch from X to Y" / "replace X with Y"
    - "remove X" with reasoning (architecture simplification)
    - BEFORE/AFTER comparisons (refactoring decisions)
    - "Why:" explanations (explicit reasoning)
    - ADR references

    Returns:
        Dict with {decision, reasoning, alternatives, confidence} or None
    """
    result = {}
    confidence = 0.0

    # Normalize message for pattern matching
    msg_lower = message.lower()

    # Pattern 1: "use X instead of Y" / "switch from X to Y" / "replace X with Y"
    # Each tuple: (pattern, confidence, is_first_group_the_choice)
    # is_first_group_the_choice: True means group1 is what we chose, False means group2 is
    choice_patterns = [
        # "use X instead of Y" - X is the choice (group 1)
        (r"use\s+(\S+(?:\s+\S+)?)\s+instead\s+of\s+(\S+(?:\s+\S+)?)", 0.85, True),
        # "switch from X to Y" - Y is the choice (group 2)
        (r"switch(?:ed|ing)?\s+(?:from\s+)?(\S+(?:\s+\S+)?)\s+to\s+(\S+(?:\s+\S+)?)", 0.85, False),
        # "replace X with Y" - Y is the choice (group 2)
        (r"replace(?:d|ing)?\s+(\S+(?:\s+\S+)?)\s+with\s+(\S+(?:\s+\S+)?)", 0.85, False),
        # "migrate from X to Y" - Y is the choice (group 2)
        (r"migrate(?:d|ing)?\s+(?:from\s+)?(\S+(?:\s+\S+)?)\s+to\s+(\S+(?:\s+\S+)?)", 0.85, False),
        # "chose X over Y" - X is the choice (group 1)
        (r"(?:chose|choosing|choose)\s+(\S+(?:\s+\S+)?)\s+over\s+(\S+(?:\s+\S+)?)", 0.9, True),
    ]

    for pattern, conf, first_is_choice in choice_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            groups = match.groups()
            if len(groups) >= 2:
                if first_is_choice:
                    chosen = groups[0].strip()
                    rejected = groups[1].strip()
                else:
                    chosen = groups[1].strip()
                    rejected = groups[0].strip()
                result["decision"] = f"Use {chosen}"
                result["alternatives"] = [{"name": rejected, "rejected_because": "replaced"}]
                confidence = max(confidence, conf)
                break  # Stop after first match

    # Pattern 2: BEFORE/AFTER structure (high confidence refactoring decision)
    if re.search(r"\bBEFORE\b.*\bAFTER\b", message, re.IGNORECASE | re.DOTALL):
        after_match = re.search(r"AFTER[:\s]*\n?(.*?)(?=\n\n|$)", message, re.IGNORECASE | re.DOTALL)
        if after_match:
            after_text = after_match.group(1).strip()
            # Get the first meaningful line (skip lines starting with parentheses or dashes only)
            for line in after_text.split('\n'):
                line = line.strip().lstrip('- ')
                # Skip empty lines, lines starting with parentheses, or too short lines
                if line and not line.startswith('(') and len(line) > 15:
                    if not result.get("decision"):
                        result["decision"] = f"Refactor: {line[:100]}"
                        confidence = max(confidence, 0.8)
                    break

    # Pattern 3: "remove X" with reasoning (architecture simplification)
    # Only match significant removals, not generic file cleanups
    remove_patterns = [
        # "enterprise bloat" or similar
        r"remove(?:d|ing)?\s+(enterprise\s+\S+|[\w-]+\s+bloat)",
        # "remove X - reason" where X is a meaningful phrase
        r"remove(?:d|ing)?\s+([\w\s/-]+?)\s*[-:]\s*(.+)",
    ]
    for pattern in remove_patterns:
        match = re.search(pattern, msg_lower)
        if match and not result.get("decision"):
            removed_item = match.group(1).strip()
            # Only accept if the removed item is meaningful (>10 chars or specific patterns)
            if len(removed_item) > 10 or 'bloat' in removed_item or 'enterprise' in removed_item:
                result["decision"] = f"Remove {removed_item}"
                result["alternatives"] = [{"name": removed_item, "rejected_because": "removed for simplification"}]
                confidence = max(confidence, 0.75)
                break

    # Pattern 4: "Why:" explanation (extract reasoning)
    why_match = re.search(r"Why:\s*(.+?)(?=\n(?:What|How|Change|Tests|$)|\n\n)", message, re.IGNORECASE | re.DOTALL)
    if why_match:
        result["reasoning"] = why_match.group(1).strip()
        confidence = max(confidence, confidence + 0.1)  # Boost confidence if reasoning present

    # Pattern 5: ADR references (high confidence - explicit decision record)
    # Only match clear ADR patterns like "add ADR 0005 for X" or "ADR: X"
    adr_match = re.search(r"(?:add\s+)?ADR\s*(?:\d+|[\d-]+)\s+(?:for\s+)?(.+?)(?:\n|$)", message, re.IGNORECASE)
    if adr_match:
        adr_topic = adr_match.group(1).strip()
        # Clean up and validate the topic
        if len(adr_topic) > 10 and not adr_topic.startswith('to '):
            result["decision"] = f"ADR: {adr_topic}"
            confidence = max(confidence, 0.95)

    # Pattern 6: Significant refactoring keywords in title
    refactor_patterns = [
        (r"refactor:\s*(.+?)(?:\n|$)", 0.6),
        (r"consolidate(?:d|ing)?\s+(.+?)(?:\n|$)", 0.7),
        (r"flatten(?:ed|ing)?\s+(.+?)(?:\n|$)", 0.7),
        (r"reorganize(?:d|ing)?\s+(.+?)(?:\n|$)", 0.7),
        (r"simplif(?:y|ied|ying)\s+(.+?)(?:\n|$)", 0.65),
    ]

    for pattern, conf in refactor_patterns:
        match = re.search(pattern, msg_lower)
        if match and not result.get("decision"):
            decision_text = match.group(1).strip()
            # Clean up common suffixes
            decision_text = re.sub(r'\s*[-:]\s*.*$', '', decision_text)
            if len(decision_text) > 10:  # Avoid too short decisions
                result["decision"] = decision_text.title()
                confidence = max(confidence, conf)

    # Extract first line as context if we have a decision but no reasoning
    if result.get("decision") and not result.get("reasoning"):
        first_line = message.split('\n')[0].strip()
        # Don't use first line if it's the same as decision
        if first_line.lower() not in result["decision"].lower():
            result["reasoning"] = first_line

    # Only return if we have a decision with sufficient confidence
    if result.get("decision") and confidence >= 0.6:
        result["confidence"] = round(min(confidence, 1.0), 2)
        result["extraction_method"] = "pattern"
        if "alternatives" not in result:
            result["alternatives"] = []
        return result

    return None


def parse_decision_from_message(message: str) -> Optional[Dict[str, Any]]:
    """
    Parse decision metadata from commit message.

    Tries two methods:
    1. Structured format (Decision:, Reasoning:, etc.) - highest confidence
    2. Pattern-based detection from natural language - automatic fallback

    Returns:
        Dict with decision metadata if found, None otherwise.
    """
    # Method 1: Try structured format first (highest confidence)
    if "Decision:" in message:
        result = _parse_structured_decision(message)
        if result:
            result["confidence"] = 1.0
            result["extraction_method"] = "structured"
            return result

    # Method 2: Fall back to pattern detection
    return extract_decision_from_pattern(message)


def _parse_structured_decision(message: str) -> Optional[Dict[str, Any]]:
    """
    Parse structured decision metadata from commit message.

    Expected format:
        Decision: <decision text>
        Reasoning: <reasoning text>
        Alternatives: <alt1 (rejected)>, <alt2 (rejected)>
        Transcript: <reference>
        Outcome: <outcome text>

    Returns:
        Dict with decision metadata if found, None otherwise.
    """
    result = {}

    # Extract Decision
    decision_match = re.search(r"Decision:\s*(.+?)(?=\n(?:Reasoning|Alternatives|Transcript|Outcome)|$)", message, re.DOTALL | re.IGNORECASE)
    if decision_match:
        result["decision"] = decision_match.group(1).strip()

    # Extract Reasoning
    reasoning_match = re.search(r"Reasoning:\s*(.+?)(?=\n(?:Alternatives|Transcript|Outcome)|$)", message, re.DOTALL | re.IGNORECASE)
    if reasoning_match:
        result["reasoning"] = reasoning_match.group(1).strip()

    # Extract Alternatives
    alternatives_match = re.search(r"Alternatives:\s*(.+?)(?=\n(?:Transcript|Outcome)|$)", message, re.DOTALL | re.IGNORECASE)
    if alternatives_match:
        alternatives_text = alternatives_match.group(1).strip()
        # Parse alternatives: "React (rejected), Vue (rejected)"
        alternatives = []
        for alt in re.findall(r"([^,\(]+)\s*\(([^\)]+)\)", alternatives_text):
            alternatives.append({
                "name": alt[0].strip(),
                "rejected_because": alt[1].strip()
            })
        result["alternatives"] = alternatives
    else:
        result["alternatives"] = []

    # Extract Transcript reference
    transcript_match = re.search(r"Transcript:\s*(.+?)(?=\n(?:Outcome|$))", message, re.DOTALL | re.IGNORECASE)
    if transcript_match:
        result["transcript_ref"] = transcript_match.group(1).strip()

    # Extract Outcome
    outcome_match = re.search(r"Outcome:\s*(.+?)(?=\n|$)", message, re.DOTALL | re.IGNORECASE)
    if outcome_match:
        result["outcome"] = outcome_match.group(1).strip()

    # Only return if we have at least decision and reasoning
    if "decision" in result and "reasoning" in result:
        return result

    return None


def extract_skill_from_files(files: List[str]) -> List[str]:
    """
    Map file extensions to skills.

    Args:
        files: List of file paths

    Returns:
        List of skill names detected from file extensions
    """
    extension_to_skill = {
        ".py": "Python Development",
        ".ts": "TypeScript Development",
        ".tsx": "TypeScript Development",
        ".js": "JavaScript Development",
        ".jsx": "JavaScript Development",
        ".go": "Go Development",
        ".rs": "Rust Development",
        ".java": "Java Development",
        ".rb": "Ruby Development",
        ".php": "PHP Development",
        ".c": "C Development",
        ".cpp": "C++ Development",
        ".h": "C/C++ Development",
        ".md": "Documentation",
        ".yaml": "Configuration Management",
        ".yml": "Configuration Management",
        ".json": "Configuration Management",
        ".toml": "Configuration Management",
        ".sh": "Shell Scripting",
        ".bash": "Shell Scripting",
        ".html": "Web Development",
        ".css": "Web Development",
        ".scss": "Web Development",
        ".sql": "Database Development",
    }

    skills = set()
    for file_path in files:
        ext = Path(file_path).suffix.lower()
        if ext in extension_to_skill:
            skills.add(extension_to_skill[ext])

    return sorted(skills)


def generate_commit_decisions(commits: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate structured decision records and skill evidence from commits.

    Args:
        commits: List of commit dictionaries from commit_index.yaml

    Returns:
        Dictionary with 'decisions' and 'skill_evidence' keys
    """
    decisions = []
    skill_commits = defaultdict(list)
    decision_counter = 1

    for commit in commits:
        sha = commit.get("sha", "")
        message = commit.get("message", "")
        date = commit.get("date", "")
        files = commit.get("files", [])

        # Parse decision metadata (tries structured format, then pattern detection)
        decision_data = parse_decision_from_message(message)
        if decision_data:
            decision_id = f"DEC-GH-{decision_counter:03d}"
            decision_counter += 1

            confidence = decision_data.get("confidence", 1.0)
            extraction_method = decision_data.get("extraction_method", "structured")

            decision_record = {
                "id": decision_id,
                "decision": decision_data.get("decision", ""),
                "reasoning": decision_data.get("reasoning", ""),
                "alternatives": decision_data.get("alternatives", []),
                "transcript_ref": decision_data.get("transcript_ref", ""),
                "commit_sha": sha,
                "commit_date": date,
                "outcome": decision_data.get("outcome", ""),
                "status": "active",
                "confidence": confidence,
                "extraction_method": extraction_method,
            }
            decisions.append(decision_record)

        # Extract skills from files
        skills = extract_skill_from_files(files)
        for skill in skills:
            skill_commits[skill].append(sha)

    # Generate skill evidence suggestions
    skill_evidence = []
    for skill, commits_list in sorted(skill_commits.items()):
        evidence = {
            "skill": skill,
            "commits": commits_list,
            "confidence": 95,  # High confidence for code shipped
            "evidence_type": "code_shipped"
        }
        skill_evidence.append(evidence)

    return {
        "decisions": decisions,
        "skill_evidence": skill_evidence
    }


def main():
    """
    Main entry point: read commit_index.yaml, extract decisions and skill evidence,
    write to commit_decisions.yaml.
    """
    # Paths
    ledger_dir = Path(__file__).parent.parent
    commit_index_path = ledger_dir / "commit_index.yaml"
    output_path = ledger_dir / "commit_decisions.yaml"

    # Read commit_index.yaml
    if not commit_index_path.exists():
        print(f"Error: {commit_index_path} not found")
        return 1

    with open(commit_index_path, "r") as f:
        commit_index = yaml.safe_load(f)

    # Collect all commits from all repos
    all_commits = []
    for repo in commit_index.get("repos", []):
        commits = repo.get("commits", [])
        for commit in commits:
            # Add files list if not present
            if "files" not in commit:
                commit["files"] = []
            all_commits.append(commit)

    print(f"Processing {len(all_commits)} commits...")

    # Generate decisions and skill evidence
    result = generate_commit_decisions(all_commits)

    # Write output
    with open(output_path, "w") as f:
        yaml.dump(result, f, default_flow_style=False, sort_keys=False)

    print(f"✓ Extracted {len(result['decisions'])} decisions")
    print(f"✓ Generated {len(result['skill_evidence'])} skill evidence entries")
    print(f"✓ Wrote to {output_path}")

    return 0


if __name__ == "__main__":
    exit(main())
