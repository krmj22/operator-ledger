#!/usr/bin/env python3
"""Basic schema validation for ledger patterns."""

import yaml
import sys
from pathlib import Path

REQUIRED_PATTERN_FIELDS = ['pattern', 'instances', 'last_updated']

def validate_pattern(pattern_data, file_path, pattern_name):
    """Check pattern has required fields."""
    errors = []

    for field in REQUIRED_PATTERN_FIELDS:
        if field not in pattern_data:
            errors.append(f"{file_path}: Pattern '{pattern_name}' missing '{field}'")

    if 'instances' in pattern_data:
        if len(pattern_data['instances']) < 2:
            errors.append(f"{file_path}: Pattern '{pattern_name}' has <2 instances")

    return errors

def main():
    ledger_files = Path('./ledger').rglob('*.yaml')
    all_errors = []

    for yaml_file in ledger_files:
        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)

            # Check for patterns in data
            if isinstance(data, dict) and 'observed_patterns' in data:
                patterns = data['observed_patterns']
                for name, pattern in patterns.items():
                    errors = validate_pattern(pattern, yaml_file, name)
                    all_errors.extend(errors)

        except Exception as e:
            all_errors.append(f"{yaml_file}: Parse error - {e}")

    if all_errors:
        print("❌ Schema validation failed:")
        for error in all_errors:
            print(f"  {error}")
        sys.exit(1)

    print("✓ Schema validation passed")
    sys.exit(0)

if __name__ == '__main__':
    main()
