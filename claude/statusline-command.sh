#!/bin/bash

# Claude Code status line — P10k-style with git, python env, and time
# Install: copy to ~/.claude/statusline-command.sh

# Read the JSON input from stdin
input=$(cat)

# Extract data from JSON
current_dir=$(echo "$input" | jq -r '.workspace.current_dir')
model_name=$(echo "$input" | jq -r '.model.display_name')
output_style=$(echo "$input" | jq -r '.output_style.name')

# Get git info if in a git repo (skip optional locks for performance)
git_info=""
if git -C "$current_dir" rev-parse --git-dir > /dev/null 2>&1; then
    branch=$(git -C "$current_dir" branch --show-current 2>/dev/null || echo "detached")

    # Check for changes (skip optional locks)
    if [[ -n $(git -C "$current_dir" -c core.useBuiltinFSMonitor=false status --porcelain 2>/dev/null) ]]; then
        status="✗"
    else
        status="✓"
    fi

    git_info=" $(printf '\033[38;5;220m') ${branch} ${status}$(printf '\033[0m')"
fi

# Get shortened directory (replace home with ~)
short_dir="${current_dir/#$HOME/~}"

# Get username and hostname
user=$(whoami)
host=$(hostname -s)

# Detect Python virtual environment
python_env=""
if [[ -n "$VIRTUAL_ENV" ]]; then
    venv_name=$(basename "$VIRTUAL_ENV")
    python_env=" $(printf '\033[38;5;148m') ${venv_name}$(printf '\033[0m')"
elif [[ -n "$CONDA_DEFAULT_ENV" ]] && [[ "$CONDA_DEFAULT_ENV" != "base" ]]; then
    python_env=" $(printf '\033[38;5;148m') ${CONDA_DEFAULT_ENV}$(printf '\033[0m')"
fi

# Get current time (24h format, matching P10k)
current_time=$(date +%H:%M:%S)

# Build status line with colors matching P10k rainbow theme
# Color scheme: cyan for directory, yellow for git, green for python, gray for user@host, dim for time
printf "$(printf '\033[38;5;51m')${short_dir}$(printf '\033[0m')${git_info}${python_env} $(printf '\033[38;5;244m')${user}@${host}$(printf '\033[0m') $(printf '\033[38;5;238m')${current_time}$(printf '\033[0m')"
