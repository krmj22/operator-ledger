#!/usr/bin/env python3
"""
Update decision recency tracking based on commit references.

Mark decisions as stale if not revisited in commits/transcripts for >90 days.
Status transitions: active → stale → archived

Part of #92: GitHub commit automation
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml


STALE_THRESHOLD_DAYS = 90


def update_decision_recency(decisions_path=None):
    """
    Update decision status based on last commit reference date.

    Args:
        decisions_path: Path to commit_decisions.yaml

    Returns:
        dict: Statistics about status changes
    """
    if decisions_path is None:
        # Default to ledger/commit_decisions.yaml
        script_dir = Path(__file__).parent
        ledger_dir = script_dir.parent
        decisions_path = ledger_dir / "commit_decisions.yaml"
    else:
        decisions_path = Path(decisions_path)

    # Load decisions
    if not decisions_path.exists():
        print(f"No decisions file found at {decisions_path}")
        return {"total": 0, "active": 0, "stale": 0, "archived": 0}

    with open(decisions_path) as f:
        data = yaml.safe_load(f) or {}

    decisions = data.get("decisions", [])
    if not decisions:
        print("No decisions found")
        return {"total": 0, "active": 0, "stale": 0, "archived": 0, "transitions": 0}

    # Calculate cutoff date
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=STALE_THRESHOLD_DAYS)

    stats = {
        "total": len(decisions),
        "active": 0,
        "stale": 0,
        "archived": 0,
        "transitions": 0,
    }

    # Update each decision
    for decision in decisions:
        old_status = decision.get("status", "active")

        # Parse commit date
        commit_date_str = decision.get("commit_date")
        if not commit_date_str:
            # No date - mark as stale
            decision["status"] = "stale"
        else:
            try:
                # Parse ISO format date
                commit_date = datetime.fromisoformat(commit_date_str.replace('Z', '+00:00'))

                # Check if stale
                if commit_date < cutoff_date:
                    # Transition: active → stale → archived
                    if old_status == "active":
                        decision["status"] = "stale"
                    elif old_status == "stale":
                        # Could transition to archived here if desired
                        decision["status"] = "stale"
                else:
                    # Recent - keep active
                    decision["status"] = "active"
            except (ValueError, AttributeError):
                # Invalid date - mark as stale
                decision["status"] = "stale"

        # Track status
        new_status = decision.get("status", "active")
        stats[new_status] = stats.get(new_status, 0) + 1

        if old_status != new_status:
            stats["transitions"] += 1

    # Write updated decisions
    with open(decisions_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    return stats


def main():
    """Main entry point for CLI."""
    stats = update_decision_recency()

    print(f"Decision recency update complete:")
    print(f"  Total decisions: {stats['total']}")
    print(f"  Active: {stats['active']}")
    print(f"  Stale: {stats['stale']}")
    print(f"  Archived: {stats['archived']}")
    print(f"  Status transitions: {stats['transitions']}")


if __name__ == "__main__":
    main()
