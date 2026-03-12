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

# ── claude-guardrails ──────────────────────────────────────────────────

if ! command -v claude-guardrails &>/dev/null && [[ ! -f "$HOME/.claude/guardrails/claude-guardrails" ]]; then
    info "Installing claude-guardrails..."
    if command -v pipx &>/dev/null; then
        pipx install claude-guardrails 2>/dev/null || warn "claude-guardrails install via pipx failed — install manually"
    else
        pip3 install claude-guardrails 2>/dev/null || warn "claude-guardrails install failed — install manually"
    fi
fi
ok "claude-guardrails ready"

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

# ── AISkills ───────────────────────────────────────────────────────────

SKILLS_REPO="$HOME/Projects/leegonzales/AISkills"
if [[ ! -d "$SKILLS_REPO" ]]; then
    info "Cloning AISkills..."
    mkdir -p "$HOME/Projects/leegonzales"
    git clone git@github.com:leegonzales/AISkills.git "$SKILLS_REPO"
fi

# Symlink skills to ~/.claude/skills/
if [[ ! -L "$HOME/.claude/skills" ]] && [[ ! -d "$HOME/.claude/skills" ]]; then
    ln -s "$SKILLS_REPO" "$HOME/.claude/skills"
    ok "Skills symlinked to ~/.claude/skills/"
elif [[ -L "$HOME/.claude/skills" ]]; then
    ok "Skills symlink already exists"
else
    warn "~/.claude/skills/ exists as directory — skipping symlink (manual merge needed)"
fi

# ── claude-sandboxes ───────────────────────────────────────────────────

SANDBOX_REPO="$HOME/Projects/claude-sandboxes"
if [[ ! -d "$SANDBOX_REPO" ]]; then
    info "Cloning claude-sandboxes..."
    git clone git@github.com:leegonzales/claude-sandboxes.git "$SANDBOX_REPO"
fi
ok "claude-sandboxes ready"

# ── claude-speak ───────────────────────────────────────────────────────

SPEAK_REPO="$HOME/Projects/claude-speak"
if [[ ! -d "$SPEAK_REPO" ]]; then
    info "Cloning claude-speak..."
    git clone git@github.com:leegonzales/claude-speak.git "$SPEAK_REPO"
    if [[ -f "$SPEAK_REPO/install.sh" ]]; then
        info "Running claude-speak installer..."
        cd "$SPEAK_REPO" && bash install.sh
        cd "$SCRIPT_DIR"
    fi
fi
ok "claude-speak ready"

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
echo "  6. Reload shell:"
echo "     source ~/.zshrc"
echo ""
echo "  7. Verify:"
echo "     claude --version && cass health && bd --version"
echo "     ls ~/.claude/skills/ | wc -l  # Should be 30+"
echo ""
