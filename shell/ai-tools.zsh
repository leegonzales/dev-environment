# ai-tools.zsh — AI development tool aliases and PATH config
# Add to .zshrc: source ~/Projects/leegonzales/dev-environment/shell/ai-tools.zsh

# --- PATH additions ---

# Go (Homebrew)
export GOROOT=/opt/homebrew/opt/go/libexec
export GOPATH=$HOME/go
export PATH=$GOPATH/bin:$GOROOT/bin:$HOME/.local/bin:$PATH

# Rust (rustup via Homebrew)
export PATH="/opt/homebrew/opt/rustup/bin:$PATH"

# Bun
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"

# --- Aliases ---

# Python
alias python=python3

# Fabric (AI patterns)
alias fabric="$HOME/go/bin/fabric"

# Claude sandbox (Docker-based)
alias sandbox="~/Projects/claude-sandboxes/scripts/sandbox.sh"

# Claude Code agent teams (tmux split pane)
alias claude-team='tmux new-session -s claude-team "claude --teammate-mode tmux"'

# VLC CLI
alias vlc="/Applications/VLC.app/Contents/MacOS/VLC"

# Google Workspace CLI — multi-org aliases
alias gws-difflab='GOOGLE_WORKSPACE_CLI_CONFIG_DIR=~/.config/gws-difflab gws'
alias gws-catalyst='GOOGLE_WORKSPACE_CLI_CONFIG_DIR=~/.config/gws-catalyst gws'
alias gws-personal='GOOGLE_WORKSPACE_CLI_CONFIG_DIR=~/.config/gws-personal gws'

# --- API Keys (load from secure env files) ---
# NOTE: Set these in ~/.config/claude-env/ — never commit actual keys

if [[ -f ~/.config/claude-env/gemini.env ]]; then
    source ~/.config/claude-env/gemini.env
    export GEMINI_API_KEY
    export GOOGLE_API_KEY="$GEMINI_API_KEY"
fi
