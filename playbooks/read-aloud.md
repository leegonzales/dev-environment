# Read-Aloud — HTML Narration Builders

## What It Does

Transforms written essays into spoken-word presentations, producing both audio files and standalone HTML players. The `essay-to-speech` skill converts prose into a talk track, then the `claude-speak` skill renders audio.

## Prerequisites

- `claude-speak` daemon running (see [claude-speak.md](claude-speak.md))
- `essay-to-speech` skill installed
- `claude-speak` skill installed

## Skill Chain

1. **`essay-to-speech`** — Converts essay text into a spoken-word talk track with natural pacing, transitions, and audience cues
2. **`claude-speak`** — Renders the talk track to audio via Kokoro TTS
3. (Optional) **`slide-builder`** — Generates companion slides if visual presentation is needed

## How to Run

### Full pipeline
```
"Convert this essay to a read-aloud presentation"
```
Claude Code will:
1. Invoke `essay-to-speech` to create the talk track
2. Invoke `claude-speak` to render audio
3. Produce a standalone HTML file with embedded audio player

### Just the talk track (no audio)
```
"Create a talk track from this essay — don't render audio"
```

## Artifact Flow

```
Input essay (markdown or text)
  │
  ▼ essay-to-speech
Talk track (markdown with speaker notes)
  │
  ▼ claude-speak
Audio file (.wav or .mp3)
  │
  ▼ HTML builder
Standalone HTML with embedded audio player
  └── Self-contained, shareable, no server needed
```

## Tips

- The talk track preserves the essay's voice but adapts for spoken delivery
- HTML output is a single file with inline base64 audio — works offline
- For long essays, the skill automatically chunks into segments
- Pair with `slide-builder` for a full presentation package
