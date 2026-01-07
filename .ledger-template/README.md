# Ledger Template

This directory contains example templates for setting up your personal operator ledger.

## Structure

```
.ledger-template/
├── operator/           # Personal identity and preferences
│   ├── identity.yaml.example
│   └── preferences.yaml.example
├── skills/             # Skill tracking
│   └── active.yaml.example
├── projects/           # Project tracking
│   └── repos.yaml.example
├── decisions/          # Technical decisions
│   └── technical.yaml.example
├── activity/           # Activity logs (auto-generated)
└── README.md
```

## Setup

To initialize your personal ledger:

1. Set the `OPERATOR_LEDGER_DIR` environment variable:
   ```bash
   export OPERATOR_LEDGER_DIR="$HOME/.operator/ledger"
   ```

2. Run the setup script:
   ```bash
   bash scripts/setup_ledger.sh
   ```

3. Customize the generated files with your personal information.

## Environment Variables

- `OPERATOR_LEDGER_DIR`: Directory for your personal ledger data (default: `./ledger`)
- `OPERATOR_DATA_DIR`: Directory for transcript data (default: `~/.claude`)

## Privacy

The ledger directory should **never** be committed to a public repository.
It contains personal information including:
- Identity and contact details
- Financial information
- Personal notes and preferences
- Private project details

Always keep your ledger in a separate, private location using `OPERATOR_LEDGER_DIR`.
