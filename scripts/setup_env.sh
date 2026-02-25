#!/usr/bin/env bash
# setup_env.sh — MetaScreener environment setup helper
set -euo pipefail

echo "=== MetaScreener Environment Setup ==="
echo ""
echo "This script helps you configure the OpenRouter API key"
echo "needed for running validation experiments with real LLM inference."
echo ""

# Check if already set
if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
    echo "OPENROUTER_API_KEY is already set."
    echo "Current value: ${OPENROUTER_API_KEY:0:8}..."
    read -r -p "Do you want to update it? (y/N): " update
    if [[ "$update" != "y" && "$update" != "Y" ]]; then
        echo "Keeping existing key."
        exit 0
    fi
fi

echo "Enter your OpenRouter API key (from https://openrouter.ai/keys):"
read -r api_key

if [[ -z "$api_key" ]]; then
    echo "Error: No API key provided."
    exit 1
fi

# Detect shell
SHELL_RC=""
if [[ -f "$HOME/.zshrc" ]]; then
    SHELL_RC="$HOME/.zshrc"
elif [[ -f "$HOME/.bashrc" ]]; then
    SHELL_RC="$HOME/.bashrc"
else
    SHELL_RC="$HOME/.profile"
fi

echo ""
echo "export OPENROUTER_API_KEY=\"$api_key\"" >> "$SHELL_RC"
echo "API key saved to $SHELL_RC"
echo ""
echo "To activate now, run:"
echo "  source $SHELL_RC"
echo ""
echo "Or for this session only:"
echo "  export OPENROUTER_API_KEY=\"$api_key\""
