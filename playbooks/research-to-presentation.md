# Research to Presentation — Full Slide Deck Pipeline

## What It Does

Research a topic, produce an essay, convert to spoken-word delivery, generate slides, and output a presentation kit (PK) with speaker notes, slide images, and audio.

## Prerequisites

- Claude Code
- `research-to-essay` skill (or `research-brief` + manual essay)
- `essay-to-speech` skill
- `slide-builder` skill
- `claude-speak` daemon running (for audio)
- Image generation MCP (Nano Banana or similar)

## Skill Chain

1. **`research-to-essay`** → Research-driven essay with citations and thematic synthesis
2. **`essay-to-speech`** → Converts essay to spoken-word talk track with natural pacing
3. **`slide-builder`** → Transforms talk track into slide deck with multiple output formats
4. (Optional) **`claude-speak`** → Renders talk track audio for rehearsal or recording

## How to Run

### Full pipeline
```
"Research [topic] and build a presentation"
```

### Step by step
```
1. "Research [topic] and write an essay"
2. "Convert this essay to a talk track"
3. "Build slides from this talk track"
4. "Render the audio for rehearsal"
```

## Artifact Flow

```
Topic / question
  │
  ▼ research-to-essay
Essay (markdown with citations)
  │
  ▼ essay-to-speech
Talk track (markdown with speaker notes + timing)
  │
  ▼ slide-builder
Presentation kit
  ├── Slide images (PNG per slide)
  ├── Speaker notes (per slide)
  ├── Combined deck (HTML or PDF)
  └── Talk track with slide markers
  │
  ▼ claude-speak (optional)
Audio files
  ├── Per-slide audio segments
  └── Full talk audio
```

## Tips

- The essay phase uses parallel web search agents — best results with specific topics
- `essay-to-speech` preserves the essay's voice but adapts cadence for speaking
- `slide-builder` supports multiple visual styles (minimal, corporate, creative)
- For quick iterations, skip research and start from an existing essay
- The PK output is self-contained — share the folder and it has everything needed to present
