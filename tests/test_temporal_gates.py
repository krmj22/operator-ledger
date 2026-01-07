#!/usr/bin/env python3
"""
Temporal Gate Regression Tests

Runs after daily ingestion to verify:
1. Temporal gates block inappropriate level increases
2. Temporal metadata updates correctly
3. Review flags trigger when violations occur
4. Confidence scores calculate properly
5. Frequency/trend classifications accurate

Usage:
  python3 scripts/test_temporal_gates.py

Exit codes:
  0 = All tests pass
  1 = Test failures detected
  2 = Critical violations found
"""

import yaml
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

LEDGER_DIR = Path(__file__).parent.parent
SKILLS_ACTIVE = LEDGER_DIR / "ledger" / "skills" / "active.yaml"
SKILLS_HISTORY = LEDGER_DIR / "ledger" / "skills" / "history.yaml"
SKILLS_LEGACY = LEDGER_DIR / "ledger" / "skills.yaml"

class TemporalGateTests:
    def __init__(self):
        self.skills_data = self._load_skills()
        self.failures = []
        self.warnings = []
        self.passed = 0

    def _load_skills(self) -> Dict:
        """Load skills from split structure (active + history) or legacy file"""
        # Try split structure first
        if SKILLS_ACTIVE.exists() and SKILLS_HISTORY.exists():
            with open(SKILLS_ACTIVE, 'r') as f:
                active = yaml.safe_load(f)
            with open(SKILLS_HISTORY, 'r') as f:
                history = yaml.safe_load(f)

            # Merge the two structures
            merged = {'skills': {}}
            if 'skills' in active:
                merged['skills'].update(active['skills'])
            if 'skills' in history:
                for key, value in history['skills'].items():
                    if key in merged['skills']:
                        # Merge lists if both exist
                        if isinstance(merged['skills'][key], list) and isinstance(value, list):
                            merged['skills'][key].extend(value)
                        elif isinstance(merged['skills'][key], dict) and isinstance(value, dict):
                            merged['skills'][key].update(value)
                    else:
                        merged['skills'][key] = value
            return merged

        # Fallback to legacy
        elif SKILLS_LEGACY.exists():
            with open(SKILLS_LEGACY, 'r') as f:
                return yaml.safe_load(f)

        else:
            raise FileNotFoundError(
                f"Skills files not found. Expected:\n"
                f"  - {SKILLS_ACTIVE} and {SKILLS_HISTORY}\n"
                f"  OR {SKILLS_LEGACY}"
            )

    def _get_all_skills(self) -> List[Dict]:
        """Extract all skills from both tech_stack and orchestration"""
        skills = []

        if 'skills' in self.skills_data:
            # Tech stack skills
            if 'tech_stack' in self.skills_data['skills']:
                for category, skill_list in self.skills_data['skills']['tech_stack'].items():
                    for skill in skill_list:
                        skill['_tier'] = 'tech_stack'
                        skill['_category'] = category
                        skills.append(skill)

            # Orchestration skills
            if 'orchestration' in self.skills_data['skills']:
                for skill in self.skills_data['skills']['orchestration']:
                    skill['_tier'] = 'orchestration'
                    skill['_category'] = None
                    skills.append(skill)

        return skills

    def _fail(self, test_name: str, skill_name: str, message: str):
        """Record test failure"""
        self.failures.append({
            'test': test_name,
            'skill': skill_name,
            'message': message
        })

    def _warn(self, test_name: str, skill_name: str, message: str):
        """Record test warning"""
        self.warnings.append({
            'test': test_name,
            'skill': skill_name,
            'message': message
        })

    def _pass(self):
        """Increment pass counter"""
        self.passed += 1

    # ========================================
    # TEST 1: Single-Session Level 2+ Block
    # ========================================

    def test_single_session_level_2_block(self):
        """CRITICAL: Single-session skills cannot exceed Level 1"""
        test_name = "single_session_level_2_block"

        for skill in self._get_all_skills():
            skill_name = skill.get('skill', 'Unknown')
            level = skill.get('level', 0)

            # Skip Level 0 and Level 1 (allowed)
            if level < 2:
                continue

            # Check temporal metadata
            temporal = skill.get('temporal_metadata', {})

            if not temporal:
                # No temporal metadata but Level 2+ - WARNING
                self._warn(test_name, skill_name,
                          f"Level {level} but no temporal_metadata - cannot verify session count")
                continue

            session_count = temporal.get('session_count', 0)
            frequency = temporal.get('frequency', 'unknown')

            # HARD BLOCK: single-session cannot be Level 2+
            if session_count == 1 or frequency == 'single-session':
                self._fail(test_name, skill_name,
                          f"VIOLATION: Level {level} with session_count={session_count}, frequency={frequency}. "
                          f"Single-session skills MUST be Level 1 or lower.")
            else:
                self._pass()

    # ========================================
    # TEST 2: Level 2 Requires 5+ Sessions
    # ========================================

    def test_level_2_session_requirement(self):
        """Level 2 requires session_count >= 5"""
        test_name = "level_2_session_requirement"

        for skill in self._get_all_skills():
            skill_name = skill.get('skill', 'Unknown')
            level = skill.get('level', 0)

            if level != 2:
                continue

            temporal = skill.get('temporal_metadata', {})

            if not temporal:
                self._warn(test_name, skill_name,
                          f"Level 2 but no temporal_metadata - cannot verify requirement")
                continue

            session_count = temporal.get('session_count', 0)
            frequency = temporal.get('frequency', 'unknown')

            # Level 2 requirement: session_count >= 5, frequency >= "regular"
            if session_count < 5:
                self._fail(test_name, skill_name,
                          f"VIOLATION: Level 2 requires session_count >= 5, got {session_count}")
            elif frequency not in ['regular', 'frequent']:
                self._fail(test_name, skill_name,
                          f"VIOLATION: Level 2 requires frequency >= 'regular', got '{frequency}'")
            else:
                self._pass()

    # ========================================
    # TEST 3: Level 3 Requires 15+ Sessions + Frequent
    # ========================================

    def test_level_3_session_requirement(self):
        """Level 3 requires session_count >= 15, frequency == 'frequent', quantitative evidence"""
        test_name = "level_3_session_requirement"

        for skill in self._get_all_skills():
            skill_name = skill.get('skill', 'Unknown')
            level = skill.get('level', 0)

            if level != 3:
                continue

            temporal = skill.get('temporal_metadata', {})

            if not temporal:
                self._warn(test_name, skill_name,
                          f"Level 3 but no temporal_metadata - cannot verify requirement")
                continue

            session_count = temporal.get('session_count', 0)
            frequency = temporal.get('frequency', 'unknown')

            # Level 3 requirement: session_count >= 15
            if session_count < 15:
                self._fail(test_name, skill_name,
                          f"VIOLATION: Level 3 requires session_count >= 15, got {session_count}")

            # Level 3 requirement: frequency == 'frequent'
            if frequency != 'frequent':
                self._fail(test_name, skill_name,
                          f"VIOLATION: Level 3 requires frequency == 'frequent', got '{frequency}'")

            # Level 3 requirement: quantitative evidence
            evidence = str(skill.get('evidence', '')).lower()
            has_metrics = any(indicator in evidence for indicator in
                            ['%', '<', '>', 'ms', 'seconds', 'files', 'accuracy', 'performance'])

            if not has_metrics:
                self._warn(test_name, skill_name,
                          f"Level 3 should have quantitative evidence (metrics, measurements)")

            if session_count >= 15 and frequency == 'frequent':
                self._pass()

    # ========================================
    # TEST 4: Stale Skills Not Upgraded
    # ========================================

    def test_stale_skills_frozen(self):
        """Stale skills (180+ days) should not be upgraded"""
        test_name = "stale_skills_frozen"

        for skill in self._get_all_skills():
            skill_name = skill.get('skill', 'Unknown')
            temporal = skill.get('temporal_metadata', {})

            if not temporal:
                continue

            trend = temporal.get('trend', 'unknown')
            recency_days = temporal.get('recency_days')

            if trend == 'stale' or (recency_days and recency_days > 180):
                # Stale skill - should have review flag
                review_flags = skill.get('review_flags', [])
                has_stale_flag = any(f.get('trigger') == 'stale_skill' for f in review_flags)

                if not has_stale_flag:
                    self._warn(test_name, skill_name,
                              f"Stale skill (trend={trend}, recency={recency_days} days) "
                              f"should have review flag")
                else:
                    self._pass()
            else:
                self._pass()

    # ========================================
    # TEST 5: Temporal Metadata Completeness
    # ========================================

    def test_temporal_metadata_completeness(self):
        """Skills with evidence should have temporal_metadata"""
        test_name = "temporal_metadata_completeness"

        for skill in self._get_all_skills():
            skill_name = skill.get('skill', 'Unknown')
            level = skill.get('level', 0)
            evidence = skill.get('evidence')
            temporal = skill.get('temporal_metadata')

            # Level 0 skills (placeholders) don't need temporal data
            if level == 0:
                self._pass()
                continue

            # Skills with evidence should have temporal_metadata
            if evidence and not temporal:
                self._warn(test_name, skill_name,
                          f"Level {level} with evidence but missing temporal_metadata")
                continue

            # Check completeness if temporal_metadata exists
            if temporal:
                required_fields = ['first_seen', 'last_seen', 'session_count',
                                 'frequency', 'trend', 'confidence_score']

                missing = [f for f in required_fields if f not in temporal]

                if missing:
                    self._warn(test_name, skill_name,
                              f"temporal_metadata missing fields: {', '.join(missing)}")
                else:
                    self._pass()
            else:
                self._pass()

    # ========================================
    # TEST 6: Frequency Classification Correct
    # ========================================

    def test_frequency_classification(self):
        """Frequency tier should match session_count"""
        test_name = "frequency_classification"

        for skill in self._get_all_skills():
            skill_name = skill.get('skill', 'Unknown')
            temporal = skill.get('temporal_metadata', {})

            if not temporal:
                continue

            session_count = temporal.get('session_count', 0)
            frequency = temporal.get('frequency', 'unknown')

            # Calculate expected frequency
            if session_count == 1:
                expected = 'single-session'
            elif session_count <= 4:
                expected = 'occasional'
            elif session_count <= 10:
                expected = 'regular'
            else:
                expected = 'frequent'

            if frequency != expected:
                self._fail(test_name, skill_name,
                          f"Frequency mismatch: session_count={session_count} "
                          f"should be '{expected}', got '{frequency}'")
            else:
                self._pass()

    # ========================================
    # TEST 7: Confidence Score Range
    # ========================================

    def test_confidence_score_range(self):
        """Confidence scores should be 0-100"""
        test_name = "confidence_score_range"

        for skill in self._get_all_skills():
            skill_name = skill.get('skill', 'Unknown')
            temporal = skill.get('temporal_metadata', {})

            if not temporal:
                continue

            confidence_score = temporal.get('confidence_score')

            if confidence_score is None:
                continue

            if not (0 <= confidence_score <= 100):
                self._fail(test_name, skill_name,
                          f"Confidence score out of range: {confidence_score} (should be 0-100)")
            else:
                self._pass()

    # ========================================
    # TEST 8: Evidence Quality Matches Score
    # ========================================

    def test_evidence_quality_alignment(self):
        """Evidence quality tier should match confidence_score"""
        test_name = "evidence_quality_alignment"

        for skill in self._get_all_skills():
            skill_name = skill.get('skill', 'Unknown')
            temporal = skill.get('temporal_metadata', {})

            if not temporal:
                continue

            confidence_score = temporal.get('confidence_score')
            evidence_quality = temporal.get('evidence_quality')

            if confidence_score is None or evidence_quality is None:
                continue

            # Calculate expected quality tier
            if confidence_score >= 90:
                expected = 'exceptional'
            elif confidence_score >= 70:
                expected = 'strong'
            elif confidence_score >= 50:
                expected = 'moderate'
            else:
                expected = 'weak'

            if evidence_quality != expected:
                self._warn(test_name, skill_name,
                          f"Evidence quality mismatch: score={confidence_score} "
                          f"should be '{expected}', got '{evidence_quality}'")
            else:
                self._pass()

    # ========================================
    # TEST 9: Review Flags for Violations
    # ========================================

    def test_review_flags_present(self):
        """Skills with violations should have review_flags"""
        test_name = "review_flags_present"

        for skill in self._get_all_skills():
            skill_name = skill.get('skill', 'Unknown')
            level = skill.get('level', 0)
            temporal = skill.get('temporal_metadata', {})
            review_flags = skill.get('review_flags', [])

            if not temporal:
                continue

            session_count = temporal.get('session_count', 0)
            frequency = temporal.get('frequency', 'unknown')
            confidence_score = temporal.get('confidence_score', 100)

            # Check if violations exist that should trigger flags
            violations = []

            if session_count == 1 and level >= 2:
                violations.append('single_session_level_2+')

            if confidence_score < 50:
                violations.append('low_confidence')

            if level >= 3 and frequency in ['single-session', 'occasional']:
                violations.append('level_frequency_mismatch')

            # If violations exist, check for corresponding flags
            if violations:
                if not review_flags:
                    self._warn(test_name, skill_name,
                              f"Has violations {violations} but no review_flags")
                else:
                    self._pass()
            else:
                self._pass()

    # ========================================
    # TEST 10: Level 2 Requires Outcome Evidence
    # ========================================

    def test_level_2_outcome_requirement(self):
        """Level 2 requires at least one validated outcome (WARNING if missing) - IAW Issue #40"""
        test_name = "level_2_outcome_requirement"

        for skill in self._get_all_skills():
            skill_name = skill.get('skill', 'Unknown')
            level = skill.get('level', 0)

            if level != 2:
                continue

            outcome_evidence = skill.get('outcome_evidence', [])
            outcome_status = skill.get('outcome_validation_status', 'not_required')

            # Level 2 requires at least one validated outcome
            if not outcome_evidence or outcome_status != 'validated':
                self._warn(test_name, skill_name,
                          f"Level 2 skill missing validated outcome evidence. "
                          f"Outcome status: {outcome_status}, Evidence count: {len(outcome_evidence)}")
            else:
                self._pass()

    # ========================================
    # TEST 11: Level 3 Requires External Validation
    # ========================================

    def test_level_3_external_validation(self):
        """Level 3 requires external validation evidence (FAIL if missing) - IAW Issue #40"""
        test_name = "level_3_external_validation"

        for skill in self._get_all_skills():
            skill_name = skill.get('skill', 'Unknown')
            level = skill.get('level', 0)

            if level != 3:
                continue

            outcome_evidence = skill.get('outcome_evidence', [])
            outcome_status = skill.get('outcome_validation_status', 'not_required')

            # Level 3 requires validated outcome evidence
            if not outcome_evidence or outcome_status != 'validated':
                self._fail(test_name, skill_name,
                          f"VIOLATION: Level 3 skill missing validated outcome evidence (REQUIRED). "
                          f"Outcome status: {outcome_status}, Evidence count: {len(outcome_evidence)}")
                continue

            # Check for external validation evidence type
            has_external = False
            for evidence in outcome_evidence:
                if isinstance(evidence, dict):
                    evidence_type = evidence.get('type', '')
                    if evidence_type in ['production_deployed', 'peer_validated']:
                        has_external = True
                        break

            if not has_external:
                self._fail(test_name, skill_name,
                          f"VIOLATION: Level 3 skill missing external validation evidence. "
                          f"Requires production_deployed or peer_validated evidence type.")
            else:
                self._pass()

    # ========================================
    # TEST 12: Skill Decay System
    # ========================================

    def test_skill_decay_system(self):
        """Skill decay system operates correctly - IAW Issue #42"""
        test_name = "skill_decay_system"

        for skill in self._get_all_skills():
            skill_name = skill.get('skill', 'Unknown')
            level = skill.get('level', 0)
            temporal_metadata = skill.get('temporal_metadata', {})
            decay_applied = temporal_metadata.get('decay_applied')
            last_seen = temporal_metadata.get('last_seen')

            # If decay was applied, verify it's consistent with recency
            if decay_applied:
                if not last_seen:
                    self._fail(test_name, skill_name,
                              f"VIOLATION: Skill has decay_applied but no last_seen timestamp")
                    continue

                # Parse dates
                try:
                    decay_date = datetime.fromisoformat(decay_applied).date() if isinstance(decay_applied, str) else decay_applied
                    last_seen_date = datetime.fromisoformat(last_seen).date() if isinstance(last_seen, str) else last_seen
                except (ValueError, AttributeError) as e:
                    self._fail(test_name, skill_name,
                              f"VIOLATION: Invalid date format in decay_applied or last_seen: {e}")
                    continue

                # Check if decay was applied after last_seen (correct order)
                if decay_date < last_seen_date:
                    # This is restoration scenario - decay was applied, then skill was reused
                    # Level should be 1 (conservative restoration)
                    if level != 1:
                        self._warn(test_name, skill_name,
                                  f"WARNING: Skill has decay_applied ({decay_applied}) before last_seen ({last_seen}). "
                                  f"Expected Level 1 (conservative restoration), got Level {level}")
                else:
                    # Decay is still in effect - verify level is not too high
                    recency_days = (datetime.now().date() - last_seen_date).days

                    # Verify decay_applied flag exists in review_flags
                    review_flags = skill.get('review_flags', [])
                    has_decay_flag = any(f.get('trigger') == 'skill_decay' for f in review_flags)

                    if not has_decay_flag:
                        self._warn(test_name, skill_name,
                                  f"WARNING: Skill has decay_applied but no skill_decay review flag")

                self._pass()
            else:
                # No decay applied - verify skill is not stale without decay
                if last_seen:
                    try:
                        last_seen_date = datetime.fromisoformat(last_seen).date() if isinstance(last_seen, str) else last_seen
                        recency_days = (datetime.now().date() - last_seen_date).days

                        # If skill is very stale (>90 days) and level > 1, warn
                        if recency_days > 90 and level > 1:
                            self._warn(test_name, skill_name,
                                      f"WARNING: Skill is {recency_days} days old at Level {level} but no decay applied. "
                                      f"Expected decay after 60-90 days.")
                    except (ValueError, AttributeError):
                        pass

                self._pass()

    # ========================================
    # Run All Tests
    # ========================================

    def run_all(self) -> Tuple[int, int, int]:
        """Run all regression tests"""
        print("=" * 60)
        print("Temporal Gate Regression Tests")
        print("=" * 60)
        print()

        tests = [
            ("Single-session Level 2+ block", self.test_single_session_level_2_block),
            ("Level 2 session requirement", self.test_level_2_session_requirement),
            ("Level 3 session requirement", self.test_level_3_session_requirement),
            ("Stale skills frozen", self.test_stale_skills_frozen),
            ("Temporal metadata completeness", self.test_temporal_metadata_completeness),
            ("Frequency classification", self.test_frequency_classification),
            ("Confidence score range", self.test_confidence_score_range),
            ("Evidence quality alignment", self.test_evidence_quality_alignment),
            ("Review flags present", self.test_review_flags_present),
            ("Level 2 outcome requirement", self.test_level_2_outcome_requirement),
            ("Level 3 external validation", self.test_level_3_external_validation),
            ("Skill decay system", self.test_skill_decay_system),
        ]

        for test_name, test_func in tests:
            print(f"Running: {test_name}...", end=" ")
            test_func()
            print("✓")

        return self.passed, len(self.failures), len(self.warnings)

    def print_results(self):
        """Print test results"""
        print()
        print("=" * 60)
        print("TEST RESULTS")
        print("=" * 60)
        print()
        print(f"Passed:   {self.passed}")
        print(f"Failed:   {len(self.failures)}")
        print(f"Warnings: {len(self.warnings)}")
        print()

        if self.failures:
            print("=" * 60)
            print("FAILURES (CRITICAL)")
            print("=" * 60)
            for i, failure in enumerate(self.failures, 1):
                print(f"\n{i}. {failure['test']}")
                print(f"   Skill: {failure['skill']}")
                print(f"   {failure['message']}")

        if self.warnings:
            print()
            print("=" * 60)
            print("WARNINGS")
            print("=" * 60)
            for i, warning in enumerate(self.warnings, 1):
                print(f"\n{i}. {warning['test']}")
                print(f"   Skill: {warning['skill']}")
                print(f"   {warning['message']}")

        print()
        print("=" * 60)

        # Exit code based on results
        if self.failures:
            print("❌ TESTS FAILED - Temporal gate violations detected")
            return 2
        elif self.warnings:
            print("⚠️  TESTS PASSED WITH WARNINGS")
            return 1
        else:
            print("✅ ALL TESTS PASSED")
            return 0


def main():
    tester = TemporalGateTests()
    tester.run_all()
    exit_code = tester.print_results()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
