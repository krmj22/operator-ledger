#!/usr/bin/env python3
"""
Intelligent Skill Ingestion System
Analyzes conversation transcripts to identify demonstrated skills and generate
evidence-based suggestions for updating the skills ledger.

IAW TICKET-011 and AGENTS.md requirements.

Review Flags Schema (IAW Issue #57):
    When adding review_flags to skills, use this structure:

    review_flags:
      - trigger: "single_session_level_1"
        severity: "low"  # low, medium, high
        message: "Monitor for continued use before advancing"
        added: "2025-12-01"  # ISO8601 date - REQUIRED for tracking
        resolved: "2025-12-15"  # ISO8601 date - OPTIONAL, set when resolved
        resolution: "Verified accuracy - evidence confirmed"  # OPTIONAL
        resolved_by: "user"  # OPTIONAL: user, agent, auto

    Use create_review_flag() helper to generate properly formatted flags.
"""

import json
import yaml
import re
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Optional

# Add packages/ to path for imports
operator_root = Path(__file__).parent.parent
sys.path.insert(0, str(operator_root / "packages"))

from capture.deduplication import (
    load_ingestion_history,
    save_ingestion_history,
    is_session_processed,
    mark_session_processed
)

# Import session_tracker functions for history.jsonl parsing
# Add scripts/ to path to import session_tracker
sys.path.insert(0, str(operator_root / "scripts"))
from session_tracker import parse_history_jsonl, convert_history_session_to_transcript


# Strategic pattern detection - high-value orchestration work
STRATEGIC_PATTERNS = {
    "Framework Design": {
        "patterns": [
            r"CRISP-E",
            r"CONSTRAINTS",
            r"REQUIREMENTS",
            r"SUCCESS CRITERIA",
            r"PROOF PROTOCOL",
            r"G\d+-G\d+",
            r"G\d+",
            r"gate system",
            r"binary outcome",
            r"SAT/UNSAT",
            r"workflow documentation",
            r"AGENTS\.md",
            r"framework file"
        ],
        "weight": 3.0
    },
    "Specification Engineering": {
        "patterns": [
            r"PRD",
            r"IAW",
            r"implement according to",
            r"ensure SAT",
            r"acceptance criteria",
            r"requirement articulation",
            r"constraint definition",
            r"success criteria definition",
            r"problem statement"
        ],
        "weight": 3.0
    },
    "Verification Architecture": {
        "patterns": [
            r"proof protocol",
            r"evidence requirement",
            r"SAT/UNSAT",
            r"capture terminal output",
            r"file state verification",
            r"test strategy",
            r"functional test",
            r"negative test"
        ],
        "weight": 3.0
    },
    "Gray Area Resolution": {
        "patterns": [
            r"INTENT\.md",
            r"check INTENT",
            r">95% confidence",
            r"declare uncertainty",
            r"gray area",
            r"ambiguous",
            r"ambiguity",
            r"align with.*vision"
        ],
        "weight": 3.0
    },
    "Framework Iteration": {
        "patterns": [
            r"lessons learned",
            r"takeaway",
            r"update framework",
            r"revise protocol",
            r"continuous improvement",
            r"what worked",
            r"what didn't",
            r"retrospective",
            r"evolve.*process"
        ],
        "weight": 3.0
    }
}

# Outcome validation patterns - detect successful completion, not just attempts
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
    },
    "peer_validated": {
        "patterns": [
            r"reviewed\s+by\s+@?\w+",
            r"approved\s+by",
            r"peer\s+review(?:ed)?",
            r"code\s+review\s+approved",
            r"published\s+(?:to|on)",
            r"external\s+validation"
        ]
    },
    "github_pr": {
        "patterns": [
            r"github\.com/[\w-]+/[\w-]+/pull/\d+",
            r"PR\s+#\d+",
            r"pull\s+request\s+#\d+",
            r"fixes\s+#\d+",
            r"closes\s+#\d+"
        ]
    }
}

# AI leverage context patterns - operator engagement quality
AI_LEVERAGE_PATTERNS = {
    "directive": {
        "patterns": [
            r"IAW",
            r"@[\w/]+",
            r"implement",
            r"ensure",
            r"verify",
            r"create",
            r"generate",
            r"build",
            r"design"
        ],
        "weight": 2.0
    },
    "evaluative": {
        "patterns": [
            r"that'?s? (not|in)correct",
            r"actually",
            r"but",
            r"however",
            r"review.*before",
            r"check.*first",
            r"shouldn't",
            r"catch.*error"
        ],
        "weight": 2.0
    },
    "iterative": {
        "patterns": [
            r"fix",
            r"refine",
            r"improve",
            r"adjust",
            r"debug",
            r"retry",
            r"revise",
            r"update"
        ],
        "weight": 2.0
    },
    "learning": {
        "patterns": [
            r"what is",
            r"how does",
            r"explain",
            r"tell me about",
            r"what's the difference"
        ],
        "weight": 0.5
    }
}

ORCHESTRATION_PATTERNS = {
    "AI Communication & Prompt Engineering": {
        "user_patterns": [
            r"IAW @\w+\.md",
            r"@[\w/]+\s",
            r"ensure.*SAT",
            r"verify.*complete",
            r"implement.*according to",
            r"follow.*protocol",
            r"generate.*report",
            r"create.*system"
        ],
        "signals": ["clear intent", "structured request", "protocol reference", "specification"],
        "tier": 1,  # High specificity - framework/protocol references
        "weight": 3.0
    },
    "Critical Thinking & Evaluation": {
        "user_patterns": [
            r"that'?s? (not|in)correct",
            r"actually",
            r"(but|however|wait)",
            r"review.*before",
            r"check.*first",
            r"verify.*against",
            r"is this (right|correct|accurate)",
            r"shouldn'?t? (that|this|it)",
            r"catch.*error"
        ],
        "signals": ["correction", "disagreement", "verification request", "quality check"],
        "tier": 3,  # Mixed specificity - has generic keywords like "but"
        "weight": 0.5,
        "compound_required": True  # Require 2+ patterns for detection
    },
    "Problem Solving & Decomposition": {
        "user_patterns": [
            r"break.*down",
            r"step by step",
            r"first.*then",
            r"start by.*then",
            r"work packet",
            r"WP-\d+",
            r"phase \d+",
            r"stage \d+"
        ],
        "signals": ["decomposition", "sequencing", "phased approach", "work breakdown"],
        "tier": 2,  # Moderate specificity - structured decomposition terms
        "weight": 2.0
    },
    "Creative/Novel Thinking": {
        "user_patterns": [
            r"what if",
            r"instead of.*try",
            r"novel approach",
            r"creative solution",
            r"unconventional",
            r"lateral thinking"
        ],
        "signals": ["alternative approach", "non-obvious solution", "innovation"],
        "tier": 2,  # Moderate specificity - creative thinking indicators
        "weight": 2.0
    },
    "Project Management": {
        "user_patterns": [
            r"TICKET-\d+",
            r"track.*progress",
            r"milestone",
            r"deadline",
            r"scope",
            r"priority",
            r"roadmap",
            r"backlog"
        ],
        "signals": ["tracking", "planning", "scope management", "ticket management"],
        "tier": 2,  # Moderate specificity - project management terms
        "weight": 2.0
    },
    "Systems Thinking & Integration": {
        "user_patterns": [
            r"how.*fit together",
            r"integrat(e|ion)",
            r"architecture",
            r"pipeline",
            r"upstream.*downstream",
            r"dependency",
            r"interconnect"
        ],
        "signals": ["architecture", "integration", "system design", "dependencies"],
        "tier": 2,  # Moderate specificity - system architecture terms
        "weight": 2.0
    },
    "Risk & Trade-off Analysis": {
        "user_patterns": [
            r"risk",
            r"trade-?off",
            r"constraint",
            r"limitation",
            r"(could|might) fail",
            r"edge case",
            r"what (if|about).*fails?"
        ],
        "signals": ["risk identification", "constraint analysis", "failure mode", "edge cases"],
        "tier": 2,  # Moderate specificity - risk analysis terms
        "weight": 2.0
    },
    "Pattern Recognition": {
        "user_patterns": [
            r"similar to",
            r"pattern",
            r"recurring",
            r"same.*before",
            r"this keeps happening",
            r"reusable"
        ],
        "signals": ["pattern identification", "reusability", "recurring problem"],
        "tier": 3,  # Low specificity - word "pattern" is too generic
        "weight": 0.5,
        "compound_required": True  # Require 2+ patterns for detection
    },
    "Technical Intuition": {
        "user_patterns": [
            r"feels? (over-engineered|too complex)",
            r"probably (won'?t|will)",
            r"gut",
            r"intuition",
            r"realistic",
            r"(in)?feasible"
        ],
        "signals": ["feasibility judgment", "complexity assessment", "intuitive reasoning"],
        "tier": 3,  # Low specificity - subjective judgment terms
        "weight": 0.5,
        "compound_required": True  # Require 2+ patterns for detection
    },
    "Documentation & Knowledge Capture": {
        "user_patterns": [
            r"document",
            r"README",
            r"LEDGER",
            r"capture.*lesson",
            r"write.*down",
            r"record.*decision"
        ],
        "signals": ["documentation", "knowledge capture", "artifact creation"],
        "tier": 3,  # Low specificity - word "document" is generic
        "weight": 0.5,
        "compound_required": True  # Require 2+ patterns for detection
    },
    "Verification & Testing Strategy": {
        "user_patterns": [
            r"test",
            r"verify",
            r"proof",
            r"acceptance criteria",
            r"success criteria",
            r"validation"
        ],
        "signals": ["testing", "verification", "proof protocol", "acceptance criteria"],
        "tier": 2,  # Moderate specificity - technical verification terms
        "weight": 2.0
    },
    "Learning Agility": {
        "user_patterns": [
            r"learn.*quick",
            r"pick.*up",
            r"adapt",
            r"new.*concept",
            r"understand.*now"
        ],
        "signals": ["learning", "adaptation", "quick understanding"],
        "tier": 3,  # Low specificity - generic learning terms
        "weight": 0.5,
        "compound_required": True  # Require 2+ patterns for detection
    },
    "Decisiveness": {
        "user_patterns": [
            r"let'?s? (go with|use|do)",
            r"decid(e|ed)",
            r"commit to",
            r"choose"
        ],
        "signals": ["decision making", "commitment", "choice"],
        "tier": 2,  # Moderate specificity - decision-making terms
        "weight": 2.0
    },
    "Stakeholder Management": {
        "user_patterns": [
            r"user needs?",
            r"customer",
            r"stakeholder",
            r"requirement",
            r"translate.*business"
        ],
        "signals": ["requirements gathering", "user focus", "translation"],
        "tier": 2,  # Moderate specificity - stakeholder management terms
        "weight": 2.0
    }
}


TECH_STACK_PATTERNS = {
    "interfaces": {
        "macOS Terminal": [r"\$\s*\w+", r"terminal", r"bash", r"zsh", r"command line"],
        "VS Code": [r"VS Code", r"vscode", r"code editor"],
        "Cursor IDE": [r"Cursor", r"cursor\.ai"],
    },
    "platforms": {
        "macOS": [r"macOS", r"Darwin", r"iCloud", r"Finder"],
        "Linux (Ubuntu/Debian)": [r"Linux", r"Ubuntu", r"Debian", r"apt-get"],
    },
    "dev_tooling": {
        "git": [r"git\s+(commit|push|pull|clone|branch|checkout)", r"repository", r"repo"],
        "Docker": [r"Docker", r"container", r"dockerfile"],
        "Python": [r"python3?", r"\.py\b", r"pip", r"venv"],
        "Whisper / ffmpeg": [r"Whisper", r"ffmpeg", r"audio", r"transcription"],
    },
    "frameworks": {
        "Modern Web UI/UX Design": [r"HTML", r"CSS", r"JavaScript", r"web interface", r"UI/UX"],
        "Tauri Desktop Application Development": [r"Tauri", r"Cargo\.toml", r"tauri\.conf"],
    },
    "data_formats": {
        "Markdown": [r"\.md\b", r"markdown", r"README"],
        "JSON": [r"\.json\b", r"JSON", r"parse.*json"],
        "YAML": [r"\.yaml\b", r"\.yml\b", r"YAML"],
        "CSV": [r"\.csv\b", r"CSV"],
    }
}


SKEPTICISM_FLAGS = {
    "passive_observation": [
        r"^(ok|okay|yes|sure|sounds good|looks good|great)[\.\!]?$",
        r"^(got it|understood|makes sense)[\.\!]?$"
    ],
    "blind_acceptance": [
        r"^(do it|go ahead|proceed)[\.\!]?$",
        r"^(whatever you think|up to you)[\.\!]?$"
    ],
    "learning_discussion": [
        r"how do(es)? \w+ work",
        r"what is \w+",
        r"explain \w+",
        r"tell me about"
    ]
}

# Negative patterns to filter out false positives
NEGATIVE_PATTERNS = {
    "Critical Thinking & Evaluation": [
        r"^(but|however|wait)[\.\,\s]*(okay|ok|sure|yes)$",  # Casual agreement
        r"but (i|you|we) (think|know|want)",  # Casual conversation
    ],
    "Pattern Recognition": [
        r"pattern[_\-\.]",  # Filenames/code (pattern.py, pattern_match)
        r"\.pattern\b",  # File extensions or code attributes
        r"\bpattern\s*(string|matching|regex)",  # Technical regex discussion
    ],
    "Documentation & Knowledge Capture": [
        r"document\.(txt|md|pdf|docx)",  # File references
        r"the document\b",  # Passive reference to existing document
        r"this document\b",  # Reading a document, not creating
    ]
}


def create_review_flag(trigger: str, severity: str, message: str) -> Dict:
    """
    Create a properly formatted review_flag dict with date tracking.
    IAW Issue #57 - review flags enforcement mechanism.

    Args:
        trigger: Flag trigger identifier (e.g., "single_session_level_1")
        severity: Flag severity level ("low", "medium", "high")
        message: Human-readable message describing the flag

    Returns:
        Dict with proper flag structure including 'added' date

    Example:
        flag = create_review_flag(
            trigger="single_session_only",
            severity="high",
            message="Single session - may be abandoned, review in 30 days"
        )
    """
    return {
        "trigger": trigger,
        "severity": severity,
        "message": message,
        "added": datetime.now().strftime("%Y-%m-%d")  # ISO8601 date for tracking
    }


def convert_cache_to_transcript(cache_file: Path) -> Optional[Dict]:
    """
    Convert cache .jsonl session to transcript format.
    Extracts user prompts from cache entries.

    Args:
        cache_file: Path to cache .jsonl file

    Returns:
        Transcript dict with {session_id, start_time, interactions} or None
    """
    if not cache_file.exists():
        return None

    session_id = ""
    interactions = []
    timestamps = []

    try:
        with open(cache_file, 'r') as f:
            for line in f:
                if not line.strip():
                    continue

                entry = json.loads(line)
                entry_type = entry.get("type")

                # Extract session_id from user/assistant entries
                if entry_type in ("user", "assistant") and not session_id:
                    session_id = entry.get("sessionId", "")

                # Only process user messages (matches existing behavior)
                if entry_type == "user":
                    message = entry.get("message", {})
                    content = message.get("content", "")

                    # Handle multi-part content (text + tool results)
                    if isinstance(content, list):
                        text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                        content = "\n".join(text_parts)

                    interactions.append({
                        "content": content,
                        "timestamp": entry.get("timestamp", ""),
                        "type": "user_prompt",  # Match expected type
                        "id": entry.get("uuid", ""),
                        "working_dir": entry.get("cwd", "")
                    })

                    # Collect timestamps
                    if "timestamp" in entry:
                        timestamps.append(entry["timestamp"])

        # Calculate start time - extract date from ISO8601 timestamp
        if timestamps:
            # Timestamps are ISO8601 strings like "2025-12-22T13:57:07.298431"
            # Extract just the date portion (YYYY-MM-DD)
            first_timestamp = timestamps[0]
            if isinstance(first_timestamp, str) and 'T' in first_timestamp:
                start_time = first_timestamp.split('T')[0]  # Get YYYY-MM-DD
            else:
                start_time = str(first_timestamp)[:10]  # Fallback: first 10 chars
        else:
            start_time = ""

        return {
            "session_id": session_id,
            "start_time": start_time,
            "interactions": interactions
        }

    except Exception as e:
        print(f"⚠️  Error converting {cache_file.name}: {e}")
        return None


def parse_transcripts(transcript_dir: Path, include_history: bool = True, include_cache: bool = True) -> List[Dict]:
    """
    Parse transcripts from multiple sources.

    Args:
        transcript_dir: Directory for legacy JSON files (also determines .claude location)
        include_history: Include sessions from history.jsonl
        include_cache: Include sessions from cache files

    Returns:
        List of transcript dicts in unified format
    """
    transcripts = []

    # 1. Parse legacy TerminalSavedOutput_*.json files (EXISTING CODE)
    json_files = sorted(transcript_dir.glob("TerminalSavedOutput_*.json"))

    for json_file in json_files:
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)

            # Validate session contract
            if not all(key in data for key in ["session_id", "start_time", "interactions"]):
                print(f"⚠️  {json_file.name} missing required fields - skipping")
                continue

            transcripts.append({
                "file": json_file.name,
                "path": str(json_file),
                "session_id": data.get("session_id", ""),
                "start_time": data.get("start_time", ""),
                "interactions": data.get("interactions", [])
            })
        except Exception as e:
            print(f"⚠️  Error parsing {json_file.name}: {e}")

    # 2. Parse history.jsonl sessions (NEW)
    if include_history:
        history_file = Path.home() / ".claude" / "history.jsonl"
        if history_file.exists():
            sessions_dict = parse_history_jsonl(history_file)

            for session_id, entries in sessions_dict.items():
                transcript_data = convert_history_session_to_transcript(session_id, entries)

                if transcript_data and transcript_data.get("interactions"):
                    transcripts.append({
                        "file": f"history.jsonl#{session_id[:8]}",
                        "path": str(history_file),
                        "session_id": session_id,
                        "start_time": transcript_data.get("start_time", ""),
                        "interactions": transcript_data.get("interactions", [])
                    })

    # 3. Parse cache .jsonl sessions (NEW)
    if include_cache:
        cache_dir = Path.home() / ".claude" / "projects"
        if cache_dir.exists():
            cache_files = sorted(cache_dir.rglob("*.jsonl"))

            for cache_file in cache_files:
                transcript_data = convert_cache_to_transcript(cache_file)

                if transcript_data and transcript_data.get("interactions"):
                    transcripts.append({
                        "file": cache_file.name,
                        "path": str(cache_file),
                        "session_id": transcript_data.get("session_id", ""),
                        "start_time": transcript_data.get("start_time", ""),
                        "interactions": transcript_data.get("interactions", [])
                    })

    return transcripts


def analyze_skepticism(user_content: str) -> Tuple[bool, str]:
    """Analyze if user message shows passive observation or active engagement."""
    content_lower = user_content.lower().strip()

    for pattern in SKEPTICISM_FLAGS["passive_observation"]:
        if re.match(pattern, content_lower):
            return True, "passive_observation"

    for pattern in SKEPTICISM_FLAGS["blind_acceptance"]:
        if re.match(pattern, content_lower):
            return True, "blind_acceptance"

    for pattern in SKEPTICISM_FLAGS["learning_discussion"]:
        if re.search(pattern, content_lower):
            return True, "learning_discussion"

    return False, "active_demonstration"


def detect_leverage_context(content: str) -> Dict[str, int]:
    """Analyze AI leverage context - how operator engages with AI."""
    leverage = {
        "strategic_patterns": 0,
        "directive_instances": 0,
        "evaluative_instances": 0,
        "iterative_instances": 0,
        "learning_instances": 0
    }

    # Check strategic patterns
    for category, config in STRATEGIC_PATTERNS.items():
        for pattern in config["patterns"]:
            if re.search(pattern, content, re.IGNORECASE):
                leverage["strategic_patterns"] += 1
                break  # Count once per category

    # Check leverage patterns
    for leverage_type, config in AI_LEVERAGE_PATTERNS.items():
        for pattern in config["patterns"]:
            if re.search(pattern, content, re.IGNORECASE):
                leverage[f"{leverage_type}_instances"] += 1
                break  # Count once per type

    return leverage


def detect_orchestration_skills(interactions: List[Dict]) -> Dict[str, Dict]:
    """Detect orchestration skills from transcript interactions with strategic pattern emphasis."""
    skill_detections = defaultdict(lambda: {
        "count": 0,
        "evidence": [],
        "quality": [],
        "leverage_context": {
            "strategic_patterns": 0,
            "directive_instances": 0,
            "evaluative_instances": 0,
            "iterative_instances": 0,
            "learning_instances": 0
        },
        "detection_breakdown": defaultdict(int)
    })

    for interaction in interactions:
        if interaction.get("type") != "user_prompt":
            continue

        content = interaction.get("content", "")
        is_passive, quality = analyze_skepticism(content)
        leverage = detect_leverage_context(content)

        # Detect strategic patterns first
        for category, config in STRATEGIC_PATTERNS.items():
            matches = 0
            matched_patterns = []

            for pattern in config["patterns"]:
                if re.search(pattern, content, re.IGNORECASE):
                    matches += 1
                    matched_patterns.append(pattern)

            if matches > 0:
                skill_detections[category]["count"] += matches
                skill_detections[category]["detection_breakdown"][category] += matches

                # Add leverage context
                for key in leverage:
                    skill_detections[category]["leverage_context"][key] += leverage[key]

                skill_detections[category]["evidence"].append({
                    "content": content[:200],
                    "interaction_id": interaction.get("id", ""),
                    "patterns": matched_patterns,
                    "quality": quality,
                    "category": category
                })
                skill_detections[category]["quality"].append(quality)

        # Detect orchestration patterns with compound requirements and filtering
        for skill_name, skill_config in ORCHESTRATION_PATTERNS.items():
            matches = 0
            matched_patterns = []

            # Skip if content too short (minimum 50 chars for context)
            if len(content.strip()) < 50:
                continue

            # Check negative patterns first - skip if false positive detected
            if skill_name in NEGATIVE_PATTERNS:
                is_false_positive = False
                for neg_pattern in NEGATIVE_PATTERNS[skill_name]:
                    if re.search(neg_pattern, content, re.IGNORECASE):
                        is_false_positive = True
                        break
                if is_false_positive:
                    continue

            for pattern in skill_config["user_patterns"]:
                if re.search(pattern, content, re.IGNORECASE):
                    matches += 1
                    matched_patterns.append(pattern)

            # Apply compound pattern requirement for Tier 3 skills
            compound_required = skill_config.get("compound_required", False)
            if compound_required and matches < 2:
                # Skip detection - need at least 2 patterns for low-tier skills
                continue

            if matches > 0:
                skill_detections[skill_name]["count"] += matches

                # Add leverage context
                for key in leverage:
                    skill_detections[skill_name]["leverage_context"][key] += leverage[key]

                skill_detections[skill_name]["evidence"].append({
                    "content": content[:200],
                    "interaction_id": interaction.get("id", ""),
                    "patterns": matched_patterns,
                    "quality": quality,
                    "tier": skill_config.get("tier", 2),  # Track pattern tier
                    "weight": skill_config.get("weight", 2.0)
                })
                skill_detections[skill_name]["quality"].append(quality)

    # Convert defaultdicts to regular dicts for YAML serialization
    result = {}
    for skill_name, data in skill_detections.items():
        result[skill_name] = {
            "count": data["count"],
            "evidence": data["evidence"],
            "quality": data["quality"],
            "leverage_context": dict(data["leverage_context"]),
            "detection_breakdown": dict(data["detection_breakdown"]) if data["detection_breakdown"] else {}
        }

    return result


def detect_tech_stack_skills(interactions: List[Dict], transcript_date: str = "") -> Dict[str, Dict]:
    """Detect tech stack skills from transcript interactions."""
    skill_detections = defaultdict(lambda: {
        "count": 0,
        "evidence": [],
        "sessions": []  # Track sessions for temporal metadata
    })

    for interaction in interactions:
        content = interaction.get("content", "")

        for category, skills in TECH_STACK_PATTERNS.items():
            for skill_name, patterns in skills.items():
                for pattern in patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        skill_key = f"tech_stack.{category}.{skill_name}"
                        skill_detections[skill_key]["count"] += 1
                        skill_detections[skill_key]["evidence"].append({
                            "content": content[:200],
                            "interaction_id": interaction.get("id", "")
                        })
                        if transcript_date and transcript_date not in skill_detections[skill_key]["sessions"]:
                            skill_detections[skill_key]["sessions"].append(transcript_date)
                        break

    return dict(skill_detections)


def calculate_confidence(skill_data: Dict, session_count: int) -> int:
    """
    Calculate confidence score with strategic weighting.

    Strategic patterns (framework design, spec engineering, etc.) weighted 3x.
    Directive/evaluative/iterative instances weighted 2x.
    Tactical patterns (keyword mentions) weighted 1x.
    Learning discussions penalized 0.5x.

    Tech_stack skills with zero leverage context heavily penalized (AI agent actions, not operator skills).
    """
    # Extract leverage context if available
    leverage = skill_data.get("leverage_context", {})

    # Weighted scoring
    strategic_score = leverage.get("strategic_patterns", 0) * 3
    directive_score = leverage.get("directive_instances", 0) * 2
    evaluative_score = leverage.get("evaluative_instances", 0) * 2
    iterative_score = leverage.get("iterative_instances", 0) * 2
    learning_penalty = leverage.get("learning_instances", 0) * 0.5

    # Base tactical score (raw count, but capped to prevent inflation)
    tactical_count = skill_data.get("count", 0)
    tactical_score = min(tactical_count * 0.5, 20)  # Cap at 20 to prevent keyword spam dominance

    # Combined weighted score
    weighted_score = strategic_score + directive_score + evaluative_score + iterative_score + tactical_score - learning_penalty
    base_score = min(weighted_score, 40)

    # CRITICAL: Zero leverage context = AI agent actions, not operator orchestration
    total_leverage = strategic_score + directive_score + evaluative_score + iterative_score
    if total_leverage == 0 and leverage:  # leverage dict exists but all values are 0
        base_score = 0  # No operator contribution = no skill demonstration

    # Quality penalty for passive observation
    quality_penalty = 0
    if "quality" in skill_data and skill_data["quality"]:
        passive_count = sum(1 for q in skill_data["quality"] if q != "active_demonstration")
        quality_ratio = passive_count / len(skill_data["quality"])
        quality_penalty = int(quality_ratio * 20)  # Reduced from 40 since strategic weighting already addresses this

    # Session consistency bonus
    session_bonus = min(session_count * 5, 30)

    # Evidence depth score
    evidence_depth = len(skill_data.get("evidence", []))
    depth_score = min(evidence_depth * 3, 30)

    confidence = base_score + session_bonus + depth_score - quality_penalty
    return max(0, min(100, confidence))


def detect_outcome_evidence(interactions: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Detect outcome evidence from transcript interactions.
    Returns structured outcome evidence by type.
    IAW Issue #40 - detect successful outcomes, not just attempts.
    """
    outcomes = defaultdict(list)

    for interaction in interactions:
        content = interaction.get("content", "")
        interaction_id = interaction.get("id", "")
        timestamp = interaction.get("timestamp", "")

        # Extract date from timestamp (ISO8601 format)
        try:
            date = timestamp[:10] if timestamp else ""
        except Exception:
            date = ""

        # Check each outcome type
        for outcome_type, config in OUTCOME_PATTERNS.items():
            for pattern in config["patterns"]:
                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    # Extract matched text for context
                    matched_text = match.group(0)

                    # For GitHub PRs, extract the full reference
                    if outcome_type == "github_pr":
                        if "github.com" in matched_text:
                            reference = f"github:{matched_text}"
                        elif "#" in matched_text:
                            # Extract just the number
                            pr_num = re.search(r'#(\d+)', matched_text)
                            reference = f"github:pr/{pr_num.group(1)}" if pr_num else f"github:{matched_text}"
                        else:
                            reference = f"github:{matched_text}"
                    # For test results, extract metrics
                    elif outcome_type == "tests_passed":
                        # Try to extract the number or percentage
                        metric_match = re.search(r'(\d+(?:\.\d+)?%?)\s+(?:passing|passed|tests?|accuracy|success|completion|coverage)', matched_text, re.IGNORECASE)
                        if metric_match:
                            reference = f"metric:{metric_match.group(1)}"
                        else:
                            reference = f"metric:{matched_text}"
                    else:
                        # For other types, use a generic reference
                        reference = f"detected:{matched_text[:50]}"

                    outcome = {
                        "type": outcome_type,
                        "reference": reference,
                        "status": "detected",  # Will be validated later
                        "date": date,
                        "interaction_id": interaction_id,
                        "matched_text": matched_text,
                        "context": content[max(0, match.start()-50):min(len(content), match.end()+50)]
                    }
                    outcomes[outcome_type].append(outcome)

    return dict(outcomes)


def recommend_validation_type(outcome_evidence: Dict[str, List[Dict]]) -> Tuple[str, str]:
    """
    Recommend validation type based on outcome evidence quality.

    Returns: (validation_type, reason)

    Validation hierarchy:
    1. external-validated: Production deployments, peer validation, external metrics
    2. user-confirmed: Explicit user confirmation or manual edits
    3. agent-assessed: Default - detected from transcripts only
    """
    # Check for external validation evidence
    external_types = ['production_deployed', 'peer_validated']
    external_evidence = []

    for outcome_type, evidence_list in outcome_evidence.items():
        if outcome_type in external_types:
            for evidence in evidence_list:
                external_evidence.append(f"{outcome_type}: {evidence.get('matched_text', 'N/A')[:50]}")

    if external_evidence:
        return 'external-validated', "; ".join(external_evidence[:2])  # Limit to 2 for brevity

    # Default to agent-assessed (user-confirmed is set manually)
    return 'agent-assessed', "Detected from transcripts - no external validation"


def detect_readiness_signals(interactions: List[Dict], skill_name: str) -> Tuple[str, str]:
    """
    Detect readiness for Level 0 skills from transcript context.
    IAW Issue #55 - provide actionable signals for Level 0 skill recommendations.

    Args:
        interactions: List of interaction objects from transcript
        skill_name: Name of the skill to assess readiness for

    Returns:
        Tuple of (readiness_value, reason)

    Readiness signals:
    - "avoid" → explicit avoidance statements
    - "not_ready" → no conceptual foundation evident
    - "ready_to_learn" → conceptual understanding + expressed interest
    - "can_learn_quickly" → strong foundation + adjacent skills evident
    """
    user_content = []
    for interaction in interactions:
        if interaction.get("type") == "user_prompt":
            user_content.append(interaction.get("content", "").lower())

    combined_content = " ".join(user_content)
    skill_lower = skill_name.lower()

    # Pattern detection
    avoidance_patterns = [
        "don't want to learn", "avoid", "not interested in", "skip",
        "don't use", "won't need"
    ]

    interest_patterns = [
        "want to learn", "interested in", "how do i", "can you teach",
        "help me understand", "guide me through", "show me how"
    ]

    conceptual_patterns = [
        "understand", "concept", "theory", "aware that", "know that",
        "familiar with", "heard of", "read about"
    ]

    strong_foundation_patterns = [
        "similar to", "like", "already know", "experience with",
        "used before", "worked with", "proficient"
    ]

    # Check for explicit avoidance
    for pattern in avoidance_patterns:
        if pattern in combined_content and skill_lower in combined_content:
            return "avoid", f"Explicit avoidance detected: '{pattern}' in context with {skill_name}"

    # Check for strong foundation (can_learn_quickly)
    strong_count = sum(1 for p in strong_foundation_patterns if p in combined_content)
    if strong_count >= 2:
        return "can_learn_quickly", f"Strong foundation evident from adjacent skills or prior experience"

    # Check for interest + conceptual understanding (ready_to_learn)
    interest_count = sum(1 for p in interest_patterns if p in combined_content)
    conceptual_count = sum(1 for p in conceptual_patterns if p in combined_content)

    if interest_count >= 1 and conceptual_count >= 1:
        return "ready_to_learn", f"Conceptual understanding + expressed interest detected"

    if conceptual_count >= 2:
        return "ready_to_learn", f"Multiple indicators of conceptual understanding"

    # Default to not_ready if insufficient evidence
    return "not_ready", "Insufficient evidence of conceptual foundation or interest"


def analyze_temporal_metadata(skill_name: str, all_transcripts: List[Dict], skill_detections: Dict) -> Dict:
    """Generate temporal metadata for a skill."""
    sessions_with_skill = []

    for transcript in all_transcripts:
        transcript_date = transcript.get("start_time", "")[:10]

        detections = detect_orchestration_skills(transcript["interactions"])
        if skill_name in detections:
            sessions_with_skill.append(transcript_date)

    if not sessions_with_skill:
        return {}

    session_count = len(sessions_with_skill)
    first_seen = min(sessions_with_skill)
    last_seen = max(sessions_with_skill)

    if session_count == 1:
        frequency = "single-session"
        trend = "learning"
    elif session_count <= 3:
        frequency = "occasional"
        trend = "growing"
    else:
        frequency = "regular"
        trend = "established"

    return {
        "first_seen": first_seen,
        "last_seen": last_seen,
        "session_count": session_count,
        "frequency": frequency,
        "trend": trend
    }


def load_existing_skills(skills_path: Path) -> Dict:
    """
    Load existing skills from BOTH skills_active.yaml and skills_history.yaml.

    IAW Issue #58: Skills are split into active (high-signal) and historical (dormant).
    This function loads both and merges them into a single structure for analysis.

    Args:
        skills_path: Path to skills.yaml (legacy) - now used to derive paths to active/history files

    Returns:
        Merged skills dict with all skills from both files
    """
    ledger_dir = skills_path.parent
    active_path = ledger_dir / "skills" / "active.yaml"
    history_path = ledger_dir / "skills" / "history.yaml"
    legacy_path = ledger_dir / "skills.yaml"  # Fallback for backwards compatibility

    # Try to load from new split structure first
    if active_path.exists() and history_path.exists():
        print(f"   Loading from split structure (active + history)")
        with open(active_path, 'r') as f:
            active_data = yaml.safe_load(f)
        with open(history_path, 'r') as f:
            history_data = yaml.safe_load(f)

        # Merge the two structures
        merged = {"skills": merge_skill_structures(
            active_data.get("skills", {}),
            history_data.get("skills", {})
        )}
        return merged

    # Fallback to legacy single file
    elif legacy_path.exists():
        print(f"   Loading from legacy skills.yaml (consider running split script)")
        with open(legacy_path, 'r') as f:
            return yaml.safe_load(f)

    else:
        raise FileNotFoundError(
            f"Skills files not found. Expected either:\n"
            f"  - {active_path} AND {history_path}\n"
            f"  - {legacy_path}"
        )


def merge_skill_structures(active: Dict, historical: Dict) -> Dict:
    """
    Merge active and historical skill structures into a single unified structure.

    Both structures may have:
    - Top-level categories (e.g., tech_stack)
    - Direct skill lists
    - Nested categories

    Returns merged structure with all skills.
    """
    merged = {}

    # Merge all keys from both structures
    all_keys = set(active.keys()) | set(historical.keys())

    for key in all_keys:
        active_value = active.get(key, {})
        historical_value = historical.get(key, {})

        # If both are dicts (nested structure like tech_stack)
        if isinstance(active_value, dict) and isinstance(historical_value, dict):
            # Recursively merge nested structures
            merged[key] = {}
            nested_keys = set(active_value.keys()) | set(historical_value.keys())
            for nested_key in nested_keys:
                active_nested = active_value.get(nested_key, [])
                historical_nested = historical_value.get(nested_key, [])

                if isinstance(active_nested, list) and isinstance(historical_nested, list):
                    merged[key][nested_key] = active_nested + historical_nested
                elif active_nested:
                    merged[key][nested_key] = active_nested
                else:
                    merged[key][nested_key] = historical_nested

        # If both are lists (skill lists)
        elif isinstance(active_value, list) and isinstance(historical_value, list):
            merged[key] = active_value + historical_value

        # Take whichever exists
        elif active_value:
            merged[key] = active_value
        else:
            merged[key] = historical_value

    return merged


def generate_temporal_metadata_for_tech_stack(skill_name: str, skill_data: Dict) -> Dict:
    """Generate temporal metadata from session tracking in tech_stack skills."""
    sessions = skill_data.get("sessions", [])

    if not sessions:
        return {}

    session_count = len(sessions)
    first_seen = min(sessions)
    last_seen = max(sessions)

    if session_count == 1:
        frequency = "single-session"
        trend = "learning"
    elif session_count <= 3:
        frequency = "occasional"
        trend = "growing"
    else:
        frequency = "regular"
        trend = "established"

    return {
        "first_seen": first_seen,
        "last_seen": last_seen,
        "session_count": session_count,
        "frequency": frequency,
        "trend": trend
    }


def build_evidence_sessions(evidence_samples: List[Dict], data_dir: Path, all_transcripts: List[Dict]) -> List[Dict]:
    """
    Build evidence_sessions from evidence samples.
    IAW Issue #71: Convert evidence array to evidence_sessions format.

    Args:
        evidence_samples: List of evidence dicts with source_file, interaction_id, content
        data_dir: Base directory for transcript files (from OPERATOR_DATA_DIR)
        all_transcripts: List of all parsed transcripts with session_id and start_time

    Returns:
        List of evidence_session dicts with session_file, session_id, date, interaction_id, snippet
    """
    evidence_sessions = []

    # Create lookup map from filename to transcript data
    transcript_map = {t.get("file", ""): t for t in all_transcripts}

    for evidence in evidence_samples:
        source_file = evidence.get("source_file", "")
        interaction_id = evidence.get("interaction_id", "")
        content = evidence.get("content", "")

        if not source_file:
            continue

        # Extract session filename from source_file path
        session_file = Path(source_file).name

        # Look up session_id and date from transcript data
        session_id = "unknown"
        date = "unknown"

        if session_file in transcript_map:
            transcript = transcript_map[session_file]
            session_id = transcript.get("session_id", "unknown")
            start_time = transcript.get("start_time", "")
            # Extract date from start_time (format: YYYY-MM-DD or ISO8601)
            if start_time:
                if 'T' in start_time:
                    date = start_time.split('T')[0]  # ISO8601 format
                else:
                    date = start_time[:10]  # Assume YYYY-MM-DD
        else:
            # Fallback: try to extract date from legacy filename format
            date_match = re.search(r'(\d{6})', session_file)
            if date_match:
                # Convert YYMMDD to YYYY-MM-DD
                date_str = date_match.group(1)
                try:
                    year = int("20" + date_str[:2])
                    month = int(date_str[2:4])
                    day = int(date_str[4:6])
                    date = f"{year:04d}-{month:02d}-{day:02d}"
                except (ValueError, IndexError):
                    date = "unknown"

        # Create 1-line snippet from content
        snippet = content[:100].replace("\n", " ").strip()
        if len(content) > 100:
            snippet += "..."

        evidence_session = {
            "session_file": session_file,
            "session_id": session_id,
            "date": date,
            "interaction_id": interaction_id,
            "snippet": snippet
        }

        evidence_sessions.append(evidence_session)

    return evidence_sessions


def generate_report(all_detections: Dict, all_transcripts: List[Dict], existing_skills: Dict) -> Dict:
    """Generate the final YAML report with enhanced strategic detection data."""
    report = {
        "analysis_metadata": {
            "timestamp": datetime.now().isoformat(),
            "transcripts_analyzed": len(all_transcripts),
            "analysis_version": "2.2.0",  # Added evidence_sessions support (Issue #71)
            "enhancements": [
                "Strategic pattern detection (5 categories)",
                "AI leverage context tracking",
                "Weighted confidence scoring",
                "tech_stack temporal metadata",
                "3-tier pattern specificity system (weights: 3.0, 2.0, 0.5)",
                "Compound pattern requirements for low-tier skills",
                "Negative pattern filtering for false positives",
                "Minimum content length filtering (50 chars)",
                "Evidence sessions for transcript drill-down (Issue #71)"
            ]
        },
        "suggested_updates": []
    }

    for skill_name, skill_data in all_detections.items():
        session_count = len(set(e.get("source_file", "") for e in skill_data.get("evidence", [])))
        confidence = calculate_confidence(skill_data, session_count)

        if confidence < 70:
            continue

        # Determine temporal metadata based on skill type
        if skill_name.startswith("tech_stack."):
            temporal_metadata = generate_temporal_metadata_for_tech_stack(skill_name, skill_data)
        else:
            temporal_metadata = analyze_temporal_metadata(skill_name, all_transcripts, all_detections)

        # Recommend validation type based on outcome evidence (IAW Issue #56)
        outcome_evidence = skill_data.get("outcome_evidence", {})
        if isinstance(outcome_evidence, list):
            # Convert list to dict for compatibility
            outcome_evidence_dict = {}
            for evidence in outcome_evidence:
                etype = evidence.get("type", "unknown")
                if etype not in outcome_evidence_dict:
                    outcome_evidence_dict[etype] = []
                outcome_evidence_dict[etype].append(evidence)
            outcome_evidence = outcome_evidence_dict

        recommended_validation, validation_reason = recommend_validation_type(outcome_evidence)

        # Build evidence_sessions from evidence samples (IAW Issue #71)
        evidence_samples = skill_data.get("evidence", [])[:3]  # Top 3 evidence samples
        data_dir = Path(os.getenv('OPERATOR_DATA_DIR', '')).expanduser() if os.getenv('OPERATOR_DATA_DIR') else Path('')
        evidence_sessions = build_evidence_sessions(evidence_samples, data_dir, all_transcripts)

        suggestion = {
            "skill_name": skill_name,
            "action": "update",
            "confidence": confidence,
            "detection_count": skill_data.get("count", 0),
            "evidence_samples": evidence_samples,
            "evidence_sessions": evidence_sessions,  # NEW: Evidence sessions for drill-down (Issue #71)
            "temporal_metadata": temporal_metadata,
            "validation": recommended_validation,
            "validation_reason": validation_reason,  # Explain why this validation type was chosen
            "approved": False  # Requires human review before applying (Issue #44)
        }

        # Add leverage context if available
        if "leverage_context" in skill_data:
            suggestion["leverage_context"] = skill_data["leverage_context"]

        # Add detection breakdown if available (strategic patterns)
        if "detection_breakdown" in skill_data and skill_data["detection_breakdown"]:
            suggestion["detection_breakdown"] = skill_data["detection_breakdown"]

        # Add quality analysis if available
        if "quality" in skill_data and skill_data["quality"]:
            quality_summary = {
                "active_demonstration": skill_data["quality"].count("active_demonstration"),
                "passive_observation": skill_data["quality"].count("passive_observation"),
                "blind_acceptance": skill_data["quality"].count("blind_acceptance"),
                "learning_discussion": skill_data["quality"].count("learning_discussion")
            }
            suggestion["quality_analysis"] = quality_summary

        report["suggested_updates"].append(suggestion)

    # Sort by confidence, then by strategic pattern count
    report["suggested_updates"].sort(
        key=lambda x: (x["confidence"], x.get("leverage_context", {}).get("strategic_patterns", 0)),
        reverse=True
    )

    return report


def main():
    parser = argparse.ArgumentParser(description="Intelligent Skill Ingestion System")
    # Use the operator_root defined at module level (already calculated correctly)
    # operator_root = Path(__file__).parent.parent  # scripts -> operator

    parser.add_argument(
        "--transcript-dir",
        type=Path,
        # Use OPERATOR_DATA_DIR env var if set, otherwise error
        default=Path(os.getenv('OPERATOR_DATA_DIR', '')).expanduser() if os.getenv('OPERATOR_DATA_DIR') else '',
        help="Directory containing transcript JSON files"
    )
    # Use OPERATOR_LEDGER_DIR env var, fallback to ./ledger for backwards compatibility
    ledger_dir = Path(os.getenv('OPERATOR_LEDGER_DIR', str(operator_root / 'ledger'))).expanduser()

    parser.add_argument(
        "--skills-file",
        type=Path,
        default=ledger_dir / "skills.yaml",
        help="Path to skills.yaml"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ledger_dir / "skill_ingestion_report.yaml",
        help="Output report file"
    )
    parser.add_argument(
        "--source",
        type=str,
        choices=["all", "legacy", "history", "cache"],
        default="all",
        help="Data sources to analyze: all, legacy (TerminalSavedOutput_*.json), history (history.jsonl), or cache (cache .jsonl files)"
    )
    parser.add_argument(
        "--skip-processed",
        action="store_true",
        default=True,
        help="Skip sessions already analyzed (tracked in ingestion_history.yaml)"
    )
    parser.add_argument(
        "--force-reprocess",
        action="store_true",
        help="Reprocess all sessions, ignoring deduplication history"
    )

    args = parser.parse_args()

    print(f"🔍 Starting skill ingestion analysis...")
    print(f"   Transcript directory: {args.transcript_dir}")
    print(f"   Skills file: {args.skills_file}")

    try:
        existing_skills = load_existing_skills(args.skills_file)
        print(f"✅ Loaded existing skills")
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        return 1

    # Load deduplication history
    history_file = ledger_dir / "_meta" / "ingestion_history.yaml"
    ingestion_history = load_ingestion_history(history_file)

    # Parse transcripts based on source selection
    print(f"📂 Parsing transcripts from source: {args.source}...")
    all_transcripts = parse_transcripts(
        args.transcript_dir,
        include_history=(args.source in ["all", "history"]),
        include_cache=(args.source in ["all", "cache"])
    )

    # Filter out already-processed sessions (unless --force-reprocess)
    transcripts = []
    skipped_count = 0

    for t in all_transcripts:
        session_id = t.get("session_id", "")

        if args.force_reprocess or not args.skip_processed:
            transcripts.append(t)
        elif not is_session_processed(ingestion_history, session_id):
            transcripts.append(t)
        else:
            skipped_count += 1

    print(f"✅ Found {len(all_transcripts)} transcripts ({len(transcripts)} new, {skipped_count} already analyzed)")

    if not transcripts:
        print("ℹ️  No new transcripts to analyze")
        return 0

    print(f"🧠 Analyzing skill demonstrations with strategic pattern emphasis...")
    all_detections = defaultdict(lambda: {
        "count": 0,
        "evidence": [],
        "quality": [],
        "leverage_context": {
            "strategic_patterns": 0,
            "directive_instances": 0,
            "evaluative_instances": 0,
            "iterative_instances": 0,
            "learning_instances": 0
        },
        "detection_breakdown": {},
        "sessions": [],
        "outcome_evidence": []  # IAW Issue #40
    })

    strategic_skill_count = 0
    orchestration_skill_count = 0
    tech_stack_skill_count = 0

    for transcript in transcripts:
        transcript_date = transcript.get("start_time", "")[:10]  # Extract YYYY-MM-DD

        orchestration = detect_orchestration_skills(transcript["interactions"])
        tech_stack = detect_tech_stack_skills(transcript["interactions"], transcript_date)
        outcomes = detect_outcome_evidence(transcript["interactions"])  # IAW Issue #40

        for skill_name, skill_data in orchestration.items():
            all_detections[skill_name]["count"] += skill_data.get("count", 0)
            for evidence in skill_data.get("evidence", []):
                evidence["source_file"] = transcript["file"]
                all_detections[skill_name]["evidence"].append(evidence)
            all_detections[skill_name]["quality"].extend(skill_data.get("quality", []))

            # Merge leverage context
            for key in all_detections[skill_name]["leverage_context"]:
                all_detections[skill_name]["leverage_context"][key] += skill_data.get("leverage_context", {}).get(key, 0)

            # Merge detection breakdown
            for breakdown_key, value in skill_data.get("detection_breakdown", {}).items():
                all_detections[skill_name]["detection_breakdown"][breakdown_key] = \
                    all_detections[skill_name]["detection_breakdown"].get(breakdown_key, 0) + value

            # Track skill type
            if skill_name in STRATEGIC_PATTERNS:
                strategic_skill_count += 1
            else:
                orchestration_skill_count += 1

        for skill_name, skill_data in tech_stack.items():
            all_detections[skill_name]["count"] += skill_data.get("count", 0)
            for evidence in skill_data.get("evidence", []):
                evidence["source_file"] = transcript["file"]
                all_detections[skill_name]["evidence"].append(evidence)

            # Merge sessions for temporal metadata
            for session in skill_data.get("sessions", []):
                if session not in all_detections[skill_name]["sessions"]:
                    all_detections[skill_name]["sessions"].append(session)

            tech_stack_skill_count += 1

        # Store outcome evidence for all skills (IAW Issue #40)
        # Outcomes apply transcript-wide, not to specific skills yet
        for outcome_type, outcome_list in outcomes.items():
            for outcome in outcome_list:
                # Add source file to outcome
                outcome["source_file"] = transcript["file"]

    # Add outcome statistics to report metadata
    total_outcomes = sum(len(all_detections[skill].get("outcome_evidence", [])) for skill in all_detections)

    print(f"✅ Detected {len(all_detections)} total skills")
    print(f"   Strategic patterns: {len([k for k in all_detections.keys() if k in STRATEGIC_PATTERNS])} skills")
    print(f"   Orchestration patterns: {len([k for k in all_detections.keys() if k not in STRATEGIC_PATTERNS and not k.startswith('tech_stack.')])} skills")
    print(f"   Tech stack patterns: {len([k for k in all_detections.keys() if k.startswith('tech_stack.')])} skills")

    print(f"📊 Generating report...")
    report = generate_report(dict(all_detections), transcripts, existing_skills)

    with open(args.output, 'w') as f:
        yaml.dump(report, f, default_flow_style=False, sort_keys=False)

    print(f"✅ Report generated: {args.output}")
    print(f"   Suggested updates: {len(report['suggested_updates'])}")
    print(f"   High confidence (>80): {sum(1 for s in report['suggested_updates'] if s['confidence'] > 80)}")

    # Enhanced reporting: leverage context summary
    strategic_count = sum(s.get("leverage_context", {}).get("strategic_patterns", 0) for s in report["suggested_updates"])
    directive_count = sum(s.get("leverage_context", {}).get("directive_instances", 0) for s in report["suggested_updates"])
    evaluative_count = sum(s.get("leverage_context", {}).get("evaluative_instances", 0) for s in report["suggested_updates"])
    iterative_count = sum(s.get("leverage_context", {}).get("iterative_instances", 0) for s in report["suggested_updates"])
    learning_count = sum(s.get("leverage_context", {}).get("learning_instances", 0) for s in report["suggested_updates"])

    print(f"\n📈 Leverage Context Summary:")
    print(f"   Strategic patterns detected: {strategic_count}")
    print(f"   Directive instances: {directive_count}")
    print(f"   Evaluative instances: {evaluative_count}")
    print(f"   Iterative instances: {iterative_count}")
    print(f"   Learning discussions: {learning_count}")

    # Approval workflow instructions (Issue #44)
    print(f"\n📋 Next Steps (Human Review Required):")
    print(f"   1. Review suggested updates in: {args.output}")
    print(f"   2. Set 'approved: true' for updates you want to apply")
    print(f"   3. Run: python scripts/apply_approved_updates.py")
    print(f"\n   ⚠️  Updates are NOT auto-applied - human review required")

    # Mark sessions as processed for deduplication
    for transcript in transcripts:
        session_id = transcript.get("session_id", "")
        if session_id:
            mark_session_processed(
                ingestion_history,
                session_id,
                source="skill-analysis",
                source_path=transcript.get("path", ""),
                timestamp=transcript.get("start_time", "")
            )

    # Save updated deduplication history
    save_ingestion_history(ingestion_history, history_file)
    print(f"💾 Updated deduplication history: {history_file}")

    return 0


if __name__ == "__main__":
    exit(main())
