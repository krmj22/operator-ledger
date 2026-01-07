#!/bin/bash
# Setup Operator Ledger
# Initializes a new ledger directory from templates

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Find repo root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Operator Ledger Setup ==="
echo ""

# Determine ledger directory
if [ -n "${OPERATOR_LEDGER_DIR:-}" ]; then
    LEDGER_DIR="$OPERATOR_LEDGER_DIR"
    echo -e "${GREEN}Using OPERATOR_LEDGER_DIR:${NC} $LEDGER_DIR"
else
    LEDGER_DIR="$HOME/.operator/ledger"
    echo -e "${YELLOW}OPERATOR_LEDGER_DIR not set${NC}"
    echo -e "Using default: ${GREEN}$LEDGER_DIR${NC}"
    echo ""
    echo "To use a different location, set OPERATOR_LEDGER_DIR:"
    echo "  export OPERATOR_LEDGER_DIR=/path/to/your/ledger"
    echo ""
fi

# Check if ledger already exists
if [ -d "$LEDGER_DIR" ] && [ "$(ls -A "$LEDGER_DIR" 2>/dev/null)" ]; then
    echo -e "${YELLOW}Warning:${NC} Ledger directory already exists and is not empty: $LEDGER_DIR"
    read -p "Overwrite existing files? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled."
        exit 0
    fi
fi

# Create ledger directory structure
echo ""
echo "Creating ledger directory structure..."
mkdir -p "$LEDGER_DIR"/{operator,skills,projects,decisions,activity,logs}

# Copy templates
echo "Copying template files..."
TEMPLATE_DIR="$REPO_ROOT/.ledger-template"

# Copy operator templates
for template in "$TEMPLATE_DIR/operator"/*.example; do
    if [ -f "$template" ]; then
        filename=$(basename "$template" .example)
        cp "$template" "$LEDGER_DIR/operator/$filename"
        echo "  ✓ Created operator/$filename"
    fi
done

# Copy skills templates
for template in "$TEMPLATE_DIR/skills"/*.example; do
    if [ -f "$template" ]; then
        filename=$(basename "$template" .example)
        cp "$template" "$LEDGER_DIR/skills/$filename"
        echo "  ✓ Created skills/$filename"
    fi
done

# Copy projects templates
for template in "$TEMPLATE_DIR/projects"/*.example; do
    if [ -f "$template" ]; then
        filename=$(basename "$template" .example)
        cp "$template" "$LEDGER_DIR/projects/$filename"
        echo "  ✓ Created projects/$filename"
    fi
done

# Copy decisions templates
for template in "$TEMPLATE_DIR/decisions"/*.example; do
    if [ -f "$template" ]; then
        filename=$(basename "$template" .example)
        cp "$template" "$LEDGER_DIR/decisions/$filename"
        echo "  ✓ Created decisions/$filename"
    fi
done

# Copy root-level templates (skills.yaml, projects.yaml)
for template in "$TEMPLATE_DIR"/*.example; do
    if [ -f "$template" ]; then
        filename=$(basename "$template" .example)
        cp "$template" "$LEDGER_DIR/$filename"
        echo "  ✓ Created $filename"
    fi
done

# Copy README
if [ -f "$TEMPLATE_DIR/README.md" ]; then
    cp "$TEMPLATE_DIR/README.md" "$LEDGER_DIR/README.md"
    echo "  ✓ Created README.md"
fi

echo ""
echo -e "${GREEN}✓ Ledger setup complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Set environment variable in your shell profile:"
echo "     echo 'export OPERATOR_LEDGER_DIR=\"$LEDGER_DIR\"' >> ~/.bashrc"
echo "     (or ~/.zshrc for zsh)"
echo ""
echo "  2. Customize the template files with your information:"
echo "     - $LEDGER_DIR/operator/identity.yaml"
echo "     - $LEDGER_DIR/operator/preferences.yaml"
echo ""
echo "  3. Test the configuration:"
echo "     bash scripts/smoke_test.sh"
echo ""
echo -e "${YELLOW}Important:${NC} Keep your ledger directory private!"
echo "  Never commit personal ledger data to public repositories."
echo ""
