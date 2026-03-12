# Claude Speak — TTS Daemon Pipeline

## What It Does

High-quality text-to-speech using Kokoro TTS on Apple Silicon. Runs as a persistent daemon so Claude Code can vocalize text instantly without startup latency.

## Prerequisites

- Apple Silicon Mac (M1/M2/M3/M4)
- `claude-speak` repo cloned with venv set up (`~/Projects/claude-speak/`)
- `espeak-ng` installed (`brew install espeak-ng`)
- launchd plist installed (handled by bootstrap.sh)

## Architecture

```
Claude Code (or user)
  │
  ▼
claude-speak-client "text to speak"     ← CLI client
  │
  ▼ (Unix socket)
claude_speak_daemon                      ← Persistent daemon process
  │
  ▼
Kokoro TTS (Apple Silicon MLX)          ← Neural voice synthesis
  │
  ▼
macOS audio output                      ← Plays through speakers
```

## Setup

Bootstrap handles cloning and daemon install. Manual setup:

```bash
git clone git@github.com:leegonzales/claude-speak.git ~/Projects/claude-speak
cd ~/Projects/claude-speak
bash install.sh                        # Creates venv, installs deps, downloads model
```

## How to Run

### From Claude Code (via skill)
Use the `claude-speak` skill: "speak this text aloud" or "read this paragraph".

### From command line
```bash
~/Projects/claude-speak/.venv/bin/claude-speak-client "Hello, this is a test."
~/Projects/claude-speak/.venv/bin/claude-speak-client --voice af_sarah "Different voice"
```

### Managing the daemon
```bash
launchctl list | grep claude-speak     # Check status
launchctl unload ~/Library/LaunchAgents/com.claude-speak.daemon.plist  # Stop
launchctl load ~/Library/LaunchAgents/com.claude-speak.daemon.plist    # Start
```

## Tips

- Daemon keeps the model loaded in memory — first utterance is fast
- Logs at `/tmp/claude-speak.log`
- If audio is choppy, check Activity Monitor for CPU contention
- Multiple voices available — check `claude-speak-client --list-voices`
- The daemon auto-restarts via launchd if it crashes
