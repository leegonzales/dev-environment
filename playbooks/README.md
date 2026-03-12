# Playbooks

Compound workflow recipes for Claude Code. Each playbook documents a multi-skill pipeline — what it does, what tools it needs, and how to run it.

These are documentation, not executable scripts. They teach Claude Code (or you) how to orchestrate the pipelines.

## Index

| Playbook | Description | Key Skills |
|----------|-------------|------------|
| [sandbox.md](sandbox.md) | Docker sandbox system for isolated execution | sandbox alias, Docker |
| [cass.md](cass.md) | CASS setup, indexing, and search workflows | cass CLI, launchd |
| [claude-speak.md](claude-speak.md) | TTS daemon pipeline (Kokoro on Apple Silicon) | claude-speak skill, launchd |
| [read-aloud.md](read-aloud.md) | Read-aloud HTML builders for narration | essay-to-speech, claude-speak |
| [sand-table.md](sand-table.md) | Multi-agent training simulation | sand-table skill, parallel agents |
| [research-to-video.md](research-to-video.md) | Research brief → script → rendered video | research-brief, write-script, render-video |
| [research-to-presentation.md](research-to-presentation.md) | Research → essay → speech → slides → PK | research-to-essay, essay-to-speech, slide-builder |
| [prose-polish-redline.md](prose-polish-redline.md) | Multi-agent parallel editing pipeline | prose-polish-redline, parallel agents |
| [multiagent-review.md](multiagent-review.md) | Fan-out code/PR review across multiple AI models | multiagent-review, Codex, Gemini |
| [skills-overview.md](skills-overview.md) | Complete skills catalog and dependency map | All skills |

## How to Use

1. Open the playbook for the workflow you want to run
2. Check the prerequisites section — install any missing tools
3. Follow the "How to Run" section — it gives exact invocations
4. Review "Artifact Flow" to understand what files get produced

## For Claude Code

When Lee asks for a compound workflow (e.g., "make a video about X"), read the relevant playbook to understand the full pipeline before starting. The playbooks encode the orchestration logic that connects individual skills into end-to-end workflows.
