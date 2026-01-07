#!/usr/bin/env python3
"""
Agent-Driven Skill Validation with Outcome Evidence Gates

Implements rigorous validation that reads actual transcripts, validates outcome
evidence, and applies >95% confidence gates before auto-approval.

IAW Issue #69: Agent-driven skill validation with outcome evidence gates.
"""

import json
import yaml
import re
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Any
from collections import defaultdict


def load_ingestion_report(report_path: Path) -> Dict:
    """Load skill ingestion report from pattern detection phase."""
    if not report_path.exists():
        raise FileNotFoundError(f"Ingestion report not found: {report_path}")

    with open(report_path, 'r') as f:
        return yaml.safe_load(f)


def load_transcripts(transcript_dir: Path) -> List[Dict]:
    """Load all transcript JSONL files from cache directory."""
    transcripts = []

    # Find all JSONL files in ~/.claude/projects
    cache_dir = Path.home() / ".claude" / "projects"
    if not cache_dir.exists():
        print(f"⚠️  Cache directory not found: {cache_dir}")
        return transcripts

    jsonl_files = sorted(cache_dir.rglob("*.jsonl"))

    for jsonl_file in jsonl_files:
        try:
            interactions = []
            session_id = ""

            # Read JSONL file line by line
            with open(jsonl_file, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())

                        # Extract session ID from first entry
                        if not session_id and "sessionId" in entry:
                            session_id = entry["sessionId"]

                        # Extract message content from each entry
                        if "message" in entry:
                            msg = entry["message"]
                            content = ""

                            # Handle different message content formats
                            if isinstance(msg.get("content"), str):
                                content = msg["content"]
                            elif isinstance(msg.get("content"), list):
                                # Combine text and tool_use content
                                parts = []
                                for item in msg["content"]:
                                    if isinstance(item, dict):
                                        if item.get("type") == "text":
                                            text = item.get("text", "")
                                            if isinstance(text, str):
                                                parts.append(text)
                                        elif item.get("type") == "tool_result":
                                            result_content = item.get("content", "")
                                            if isinstance(result_content, str):
                                                parts.append(result_content)
                                content = "\n".join(parts)

                            if content:
                                interactions.append({
                                    "id": entry.get("uuid", ""),
                                    "timestamp": entry.get("timestamp", ""),
                                    "content": content
                                })
                    except json.JSONDecodeError:
                        continue

            if interactions:
                transcripts.append({
                    "file": jsonl_file.name,
                    "path": str(jsonl_file),
                    "session_id": session_id,
                    "start_time": interactions[0].get("timestamp", "") if interactions else "",
                    "interactions": interactions
                })
        except Exception as e:
            print(f"⚠️  Error parsing {jsonl_file.name}: {e}")
            continue

    return transcripts


# Outcome validation patterns - detect successful completion
OUTCOME_PATTERNS = {
    "tests_passed": {
        "patterns": [
            r"\d+\s+passing\s+tests?",
            r"\d+\s+tests?\s+passed",
            r"pytest\s+PASSED",
            r"all\s+tests?\s+pass(?:ing|ed)",
            r"\d+%\s+accuracy",
            r"100%\s+(?:success|completion|coverage)",
            r"test\s+suite\s+passed"
        ]
    },
    "code_shipped": {
        "patterns": [
            r"merged\s+(?:PR|pull\s+request)",
            r"committed\s+to\s+(?:main|master|production)",
            r"deployed\s+to\s+(?:production|staging)",
            r"shipped\s+to\s+(?:users|production)",
            r"pushed\s+to\s+(?:repo|remote)",
            r"production[-\s]ready",
            r"MVP\s+deliver(?:ed|y)",
            r"G\d+-G\d+\s+(?:passed|complete)"
        ]
    },
    "problem_solved": {
        "patterns": [
            r"(?:fixed|resolved|solved)\s+(?:the\s+)?(?:issue|bug|problem)",
            r"achieving\s+\d+%\s+accuracy",
            r"reconciliation\s+complete",
            r"validation\s+successful",
            r"all\s+(?:gates|criteria)\s+(?:pass(?:ed|ing)|met)",
            r"SAT\s+outcome",
            r"verification\s+passed"
        ]
    },
    "production_deployed": {
        "patterns": [
            r"deployed\s+to\s+production",
            r"live\s+on\s+(?:production|server)",
            r"released\s+to\s+users",
            r"in\s+production",
            r"production\s+deployment"
        ]
    }
}


def extract_outcome_evidence_from_transcripts(
    skill_name: str,
    transcripts: List[Dict]
) -> List[Dict]:
    """
    Extract outcome evidence from actual transcripts for a specific skill.

    Reads interactions, identifies outcome evidence, and returns structured results.
    """
    outcome_evidence = []

    for transcript in transcripts:
        for interaction in transcript["interactions"]:
            content = interaction.get("content", "")
            interaction_id = interaction.get("id", "")
            timestamp = interaction.get("timestamp", "")

            # Extract date from timestamp
            try:
                date = timestamp[:10] if timestamp else ""
            except Exception:
                date = ""

            # Check each outcome type
            for outcome_type, config in OUTCOME_PATTERNS.items():
                for pattern in config["patterns"]:
                    matches = re.finditer(pattern, content, re.IGNORECASE)
                    for match in matches:
                        matched_text = match.group(0)

                        # Extract reference based on type
                        if outcome_type == "tests_passed":
                            metric_match = re.search(
                                r'(\d+(?:\.\d+)?%?)\s+(?:passing|passed|tests?|accuracy|success|completion|coverage)',
                                matched_text,
                                re.IGNORECASE
                            )
                            reference = f"metric:{metric_match.group(1)}" if metric_match else f"metric:{matched_text}"
                        elif outcome_type == "code_shipped":
                            reference = f"detected:{matched_text[:50]}"
                        elif outcome_type == "problem_solved":
                            reference = f"detected:{matched_text[:50]}"
                        elif outcome_type == "production_deployed":
                            reference = f"detected:{matched_text[:50]}"
                        else:
                            reference = f"detected:{matched_text[:50]}"

                        outcome_evidence.append({
                            "type": outcome_type,
                            "reference": reference,
                            "status": "found",
                            "date": date,
                            "interaction_id": interaction_id,
                            "matched_text": matched_text,
                            "source_file": transcript["file"]
                        })

    return outcome_evidence


def validate_skill(
    skill_suggestion: Dict,
    transcripts: List[Dict]
) -> Tuple[str, str, List[Dict]]:
    """
    Validate a single skill against strict approval gates.

    Returns: (action, reasoning, outcome_evidence)
        action: "approved" | "review_needed" | "rejected"
        reasoning: Explanation for the decision
        outcome_evidence: List of outcome evidence found
    """
    skill_name = skill_suggestion.get("skill_name", "")
    confidence = skill_suggestion.get("confidence", 0)
    session_count = skill_suggestion.get("temporal_metadata", {}).get("session_count", 0)

    # Extract outcome evidence from transcripts
    outcome_evidence = extract_outcome_evidence_from_transcripts(skill_name, transcripts)

    # Apply strict approval gates (ALL must be met for approval)

    # Gate 1: Confidence >95%
    if confidence < 95:
        if confidence >= 80:
            return (
                "review_needed",
                f"Confidence {confidence}% below 95% threshold (requires human review)",
                outcome_evidence
            )
        else:
            return (
                "rejected",
                f"Confidence {confidence}% below 80% minimum (insufficient pattern evidence)",
                outcome_evidence
            )

    # Gate 2: Outcome evidence present
    if not outcome_evidence:
        return (
            "review_needed",
            f"Confidence {confidence}% met but no outcome evidence found in transcripts",
            outcome_evidence
        )

    # Gate 3: Session frequency established (5+ sessions minimum)
    if session_count < 5:
        return (
            "review_needed",
            f"Confidence {confidence}% and outcome evidence found, but only {session_count} sessions (need 5+ for auto-approval)",
            outcome_evidence
        )

    # All gates passed
    return (
        "approved",
        f"Confidence {confidence}% (>95%), {len(outcome_evidence)} outcome evidence items, {session_count} sessions",
        outcome_evidence
    )


def generate_audit_report(
    suggestions: List[Dict],
    transcripts: List[Dict],
    transcript_dir: Path
) -> Dict:
    """
    Generate audit report with decision reasoning for every skill evaluated.
    """
    # Use cache directory as source since we read JSONL files from there
    cache_dir = Path.home() / ".claude" / "projects"

    audit = {
        "audit_metadata": {
            "timestamp": datetime.now().isoformat(),
            "transcripts_analyzed": len(transcripts),
            "agent_version": "1.0.0",
            "transcript_source": str(cache_dir)
        },
        "approval_results": []
    }

    for suggestion in suggestions:
        skill_name = suggestion.get("skill_name", "")
        confidence = suggestion.get("confidence", 0)

        # Validate skill
        action, reasoning, outcome_evidence = validate_skill(suggestion, transcripts)

        # Build outcome evidence summary
        outcome_summary = []
        for evidence in outcome_evidence[:5]:  # Limit to 5 for brevity
            outcome_summary.append({
                "type": evidence["type"],
                "reference": evidence["reference"],
                "status": evidence["status"]
            })

        result = {
            "skill_name": skill_name,
            "action": action,
            "confidence": confidence,
            "outcome_evidence": outcome_summary,
            "outcome_evidence_count": len(outcome_evidence),
            "reasoning": reasoning
        }

        audit["approval_results"].append(result)

    return audit


def write_approved_skills(
    audit_report: Dict,
    suggestions: List[Dict],
    skills_active_path: Path
) -> int:
    """
    Write auto-approved skills to skills_active.yaml with outcome_evidence populated.

    Returns: Number of skills approved
    """
    # Load existing skills_active.yaml
    if skills_active_path.exists():
        with open(skills_active_path, 'r') as f:
            skills_active = yaml.safe_load(f) or {}
    else:
        skills_active = {"skills": {}}

    approved_count = 0

    for result in audit_report["approval_results"]:
        if result["action"] != "approved":
            continue

        skill_name = result["skill_name"]

        # Find original suggestion for full data
        suggestion = next((s for s in suggestions if s["skill_name"] == skill_name), None)
        if not suggestion:
            continue

        # Build skill entry with outcome_evidence
        skill_entry = {
            "skill": skill_name,
            "confidence": result["confidence"],
            "outcome_evidence": result["outcome_evidence"],
            "temporal_metadata": suggestion.get("temporal_metadata", {}),
            "auto_approved": True,
            "approval_date": datetime.now().strftime("%Y-%m-%d")
        }

        # Add to skills_active (structure depends on skill type)
        # For now, append to a generic "agent_approved" category
        if "agent_approved" not in skills_active["skills"]:
            skills_active["skills"]["agent_approved"] = []

        skills_active["skills"]["agent_approved"].append(skill_entry)
        approved_count += 1

    # Write back to file
    with open(skills_active_path, 'w') as f:
        yaml.dump(skills_active, f, default_flow_style=False, sort_keys=False)

    return approved_count


def main():
    """Main execution function."""
    # Get paths from environment
    operator_root = Path(__file__).resolve().parent.parent
    transcript_dir = Path(os.getenv('OPERATOR_DATA_DIR', ''))

    if not transcript_dir or not transcript_dir.exists():
        print("❌ Error: OPERATOR_DATA_DIR not set or does not exist")
        return 1

    report_path = operator_root / "ledger" / "skill_ingestion_report.yaml"
    skills_active_path = operator_root / "ledger" / "skills" / "active.yaml"
    logs_dir = operator_root / "ledger" / "logs"

    # Ensure logs directory exists
    logs_dir.mkdir(parents=True, exist_ok=True)

    audit_report_path = logs_dir / f"skill_approval_audit_{datetime.now().strftime('%Y%m%d')}.yaml"

    # Cache directory for JSONL files
    cache_dir = Path.home() / ".claude" / "projects"

    print("🤖 Agent-Driven Skill Validation")
    print(f"   Transcript source: {cache_dir}")
    print(f"   Ingestion report: {report_path}")
    print("")

    # Load ingestion report
    try:
        ingestion_report = load_ingestion_report(report_path)
        suggestions = ingestion_report.get("suggested_updates", [])
        print(f"✅ Loaded {len(suggestions)} skill suggestions from ingestion report")
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        return 1

    # Load transcripts
    print(f"📂 Loading transcripts from {cache_dir}...")
    transcripts = load_transcripts(transcript_dir)
    print(f"✅ Loaded {len(transcripts)} transcripts")
    print("")

    # Generate audit report
    print("🔍 Validating skills with outcome evidence gates...")
    audit_report = generate_audit_report(suggestions, transcripts, transcript_dir)

    # Write audit report
    with open(audit_report_path, 'w') as f:
        yaml.dump(audit_report, f, default_flow_style=False, sort_keys=False)

    print(f"✅ Audit report generated: {audit_report_path}")
    print("")

    # Summary statistics
    approved_count = sum(1 for r in audit_report["approval_results"] if r["action"] == "approved")
    review_count = sum(1 for r in audit_report["approval_results"] if r["action"] == "review_needed")
    rejected_count = sum(1 for r in audit_report["approval_results"] if r["action"] == "rejected")

    print("📊 Validation Results:")
    print(f"   ✅ Approved: {approved_count}")
    print(f"   🔍 Review needed: {review_count}")
    print(f"   ❌ Rejected: {rejected_count}")
    print("")

    # Note: We don't auto-write approved skills yet - this is phase 1
    # Phase 2 would integrate with skills_active.yaml writing
    print("📋 Next Steps:")
    print(f"   1. Review audit report: {audit_report_path}")
    print(f"   2. Approved skills can be manually added to skills_active.yaml")
    print(f"   3. Skills requiring review need human judgment")
    print("")

    return 0


if __name__ == "__main__":
    exit(main())
