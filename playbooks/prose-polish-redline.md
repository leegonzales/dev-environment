# Prose Polish Redline — Multi-Agent Editing Pipeline

## What It Does

Runs parallel editing agents (kata agents) that each focus on a different dimension of writing quality. Produces tracked-changes .docx files and animated HTML replays showing every edit.

## Prerequisites

- Claude Code with parallel agent capability
- `prose-polish-redline` skill installed
- `pandoc` installed (`brew install pandoc`) — for .docx generation

## Skill Chain

1. **`prose-polish`** (optional pre-step) — Evaluates writing quality across 5 dimensions (craft, coherence, authority, purpose, voice) to identify where editing is needed
2. **`prose-polish-redline`** — Spawns parallel kata agents that produce line-level edits:
   - **Clarity kata** — Simplifies complex sentences, removes ambiguity
   - **Rhythm kata** — Varies sentence length, improves flow
   - **Precision kata** — Tightens word choice, removes filler
   - **Structure kata** — Reorders for logical flow
   - **Voice kata** — Aligns tone with genre and audience

## How to Run

### Full pipeline (assess then edit)
```
"Polish this essay with redline tracking"
```

### Just assessment (no edits)
```
"Evaluate this writing — don't make changes"
```

### Specific dimensions only
```
"Run clarity and precision katas on this text"
```

## Artifact Flow

```
Input text (markdown, essay, report)
  │
  ▼ prose-polish (optional assessment)
Quality report
  ├── Dimension scores (1-10)
  ├── Specific findings
  └── Priority edit recommendations
  │
  ▼ prose-polish-redline (parallel kata agents)
Redline output
  ├── tracked-changes.docx    # Word doc with track changes
  ├── redline-replay.html     # Animated HTML showing edits
  ├── edit-summary.md         # What changed and why
  └── per-kata reports        # Individual agent output
```

## Tips

- The kata agents run in parallel — a full pass takes 1-2 minutes
- The animated HTML replay is great for understanding what changed and why
- Use `prose-polish` first to see which dimensions need the most work
- For short pieces (< 500 words), a single-pass edit may be sufficient — the parallel pipeline shines on longer documents
- The .docx output opens in Word/Google Docs with native track changes
