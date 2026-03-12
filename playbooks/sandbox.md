# Sandbox — Docker Isolation System

## What It Does

Runs Claude Code sessions inside Docker containers with full filesystem isolation. Useful for untrusted code execution, destructive experiments, or testing bootstrap scripts without affecting the host.

## Prerequisites

- Docker Desktop installed and running (`brew install --cask docker`)
- `claude-sandboxes` repo cloned (`~/Projects/claude-sandboxes/`)
- `sandbox` alias in shell (set by `ai-tools.zsh`)

## Setup

The bootstrap script clones the repo and sets the alias. If manual:

```bash
git clone git@github.com:leegonzales/claude-sandboxes.git ~/Projects/claude-sandboxes
alias sandbox="~/Projects/claude-sandboxes/scripts/sandbox.sh"
```

## How to Run

### Quick sandbox (ephemeral)
```bash
sandbox                     # Start a new sandbox
sandbox --name my-experiment  # Named sandbox
sandbox --persist           # Keep container after exit
```

### With mounted directory
```bash
sandbox --mount ./my-project  # Mount local dir into container
```

### Claude Code inside sandbox
```bash
sandbox --claude            # Start sandbox with Claude Code available
```

## Artifact Flow

```
Host filesystem
  └── ~/Projects/claude-sandboxes/
       ├── scripts/sandbox.sh      # Entry point
       ├── Dockerfile              # Base image
       └── configs/                # Sandbox configurations
            ├── default.yml        # Standard sandbox
            ├── python.yml         # Python-focused
            └── node.yml           # Node-focused

Docker container (ephemeral by default)
  └── /workspace/                  # Mounted or empty
```

## Tips

- Sandboxes are ephemeral by default — everything is lost on exit unless `--persist` is used
- Use `--mount` to share files between host and container
- The sandbox has no access to your API keys unless you explicitly pass them
- Good for testing `bootstrap.sh` changes without affecting your real setup
- Network access is available by default; use `--no-network` for full isolation
