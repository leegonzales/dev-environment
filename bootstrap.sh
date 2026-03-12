#!/bin/bash
set -euo pipefail

# bootstrap.sh — Idempotent setup for Lee's Claude Code dev environment
# Usage: ./bootstrap.sh
# Safe to re-run — checks before installing.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USERNAME="$(whoami)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }

# ── Prerequisites ──────────────────────────────────────────────────────

info "Checking prerequisites..."

[[ "$(uname)" == "Darwin" ]] || fail "macOS required"
[[ "$(uname -m)" == "arm64" ]] || warn "Not Apple Silicon — some tools (claude-speak) require M-series"

if ! command -v brew &>/dev/null; then
    info "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi
ok "Homebrew ready"

# ── Brew Bundle ────────────────────────────────────────────────────────

info "Installing Homebrew packages..."
brew bundle --file="$SCRIPT_DIR/Brewfile" --no-lock
ok "Brew packages installed"

# ── Rust (via rustup) ──────────────────────────────────────────────────

if ! command -v rustc &>/dev/null; then
    info "Installing Rust stable toolchain..."
    rustup-init -y --default-toolchain stable
    source "$HOME/.cargo/env"
fi
ok "Rust ready ($(rustc --version 2>/dev/null || echo 'pending shell reload'))"

# ── npm globals ────────────────────────────────────────────────────────

info "Installing npm global packages..."
npm_globals=(
    "@anthropic-ai/claude-code"
    "@google/generative-ai-cli"
    "@anthropic-ai/codex"
    "typescript"
    "netlify-cli"
    "wrangler"
    "md-to-pdf"
)
for pkg in "${npm_globals[@]}"; do
    if ! npm list -g "$pkg" &>/dev/null; then
        npm install -g "$pkg" || warn "Failed to install $pkg"
    fi
done
ok "npm globals installed"

# ── fabric (Go) ────────────────────────────────────────────────────────

if ! command -v fabric &>/dev/null && [[ ! -f "$HOME/go/bin/fabric" ]]; then
    info "Installing fabric..."
    go install github.com/danielmiessler/fabric@latest || warn "fabric install failed"
fi
ok "fabric ready"

# ── Rust nightly (needed for CASS and some deps) ──────────────────────

if command -v rustup &>/dev/null; then
    if ! rustup toolchain list | grep -q nightly; then
        info "Installing Rust nightly toolchain..."
        rustup toolchain install nightly
    fi
    ok "Rust nightly ready"
fi

# ── Claude Code config ─────────────────────────────────────────────────

info "Installing Claude Code configuration..."
mkdir -p ~/.claude/guardrails/patterns

# Copy config files (don't overwrite if they exist and differ)
copy_if_missing() {
    local src="$1" dst="$2"
    if [[ ! -f "$dst" ]]; then
        cp "$src" "$dst"
        info "  Installed $dst"
    else
        ok "  Already exists: $dst"
    fi
}

copy_if_missing "$SCRIPT_DIR/claude/settings.json" "$HOME/.claude/settings.json"
copy_if_missing "$SCRIPT_DIR/claude/settings.local.json" "$HOME/.claude/settings.local.json"
copy_if_missing "$SCRIPT_DIR/claude/statusline-command.sh" "$HOME/.claude/statusline-command.sh"
copy_if_missing "$SCRIPT_DIR/claude/CLAUDE.md" "$HOME/.claude/CLAUDE.md"
copy_if_missing "$SCRIPT_DIR/claude/guardrails/config.toml" "$HOME/.claude/guardrails/config.toml"
copy_if_missing "$SCRIPT_DIR/claude/guardrails/patterns/block.txt" "$HOME/.claude/guardrails/patterns/block.txt"
copy_if_missing "$SCRIPT_DIR/claude/guardrails/patterns/secrets.txt" "$HOME/.claude/guardrails/patterns/secrets.txt"
copy_if_missing "$SCRIPT_DIR/claude/guardrails/patterns/allow.txt" "$HOME/.claude/guardrails/patterns/allow.txt"

chmod +x "$HOME/.claude/statusline-command.sh"
ok "Claude Code config installed"

# ── Launchd plists ─────────────────────────────────────────────────────

info "Installing launchd daemons..."
LAUNCH_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_DIR"

for plist in "$SCRIPT_DIR"/launchd/*.plist; do
    filename="$(basename "$plist")"
    dst="$LAUNCH_DIR/$filename"
    if [[ ! -f "$dst" ]]; then
        sed "s/__USERNAME__/$USERNAME/g" "$plist" > "$dst"
        launchctl load "$dst" 2>/dev/null || warn "Failed to load $filename"
        info "  Installed and loaded $filename"
    else
        ok "  Already exists: $filename"
    fi
done
ok "Launchd daemons installed"

# ── Helper: clone repo if missing ──────────────────────────────────────

clone_repo() {
    local remote="$1" dest="$2" label="$3"
    if [[ ! -d "$dest" ]]; then
        info "Cloning $label..."
        mkdir -p "$(dirname "$dest")"
        git clone "$remote" "$dest" || { warn "Failed to clone $label"; return 1; }
    fi
    ok "$label ready"
}

# ── Tier 1: Core AI Agent Infrastructure ──────────────────────────────

info "=== Tier 1: Core AI Agent Infrastructure ==="

# AISkills
clone_repo "git@github.com:leegonzales/AISkills.git" \
    "$HOME/Projects/leegonzales/AISkills" "AISkills"

# Symlink skills to ~/.claude/skills/
if [[ ! -L "$HOME/.claude/skills" ]] && [[ ! -d "$HOME/.claude/skills" ]]; then
    ln -s "$HOME/Projects/leegonzales/AISkills" "$HOME/.claude/skills"
    ok "Skills symlinked to ~/.claude/skills/"
elif [[ -L "$HOME/.claude/skills" ]]; then
    ok "Skills symlink already exists"
else
    warn "~/.claude/skills/ exists as directory — skipping symlink (manual merge needed)"
fi

# claude-sandboxes
clone_repo "git@github.com:leegonzales/claude-sandboxes.git" \
    "$HOME/Projects/claude-sandboxes" "claude-sandboxes"

# claude-speak (with install script)
SPEAK_REPO="$HOME/Projects/claude-speak"
if [[ ! -d "$SPEAK_REPO" ]]; then
    clone_repo "git@github.com:leegonzales/claude-speak.git" \
        "$SPEAK_REPO" "claude-speak"
    if [[ -f "$SPEAK_REPO/install.sh" ]]; then
        info "Running claude-speak installer..."
        cd "$SPEAK_REPO" && bash install.sh
        cd "$SCRIPT_DIR"
    fi
else
    ok "claude-speak ready"
fi

# claude-guardrails (Rust binary — build from source)
GUARDRAILS_REPO="$HOME/Projects/leegonzales/claude-guardrails"
clone_repo "git@github.com:leegonzales/claude-guardrails.git" \
    "$GUARDRAILS_REPO" "claude-guardrails"
if [[ -d "$GUARDRAILS_REPO" ]] && ! command -v claude-guardrails &>/dev/null && [[ ! -f "$HOME/.claude/guardrails/claude-guardrails" ]]; then
    info "Building claude-guardrails from source..."
    cd "$GUARDRAILS_REPO"
    if [[ -f "Cargo.toml" ]]; then
        cargo build --release 2>/dev/null && \
            cp target/release/claude-guardrails "$HOME/.claude/guardrails/claude-guardrails" && \
            ok "claude-guardrails binary installed" || \
            warn "claude-guardrails build failed — install manually"
    elif [[ -f "install.sh" ]]; then
        bash install.sh || warn "claude-guardrails install.sh failed"
    else
        warn "claude-guardrails: no Cargo.toml or install.sh found — install manually"
    fi
    cd "$SCRIPT_DIR"
fi

# claude-allowlist
clone_repo "git@github.com:leegonzales/claude-allowlist.git" \
    "$HOME/Projects/leegonzales/claude-allowlist" "claude-allowlist"

# agent-orchestra
clone_repo "git@github.com:leegonzales/agent-orchestra.git" \
    "$HOME/Projects/leegonzales/agent-orchestra" "agent-orchestra"

# ── Tier 2: CASS + Dependencies (build from source) ──────────────────

info "=== Tier 2: CASS + Dependencies ==="

# CASS dependency repos (must be cloned before CASS for local path resolution)
clone_repo "git@github.com:Dicklesworthstone/frankensearch.git" \
    "$HOME/Projects/leegonzales/frankensearch" "frankensearch"

clone_repo "git@github.com:Dicklesworthstone/frankentui.git" \
    "$HOME/Projects/leegonzales/frankentui" "frankentui (ftui)"

clone_repo "git@github.com:Dicklesworthstone/franken_agent_detection.git" \
    "$HOME/Projects/leegonzales/franken_agent_detection" "franken_agent_detection"

clone_repo "git@github.com:Dicklesworthstone/asupersync.git" \
    "$HOME/Projects/leegonzales/asupersync" "asupersync"

clone_repo "git@github.com:Dicklesworthstone/toon_rust.git" \
    "$HOME/Projects/leegonzales/toon_rust" "toon_rust"

# CASS itself (Lee's fork — includes cass-monitor work)
CASS_REPO="$HOME/Projects/leegonzales/cass"
clone_repo "git@github.com:leegonzales/cass.git" \
    "$CASS_REPO" "CASS (leegonzales/cass)"

# Set up upstream remote for syncing with Dicklesworthstone's repo
if [[ -d "$CASS_REPO" ]]; then
    cd "$CASS_REPO"
    if ! git remote | grep -q upstream; then
        git remote add upstream https://github.com/Dicklesworthstone/coding_agent_session_search.git
        ok "CASS upstream remote added"
    fi
    cd "$SCRIPT_DIR"
fi

if [[ -d "$CASS_REPO" ]]; then
    info "Building CASS from source..."
    cd "$CASS_REPO"
    # CASS requires nightly Rust and local path deps at ../frankentui, ../frankensearch, etc.
    if cargo +nightly build --release 2>/dev/null; then
        # Install binary to ~/.local/bin/
        mkdir -p "$HOME/.local/bin"
        cp target/release/cass "$HOME/.local/bin/cass" 2>/dev/null && \
            ok "CASS binary installed to ~/.local/bin/cass" || \
            warn "CASS binary copy failed"
    else
        warn "CASS build failed — may need nightly Rust or dependency fixes. Falling back to brew version."
        info "  Brew CASS is still available as a fallback (installed via Brewfile)"
    fi
    cd "$SCRIPT_DIR"
fi

# ── Tier 3: MCP Servers ──────────────────────────────────────────────

info "=== Tier 3: MCP Servers ==="

# Google Workspace MCP
GWS_MCP="$HOME/Projects/leegonzales/google-workspace-mcp"
clone_repo "git@github.com:leegonzales/google-workspace-mcp.git" \
    "$GWS_MCP" "google-workspace-mcp"
if [[ -d "$GWS_MCP" ]] && [[ -f "$GWS_MCP/package.json" ]]; then
    cd "$GWS_MCP" && npm install --silent 2>/dev/null && ok "google-workspace-mcp deps installed" || warn "npm install failed for google-workspace-mcp"
    cd "$SCRIPT_DIR"
fi

# MCP Agent Mail
AGENT_MAIL="$HOME/Projects/mcp_agent_mail"
clone_repo "git@github.com:leegonzales/mcp_agent_mail.git" \
    "$AGENT_MAIL" "mcp-agent-mail"
if [[ -d "$AGENT_MAIL" ]] && [[ -f "$AGENT_MAIL/requirements.txt" ]]; then
    cd "$AGENT_MAIL"
    if [[ ! -d ".venv" ]]; then
        python3 -m venv .venv && .venv/bin/pip install -r requirements.txt --quiet 2>/dev/null && \
            ok "mcp-agent-mail venv ready" || warn "mcp-agent-mail venv setup failed"
    else
        ok "mcp-agent-mail venv already exists"
    fi
    cd "$SCRIPT_DIR"
fi

# HeyGen MCP (optional)
clone_repo "git@github.com:leegonzales/heygen-mcp.git" \
    "$HOME/Projects/leegonzales/heygen-mcp-fork" "heygen-mcp (optional)"

# ── Tier 4: Reference ────────────────────────────────────────────────

info "=== Tier 4: Reference ==="

clone_repo "https://github.com/affaan-m/everything-claude-code.git" \
    "$HOME/Projects/leegonzales/everything-claude-code" "everything-claude-code (reference)"

# ── Shell config ───────────────────────────────────────────────────────

SOURCE_LINE="source $SCRIPT_DIR/shell/ai-tools.zsh"
if ! grep -qF "$SOURCE_LINE" "$HOME/.zshrc" 2>/dev/null; then
    echo "" >> "$HOME/.zshrc"
    echo "# AI development tools (dev-environment)" >> "$HOME/.zshrc"
    echo "$SOURCE_LINE" >> "$HOME/.zshrc"
    ok "Added ai-tools.zsh source to .zshrc"
else
    ok "ai-tools.zsh already sourced in .zshrc"
fi

# ── GWS config dirs ───────────────────────────────────────────────────

mkdir -p "$HOME/.config/gws-difflab"
mkdir -p "$HOME/.config/gws-catalyst"
mkdir -p "$HOME/.config/gws-personal"
mkdir -p "$HOME/.config/claude-env"
ok "GWS and env config directories created"

# ── .gitignore ─────────────────────────────────────────────────────────

info "Ensuring global .gitignore..."
GLOBAL_GITIGNORE="$HOME/.gitignore_global"
if [[ ! -f "$GLOBAL_GITIGNORE" ]]; then
    cat > "$GLOBAL_GITIGNORE" << 'EOF'
.DS_Store
.vscode/
.idea/
*.swp
*.swo
*~
.env
.env.local
EOF
    git config --global core.excludesfile "$GLOBAL_GITIGNORE"
    ok "Created global .gitignore"
else
    ok "Global .gitignore already exists"
fi

# ── Summary ────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Bootstrap complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Manual steps remaining:${NC}"
echo ""
echo "  1. API Keys — create ~/.config/claude-env/gemini.env:"
echo '     GEMINI_API_KEY="your-key-here"'
echo ""
echo "  2. Set ANTHROPIC_API_KEY in your environment"
echo ""
echo "  3. Google Workspace CLI — authenticate each org:"
echo "     gws-difflab auth login"
echo "     gws-catalyst auth login"
echo "     gws-personal auth login"
echo ""
echo "  4. Claude Code plugins — install from the Claude Code UI:"
echo "     beads, frontend-design, pyright-lsp, superpowers,"
echo "     please-hold, rust-analyzer-lsp"
echo ""
echo "  5. Playwright browsers:"
echo "     npx playwright install"
echo ""
echo "  6. Configure MCP servers in Claude Code settings:"
echo "     - google-workspace-mcp (~/Projects/leegonzales/google-workspace-mcp)"
echo "     - mcp-agent-mail (~/Projects/mcp_agent_mail)"
echo "     - heygen-mcp (~/Projects/leegonzales/heygen-mcp-fork) [optional]"
echo ""
echo "  7. Reload shell:"
echo "     source ~/.zshrc"
echo ""
echo "  8. Verify:"
echo "     claude --version && cass health && bd --version"
echo "     ls ~/.claude/skills/ | wc -l  # Should be 30+"
echo "     which claude-guardrails       # Guardrails binary"
echo ""
echo -e "${BLUE}Repos cloned to ~/Projects/leegonzales/:${NC}"
echo "  AISkills, agent-orchestra, asupersync, cass,"
echo "  claude-allowlist, claude-guardrails, everything-claude-code,"
echo "  franken_agent_detection, frankensearch, frankentui,"
echo "  google-workspace-mcp, heygen-mcp-fork, toon_rust"
echo ""
echo -e "${BLUE}Repos cloned to ~/Projects/:${NC}"
echo "  claude-sandboxes, claude-speak, mcp_agent_mail"
echo ""
