#!/usr/bin/env python3
"""One-time script to deduplicate ingestion_history.yaml"""

import yaml
from pathlib import Path

# Path to history file
history_file = Path("ledger/_meta/ingestion_history.yaml")

# Load current history
with open(history_file, 'r') as f:
    history = yaml.safe_load(f)

# Keep latest entry per session_id
unique = {}
for session in history.get('processed_sessions', []):
    sid = session['session_id']
    date = session.get('ingestion_date', '1970-01-01')

    if sid not in unique or date > unique[sid].get('ingestion_date', '1970-01-01'):
        unique[sid] = session

# Replace with deduplicated list
history['processed_sessions'] = list(unique.values())

# Save deduplicated history
with open(history_file, 'w') as f:
    yaml.dump(history, f, default_flow_style=False, sort_keys=False)

print(f"Deduplicated: {len(unique)} unique sessions")
