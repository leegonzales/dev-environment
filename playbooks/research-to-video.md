# Research to Video — Full Production Pipeline

## What It Does

End-to-end pipeline: research a topic, produce a structured brief, write a narration script with graphic markers, generate images, synthesize audio, and render a final video with timeline.

## Prerequisites

- Claude Code
- `research-brief` skill
- `write-script` skill
- `render-video` skill
- Veo MCP server (for video generation) or image generation MCP
- `claude-speak` daemon running (for audio synthesis)
- `ffmpeg` installed (`brew install ffmpeg`)

## Skill Chain

1. **`research-brief`** → Structured brief with claims registry, stories, and emotional anchors
2. **`write-script`** → 4-phase pipeline: Architecture → Drafting → Multi-Model Review → Final polish. Produces narration script with `[GRAPHIC: description]` markers
3. **`render-video`** → Takes script, generates images for each `[GRAPHIC:]` marker, synthesizes audio from narration text, builds timeline, renders MP4

## How to Run

### Full pipeline
```
"Research [topic] and produce a video"
```

### Step by step
```
1. "Research [topic] and produce a brief"
2. "Write a video script from this brief"
3. "Render this script into a video"
```

### Just the script (no video)
```
"Research [topic] and write a video script — don't render"
```

## Artifact Flow

```
Topic / question
  │
  ▼ research-brief
Research brief (markdown)
  ├── Claims registry (sourced facts)
  ├── Story candidates (narrative hooks)
  └── Emotional anchors (engagement points)
  │
  ▼ write-script
Narration script (markdown)
  ├── Narration text (what the speaker says)
  ├── [GRAPHIC: ...] markers (visual cues)
  └── Timing notes
  │
  ▼ render-video
Final video (MP4)
  ├── Generated images (one per GRAPHIC marker)
  ├── Synthesized audio (from narration text)
  ├── Timeline (image + audio sync)
  └── Output: ./output/video-YYYY-MM-DD.mp4
```

## Tips

- The research brief phase spawns parallel search agents — takes 2-3 minutes
- write-script's multi-model review uses Codex/Gemini for cross-validation
- render-video needs ffmpeg for final compositing
- For quick iterations, skip research and feed a brief directly to write-script
- Video resolution defaults to 1080p; override with `--resolution 720p` for faster renders
