#!/usr/bin/env python3
"""
Bottleneck Analysis - Detect Automation Opportunities Using Linus Rule

Analyzes session data to identify time-consuming, repetitive activities that should
be automated. Applies measurement-first approach: only recommend automation for proven
bottlenecks with >5 occurrences and >60 minutes total time.

Examples:
    python analyze_bottlenecks.py --last-n-days 14
    python analyze_bottlenecks.py --last-n-days 90 --recommend-only
    python analyze_bottlenecks.py --activity "Code Review"

Output: Saves results to .claude/metrics/bottlenecks-YYYY-MM-DD.json
"""

import argparse
import json
import os
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from collections import defaultdict


def load_sessions(ledger_path: Path) -> List[Dict]:
    """Load sessions.yaml from ledger."""
    sessions_file = ledger_path / "packages" / "ledger" / "sessions.yaml"

    if not sessions_file.exists():
        raise FileNotFoundError(f"Sessions file not found: {sessions_file}")

    with open(sessions_file, 'r') as f:
        data = yaml.safe_load(f)

    return data.get('sessions', [])


def filter_sessions_by_date(sessions: List[Dict], days: int) -> List[Dict]:
    """Filter sessions to last N days."""
    cutoff_date = datetime.now() - timedelta(days=days)
    filtered = []

    for session in sessions:
        date_str = session.get('date', '')
        if date_str:
            try:
                # Parse YYYY-MM-DD format
                session_date = datetime.strptime(date_str, '%Y-%m-%d')
                if session_date >= cutoff_date:
                    filtered.append(session)
            except ValueError:
                continue

    return filtered


def aggregate_time_by_activity(sessions: List[Dict]) -> Dict[str, Dict]:
    """
    Group sessions by skill/activity and aggregate time spent.

    Returns:
        Dict mapping activity name -> {
            'total_minutes': float,
            'occurrences': int,
            'sessions': [session_ids],
            'avg_minutes': float
        }
    """
    activity_stats = defaultdict(lambda: {
        'total_minutes': 0.0,
        'occurrences': 0,
        'sessions': [],
        'avg_minutes': 0.0
    })

    for session in sessions:
        duration = session.get('duration_minutes', 0.0)
        skills = session.get('skills_demonstrated', [])
        session_id = session.get('session_id', '')

        # If session has skills, attribute time to each skill
        if skills:
            # Split time equally across skills demonstrated
            time_per_skill = duration / len(skills) if len(skills) > 0 else duration

            for skill in skills:
                activity_stats[skill]['total_minutes'] += time_per_skill
                activity_stats[skill]['occurrences'] += 1
                activity_stats[skill]['sessions'].append(session_id[:12])
        else:
            # Sessions without skills go to "Unclassified"
            activity_stats['Unclassified']['total_minutes'] += duration
            activity_stats['Unclassified']['occurrences'] += 1
            activity_stats['Unclassified']['sessions'].append(session_id[:12])

    # Calculate averages
    for activity, stats in activity_stats.items():
        if stats['occurrences'] > 0:
            stats['avg_minutes'] = stats['total_minutes'] / stats['occurrences']

    return dict(activity_stats)


def detect_repetitive_patterns(activity_stats: Dict[str, Dict],
                               min_occurrences: int = 5) -> List[Dict]:
    """
    Identify activities done more than N times.

    Returns list of high-frequency activities sorted by total time.
    """
    patterns = []

    for activity, stats in activity_stats.items():
        if stats['occurrences'] >= min_occurrences:
            patterns.append({
                'activity': activity,
                'total_minutes': stats['total_minutes'],
                'occurrences': stats['occurrences'],
                'avg_minutes': stats['avg_minutes'],
                'sessions': stats['sessions']
            })

    # Sort by total time spent (descending)
    patterns.sort(key=lambda x: x['total_minutes'], reverse=True)

    return patterns


def apply_linus_rules(activity_stats: Dict[str, Dict],
                     frequency_threshold: int = 5,
                     time_threshold: int = 60) -> List[Dict]:
    """
    Apply Linus Rule thresholds to determine automation candidates.

    Rules:
    1. Frequency: >5 occurrences in analysis window
    2. Time cost: >60 minutes total
    3. Binary decision: BUILD or DON'T BUILD

    Returns list of recommendations with BUILD/DON'T BUILD decisions.
    """
    recommendations = []

    for activity, stats in activity_stats.items():
        meets_frequency = stats['occurrences'] >= frequency_threshold
        meets_time = stats['total_minutes'] >= time_threshold

        should_automate = meets_frequency and meets_time

        # Calculate expected ROI (assume 80% time savings if automated)
        expected_savings = stats['total_minutes'] * 0.8 if should_automate else 0

        recommendation = {
            'activity': activity,
            'decision': 'BUILD' if should_automate else "DON'T BUILD",
            'metrics': {
                'frequency': stats['occurrences'],
                'total_minutes': round(stats['total_minutes'], 1),
                'avg_minutes_per_occurrence': round(stats['avg_minutes'], 1),
                'expected_savings_minutes': round(expected_savings, 1)
            },
            'thresholds': {
                'frequency_threshold': frequency_threshold,
                'time_threshold': time_threshold,
                'meets_frequency': meets_frequency,
                'meets_time': meets_time
            },
            'reason': _build_reason(meets_frequency, meets_time,
                                   stats['occurrences'], stats['total_minutes'],
                                   frequency_threshold, time_threshold)
        }

        # Add measurement plan for BUILD recommendations
        if should_automate:
            decision_date = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')
            recommendation['measurement'] = {
                'hit_rate_threshold': 30,  # % of times tool finds issue
                'false_positive_threshold': 20,  # % max acceptable false positives
                'sample_size': min(20, stats['occurrences']),
                'decision_date': decision_date,
                'evaluation_criteria': [
                    f"Run on next {min(20, stats['occurrences'])} occurrences",
                    "Track: issues found / false positives",
                    "Keep if hit rate >30% AND false positive <20%"
                ]
            }

        recommendations.append(recommendation)

    # Sort: BUILD first, then by expected savings
    recommendations.sort(key=lambda x: (
        0 if x['decision'] == 'BUILD' else 1,
        -x['metrics']['expected_savings_minutes']
    ))

    return recommendations


def _build_reason(meets_frequency: bool, meets_time: bool,
                 occurrences: int, total_minutes: float,
                 freq_threshold: int, time_threshold: int) -> str:
    """Build human-readable reason for BUILD/DON'T BUILD decision."""
    if meets_frequency and meets_time:
        return (f"Frequent ({occurrences} occurrences) and costly "
               f"({total_minutes:.0f} minutes total) - automate")
    elif not meets_frequency and not meets_time:
        return (f"Below threshold: {occurrences} occurrences "
               f"(need {freq_threshold}) and {total_minutes:.0f} minutes "
               f"(need {time_threshold})")
    elif not meets_frequency:
        return (f"Frequency too low: {occurrences} occurrences "
               f"(need {freq_threshold})")
    else:  # not meets_time
        return (f"Time cost too low: {total_minutes:.0f} minutes "
               f"(need {time_threshold})")


def format_console_output(activity_stats: Dict[str, Dict],
                         recommendations: List[Dict],
                         analysis_window_days: int) -> str:
    """Format results for console output."""
    lines = []
    lines.append(f"\nBOTTLENECKS (last {analysis_window_days} days):\n")

    # Time spent by activity (sorted by total time)
    sorted_activities = sorted(activity_stats.items(),
                              key=lambda x: x[1]['total_minutes'],
                              reverse=True)

    lines.append("Time Spent by Activity:")
    for i, (activity, stats) in enumerate(sorted_activities[:10], 1):
        total = stats['total_minutes']
        count = stats['occurrences']
        avg = stats['avg_minutes']

        # Flag automation candidates
        flag = ""
        for rec in recommendations:
            if rec['activity'] == activity and rec['decision'] == 'BUILD':
                flag = " ⚠️  AUTOMATE"
                break

        lines.append(f"{i}. {activity:<40} {total:>6.0f} min across "
                    f"{count:>3} sessions (avg: {avg:>5.1f} min){flag}")

    # Automation recommendations
    lines.append("\n\nAUTOMATION RECOMMENDATIONS:\n")

    build_recs = [r for r in recommendations if r['decision'] == 'BUILD']
    dont_build_recs = [r for r in recommendations if r['decision'] == "DON'T BUILD"]

    if build_recs:
        for rec in build_recs[:5]:  # Top 5 BUILD recommendations
            lines.append(f"✅ BUILD: {rec['activity']}")
            lines.append(f"   Frequency: {rec['metrics']['frequency']} occurrences "
                        f"in {analysis_window_days} days")
            lines.append(f"   Time cost: {rec['metrics']['total_minutes']:.0f} minutes total "
                        f"({rec['metrics']['avg_minutes_per_occurrence']:.1f} min/occurrence)")
            lines.append(f"   Expected savings: {rec['metrics']['expected_savings_minutes']:.0f} minutes "
                        f"over next {analysis_window_days} days")

            if 'measurement' in rec:
                meas = rec['measurement']
                lines.append(f"   Measurement plan:")
                for criterion in meas['evaluation_criteria']:
                    lines.append(f"     - {criterion}")
                lines.append(f"     - Decide by: {meas['decision_date']}")
            lines.append("")
    else:
        lines.append("No activities meet BUILD criteria (>5 occurrences AND >60 minutes)\n")

    if dont_build_recs and len(build_recs) < 3:
        lines.append("\nDON'T BUILD (below threshold):\n")
        for rec in dont_build_recs[:3]:  # Show top 3 that didn't make cut
            lines.append(f"❌ DON'T BUILD: {rec['activity']}")
            lines.append(f"   {rec['reason']}")
            lines.append("")

    return '\n'.join(lines)


def save_results(activity_stats: Dict[str, Dict],
                recommendations: List[Dict],
                analysis_window_days: int,
                output_dir: Path) -> Path:
    """Save results to .claude/metrics/bottlenecks-YYYY-MM-DD.json"""
    # Create metrics directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename with current date
    today = datetime.now().strftime('%Y-%m-%d')
    output_file = output_dir / f"bottlenecks-{today}.json"

    results = {
        'analysis_metadata': {
            'generated_at': datetime.now().isoformat(),
            'analysis_window_days': analysis_window_days,
            'total_activities': len(activity_stats),
            'build_recommendations': sum(1 for r in recommendations if r['decision'] == 'BUILD'),
            'dont_build_count': sum(1 for r in recommendations if r['decision'] == "DON'T BUILD")
        },
        'activity_statistics': activity_stats,
        'recommendations': recommendations
    }

    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--last-n-days', type=int, default=90,
                       help='Analyze sessions from last N days (default: 90)')
    parser.add_argument('--activity', type=str,
                       help='Show details for specific activity only')
    parser.add_argument('--recommend-only', action='store_true',
                       help='Show only automation recommendations (skip time breakdown)')
    parser.add_argument('--frequency-threshold', type=int, default=5,
                       help='Minimum occurrences to recommend automation (default: 5)')
    parser.add_argument('--time-threshold', type=int, default=60,
                       help='Minimum total minutes to recommend automation (default: 60)')

    args = parser.parse_args()

    # Get operator repo root
    script_dir = Path(__file__).resolve().parent
    ledger_path = script_dir.parent.parent  # analysis/scripts -> operator root
    metrics_dir = ledger_path / ".claude" / "metrics"

    try:
        # Load and filter sessions
        sessions = load_sessions(ledger_path)
        filtered_sessions = filter_sessions_by_date(sessions, args.last_n_days)

        if not filtered_sessions:
            print(f"No sessions found in last {args.last_n_days} days")
            return 1

        # Aggregate time by activity
        activity_stats = aggregate_time_by_activity(filtered_sessions)

        if not activity_stats:
            print("No activities found in sessions")
            return 1

        # Filter to specific activity if requested
        if args.activity:
            if args.activity not in activity_stats:
                print(f"Activity '{args.activity}' not found")
                print(f"Available: {', '.join(sorted(activity_stats.keys())[:10])}")
                return 1
            activity_stats = {args.activity: activity_stats[args.activity]}

        # Generate recommendations
        recommendations = apply_linus_rules(
            activity_stats,
            frequency_threshold=args.frequency_threshold,
            time_threshold=args.time_threshold
        )

        # Save results to filesystem
        output_file = save_results(activity_stats, recommendations,
                                   args.last_n_days, metrics_dir)

        # Print console output
        if not args.recommend_only:
            console_output = format_console_output(activity_stats, recommendations,
                                                   args.last_n_days)
            print(console_output)
        else:
            # Show only BUILD recommendations
            build_recs = [r for r in recommendations if r['decision'] == 'BUILD']
            print(f"\nBUILD Recommendations ({len(build_recs)} total):\n")
            for rec in build_recs:
                print(f"✅ {rec['activity']}")
                print(f"   {rec['reason']}")
                print(f"   Expected savings: {rec['metrics']['expected_savings_minutes']:.0f} min\n")

        print(f"\nResults saved to: {output_file}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
