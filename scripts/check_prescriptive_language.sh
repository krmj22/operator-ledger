#!/bin/bash
# Check ledger files for prescriptive keywords

PRESCRIPTIVE_KEYWORDS=("explicitly_avoid" "always" "never" "must" "forbidden")
LEDGER_FILES="./ledger/projects/*.yaml ./ledger/operator/*.yaml"

for keyword in "${PRESCRIPTIVE_KEYWORDS[@]}"; do
  matches=$(grep -n -i "$keyword" $LEDGER_FILES 2>/dev/null)
  if [ ! -z "$matches" ]; then
    echo "❌ Prescriptive language detected: '$keyword'"
    echo "$matches"
    exit 1
  fi
done

echo "✓ No prescriptive language detected"
exit 0
