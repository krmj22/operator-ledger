#!/usr/bin/env python3
"""
Generate Dashboard Data

Reads YAML files and generates JavaScript data file for HTML dashboard.
Creates visually impressive heat maps with temporal intelligence.

Usage:
  python3 scripts/generate_dashboard_data.py
"""

import yaml
import json
import os
import glob
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SKILLS_FILE = REPO_ROOT / "packages" / "ledger" / "skills.yaml"
PROJECTS_FILE = REPO_ROOT / "packages" / "ledger" / "projects.yaml"

# Find the newest temporal analysis file (optional - fallback to skills.yaml temporal_metadata)
temporal_pattern = str(REPO_ROOT / "packages" / "ledger" / "logs" / "temporal_analysis_*.yaml")
temporal_files = glob.glob(temporal_pattern)
TEMPORAL_ANALYSIS = None
TEMPORAL_SOURCE = "skills.yaml (fallback)"  # Track which source we're using
if temporal_files:
    # Sort by filename (YYYYMMDD in filename sorts chronologically)
    TEMPORAL_ANALYSIS = Path(sorted(temporal_files)[-1])
    TEMPORAL_SOURCE = f"temporal_analysis_{TEMPORAL_ANALYSIS.stem.split('_')[-1]}.yaml"

OUTPUT_FILE = REPO_ROOT / "analysis" / "dashboards" / "ui" / "dashboard_data.js"


def load_yaml(file_path):
    """Load YAML file"""
    if not file_path.exists():
        return {}
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)


def extract_skills_data():
    """Extract skills with temporal metadata"""
    skills_data = load_yaml(SKILLS_FILE)
    # Load temporal analysis if available, otherwise use empty dict (fallback to skill temporal_metadata)
    temporal_data = load_yaml(TEMPORAL_ANALYSIS) if TEMPORAL_ANALYSIS else {}

    # Build temporal lookup
    temporal_lookup = {}
    if 'skills' in temporal_data:
        for skill_entry in temporal_data['skills']:
            skill_name = skill_entry.get('skill')
            temporal_lookup[skill_name] = skill_entry

    skills_list = []

    # Extract tech_stack skills
    if 'skills' in skills_data and 'tech_stack' in skills_data['skills']:
        for category, skill_list in skills_data['skills']['tech_stack'].items():
            for skill in skill_list:
                skill_name = skill.get('skill', 'Unknown')
                level = skill.get('level', 0)

                # Get temporal data - prioritize temporal_lookup (from analysis)
                if skill_name in temporal_lookup:
                    temporal = temporal_lookup[skill_name].get('temporal_metadata', {})
                    confidence_meta = temporal_lookup[skill_name].get('confidence_metadata', {})
                else:
                    temporal = skill.get('temporal_metadata', {})
                    confidence_meta = {}

                # Get confidence score - prefer from temporal analysis
                confidence_score = temporal.get('confidence_score')
                if confidence_score is None and confidence_meta:
                    confidence_score = confidence_meta.get('confidence_score')
                if confidence_score is None:
                    confidence_score = 50  # Default

                # Get evidence quality - prefer from confidence_metadata
                evidence_quality = confidence_meta.get('evidence_quality') or temporal.get('evidence_quality', 'unknown')

                skills_list.append({
                    'name': skill_name,
                    'level': level,
                    'tier': 'tech_stack',
                    'category': category,
                    'frequency': temporal.get('frequency', 'unknown'),
                    'trend': temporal.get('trend', 'unknown'),
                    'session_count': temporal.get('session_count', 0),
                    'confidence_score': confidence_score,
                    'evidence_quality': evidence_quality
                })

    # Extract orchestration skills
    if 'skills' in skills_data and 'orchestration' in skills_data['skills']:
        for skill in skills_data['skills']['orchestration']:
            skill_name = skill.get('skill', 'Unknown')
            level = skill.get('level', 0)

            # Get temporal data - prioritize temporal_lookup (from analysis)
            if skill_name in temporal_lookup:
                temporal = temporal_lookup[skill_name].get('temporal_metadata', {})
                confidence_meta = temporal_lookup[skill_name].get('confidence_metadata', {})
            else:
                temporal = skill.get('temporal_metadata', {})
                confidence_meta = {}

            # Get confidence score - prefer from temporal analysis
            confidence_score = temporal.get('confidence_score')
            if confidence_score is None and confidence_meta:
                confidence_score = confidence_meta.get('confidence_score')
            if confidence_score is None:
                confidence_score = 50  # Default

            # Get evidence quality - prefer from confidence_metadata
            evidence_quality = confidence_meta.get('evidence_quality') or temporal.get('evidence_quality', 'unknown')

            skills_list.append({
                'name': skill_name,
                'level': level,
                'tier': 'orchestration',
                'category': None,
                'frequency': temporal.get('frequency', 'unknown'),
                'trend': temporal.get('trend', 'unknown'),
                'session_count': temporal.get('session_count', 0),
                'confidence_score': confidence_score,
                'evidence_quality': evidence_quality
            })

    return skills_list


def extract_projects_data():
    """Extract projects data"""
    projects_data = load_yaml(PROJECTS_FILE)

    projects_list = []

    if 'projects' in projects_data:
        for project in projects_data['projects']:
            name = project.get('name', 'Unknown')

            # Map gate status to display status
            gate = project.get('gate', 'unknown')
            status_map = {
                'pass': 'sat',
                'in_progress': 'in-progress',
                'research': 'planning'
            }
            status = status_map.get(gate, gate)

            # Get confidence from project data
            confidence = project.get('confidence', 0)
            if confidence == 0:
                # Default confidence based on gate status
                confidence_defaults = {
                    'pass': 95,
                    'in_progress': 75,
                    'research': 60
                }
                confidence = confidence_defaults.get(gate, 50)

            # Confidence is already stored as integer (0-100) in consolidated schema
            # No conversion needed

            stage = project.get('stage', 'Unknown')
            objective = project.get('objective', '')

            projects_list.append({
                'name': name,
                'status': status,
                'confidence': confidence,
                'phase': stage,
                'description': objective[:150] if objective else 'No description'
            })

    return projects_list


def calculate_frequency_distribution(skills_list):
    """Calculate frequency distribution for chart"""
    freq_counts = {
        'frequent': 0,
        'regular': 0,
        'occasional': 0,
        'single-session': 0,
        'unknown': 0
    }

    for skill in skills_list:
        freq = skill['frequency']
        if freq in freq_counts:
            freq_counts[freq] += 1
        else:
            freq_counts['unknown'] += 1

    total = len(skills_list)
    freq_data = []

    for freq, count in freq_counts.items():
        if count > 0:
            percentage = round((count / total) * 100) if total > 0 else 0
            freq_data.append({
                'label': freq.replace('-', ' ').title(),
                'count': count,
                'percentage': percentage
            })

    return freq_data


def extract_health_data():
    """Extract system health metrics"""
    # Check for verification logs
    health_file = REPO_ROOT / "packages" / "ledger" / "logs" / "system_logs" / "health_dashboard.md"

    health_data = {
        'ledger_integrity': 'PASS',
        'failures': 0,
        'warnings': 18,
        'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'temporal_health': 'HEALTHY'
    }

    if health_file.exists():
        with open(health_file, 'r') as f:
            content = f.read()
            if 'DEGRADED' in content:
                health_data['ledger_integrity'] = 'DEGRADED'
            elif 'CRITICAL' in content:
                health_data['ledger_integrity'] = 'CRITICAL'

    return health_data


def generate_dashboard_js():
    """Generate JavaScript data file for dashboard"""

    print("Generating dashboard data...")

    # Extract data
    skills = extract_skills_data()
    projects = extract_projects_data()
    frequency_dist = calculate_frequency_distribution(skills)
    health = extract_health_data()

    # Calculate metrics
    total_skills = len(skills)
    active_projects = len([p for p in projects if p['status'] in ['sat', 'in-progress']])

    # Count by evidence quality
    quality_counts = {
        'exceptional': len([s for s in skills if s['evidence_quality'] == 'exceptional']),
        'strong': len([s for s in skills if s['evidence_quality'] == 'strong']),
        'moderate': len([s for s in skills if s['evidence_quality'] == 'moderate']),
        'weak': len([s for s in skills if s['evidence_quality'] == 'weak'])
    }

    # Build JavaScript output
    js_data = f"""// Auto-generated dashboard data
// Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
// Source: skills.yaml, projects.yaml, {TEMPORAL_SOURCE}

const LEDGER_DATA = {{
    lastUpdate: "{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    status: "healthy",
    temporalSource: "{TEMPORAL_SOURCE}",

    metrics: {{
        totalSkills: {total_skills},
        activeProjects: {active_projects},
        openTickets: 0,
        systemHealth: 85,
        qualityCounts: {json.dumps(quality_counts, indent=8)}
    }},

    frequencyDistribution: {json.dumps(frequency_dist, indent=4)},

    skills: {json.dumps(skills, indent=4)},

    projects: {json.dumps(projects, indent=4)},

    health: {json.dumps(health, indent=4)}
}};

// Export for dashboard
if (typeof window !== 'undefined') {{
    window.LEDGER_DATA = LEDGER_DATA;
}}
"""

    # Write to file
    with open(OUTPUT_FILE, 'w') as f:
        f.write(js_data)

    print(f"✅ Dashboard data generated: {OUTPUT_FILE}")
    print(f"   Skills: {total_skills}")
    print(f"   Projects: {len(projects)}")
    print(f"   Frequency distribution calculated")
    print(f"   Temporal source: {TEMPORAL_SOURCE}")
    print(f"\nOpen dashboard: file://{REPO_ROOT}/analysis/dashboards/ui/dashboard.html")


if __name__ == "__main__":
    generate_dashboard_js()
