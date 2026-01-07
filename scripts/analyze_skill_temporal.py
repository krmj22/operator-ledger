#!/usr/bin/env python3
"""
Temporal Skill Analysis Script - VALIDATION & AUDIT TOOL

This script is a SECONDARY validation mechanism. The PRIMARY skill detection
happens during daily ingestion by the AI agent, which has full context understanding.

Purpose:
- VALIDATE: Cross-check AI agent's temporal_metadata updates against transcript corpus
- AUDIT: Catch if AI agent missed sessions or misclassified skills
- BACKFILL: Analyze historical transcripts before temporal system was implemented
- REPORT: Generate health metrics and identify gaps

NOTE: This uses keyword-based heuristics as a FALLBACK. The AI agent should be
updating temporal_metadata during daily ingestion with full context awareness.

Usage:
  python3 scripts/analyze_skill_temporal.py [--output temporal_report.yaml]
"""

import json
import yaml
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any

# Use OPERATOR_DATA_DIR env var, fail if not set
TRANSCRIPT_DIR = os.getenv('OPERATOR_DATA_DIR')
if not TRANSCRIPT_DIR:
    raise EnvironmentError("OPERATOR_DATA_DIR environment variable not set. Run: source scripts/bootstrap.sh")

# Use script location to find operator repo root
_SCRIPT_DIR = Path(__file__).resolve().parent
OPERATOR_ROOT = str(_SCRIPT_DIR.parent)  # scripts -> operator
SKILLS_FILE = os.path.join(OPERATOR_ROOT, "ledger", "skills", "active.yaml")
SKILLS_ACTIVE_FILE = os.path.join(OPERATOR_ROOT, "ledger", "skills", "active.yaml")
SKILLS_HISTORY_FILE = os.path.join(OPERATOR_ROOT, "ledger", "skills", "history.yaml")
ETHOS_FILE = os.path.join(OPERATOR_ROOT, "ledger", "operator", "philosophy.yaml")


def load_skills():
    """
    Load skills from both active and historical files.
    Returns: dict with 'active', 'historical', and 'combined' keys
    """
    skills_data = {}

    # Load active skills
    if os.path.exists(SKILLS_ACTIVE_FILE):
        with open(SKILLS_ACTIVE_FILE, 'r') as f:
            skills_data['active'] = yaml.safe_load(f)
    else:
        skills_data['active'] = None

    # Load historical skills
    if os.path.exists(SKILLS_HISTORY_FILE):
        with open(SKILLS_HISTORY_FILE, 'r') as f:
            skills_data['historical'] = yaml.safe_load(f)
    else:
        skills_data['historical'] = None

    # If split files don't exist, fall back to unified skills.yaml
    if skills_data['active'] is None and skills_data['historical'] is None:
        if os.path.exists(SKILLS_FILE):
            with open(SKILLS_FILE, 'r') as f:
                unified = yaml.safe_load(f)
            skills_data['unified'] = unified
            skills_data['active'] = unified  # Treat as active for processing

    return skills_data


def get_transcript_files():
    """Get all JSON transcript files sorted by date"""
    transcript_path = Path(TRANSCRIPT_DIR)
    files = list(transcript_path.glob("TerminalSavedOutput_*.json"))

    # Sort by filename (contains date)
    files.sort()
    return files


def extract_date_from_filename(filename: str) -> datetime:
    """Extract date from TerminalSavedOutput_YYMMDD-HHMMSS.json"""
    match = re.search(r'TerminalSavedOutput_(\d{6})-\d{6}\.json', filename)
    if match:
        date_str = match.group(1)
        # Parse YYMMDD format
        year = 2000 + int(date_str[0:2])
        month = int(date_str[2:4])
        day = int(date_str[4:6])
        return datetime(year, month, day)
    return datetime.now()


def skill_mentioned_in_transcript(skill_name: str, transcript_data: Dict) -> bool:
    """
    Check if skill is mentioned/demonstrated in transcript.

    WARNING: This is a FALLBACK heuristic. The AI agent during daily ingestion
    should be the primary detector with full context understanding.

    This keyword-based approach is limited and won't catch:
    - New technologies not in keyword list
    - Contextual skill usage without explicit naming
    - Subtle demonstrations vs. just talking about something

    Heuristics:
    - Skill name appears in conversation
    - Related keywords/tools mentioned
    - Evidence source references this transcript
    """

    # Convert transcript to searchable text
    text = json.dumps(transcript_data).lower()
    skill_lower = skill_name.lower()

    # Direct mention
    if skill_lower in text:
        return True

    # Keyword mapping for indirect mentions
    keywords = {
        "json": ["json", "schema", "parsing", "transcript"],
        "git": ["git", "commit", "repository", "github"],
        "python": ["python", "py", "script"],
        "markdown": ["markdown", ".md", "documentation"],
        "whisper": ["whisper", "transcription", "audio"],
        "tauri": ["tauri", "desktop", "cargo"],
        "pipeline": ["pipeline", "gate", "validation"],
        "crisp-e": ["crisp-e", "ticket", "verification"],
    }

    skill_key = skill_lower.split()[0]  # First word
    if skill_key in keywords:
        for keyword in keywords[skill_key]:
            if keyword in text:
                return True

    return False


def analyze_temporal_metadata(skills_data: Dict) -> Dict:
    """Analyze all skills and build temporal metadata"""

    temporal_data = defaultdict(lambda: {
        'sessions': [],
        'first_seen': None,
        'last_seen': None,
        'session_count': 0,
        'evidence_sources': set()
    })

    # Get all transcript files
    transcript_files = get_transcript_files()

    print(f"Analyzing {len(transcript_files)} transcript files...")

    # Extract all skills into flat list
    all_skills = []

    # Tech stack skills
    if 'skills' in skills_data and 'tech_stack' in skills_data['skills']:
        for category, skills_list in skills_data['skills']['tech_stack'].items():
            for skill_entry in skills_list:
                all_skills.append(skill_entry)

    # Orchestration skills
    if 'skills' in skills_data and 'orchestration' in skills_data['skills']:
        for skill_entry in skills_data['skills']['orchestration']:
            all_skills.append(skill_entry)

    # Analyze each skill against all transcripts
    for skill_entry in all_skills:
        skill_name = skill_entry['skill']
        print(f"  Analyzing: {skill_name}")

        # Check existing evidence for sources
        if 'evidence' in skill_entry:
            evidence = skill_entry['evidence']

            # Handle different evidence formats
            if isinstance(evidence, list):
                for ev in evidence:
                    if isinstance(ev, dict) and 'source' in ev:
                        temporal_data[skill_name]['evidence_sources'].add(ev['source'])
            elif isinstance(evidence, str):
                # Text evidence - check if contains paths
                paths = re.findall(r'/[^\s]+\.json', evidence)
                for path in paths:
                    temporal_data[skill_name]['evidence_sources'].add(path)

        # Scan transcripts for mentions
        for transcript_file in transcript_files:
            try:
                with open(transcript_file, 'r') as f:
                    transcript_data = json.load(f)

                if skill_mentioned_in_transcript(skill_name, transcript_data):
                    session_date = extract_date_from_filename(transcript_file.name)
                    temporal_data[skill_name]['sessions'].append(session_date)

                    # Update first/last seen
                    if temporal_data[skill_name]['first_seen'] is None:
                        temporal_data[skill_name]['first_seen'] = session_date

                    temporal_data[skill_name]['last_seen'] = session_date

            except Exception as e:
                print(f"    Warning: Could not parse {transcript_file.name}: {e}")
                continue

        # Calculate session count (deduplicate by day)
        unique_dates = set(s.date() for s in temporal_data[skill_name]['sessions'])
        temporal_data[skill_name]['session_count'] = len(unique_dates)

    return temporal_data


def calculate_frequency(session_count: int) -> str:
    """Calculate frequency tier"""
    if session_count == 1:
        return "single-session"
    elif session_count <= 4:
        return "occasional"
    elif session_count <= 10:
        return "regular"
    else:
        return "frequent"


def calculate_trend(last_seen: datetime, session_count: int) -> str:
    """Calculate skill trend"""
    if last_seen is None:
        return "unknown"

    days_since = (datetime.now() - last_seen).days

    if days_since <= 30 and session_count < 3:
        return "learning"
    elif days_since <= 60 and session_count >= 3:
        return "growing"
    elif days_since <= 90:
        return "stable"
    elif days_since <= 180:
        return "declining"
    else:
        return "stale"


def calculate_confidence_score(
    session_count: int,
    recency_days: int,
    has_quantitative: bool,
    evidence_source_count: int,
    frequency: str,
    trend: str
) -> int:
    """Calculate confidence score using framework formula"""

    base_score = 50

    # Temporal factors (+30 max)
    session_boost = min(session_count * 2, 20)

    if recency_days < 30:
        recency_boost = 10
    elif recency_days < 90:
        recency_boost = 5
    else:
        recency_boost = 0

    # Evidence factors (+30 max)
    quant_boost = 15 if has_quantitative else 0

    if evidence_source_count >= 3:
        diversity_boost = 10
    elif evidence_source_count >= 2:
        diversity_boost = 5
    else:
        diversity_boost = 0

    # Risk factors (-20 max)
    single_session_penalty = 15 if session_count == 1 else 0
    stale_penalty = 10 if trend == "stale" else 0

    final_score = base_score + session_boost + recency_boost + quant_boost + diversity_boost
    final_score -= (single_session_penalty + stale_penalty)

    return max(0, min(100, final_score))


def determine_evidence_quality(confidence_score: int) -> str:
    """Determine evidence quality tier"""
    if confidence_score >= 90:
        return "exceptional"
    elif confidence_score >= 70:
        return "strong"
    elif confidence_score >= 50:
        return "moderate"
    else:
        return "weak"


def load_ethos():
    """Load ethos.yaml for decay rules"""
    with open(ETHOS_FILE, 'r') as f:
        return yaml.safe_load(f)


def check_restoration(skill_entry: Dict, restoration_policy: Dict) -> tuple:
    """
    Check if a decayed skill should be restored based on recent usage.

    Returns: (should_restore, new_level, message)
    """
    temporal_metadata = skill_entry.get('temporal_metadata', {})
    decay_applied = temporal_metadata.get('decay_applied')
    last_seen = temporal_metadata.get('last_seen')

    if not decay_applied:
        return (False, None, None)

    # Parse dates
    try:
        decay_date = datetime.fromisoformat(decay_applied).date() if isinstance(decay_applied, str) else decay_applied
        last_seen_date = datetime.fromisoformat(last_seen).date() if isinstance(last_seen, str) else last_seen
    except (ValueError, AttributeError):
        return (False, None, None)

    # Check if skill used after decay was applied
    if last_seen_date > decay_date:
        # Conservative restoration: restore to Level 1
        restore_level = 1
        message = f"Skill reused after decay ({last_seen}) - restored conservatively to Level 1"
        return (True, restore_level, message)

    return (False, None, None)


def calculate_decay(current_level: int, recency_days: int, decay_rules: Dict) -> tuple:
    """
    Calculate decay for a skill based on inactivity.

    Returns: (new_level, decay_applied, severity, message, should_flag)
    """
    if recency_days < 30:
        return (current_level, False, None, None, False)

    # Calculate total levels to downgrade based on thresholds
    levels_to_downgrade = 0
    severity = "low"
    message = ""
    should_flag = False

    thresholds = decay_rules.get('thresholds', [])

    for threshold in thresholds:
        days = threshold['days']
        action = threshold['action']

        if recency_days >= days:
            if action == "downgrade_one_level":
                levels_to_downgrade += 1
                severity = threshold['severity']
                message = threshold['message']
            elif action == "flag_for_review":
                # 30-day threshold - add flag but don't downgrade
                should_flag = True
                if not message:  # Only set if not already set by downgrade
                    severity = threshold['severity']
                    message = threshold['message']

    # If only flagging (no downgrade), still return flag info
    if levels_to_downgrade == 0 and not should_flag:
        return (current_level, False, None, None, False)

    # Apply decay with Level 0 floor
    new_level = max(0, current_level - levels_to_downgrade)

    # decay_applied is True if either downgraded OR flagged
    decay_applied = levels_to_downgrade > 0 or should_flag

    return (new_level, decay_applied, severity, message, should_flag)


def apply_restoration_to_skills(skills_data: Dict, restoration_report: List[Dict]) -> int:
    """
    Apply restoration to skills.yaml in-place.

    Returns: count of skills restored
    """
    restore_count = 0

    for restore_entry in restoration_report:
        skill_name = restore_entry['skill']
        new_level = restore_entry['new_level']

        # Find and update the skill in skills_data
        updated = False

        # Search in tech_stack
        if 'skills' in skills_data and 'tech_stack' in skills_data['skills']:
            for category, skills_list in skills_data['skills']['tech_stack'].items():
                for skill_entry in skills_list:
                    if skill_entry['skill'] == skill_name:
                        skill_entry['level'] = new_level

                        # Clear decay_applied from temporal_metadata
                        if 'temporal_metadata' in skill_entry:
                            if 'decay_applied' in skill_entry['temporal_metadata']:
                                del skill_entry['temporal_metadata']['decay_applied']

                        # Remove decay review flags
                        if 'review_flags' in skill_entry:
                            skill_entry['review_flags'] = [
                                f for f in skill_entry['review_flags']
                                if f.get('trigger') != 'skill_decay'
                            ]

                        # Add restoration note
                        if 'review_flags' not in skill_entry:
                            skill_entry['review_flags'] = []

                        skill_entry['review_flags'].append({
                            'trigger': 'skill_restored',
                            'severity': 'low',
                            'message': restore_entry['message']
                        })

                        updated = True
                        restore_count += 1
                        break
                if updated:
                    break

        # Search in orchestration if not found
        if not updated and 'skills' in skills_data and 'orchestration' in skills_data['skills']:
            for skill_entry in skills_data['skills']['orchestration']:
                if skill_entry['skill'] == skill_name:
                    skill_entry['level'] = new_level

                    # Clear decay_applied from temporal_metadata
                    if 'temporal_metadata' in skill_entry:
                        if 'decay_applied' in skill_entry['temporal_metadata']:
                            del skill_entry['temporal_metadata']['decay_applied']

                    # Remove decay review flags
                    if 'review_flags' in skill_entry:
                        skill_entry['review_flags'] = [
                            f for f in skill_entry['review_flags']
                            if f.get('trigger') != 'skill_decay'
                        ]

                    # Add restoration note
                    if 'review_flags' not in skill_entry:
                        skill_entry['review_flags'] = []

                    skill_entry['review_flags'].append({
                        'trigger': 'skill_restored',
                        'severity': 'low',
                        'message': restore_entry['message']
                    })

                    restore_count += 1
                    break

    return restore_count


def apply_decay_to_skills(skills_data: Dict, decay_report: List[Dict]) -> int:
    """
    Apply decay to skills.yaml in-place.

    Returns: count of skills decayed (including flag-only)
    """
    decay_count = 0
    today = datetime.now().date().isoformat()

    for decay_entry in decay_report:
        skill_name = decay_entry['skill']
        new_level = decay_entry['new_level']
        flag_only = decay_entry.get('flag_only', False)

        # Find and update the skill in skills_data
        updated = False

        # Search in tech_stack
        if 'skills' in skills_data and 'tech_stack' in skills_data['skills']:
            for category, skills_list in skills_data['skills']['tech_stack'].items():
                for skill_entry in skills_list:
                    if skill_entry['skill'] == skill_name:
                        # Update level if it changed
                        if not flag_only:
                            skill_entry['level'] = new_level

                            # Add decay_applied to temporal_metadata only if level changed
                            if 'temporal_metadata' not in skill_entry:
                                skill_entry['temporal_metadata'] = {}

                            skill_entry['temporal_metadata']['decay_applied'] = today

                        # Add review flag
                        if 'review_flags' not in skill_entry:
                            skill_entry['review_flags'] = []

                        flag_trigger = 'skill_decay_flag' if flag_only else 'skill_decay'
                        skill_entry['review_flags'].append({
                            'trigger': flag_trigger,
                            'severity': decay_entry['severity'],
                            'message': decay_entry['message']
                        })

                        updated = True
                        decay_count += 1
                        break
                if updated:
                    break

        # Search in orchestration if not found
        if not updated and 'skills' in skills_data and 'orchestration' in skills_data['skills']:
            for skill_entry in skills_data['skills']['orchestration']:
                if skill_entry['skill'] == skill_name:
                    # Update level if it changed
                    if not flag_only:
                        skill_entry['level'] = new_level

                        # Add decay_applied to temporal_metadata only if level changed
                        if 'temporal_metadata' not in skill_entry:
                            skill_entry['temporal_metadata'] = {}

                        skill_entry['temporal_metadata']['decay_applied'] = today

                    # Add review flag
                    if 'review_flags' not in skill_entry:
                        skill_entry['review_flags'] = []

                    flag_trigger = 'skill_decay_flag' if flag_only else 'skill_decay'
                    skill_entry['review_flags'].append({
                        'trigger': flag_trigger,
                        'severity': decay_entry['severity'],
                        'message': decay_entry['message']
                    })

                    decay_count += 1
                    break

    return decay_count


def save_skills(skills_data: Dict):
    """
    Save updated skills to appropriate files.
    Handles both split (active/historical) and unified (skills.yaml) formats.
    """
    # If unified format (fallback to single file)
    if 'unified' in skills_data:
        with open(SKILLS_FILE, 'w') as f:
            yaml.dump(skills_data['active'], f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        return

    # Save active skills
    if skills_data.get('active') is not None:
        with open(SKILLS_ACTIVE_FILE, 'w') as f:
            yaml.dump(skills_data['active'], f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # Save historical skills
    if skills_data.get('historical') is not None:
        with open(SKILLS_HISTORY_FILE, 'w') as f:
            yaml.dump(skills_data['historical'], f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def generate_temporal_report(skills_data: Dict, temporal_data: Dict) -> Dict:
    """Generate complete temporal analysis report"""

    report = {
        'analysis_date': datetime.now().isoformat(),
        'skills': []
    }

    # Extract all skills
    all_skills = []

    if 'skills' in skills_data and 'tech_stack' in skills_data['skills']:
        for category, skills_list in skills_data['skills']['tech_stack'].items():
            for skill_entry in skills_list:
                all_skills.append(('tech_stack', category, skill_entry))

    if 'skills' in skills_data and 'orchestration' in skills_data['skills']:
        for skill_entry in skills_data['skills']['orchestration']:
            all_skills.append(('orchestration', None, skill_entry))

    # Build report for each skill
    for tier, category, skill_entry in all_skills:
        skill_name = skill_entry['skill']
        current_level = skill_entry.get('level', 0)

        temporal = temporal_data[skill_name]

        # Calculate derived metrics
        session_count = temporal['session_count']
        first_seen = temporal['first_seen']
        last_seen = temporal['last_seen']
        evidence_source_count = len(temporal['evidence_sources'])

        if last_seen:
            recency_days = (datetime.now() - last_seen).days
        else:
            recency_days = 9999

        frequency = calculate_frequency(session_count)
        trend = calculate_trend(last_seen, session_count)

        # Check for quantitative evidence
        evidence = skill_entry.get('evidence', '')
        has_quantitative = bool(re.search(r'\d+(\.\d+)?%|<\d+|>\d+|\d+\s*ms|\d+\s*files', str(evidence)))

        confidence_score = calculate_confidence_score(
            session_count, recency_days, has_quantitative,
            evidence_source_count, frequency, trend
        )

        evidence_quality = determine_evidence_quality(confidence_score)

        # Check for review flags
        review_flags = []

        if session_count == 1 and current_level >= 2:
            review_flags.append({
                'trigger': 'single_session_level_2+',
                'severity': 'high',
                'message': 'Only 1 session but Level 2+ - consider downgrade'
            })

        if recency_days > 180:
            review_flags.append({
                'trigger': 'stale_skill',
                'severity': 'medium',
                'message': f'{recency_days} days since last use - review for removal'
            })

        if confidence_score < 50:
            review_flags.append({
                'trigger': 'low_confidence',
                'severity': 'medium',
                'message': f'Confidence score {confidence_score} - strengthen evidence'
            })

        if current_level >= 3 and frequency in ['single-session', 'occasional']:
            review_flags.append({
                'trigger': 'level_frequency_mismatch',
                'severity': 'high',
                'message': f'Level {current_level} but {frequency} use - downgrade recommended'
            })

        skill_report = {
            'skill': skill_name,
            'tier': tier,
            'category': category,
            'current_level': current_level,
            'temporal_metadata': {
                'first_seen': first_seen.isoformat() if first_seen else None,
                'last_seen': last_seen.isoformat() if last_seen else None,
                'session_count': session_count,
                'recency_days': recency_days if recency_days < 9999 else None,
                'frequency': frequency,
                'evidence_sources': evidence_source_count,
                'trend': trend
            },
            'confidence_metadata': {
                'confidence_score': confidence_score,
                'evidence_quality': evidence_quality,
                'quantitative_evidence': has_quantitative
            },
            'review_flags': review_flags
        }

        report['skills'].append(skill_report)

    # Add summary statistics
    report['summary'] = {
        'total_skills': len(report['skills']),
        'by_frequency': {
            'single-session': sum(1 for s in report['skills'] if s['temporal_metadata']['frequency'] == 'single-session'),
            'occasional': sum(1 for s in report['skills'] if s['temporal_metadata']['frequency'] == 'occasional'),
            'regular': sum(1 for s in report['skills'] if s['temporal_metadata']['frequency'] == 'regular'),
            'frequent': sum(1 for s in report['skills'] if s['temporal_metadata']['frequency'] == 'frequent')
        },
        'by_trend': {
            'learning': sum(1 for s in report['skills'] if s['temporal_metadata']['trend'] == 'learning'),
            'growing': sum(1 for s in report['skills'] if s['temporal_metadata']['trend'] == 'growing'),
            'stable': sum(1 for s in report['skills'] if s['temporal_metadata']['trend'] == 'stable'),
            'declining': sum(1 for s in report['skills'] if s['temporal_metadata']['trend'] == 'declining'),
            'stale': sum(1 for s in report['skills'] if s['temporal_metadata']['trend'] == 'stale')
        },
        'by_confidence': {
            'exceptional': sum(1 for s in report['skills'] if s['confidence_metadata']['evidence_quality'] == 'exceptional'),
            'strong': sum(1 for s in report['skills'] if s['confidence_metadata']['evidence_quality'] == 'strong'),
            'moderate': sum(1 for s in report['skills'] if s['confidence_metadata']['evidence_quality'] == 'moderate'),
            'weak': sum(1 for s in report['skills'] if s['confidence_metadata']['evidence_quality'] == 'weak')
        },
        'total_review_flags': sum(len(s['review_flags']) for s in report['skills']),
        'high_severity_flags': sum(1 for s in report['skills'] for flag in s['review_flags'] if flag['severity'] == 'high')
    }

    return report


def process_skills_file(skills_file_data: Dict, file_label: str, decay_rules: Dict, temporal_data: Dict) -> tuple:
    """
    Process a single skills file (active or historical) for decay/restoration.
    Returns: (restoration_report, decay_report)
    """
    print(f"\n{'=' * 60}")
    print(f"Processing {file_label}")
    print(f"{'=' * 60}")

    restoration_report = []
    decay_report = []
    restoration_policy = decay_rules.get('restoration', {}) if decay_rules else {}

    # Extract all skill entries for restoration check
    all_skill_entries = []
    if 'skills' in skills_file_data and 'tech_stack' in skills_file_data['skills']:
        for category, skills_list in skills_file_data['skills']['tech_stack'].items():
            for skill_entry in skills_list:
                all_skill_entries.append(skill_entry)

    if 'skills' in skills_file_data and 'orchestration' in skills_file_data['skills']:
        for skill_entry in skills_file_data['skills']['orchestration']:
            all_skill_entries.append(skill_entry)

    # Check for restoration
    print("\nChecking restoration...")
    for skill_entry in all_skill_entries:
        should_restore, new_level, message = check_restoration(skill_entry, restoration_policy)

        if should_restore:
            restoration_report.append({
                'skill': skill_entry['skill'],
                'old_level': skill_entry.get('level', 0),
                'new_level': new_level,
                'message': message
            })
            print(f"  ✅ {skill_entry['skill']}: Level {skill_entry.get('level', 0)} → {new_level} (restored)")

    if not restoration_report:
        print("  ℹ️  No skills require restoration")

    # Check for decay
    print("\nChecking decay...")
    if decay_rules:
        for skill_entry in all_skill_entries:
            skill_name = skill_entry['skill']
            current_level = skill_entry.get('level', 0)

            # Skip if skill was just restored
            if any(r['skill'] == skill_name for r in restoration_report):
                continue

            # Calculate recency_days
            # Priority: 1) Valid transcript data 2) YAML last_seen field
            recency_days = 9999

            if skill_name in temporal_data:
                temporal_info = temporal_data[skill_name]
                transcript_recency = temporal_info.get('recency_days', 9999)
                if transcript_recency < 9999:
                    recency_days = transcript_recency

            # If not found in transcripts or recency is 9999, check YAML
            if recency_days == 9999:
                temporal_metadata = skill_entry.get('temporal_metadata', {})
                last_seen_str = temporal_metadata.get('last_seen')

                if last_seen_str:
                    try:
                        last_seen_date = datetime.fromisoformat(last_seen_str).date()
                        today = datetime.now().date()
                        recency_days = (today - last_seen_date).days
                    except (ValueError, AttributeError):
                        recency_days = 9999

            if recency_days and recency_days < 9999:
                new_level, should_decay, severity, message, should_flag = calculate_decay(
                    current_level, recency_days, decay_rules
                )

                if should_decay:
                    decay_report.append({
                        'skill': skill_name,
                        'old_level': current_level,
                        'new_level': new_level,
                        'recency_days': recency_days,
                        'severity': severity,
                        'message': message,
                        'flag_only': should_flag and new_level == current_level
                    })
                    if new_level < current_level:
                        print(f"  ❌ {skill_name}: Level {current_level} → {new_level} ({recency_days} days)")
                    elif should_flag:
                        print(f"  ⚠️  {skill_name}: Level {current_level} (flagged - {recency_days} days)")

    if not decay_report:
        print("  ℹ️  No skills require decay")

    return restoration_report, decay_report


def main():
    print("=" * 60)
    print("Temporal Skill Analysis with Decay")
    print("=" * 60)

    # Load skills (both active and historical)
    print("\nLoading skills files...")
    skills_data = load_skills()

    # Determine which files we're working with
    has_split_files = skills_data.get('active') is not None and 'unified' not in skills_data

    if has_split_files:
        print("✓ Found split files: skills_active.yaml and skills_history.yaml")
    else:
        print("✓ Using unified file: skills.yaml")

    # Load ethos for decay rules
    print("Loading decay rules from ethos.yaml...")
    ethos_data = load_ethos()
    decay_rules = ethos_data.get('ethos', {}).get('skill_decay', {})

    if not decay_rules:
        print("⚠️  WARNING: No decay rules found in ethos.yaml - skipping decay")

    # Analyze temporal metadata (combine all skills for temporal analysis)
    print("\nAnalyzing temporal metadata from transcripts...")
    # For temporal analysis, we need to combine active and historical
    if has_split_files:
        # Create a combined structure for temporal analysis
        combined_for_analysis = {'skills': {}}
        if skills_data.get('active'):
            for key in skills_data['active'].get('skills', {}):
                combined_for_analysis['skills'][key] = skills_data['active']['skills'][key]
        temporal_data = analyze_temporal_metadata(combined_for_analysis)

        # Also analyze historical if it exists
        if skills_data.get('historical'):
            historical_temporal = analyze_temporal_metadata(skills_data['historical'])
            temporal_data.update(historical_temporal)
    else:
        temporal_data = analyze_temporal_metadata(skills_data['active'])

    # Process skills for decay/restoration
    all_restoration_reports = []
    all_decay_reports = []

    if has_split_files:
        # Process active skills
        if skills_data.get('active'):
            active_restore, active_decay = process_skills_file(
                skills_data['active'],
                "ACTIVE SKILLS (skills_active.yaml)",
                decay_rules,
                temporal_data
            )

            # Apply changes to active file
            if active_restore:
                restore_count = apply_restoration_to_skills(skills_data['active'], active_restore)
                print(f"  ✅ Applied {restore_count} restorations to active file")
            if active_decay:
                decay_count = apply_decay_to_skills(skills_data['active'], active_decay)
                print(f"  ✅ Applied {decay_count} decays to active file")

            all_restoration_reports.extend(active_restore)
            all_decay_reports.extend(active_decay)

        # Process historical skills
        if skills_data.get('historical'):
            historical_restore, historical_decay = process_skills_file(
                skills_data['historical'],
                "HISTORICAL SKILLS (skills_history.yaml)",
                decay_rules,
                temporal_data
            )

            # Apply changes to historical file
            if historical_restore:
                restore_count = apply_restoration_to_skills(skills_data['historical'], historical_restore)
                print(f"  ✅ Applied {restore_count} restorations to historical file")
            if historical_decay:
                decay_count = apply_decay_to_skills(skills_data['historical'], historical_decay)
                print(f"  ✅ Applied {decay_count} decays to historical file")

            all_restoration_reports.extend(historical_restore)
            all_decay_reports.extend(historical_decay)
    else:
        # Process unified file
        unified_restore, unified_decay = process_skills_file(
            skills_data['active'],
            "UNIFIED SKILLS (skills.yaml)",
            decay_rules,
            temporal_data
        )

        # Apply changes to unified file
        if unified_restore:
            restore_count = apply_restoration_to_skills(skills_data['active'], unified_restore)
            print(f"  ✅ Applied {restore_count} restorations")
        if unified_decay:
            decay_count = apply_decay_to_skills(skills_data['active'], unified_decay)
            print(f"  ✅ Applied {decay_count} decays")

        all_restoration_reports.extend(unified_restore)
        all_decay_reports.extend(unified_decay)

    # Save updated files if any changes were made
    if all_restoration_reports or all_decay_reports:
        print(f"\nSaving updated skill files...")
        save_skills(skills_data)
        print(f"✅ Skill files saved successfully")

    # Use combined reports for summary
    restoration_report = all_restoration_reports
    decay_report = all_decay_reports

    # Generate report
    print("\nGenerating temporal analysis report...")
    report = generate_temporal_report(skills_data['active'], temporal_data)

    # Save report
    timestamp = datetime.now().strftime("%Y%m%d")
    output_file = os.path.join(LEDGER_DIR, f"ledger/logs/temporal_analysis_{timestamp}.yaml")
    print(f"\nSaving report to {output_file}...")

    # Add decay and restoration summary to report
    report['decay_summary'] = {
        'decay_count': len(decay_report),
        'decayed_skills': decay_report,
        'restoration_count': len(restoration_report),
        'restored_skills': restoration_report
    }

    with open(output_file, 'w') as f:
        yaml.dump(report, f, default_flow_style=False, sort_keys=False)

    # Print summary
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"\nTotal skills analyzed: {report['summary']['total_skills']}")
    print(f"\nFrequency distribution:")
    for freq, count in report['summary']['by_frequency'].items():
        print(f"  {freq}: {count}")
    print(f"\nTrend distribution:")
    for trend, count in report['summary']['by_trend'].items():
        print(f"  {trend}: {count}")
    print(f"\nConfidence distribution:")
    for quality, count in report['summary']['by_confidence'].items():
        print(f"  {quality}: {count}")
    print(f"\nReview flags:")
    print(f"  Total: {report['summary']['total_review_flags']}")
    print(f"  High severity: {report['summary']['high_severity_flags']}")

    print(f"\nSkill decay/restoration:")
    print(f"  Skills restored: {len(restoration_report)}")
    print(f"  Skills decayed: {len(decay_report)}")

    # Highlight high-priority issues
    print(f"\n" + "=" * 60)
    print("HIGH-PRIORITY REVIEW FLAGS")
    print("=" * 60)
    for skill_data in report['skills']:
        high_flags = [f for f in skill_data['review_flags'] if f['severity'] == 'high']
        if high_flags:
            print(f"\n{skill_data['skill']} (Level {skill_data['current_level']}):")
            for flag in high_flags:
                print(f"  ⚠️  {flag['message']}")

    print(f"\nFull report saved to: {output_file}")


if __name__ == "__main__":
    main()
