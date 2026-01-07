#!/usr/bin/env python3
"""
Test suite for manage_skill_status.py

Tests all promotion/demotion rules and edge cases.
"""

import unittest
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add parent directory to path to import the script
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from manage_skill_status import (
    should_promote,
    should_demote,
    calculate_days_since,
    count_recent_sessions,
    has_validated_outcome_evidence,
    promote_skill,
    demote_skill
)


class TestPromotionRules(unittest.TestCase):
    """Test promotion rules (historical -> active)."""

    def test_rule1_manual_override(self):
        """Test Rule 1: Manual override with status='active'"""
        skill = {
            'skill': 'Test Skill',
            'level': 1,
            'status': 'active',
            'temporal_metadata': {
                'session_count': 2,
                'last_seen': '2025-11-01'
            }
        }
        should, reason = should_promote(skill)
        self.assertTrue(should)
        self.assertIn('Manual override', reason)

    def test_rule2_session_threshold_met(self):
        """Test Rule 2: session_count >= 5"""
        skill = {
            'skill': 'Test Skill',
            'level': 1,
            'temporal_metadata': {
                'session_count': 5,
                'last_seen': '2025-11-01'
            }
        }
        should, reason = should_promote(skill)
        self.assertTrue(should)
        self.assertIn('Session threshold', reason)

    def test_rule2_session_threshold_not_met(self):
        """Test Rule 2: session_count < 5 should not promote"""
        # Use an old date to ensure no recent activity
        old_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        skill = {
            'skill': 'Test Skill',
            'level': 1,
            'temporal_metadata': {
                'session_count': 4,
                'last_seen': old_date,
                'frequency': 'rare'
            }
        }
        should, reason = should_promote(skill)
        self.assertFalse(should)

    def test_rule3_recent_activity(self):
        """Test Rule 3: 3+ sessions in last 30 days"""
        today = datetime.now().strftime("%Y-%m-%d")
        skill = {
            'skill': 'Test Skill',
            'level': 1,
            'temporal_metadata': {
                'session_count': 4,
                'last_seen': today,
                'frequency': 'frequent'
            }
        }
        should, reason = should_promote(skill)
        self.assertTrue(should)
        self.assertIn('Recent activity', reason)

    def test_rule4_level2_with_validated_evidence(self):
        """Test Rule 4: Level 2+ with validated outcome evidence"""
        skill = {
            'skill': 'Test Skill',
            'level': 2,
            'outcome_validation_status': 'validated',
            'outcome_evidence': [{'type': 'tests_passed', 'count': 100}],
            'temporal_metadata': {
                'session_count': 3
            }
        }
        should, reason = should_promote(skill)
        self.assertTrue(should)
        self.assertIn('validated outcome evidence', reason)

    def test_no_promotion_criteria_met(self):
        """Test that skill with no criteria met is not promoted"""
        skill = {
            'skill': 'Test Skill',
            'level': 1,
            'temporal_metadata': {
                'session_count': 3,
                'last_seen': '2025-09-01'  # Old date
            }
        }
        should, reason = should_promote(skill)
        self.assertFalse(should)
        self.assertEqual(reason, "")


class TestDemotionRules(unittest.TestCase):
    """Test demotion rules (active -> historical)."""

    def test_rule1_manual_override_dormant(self):
        """Test Rule 1: Manual override with status='dormant'"""
        skill = {
            'skill': 'Test Skill',
            'level': 2,
            'status': 'dormant',
            'temporal_metadata': {
                'session_count': 10,
                'last_seen': '2025-11-01'
            }
        }
        should, reason = should_demote(skill)
        self.assertTrue(should)
        self.assertIn('Manual override', reason)

    def test_rule2_90_days_inactive(self):
        """Test Rule 2: 90+ days inactive"""
        old_date = (datetime.now() - timedelta(days=95)).strftime("%Y-%m-%d")
        skill = {
            'skill': 'Test Skill',
            'level': 2,
            'temporal_metadata': {
                'session_count': 10,
                'last_seen': old_date
            }
        }
        should, reason = should_demote(skill)
        self.assertTrue(should)
        self.assertIn('90+ days inactive', reason)

    def test_rule2_not_90_days_inactive(self):
        """Test Rule 2: Less than 90 days should not demote"""
        recent_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        skill = {
            'skill': 'Test Skill',
            'level': 2,
            'temporal_metadata': {
                'session_count': 10,
                'last_seen': recent_date
            }
        }
        should, reason = should_demote(skill)
        self.assertFalse(should)

    def test_rule3_low_level_after_decay(self):
        """Test Rule 3: Level 0-1 after decay"""
        skill = {
            'skill': 'Test Skill',
            'level': 1,
            'temporal_metadata': {
                'session_count': 5,
                'last_seen': '2025-10-01'
            }
        }
        should, reason = should_demote(skill)
        self.assertTrue(should)
        self.assertIn('Low level after decay', reason)

    def test_rule4_weak_evidence_single_session(self):
        """Test Rule 4: session_count <= 2 AND Level 2+ (weak evidence)"""
        skill = {
            'skill': 'Test Skill',
            'level': 2,
            'temporal_metadata': {
                'session_count': 2,
                'last_seen': '2025-11-01'
            }
        }
        should, reason = should_demote(skill)
        self.assertTrue(should)
        self.assertIn('Weak evidence', reason)

    def test_no_demotion_criteria_met(self):
        """Test that skill with no demotion criteria is not demoted"""
        recent_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        skill = {
            'skill': 'Test Skill',
            'level': 2,
            'temporal_metadata': {
                'session_count': 10,
                'last_seen': recent_date
            }
        }
        should, reason = should_demote(skill)
        self.assertFalse(should)
        self.assertEqual(reason, "")


class TestHelperFunctions(unittest.TestCase):
    """Test helper functions."""

    def test_calculate_days_since_recent(self):
        """Test calculation of days since recent date"""
        today = datetime.now().strftime("%Y-%m-%d")
        days = calculate_days_since(today)
        self.assertEqual(days, 0)

    def test_calculate_days_since_old(self):
        """Test calculation of days since old date"""
        old_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        days = calculate_days_since(old_date)
        self.assertEqual(days, 100)

    def test_calculate_days_since_invalid(self):
        """Test calculation with invalid date returns 0"""
        days = calculate_days_since("invalid-date")
        self.assertEqual(days, 0)

    def test_has_validated_outcome_evidence_true(self):
        """Test detection of validated outcome evidence"""
        skill = {
            'outcome_validation_status': 'validated',
            'outcome_evidence': [{'type': 'tests_passed'}]
        }
        self.assertTrue(has_validated_outcome_evidence(skill))

    def test_has_validated_outcome_evidence_with_evidence_only(self):
        """Test detection when only outcome_evidence exists"""
        skill = {
            'outcome_evidence': [{'type': 'tests_passed'}]
        }
        self.assertTrue(has_validated_outcome_evidence(skill))

    def test_has_validated_outcome_evidence_false(self):
        """Test when no validated evidence exists"""
        skill = {
            'outcome_validation_status': 'pending'
        }
        self.assertFalse(has_validated_outcome_evidence(skill))

    def test_count_recent_sessions_frequent(self):
        """Test counting recent sessions for frequent skills"""
        today = datetime.now().strftime("%Y-%m-%d")
        skill = {
            'temporal_metadata': {
                'last_seen': today,
                'session_count': 10,
                'frequency': 'frequent'
            }
        }
        count = count_recent_sessions(skill, days=30)
        self.assertGreater(count, 0)
        self.assertLessEqual(count, 10)

    def test_count_recent_sessions_old(self):
        """Test counting recent sessions for old skills"""
        old_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        skill = {
            'temporal_metadata': {
                'last_seen': old_date,
                'session_count': 10,
                'frequency': 'frequent'
            }
        }
        count = count_recent_sessions(skill, days=30)
        self.assertEqual(count, 0)


class TestSkillTransformations(unittest.TestCase):
    """Test promote_skill and demote_skill transformations."""

    def test_promote_skill_adds_metadata(self):
        """Test that promotion adds required metadata"""
        skill = {
            'skill': 'Test Skill',
            'level': 2,
            'temporal_metadata': {
                'session_count': 5
            }
        }
        promoted = promote_skill(skill, 'Test Skill')

        self.assertEqual(promoted['status'], 'active')
        self.assertIn('promoted_date', promoted['temporal_metadata'])
        self.assertIn('evidence', promoted)
        self.assertIn('outcome_evidence', promoted)

    def test_promote_skill_preserves_data(self):
        """Test that promotion preserves all original data"""
        skill = {
            'skill': 'Test Skill',
            'level': 2,
            'validation': 'user-confirmed',
            'temporal_metadata': {
                'session_count': 5,
                'first_seen': '2025-01-01'
            },
            'evidence': [{'source': 'test.json', 'note': 'Test evidence'}]
        }
        promoted = promote_skill(skill, 'Test Skill')

        self.assertEqual(promoted['level'], 2)
        self.assertEqual(promoted['validation'], 'user-confirmed')
        self.assertEqual(promoted['temporal_metadata']['session_count'], 5)
        self.assertEqual(promoted['temporal_metadata']['first_seen'], '2025-01-01')
        self.assertEqual(len(promoted['evidence']), 1)

    def test_demote_skill_creates_minimal_format(self):
        """Test that demotion creates minimal format"""
        skill = {
            'skill': 'Test Skill',
            'level': 2,
            'validation': 'agent-assessed',
            'temporal_metadata': {
                'session_count': 5,
                'last_seen': '2025-11-01'
            },
            'evidence': [
                {
                    'source': 'test.json',
                    'date': '2025-11-01',
                    'note': 'Test evidence with a long description that should be truncated'
                }
            ]
        }
        demoted = demote_skill(skill, 'Test Skill')

        self.assertEqual(demoted['skill'], 'Test Skill')
        self.assertEqual(demoted['level'], 2)
        self.assertEqual(demoted['validation'], 'agent-assessed')
        self.assertEqual(demoted['status'], 'dormant')
        self.assertIn('demoted_date', demoted['temporal_metadata'])
        self.assertIn('status_note', demoted)
        self.assertIn('evidence_note', demoted)

    def test_demote_skill_preserves_temporal_metadata(self):
        """Test that demotion preserves temporal_metadata"""
        skill = {
            'skill': 'Test Skill',
            'level': 1,
            'temporal_metadata': {
                'session_count': 3,
                'last_seen': '2025-10-01',
                'first_seen': '2025-01-01',
                'frequency': 'occasional'
            }
        }
        demoted = demote_skill(skill, 'Test Skill')

        self.assertEqual(demoted['temporal_metadata']['session_count'], 3)
        self.assertEqual(demoted['temporal_metadata']['last_seen'], '2025-10-01')
        self.assertEqual(demoted['temporal_metadata']['first_seen'], '2025-01-01')
        self.assertEqual(demoted['temporal_metadata']['frequency'], 'occasional')
        self.assertIn('demoted_date', demoted['temporal_metadata'])


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def test_skill_with_missing_temporal_metadata(self):
        """Test handling of skills with missing temporal_metadata"""
        skill = {
            'skill': 'Test Skill',
            'level': 2
        }
        should_promote_flag, _ = should_promote(skill)
        should_demote_flag, reason = should_demote(skill)

        # Should not crash, should handle gracefully
        self.assertFalse(should_promote_flag)
        # Level 2 with no temporal data has session_count=0 (<=2), so it triggers
        # Rule 4: weak evidence (session_count <= 2 AND Level 2+)
        self.assertTrue(should_demote_flag)
        self.assertIn('Weak evidence', reason)

    def test_skill_exactly_90_days_inactive(self):
        """Test boundary condition of exactly 90 days"""
        date_90_days_ago = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        skill = {
            'skill': 'Test Skill',
            'level': 2,
            'temporal_metadata': {
                'session_count': 10,
                'last_seen': date_90_days_ago
            }
        }
        should, reason = should_demote(skill)
        self.assertTrue(should)

    def test_skill_exactly_5_sessions(self):
        """Test boundary condition of exactly 5 sessions"""
        skill = {
            'skill': 'Test Skill',
            'level': 1,
            'temporal_metadata': {
                'session_count': 5
            }
        }
        should, reason = should_promote(skill)
        self.assertTrue(should)

    def test_level_0_demotion(self):
        """Test that Level 0 skills are demoted"""
        skill = {
            'skill': 'Test Skill',
            'level': 0,
            'temporal_metadata': {
                'session_count': 5,
                'last_seen': '2025-11-01'
            }
        }
        should, reason = should_demote(skill)
        self.assertTrue(should)


if __name__ == '__main__':
    unittest.main()
