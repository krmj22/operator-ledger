#!/usr/bin/env python3
"""
Ledger Preflight Verification

Purpose:
- Give agents a single command to detect issues before starting work.
- Provide clear terminal output (PASS/FAIL/WARN) and a machine-readable report.

Checks performed (graceful if deps missing):
- YAML parse (if PyYAML available)
- index.yaml references exist
- Absolute external paths exist (best-effort)
- Hash drift vs baseline for top-level .yaml files
- last_verified coherence vs file mtimes (best-effort)

Outputs:
- Human: concise summary with ✓/❌/⚠️
- Machine: .ledger_verify_report.json
- Baseline: .ledger_hashes.json (created on first run)

Exit codes:
- 0 = SAT (no failures; warnings possible)
- 1 = UNSAT (any failure)
"""

from __future__ import annotations
import json
import os
import re
import sys
import hashlib
from pathlib import Path
from datetime import datetime, UTC

# Use OPERATOR_LEDGER_DIR env var, fallback to ./ledger for backwards compatibility
REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.getenv('OPERATOR_LEDGER_DIR', REPO_ROOT / 'ledger')).expanduser()
UPDATE_BASELINE = "--update-baseline" in sys.argv


def load_yaml(path: Path):
    try:
        import yaml  # type: ignore
    except Exception:
        return None, "PyYAML not installed"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f), None
    except Exception as e:
        return None, str(e)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def gather_yaml_files() -> list[Path]:
    return sorted(ROOT.glob("*.yaml"))


def check_yaml_parse(files: list[Path]):
    results = []
    failures = 0
    warnings = 0
    for p in files:
        data, err = load_yaml(p)
        if err == "PyYAML not installed":
            # Single warning, not per-file
            warnings += 1
            results.append({
                "file": str(p),
                "status": "WARN",
                "msg": "PyYAML not installed; schema checks skipped"
            })
            break
        elif err is not None:
            failures += 1
            results.append({"file": str(p), "status": "FAIL", "msg": f"YAML parse error: {err}"})
        else:
            results.append({"file": str(p), "status": "PASS", "msg": "Parsed"})
    return results, failures, warnings


def check_index_references():
    idx = ROOT / "ledger" / "_meta" / "index.yaml"
    if not idx.exists():
        return [{"file": str(idx), "status": "FAIL", "msg": "index.yaml missing"}], 1, 0

    data, err = load_yaml(idx)
    if err == "PyYAML not installed":
        return [{"file": str(idx), "status": "WARN", "msg": "PyYAML not installed; cannot validate index structure"}], 0, 1
    if err:
        return [{"file": str(idx), "status": "FAIL", "msg": f"YAML parse error: {err}"}], 1, 0

    missing = []
    try:
        # Handle new directory-based structure
        directories = data["operator_ledger"].get("directories", {})
        for dir_name, dir_data in directories.items():
            if dir_name == "logs":  # Skip logs directory (has pattern, not files list)
                continue
            files = dir_data.get("files", [])
            for filename in files:
                if isinstance(filename, str) and filename.endswith(".yaml"):
                    file_path = ROOT / "ledger" / dir_name / filename
                    if not file_path.exists():
                        missing.append(f"{dir_name}/{filename}")
    except Exception as e:
        return [{"file": str(idx), "status": "FAIL", "msg": f"index.yaml structure error: {e}"}], 1, 0

    if missing:
        return [{"file": str(idx), "status": "FAIL", "msg": f"Missing referenced files: {', '.join(missing)}"}], 1, 0
    return [{"file": str(idx), "status": "PASS", "msg": "All referenced files exist"}], 0, 0


def scan_external_paths():
    # Best-effort: look for absolute user paths in yaml files
    issues = []
    warnings = 0
    seen_paths = set()
    # Match both quoted and unquoted paths
    # Quoted paths: "/(Users|Volumes)/..."
    # Unquoted paths: /(Users|Volumes)/[^\s"']+
    quoted_pattern = re.compile(r'"(/(Users|Volumes)/[^"]+)"')
    unquoted_pattern = re.compile(r"(?<![\"'])/(Users|Volumes)/[^\s'\"]+(?![\"'])")
    for p in ROOT.glob("*.yaml"):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        # Check quoted paths first (more accurate)
        for m in quoted_pattern.finditer(text):
            path = m.group(1)
            if path not in seen_paths:
                seen_paths.add(path)
                if not os.path.exists(path):
                    warnings += 1
                    issues.append({"file": str(p), "status": "WARN", "msg": f"External path missing: {path}"})
        # Check unquoted paths
        for m in unquoted_pattern.finditer(text):
            path = m.group(0)
            if path not in seen_paths:
                seen_paths.add(path)
                if not os.path.exists(path):
                    warnings += 1
                    issues.append({"file": str(p), "status": "WARN", "msg": f"External path missing: {path}"})
    if not issues:
        return [{"status": "PASS", "msg": "External path scan OK"}], 0, 0
    return issues, 0, warnings


def check_hash_drift(files: list[Path]):
    baseline_path = ROOT / ".ledger_hashes.json"
    current = {str(p.name): sha256_file(p) for p in files}
    if not baseline_path.exists():
        baseline_path.write_text(json.dumps({"created": datetime.utcnow().isoformat() + "Z", "hashes": current}, indent=2))
        return [{"status": "WARN", "msg": "Baseline created (.ledger_hashes.json). Future drift will be detected."}], 0, 1

    try:
        base = json.loads(baseline_path.read_text())
        prev = base.get("hashes", {})
    except Exception as e:
        return [{"status": "FAIL", "msg": f"Cannot read baseline: {e}"}], 1, 0

    if UPDATE_BASELINE:
        baseline_path.write_text(json.dumps({"updated": datetime.utcnow().isoformat() + "Z", "hashes": current}, indent=2))
        return [{"status": "PASS", "msg": "Baseline updated to current hashes"}], 0, 0

    drift = [name for name, h in current.items() if prev.get(name) and prev.get(name) != h]
    new_files = [name for name in current.keys() if name not in prev]
    removed = [name for name in prev.keys() if name not in current]

    issues = []
    failures = 0
    warnings = 0
    if drift:
        # Hash drift is a WARN (content changed), not necessarily a failure.
        warnings += 1
        issues.append({"status": "WARN", "msg": f"Hash drift: {', '.join(sorted(drift))}"})
    if new_files or removed:
        warnings += 1
        issues.append({"status": "WARN", "msg": f"Baseline mismatch (new: {new_files or '-'}, removed: {removed or '-'}). Run update if expected."})
    if not issues:
        issues.append({"status": "PASS", "msg": "No hash drift"})
    return issues, failures, warnings


def check_last_verified(files: list[Path]):
    idx = ROOT / "ledger" / "_meta" / "index.yaml"
    data, err = load_yaml(idx)
    if not idx.exists():
        return [{"status": "WARN", "msg": "index.yaml missing; cannot check last_verified"}], 0, 1
    if err == "PyYAML not installed":
        return [{"status": "WARN", "msg": "PyYAML not installed; skipping last_verified coherence"}], 0, 1
    if err:
        return [{"status": "WARN", "msg": f"index.yaml parse error; skipping last_verified coherence: {err}"}], 0, 1

    try:
        last_verified = data["operator_ledger"]["last_verified"]
    except Exception:
        return [{"status": "WARN", "msg": "index.yaml missing operator_ledger.last_verified"}], 0, 1

    # If last_verified predates any YAML mtime, warn
    try:
        lv = datetime.fromisoformat(str(last_verified))
    except Exception:
        return [{"status": "WARN", "msg": "last_verified not ISO-8601; expected YYYY-MM-DD"}], 0, 1

    stale = []
    for p in files:
        mtime = datetime.fromtimestamp(p.stat().st_mtime)
        if mtime > lv:
            stale.append(p.name)
    if stale:
        return [{"status": "WARN", "msg": f"last_verified is stale vs: {', '.join(sorted(stale))}"}], 0, 1
    return [{"status": "PASS", "msg": "last_verified is up-to-date"}], 0, 0


def check_sessions_validation():
    """
    Verify sessions.yaml structure and data integrity.
    IAW Issue #45 - session activity tracking.

    Checks:
    - sessions.yaml exists and is valid YAML
    - Each session has required fields
    - No duplicate session_ids
    - session_id format is valid (SHA-256)
    """
    sessions_file = ROOT / "ledger" / "activity" / "sessions.yaml"
    if not sessions_file.exists():
        return [{"file": str(sessions_file), "status": "WARN", "msg": "sessions.yaml missing (run daily_ingestion.sh to create)"}], 0, 1

    data, err = load_yaml(sessions_file)
    if err == "PyYAML not installed":
        return [{"file": str(sessions_file), "status": "WARN", "msg": "PyYAML not installed; skipping sessions validation"}], 0, 1
    if err:
        return [{"file": str(sessions_file), "status": "FAIL", "msg": f"YAML parse error: {err}"}], 1, 0

    issues = []
    failures = 0
    warnings = 0

    try:
        sessions = data.get("sessions", [])

        if not isinstance(sessions, list):
            return [{"file": str(sessions_file), "status": "FAIL", "msg": "sessions must be a list"}], 1, 0

        # Check for duplicate session_ids
        seen_ids = set()
        required_fields = ["session_id", "date", "start_time", "interaction_count"]

        for i, session in enumerate(sessions):
            if not isinstance(session, dict):
                failures += 1
                issues.append({
                    "file": str(sessions_file),
                    "status": "FAIL",
                    "msg": f"Session #{i} is not a dict"
                })
                continue

            session_id = session.get("session_id")

            # Check required fields
            missing_fields = [f for f in required_fields if f not in session]
            if missing_fields:
                failures += 1
                issues.append({
                    "file": str(sessions_file),
                    "status": "FAIL",
                    "msg": f"Session #{i} missing fields: {', '.join(missing_fields)}"
                })
                continue

            # Check for duplicates
            if session_id in seen_ids:
                failures += 1
                issues.append({
                    "file": str(sessions_file),
                    "status": "FAIL",
                    "msg": f"Duplicate session_id: {session_id[:8]}..."
                })
            else:
                seen_ids.add(session_id)

            # Validate session_id format (SHA-256 is 64 hex chars)
            if not isinstance(session_id, str) or len(session_id) != 64 or not all(c in '0123456789abcdef' for c in session_id):
                warnings += 1
                issues.append({
                    "file": str(sessions_file),
                    "status": "WARN",
                    "msg": f"Session #{i} has invalid session_id format (expected SHA-256)"
                })

    except Exception as e:
        return [{"file": str(sessions_file), "status": "FAIL", "msg": f"Error checking sessions: {e}"}], 1, 0

    if not issues:
        return [{"status": "PASS", "msg": f"Sessions validation OK ({len(sessions)} sessions)"}], 0, 0

    return issues, failures, warnings


def check_outcome_validation():
    """
    Verify Level 2+ skills have outcome evidence with validated status.
    IAW Issue #40 - outcome validation gate for skill level advancement.
    IAW Issue #58 - supports split structure (skills_active.yaml + skills_history.yaml)

    Level 1: No outcome evidence required (pattern detection only)
    Level 2: At least 1 validated outcome required (WARN if missing)
    Level 3: External validation required (FAIL if missing)
    """
    # Try split structure first (IAW Issue #58)
    active_file = ROOT / "ledger" / "skills" / "active.yaml"
    history_file = ROOT / "ledger" / "skills" / "history.yaml"
    legacy_file = ROOT / "ledger" / "skills.yaml"

    files_to_check = []
    if active_file.exists() and history_file.exists():
        # Split structure
        files_to_check = [(active_file, "active"), (history_file, "historical")]
    elif legacy_file.exists():
        # Legacy single file
        files_to_check = [(legacy_file, "legacy")]
    else:
        return [{
            "file": "skills files",
            "status": "FAIL",
            "msg": "No skills files found (expected ledger/skills/active.yaml + ledger/skills/history.yaml)"
        }], 1, 0

    all_issues = []
    total_failures = 0
    total_warnings = 0

    for skills_file, file_type in files_to_check:
        data, err = load_yaml(skills_file)
        if err == "PyYAML not installed":
            all_issues.append({
                "file": str(skills_file),
                "status": "WARN",
                "msg": "PyYAML not installed; skipping outcome validation"
            })
            total_warnings += 1
            continue
        if err:
            all_issues.append({
                "file": str(skills_file),
                "status": "FAIL",
                "msg": f"YAML parse error: {err}"
            })
            total_failures += 1
            continue

        # Validate this file
        issues, failures, warnings = _validate_skills_data(skills_file, data, file_type)
        all_issues.extend(issues)
        total_failures += failures
        total_warnings += warnings

    return all_issues, total_failures, total_warnings


def _validate_skills_data(skills_file: Path, data: dict, file_type: str):
    """Helper to validate a single skills file's data structure."""
    issues = []
    failures = 0
    warnings = 0

    try:
        skills_data = data.get("skills", {})

        # Check tech_stack skills
        tech_stack = skills_data.get("tech_stack", {})
        for category_name, category_skills in tech_stack.items():
            if not isinstance(category_skills, list):
                continue
            for skill in category_skills:
                if not isinstance(skill, dict):
                    continue

                skill_name = skill.get("skill", "Unknown")
                level = skill.get("level", 0)
                outcome_evidence = skill.get("outcome_evidence", [])
                outcome_status = skill.get("outcome_validation_status", "not_required")

                # Level 2 requires at least one validated outcome (WARNING)
                if level == 2:
                    if not outcome_evidence or outcome_status != "validated":
                        warnings += 1
                        issues.append({
                            "file": str(skills_file),
                            "status": "WARN",
                            "msg": f"Level 2 skill '{skill_name}' missing validated outcome evidence"
                        })

                # Level 3 requires external validation (FAIL)
                elif level == 3:
                    if not outcome_evidence or outcome_status != "validated":
                        failures += 1
                        issues.append({
                            "file": str(skills_file),
                            "status": "FAIL",
                            "msg": f"Level 3 skill '{skill_name}' missing validated outcome evidence (required)"
                        })
                    else:
                        # Check for external validation evidence type
                        has_external = any(
                            e.get("type") in ["production_deployed", "peer_validated"]
                            for e in outcome_evidence if isinstance(e, dict)
                        )
                        if not has_external:
                            failures += 1
                            issues.append({
                                "file": str(skills_file),
                                "status": "FAIL",
                                "msg": f"Level 3 skill '{skill_name}' missing external validation evidence"
                            })

        # Check orchestration skills
        orchestration = skills_data.get("orchestration", [])
        for skill in orchestration:
            if not isinstance(skill, dict):
                continue

            skill_name = skill.get("skill", "Unknown")
            level = skill.get("level", 0)
            outcome_evidence = skill.get("outcome_evidence", [])
            outcome_status = skill.get("outcome_validation_status", "not_required")

            # Level 2 requires at least one validated outcome (WARNING)
            if level == 2:
                if not outcome_evidence or outcome_status != "validated":
                    warnings += 1
                    issues.append({
                        "file": str(skills_file),
                        "status": "WARN",
                        "msg": f"Level 2 skill '{skill_name}' missing validated outcome evidence"
                    })

            # Level 3 requires external validation (FAIL)
            elif level == 3:
                if not outcome_evidence or outcome_status != "validated":
                    failures += 1
                    issues.append({
                        "file": str(skills_file),
                        "status": "FAIL",
                        "msg": f"Level 3 skill '{skill_name}' missing validated outcome evidence (required)"
                    })
                else:
                    # Check for external validation evidence type
                    has_external = any(
                        e.get("type") in ["production_deployed", "peer_validated"]
                        for e in outcome_evidence if isinstance(e, dict)
                    )
                    if not has_external:
                        failures += 1
                        issues.append({
                            "file": str(skills_file),
                            "status": "FAIL",
                            "msg": f"Level 3 skill '{skill_name}' missing external validation evidence"
                        })

    except Exception as e:
        return [{"file": str(skills_file), "status": "FAIL", "msg": f"Error checking outcome validation: {e}"}], 1, 0

    if not issues:
        return [{"status": "PASS", "msg": "Outcome validation gates OK"}], 0, 0

    return issues, failures, warnings


def check_validation_types():
    """
    Verify skills have appropriate validation types based on evidence quality.
    IAW Issue #56 - validation types should reflect evidence quality.

    Checks:
    - Skills with production_deployed or peer_validated evidence should be external-validated
    - Warns if agent-assessed skills have external validation evidence
    """
    # Try split structure first (IAW Issue #58)
    active_file = ROOT / "ledger" / "skills" / "active.yaml"
    history_file = ROOT / "ledger" / "skills" / "history.yaml"
    legacy_file = ROOT / "ledger" / "skills.yaml"

    files_to_check = []
    if active_file.exists() and history_file.exists():
        # Split structure
        files_to_check = [(active_file, "active")]  # Only check active skills
    elif legacy_file.exists():
        # Legacy single file
        files_to_check = [(legacy_file, "legacy")]
    else:
        return [{
            "file": "skills files",
            "status": "FAIL",
            "msg": "No skills files found"
        }], 1, 0

    all_issues = []
    total_failures = 0
    total_warnings = 0

    for skills_file, file_type in files_to_check:
        data, err = load_yaml(skills_file)
        if err == "PyYAML not installed":
            all_issues.append({
                "file": str(skills_file),
                "status": "WARN",
                "msg": "PyYAML not installed; skipping validation type check"
            })
            total_warnings += 1
            continue
        if err:
            all_issues.append({
                "file": str(skills_file),
                "status": "FAIL",
                "msg": f"YAML parse error: {err}"
            })
            total_failures += 1
            continue

        # Check validation types
        try:
            skills_data = data.get("skills", {})

            # Check tech_stack skills
            tech_stack = skills_data.get("tech_stack", {})
            for category_name, category_skills in tech_stack.items():
                if not isinstance(category_skills, list):
                    continue
                for skill in category_skills:
                    if not isinstance(skill, dict):
                        continue

                    skill_name = skill.get("skill", "Unknown")
                    validation = skill.get("validation", "agent-assessed")
                    outcome_evidence = skill.get("outcome_evidence", [])

                    # Check if skill has external validation evidence but wrong validation type
                    external_types = ['production_deployed', 'peer_validated']
                    has_external = any(
                        e.get("type") in external_types
                        for e in outcome_evidence
                    )

                    if has_external and validation != "external-validated":
                        all_issues.append({
                            "file": str(skills_file),
                            "status": "WARN",
                            "msg": f"tech_stack.{category_name}: '{skill_name}' has external evidence but validation={validation}"
                        })
                        total_warnings += 1

            # Check orchestration skills (flat list)
            orchestration = skills_data.get("orchestration", [])
            if isinstance(orchestration, list):
                for skill in orchestration:
                    if not isinstance(skill, dict):
                        continue

                    skill_name = skill.get("skill", "Unknown")
                    validation = skill.get("validation", "agent-assessed")
                    outcome_evidence = skill.get("outcome_evidence", [])

                    # Check if skill has external validation evidence but wrong validation type
                    external_types = ['production_deployed', 'peer_validated']
                    has_external = any(
                        e.get("type") in external_types
                        for e in outcome_evidence
                    )

                    if has_external and validation != "external-validated":
                        all_issues.append({
                            "file": str(skills_file),
                            "status": "WARN",
                            "msg": f"orchestration: '{skill_name}' has external evidence but validation={validation}"
                        })
                        total_warnings += 1

        except Exception as e:
            return [{"file": str(skills_file), "status": "FAIL", "msg": f"Error checking validation types: {e}"}], 1, 0

    if not all_issues:
        return [{"status": "PASS", "msg": "Validation types match evidence quality"}], 0, 0

    return all_issues, total_failures, total_warnings


def check_review_flags():
    """
    Verify review_flags are tracked and resolved in a timely manner.
    IAW Issue #57 - review flags enforcement mechanism.

    Checks:
    - Flags have 'added' date for tracking (WARN if missing)
    - Flags 60+ days old without resolution (WARN - needs review)
    - Flags with resolution marked as resolved (PASS)

    Returns tuple of (issues, failures, warnings)
    """
    # Load skills from appropriate file
    skills_path = ROOT / "ledger" / "skills.yaml"
    active_path = ROOT / "ledger" / "skills" / "active.yaml"
    history_path = ROOT / "ledger" / "skills" / "history.yaml"

    # Prioritize skills.yaml if it exists
    if skills_path.exists():
        data, err = load_yaml(skills_path)
        file_used = "skills.yaml"
    elif active_path.exists() and history_path.exists():
        # Would need to merge - for now just check active
        data, err = load_yaml(active_path)
        file_used = "skills_active.yaml"
    else:
        return [{
            "status": "WARN",
            "msg": "No skills files found for review_flags check"
        }], 0, 1

    if err == "PyYAML not installed":
        return [{
            "status": "WARN",
            "msg": "PyYAML not installed; skipping review_flags check"
        }], 0, 1
    if err:
        return [{
            "status": "FAIL",
            "msg": f"Error loading {file_used}: {err}"
        }], 1, 0

    issues = []
    warnings = 0
    flagged_count = 0
    no_date_count = 0
    old_unresolved_count = 0

    try:
        skills_data = data.get("skills", {})

        # Check tech_stack
        tech_stack = skills_data.get("tech_stack", {})
        for category, skills_list in tech_stack.items():
            if not isinstance(skills_list, list):
                continue
            for skill in skills_list:
                if not isinstance(skill, dict):
                    continue

                flags = skill.get("review_flags", [])
                skill_name = skill.get("skill", "Unknown")

                for flag in flags:
                    flagged_count += 1

                    # Check if flag is resolved
                    if flag.get("resolved"):
                        continue  # Skip resolved flags

                    # Check for added date
                    added_str = flag.get("added")
                    if not added_str:
                        no_date_count += 1
                        continue  # Can't check age without date

                    # Check flag age
                    try:
                        from datetime import datetime
                        added_date = datetime.fromisoformat(added_str)
                        days_old = (datetime.now() - added_date).days

                        if days_old >= 60:
                            old_unresolved_count += 1
                            issues.append({
                                "file": file_used,
                                "status": "WARN",
                                "msg": f"tech_stack.{category}: '{skill_name}' has unresolved flag for {days_old} days (trigger: {flag.get('trigger', 'unknown')})"
                            })
                            warnings += 1
                    except Exception:
                        pass  # Skip malformed dates

        # Check orchestration
        orchestration = skills_data.get("orchestration", [])
        for skill in orchestration:
            if not isinstance(skill, dict):
                continue

            flags = skill.get("review_flags", [])
            skill_name = skill.get("skill", "Unknown")

            for flag in flags:
                flagged_count += 1

                # Check if flag is resolved
                if flag.get("resolved"):
                    continue  # Skip resolved flags

                # Check for added date
                added_str = flag.get("added")
                if not added_str:
                    no_date_count += 1
                    continue  # Can't check age without date

                # Check flag age
                try:
                    from datetime import datetime
                    added_date = datetime.fromisoformat(added_str)
                    days_old = (datetime.now() - added_date).days

                    if days_old >= 60:
                        old_unresolved_count += 1
                        issues.append({
                            "file": file_used,
                            "status": "WARN",
                            "msg": f"orchestration: '{skill_name}' has unresolved flag for {days_old} days (trigger: {flag.get('trigger', 'unknown')})"
                        })
                        warnings += 1
                except Exception:
                    pass  # Skip malformed dates

    except Exception as e:
        return [{
            "file": file_used,
            "status": "FAIL",
            "msg": f"Error checking review_flags: {e}"
        }], 1, 0

    # Add summary messages
    if flagged_count == 0:
        return [{
            "status": "PASS",
            "msg": "No review_flags - system is clean"
        }], 0, 0

    if no_date_count > 0:
        issues.append({
            "status": "WARN",
            "msg": f"{no_date_count} flags missing 'added' date - run generate_review_flags_report.py to track"
        })
        warnings += 1

    if old_unresolved_count == 0 and no_date_count == 0:
        return [{
            "status": "PASS",
            "msg": f"All {flagged_count} flags are recent or properly tracked"
        }], 0, 0

    return issues, 0, warnings


def check_level0_readiness():
    """
    Verify Level 0 skills have readiness field.
    IAW Issue #55 - readiness field for actionable Level 0 signals.

    Checks:
    - All Level 0 skills have readiness field
    - Readiness value is valid (not_ready, ready_to_learn, can_learn_quickly, avoid)
    - readiness_note is present for context

    Level 0 without readiness: WARN (should be added)
    Level 0 with invalid readiness: FAIL
    """
    # Try split structure first (IAW Issue #58)
    active_file = ROOT / "ledger" / "skills" / "active.yaml"
    history_file = ROOT / "ledger" / "skills" / "history.yaml"
    legacy_file = ROOT / "ledger" / "skills.yaml"

    files_to_check = []
    if active_file.exists() and history_file.exists():
        # Split structure - check both active and history
        files_to_check = [(active_file, "active"), (history_file, "history")]
    elif legacy_file.exists():
        # Legacy single file
        files_to_check = [(legacy_file, "legacy")]
    else:
        return [{
            "file": "skills files",
            "status": "FAIL",
            "msg": "No skills files found"
        }], 1, 0

    valid_readiness = ["not_ready", "ready_to_learn", "can_learn_quickly", "avoid"]
    all_issues = []
    total_failures = 0
    total_warnings = 0

    for skills_file, file_type in files_to_check:
        data, err = load_yaml(skills_file)
        if err == "PyYAML not installed":
            all_issues.append({
                "file": str(skills_file),
                "status": "WARN",
                "msg": "PyYAML not installed; skipping Level 0 readiness check"
            })
            total_warnings += 1
            continue
        if err:
            all_issues.append({
                "file": str(skills_file),
                "status": "FAIL",
                "msg": f"YAML parse error: {err}"
            })
            total_failures += 1
            continue

        skills_section = data.get("skills", {})

        # Flatten skills structure (tech_stack subcategories + orchestration list)
        all_skills = []
        if "tech_stack" in skills_section:
            for category, skill_list in skills_section["tech_stack"].items():
                if isinstance(skill_list, list):
                    all_skills.extend(skill_list)
        if "orchestration" in skills_section:
            all_skills.extend(skills_section["orchestration"])

        # Check each Level 0 skill
        for skill in all_skills:
            if not isinstance(skill, dict):
                continue

            skill_name = skill.get("skill", "Unknown")
            level = skill.get("level")

            if level == 0:
                # Level 0 skill found - check readiness
                readiness = skill.get("readiness")
                readiness_note = skill.get("readiness_note")

                if not readiness:
                    all_issues.append({
                        "file": str(skills_file),
                        "status": "WARN",
                        "msg": f"Level 0 skill '{skill_name}' missing readiness field (IAW Issue #55)"
                    })
                    total_warnings += 1
                elif readiness not in valid_readiness:
                    all_issues.append({
                        "file": str(skills_file),
                        "status": "FAIL",
                        "msg": f"Level 0 skill '{skill_name}' has invalid readiness value: '{readiness}' (valid: {', '.join(valid_readiness)})"
                    })
                    total_failures += 1
                elif not readiness_note:
                    all_issues.append({
                        "file": str(skills_file),
                        "status": "WARN",
                        "msg": f"Level 0 skill '{skill_name}' missing readiness_note (context recommended)"
                    })
                    total_warnings += 1

    if not all_issues:
        return [{"status": "PASS", "msg": "All Level 0 skills have valid readiness fields"}], 0, 0

    return all_issues, total_failures, total_warnings


def check_project_skill_references():
    """
    Verify bidirectional project-skill cross-references.
    IAW Issue #52 - bidirectional refs (connects data).

    Checks:
    - All skills in projects.yaml skills_demonstrated exist in skills.yaml
    - All projects in skills.yaml projects_applied exist in projects.yaml
    - Cross-reference consistency (warnings only, not failures)

    Returns tuple of (issues, failures, warnings)
    """
    projects_file = ROOT / "ledger" / "projects" / "repos.yaml"
    skills_file = ROOT / "ledger" / "skills" / "active.yaml"
    active_skills_file = ROOT / "skills_active.yaml"

    # Use active skills if split structure exists
    if active_skills_file.exists():
        skills_file = active_skills_file

    if not projects_file.exists():
        return [{"status": "WARN", "msg": "repos.yaml missing; cannot check cross-references"}], 0, 1
    if not skills_file.exists():
        return [{"status": "WARN", "msg": "skills file missing; cannot check cross-references"}], 0, 1

    projects_data, err = load_yaml(projects_file)
    if err == "PyYAML not installed":
        return [{"status": "WARN", "msg": "PyYAML not installed; skipping cross-reference check"}], 0, 1
    if err:
        return [{"status": "FAIL", "msg": f"Error loading projects.yaml: {err}"}], 1, 0

    skills_data, err = load_yaml(skills_file)
    if err:
        return [{"status": "FAIL", "msg": f"Error loading {skills_file.name}: {err}"}], 1, 0

    issues = []
    failures = 0
    warnings = 0

    try:
        projects = projects_data.get("projects", [])
        skills_section = skills_data.get("skills", {})

        # Build skill name lookup set
        all_skill_names = set()

        # Index tech_stack skills
        tech_stack = skills_section.get("tech_stack", {})
        for category, skill_list in tech_stack.items():
            if isinstance(skill_list, list):
                for skill in skill_list:
                    if isinstance(skill, dict):
                        skill_name = skill.get("skill")
                        if skill_name:
                            all_skill_names.add(skill_name)

        # Index orchestration skills
        orchestration = skills_section.get("orchestration", [])
        for skill in orchestration:
            if isinstance(skill, dict):
                skill_name = skill.get("skill")
                if skill_name:
                    all_skill_names.add(skill_name)

        # Build project name lookup set
        all_project_names = {p.get("name") for p in projects if isinstance(p, dict) and p.get("name")}

        # Check 1: All skills in projects.yaml exist in skills.yaml
        for project in projects:
            if not isinstance(project, dict):
                continue

            project_name = project.get("name", "Unknown")
            skills_demonstrated = project.get("skills_demonstrated", [])

            for skill_ref in skills_demonstrated:
                if isinstance(skill_ref, dict):
                    skill_name = skill_ref.get("skill")

                    if skill_name and skill_name not in all_skill_names:
                        failures += 1
                        issues.append({
                            "file": "projects.yaml",
                            "status": "FAIL",
                            "msg": f"Project '{project_name}' references non-existent skill '{skill_name}'"
                        })

        # Check 2: All projects in skills.yaml exist in projects.yaml
        # Check tech_stack
        for category, skill_list in tech_stack.items():
            if isinstance(skill_list, list):
                for skill in skill_list:
                    if not isinstance(skill, dict):
                        continue

                    skill_name = skill.get("skill", "Unknown")
                    projects_applied = skill.get("projects_applied", [])

                    for project_ref in projects_applied:
                        if isinstance(project_ref, dict):
                            project_name = project_ref.get("project")

                            if project_name and project_name not in all_project_names:
                                failures += 1
                                issues.append({
                                    "file": "skills.yaml",
                                    "status": "FAIL",
                                    "msg": f"Skill '{skill_name}' references non-existent project '{project_name}'"
                                })

        # Check orchestration
        for skill in orchestration:
            if not isinstance(skill, dict):
                continue

            skill_name = skill.get("skill", "Unknown")
            projects_applied = skill.get("projects_applied", [])

            for project_ref in projects_applied:
                if isinstance(project_ref, dict):
                    project_name = project_ref.get("project")

                    if project_name and project_name not in all_project_names:
                        failures += 1
                        issues.append({
                            "file": "skills.yaml",
                            "status": "FAIL",
                            "msg": f"Skill '{skill_name}' references non-existent project '{project_name}'"
                        })

    except Exception as e:
        return [{"status": "FAIL", "msg": f"Error checking project-skill cross-references: {e}"}], 1, 0

    if not issues:
        return [{"status": "PASS", "msg": "All project-skill cross-references are valid"}], 0, 0

    return issues, failures, warnings


def check_timestamp_consistency():
    """
    Verify related entities have synchronized timestamps.
    IAW Issue #53 - timestamp sync for deterministic operations.

    Checks:
    - Project last_update vs skills last_seen for skills used in that project
    - Allows 7-day tolerance window
    - Reports drift >7 days as WARNING (data quality issue)

    Returns tuple of (issues, failures, warnings)
    """
    projects_file = ROOT / "ledger" / "projects" / "repos.yaml"
    skills_file = ROOT / "ledger" / "skills" / "active.yaml"
    active_skills_file = ROOT / "skills_active.yaml"

    # Use active skills if split structure exists
    if active_skills_file.exists():
        skills_file = active_skills_file

    if not projects_file.exists():
        return [{"status": "WARN", "msg": "repos.yaml missing; cannot check timestamp consistency"}], 0, 1
    if not skills_file.exists():
        return [{"status": "WARN", "msg": "skills file missing; cannot check timestamp consistency"}], 0, 1

    projects_data, err = load_yaml(projects_file)
    if err == "PyYAML not installed":
        return [{"status": "WARN", "msg": "PyYAML not installed; skipping timestamp consistency check"}], 0, 1
    if err:
        return [{"status": "FAIL", "msg": f"Error loading projects.yaml: {err}"}], 1, 0

    skills_data, err = load_yaml(skills_file)
    if err:
        return [{"status": "FAIL", "msg": f"Error loading {skills_file.name}: {err}"}], 1, 0

    issues = []
    warnings = 0

    try:
        projects = projects_data.get("projects", [])
        skills_section = skills_data.get("skills", {})

        # Build skill lookup (name -> temporal_metadata)
        skill_lookup = {}

        # Index tech_stack skills
        tech_stack = skills_section.get("tech_stack", {})
        for category, skill_list in tech_stack.items():
            if isinstance(skill_list, list):
                for skill in skill_list:
                    if isinstance(skill, dict):
                        skill_name = skill.get("skill")
                        temporal = skill.get("temporal_metadata", {})
                        if skill_name:
                            skill_lookup[skill_name] = temporal

        # Index orchestration skills
        orchestration = skills_section.get("orchestration", [])
        for skill in orchestration:
            if isinstance(skill, dict):
                skill_name = skill.get("skill")
                temporal = skill.get("temporal_metadata", {})
                if skill_name:
                    skill_lookup[skill_name] = temporal

        # Check each project
        for project in projects:
            if not isinstance(project, dict):
                continue

            project_name = project.get("name", "Unknown")
            project_last_update = project.get("last_update")

            if not project_last_update:
                continue  # Skip projects without timestamps

            # Parse project timestamp
            try:
                project_date = datetime.fromisoformat(str(project_last_update))
            except Exception:
                continue  # Skip malformed dates

            # Check skills demonstrated in this project
            skills_demonstrated = project.get("skills_demonstrated", [])

            for skill_ref in skills_demonstrated:
                if isinstance(skill_ref, dict):
                    skill_name = skill_ref.get("skill")
                elif isinstance(skill_ref, str):
                    skill_name = skill_ref
                else:
                    continue

                if not skill_name or skill_name not in skill_lookup:
                    continue

                temporal = skill_lookup[skill_name]
                skill_last_seen = temporal.get("last_seen")

                if not skill_last_seen:
                    continue

                # Parse skill timestamp
                try:
                    skill_date = datetime.fromisoformat(str(skill_last_seen))
                except Exception:
                    continue

                # Calculate drift
                drift_days = abs((project_date - skill_date).days)

                if drift_days > 7:
                    warnings += 1
                    issues.append({
                        "file": "projects.yaml + skills file",
                        "status": "WARN",
                        "msg": f"Timestamp drift: project '{project_name}' (last_update={project_last_update}) and skill '{skill_name}' (last_seen={skill_last_seen}): {drift_days} days apart"
                    })

    except Exception as e:
        return [{"status": "FAIL", "msg": f"Error checking timestamp consistency: {e}"}], 1, 0

    if not issues:
        return [{"status": "PASS", "msg": "All related entity timestamps within 7-day window"}], 0, 0

    return issues, 0, warnings


def main():
    yaml_files = gather_yaml_files()

    sections = {}
    total_fail = 0
    total_warn = 0

    # 1) YAML parse
    res, f, w = check_yaml_parse(yaml_files)
    sections["yaml_parse"] = res
    total_fail += f
    total_warn += w

    # 2) index references
    res, f, w = check_index_references()
    sections["index_references"] = res
    total_fail += f
    total_warn += w

    # 3) external paths
    res, f, w = scan_external_paths()
    sections["external_paths"] = res
    total_fail += f
    total_warn += w

    # 4) hash drift
    res, f, w = check_hash_drift(yaml_files)
    sections["hash_drift"] = res
    total_fail += f
    total_warn += w

    # 5) last_verified coherence
    res, f, w = check_last_verified(yaml_files)
    sections["last_verified"] = res
    total_fail += f
    total_warn += w

    # 6) outcome validation gates (IAW Issue #40)
    res, f, w = check_outcome_validation()
    sections["outcome_validation"] = res
    total_fail += f
    total_warn += w

    # 7) sessions validation (IAW Issue #45)
    res, f, w = check_sessions_validation()
    sections["sessions_validation"] = res
    total_fail += f
    total_warn += w

    # 8) validation types (IAW Issue #56)
    res, f, w = check_validation_types()
    sections["validation_types"] = res
    total_fail += f
    total_warn += w

    # 9) Level 0 readiness (IAW Issue #55)
    res, f, w = check_level0_readiness()
    sections["level0_readiness"] = res
    total_fail += f
    total_warn += w

    # 10) Review flags enforcement (IAW Issue #57)
    res, f, w = check_review_flags()
    sections["review_flags"] = res
    total_fail += f
    total_warn += w

    # 11) Timestamp consistency (IAW Issue #53)
    res, f, w = check_timestamp_consistency()
    sections["timestamp_consistency"] = res
    total_fail += f
    total_warn += w

    # 12) Project-skill cross-references (IAW Issue #52)
    res, f, w = check_project_skill_references()
    sections["project_skill_references"] = res
    total_fail += f
    total_warn += w

    # Machine-readable report
    report_path = ROOT / ".ledger_verify_report.json"
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "failures": total_fail,
        "warnings": total_warn,
        "sections": sections,
    }
    report_path.write_text(json.dumps(report, indent=2))

    # Human-readable summary
    def show(items):
        for it in items:
            status = it.get("status")
            msg = it.get("msg", "")
            f = it.get("file")
            if status == "PASS":
                icon = "✓"
            elif status == "FAIL":
                icon = "❌"
            else:
                icon = "⚠️"
            where = f" [{f}]" if f else ""
            print(f"  {icon} {status}{where}: {msg}")

    print("\nLedger Verification Summary")
    print("---------------------------")
    for name in ["yaml_parse", "index_references", "external_paths", "hash_drift", "last_verified", "outcome_validation", "sessions_validation", "validation_types", "level0_readiness", "review_flags", "timestamp_consistency", "project_skill_references"]:
        print(f"\n{name}:")
        show(sections[name])

    if total_fail > 0:
        print(f"\nOVERALL: UNSAT (failures={total_fail}, warnings={total_warn})")
        sys.exit(1)
    else:
        if total_warn > 0:
            print(f"\nOVERALL: SAT with warnings (warnings={total_warn})")
        else:
            print("\nOVERALL: SAT")
        sys.exit(0)


if __name__ == "__main__":
    main()
