# Skills Overview — Complete Catalog

Master catalog of all skills available in Lee's Claude Code environment. Skills are installed via the [AISkills](https://github.com/leegonzales/AISkills) repo, symlinked to `~/.claude/skills/`.

## Skills by Category

### Research & Analysis

| Skill | Description | External Tools | Platform |
|-------|-------------|----------------|----------|
| `research-brief` | Structured research brief with claims registry and emotional anchors | Web search | All |
| `research-to-essay` | Research-driven essay/post creation with citation management | Web search | All |
| `claimify` | Extract claims from discourse into analyzable argument maps | None | All |
| `notebooklm` | Query NotebookLM for source-grounded answers | Google NotebookLM | All |
| `inevitability-engine` | AI-native business discovery protocol | Web search | All |

### Content Production

| Skill | Description | External Tools | Platform |
|-------|-------------|----------------|----------|
| `write-script` | Transform research brief into narration script (4-phase pipeline) | Codex, Gemini (review) | Claude Code |
| `render-video` | Render script into video with images, audio, timeline | ffmpeg, image gen MCP | Claude Code |
| `veo3-prompter` | Craft video prompts for Veo 3.1 | Veo MCP | All |
| `nano-banana` | Generate/edit images via Gemini 3 Pro Image | Nano Banana MCP | All |
| `slide-builder` | Transform talk tracks into slide decks | Image gen MCP | Claude Code |
| `essay-to-speech` | Convert essays to spoken-word presentations | claude-speak | Apple Silicon |
| `claude-speak` | TTS via Kokoro daemon | claude-speak daemon | Apple Silicon |
| `produce-show` | Produce audio/video from Show Runner conversations | ffmpeg | Claude Code |

### Writing & Editing

| Skill | Description | External Tools | Platform |
|-------|-------------|----------------|----------|
| `prose-polish` | Multi-dimensional writing quality assessment | None | All |
| `prose-polish-redline` | Parallel kata agents with tracked changes output | pandoc | Claude Code |

### Code & Development

| Skill | Description | External Tools | Platform |
|-------|-------------|----------------|----------|
| `multiagent-review` | Fan-out review across Codex, Gemini, Claude agents | Codex, Gemini | Claude Code |
| `codex-peer-review` | Codex CLI for second-opinion code review | Codex CLI | Claude Code |
| `gemini-peer-review` | Gemini CLI for cross-validation | Gemini CLI | Claude Code |
| `pr-review-loop` | Manage PR review feedback loop (CI checks, comments, fixes) | gh CLI | Claude Code |
| `requesting-code-review` | Dispatch 3 independent reviewers for verification | None | Claude Code |
| `codebase-navigator` | Semantic code search via osgrep | osgrep | Claude Code |
| `unix-review` | Evaluate codebases against Unix rules and SOLID | None | All |
| `mcp-builder` | Guide for creating MCP servers | None | All |
| `playground` | Create interactive HTML playgrounds | None | All |
| `playwright` | Browser automation with Playwright | Playwright | Claude Code |
| `frontend-design` | Production-grade frontend interfaces (plugin) | None | Claude Code |

### Training & Facilitation

| Skill | Description | External Tools | Platform |
|-------|-------------|----------------|----------|
| `sand-table` | Multi-agent training simulation (6 personas) | None | Claude Code |
| `module-build` | Training module build pipeline (4 phases) | None | Claude Code |
| `training-build` | Execute approved training module build | None | Claude Code |
| `training-brainstorm` | Design walkthrough for new/revised modules | None | All |
| `training-review` | Score completed modules against rubric | None | All |
| `training-slide-gen` | Generate slide images (LEGO + corporate styles) | Image gen MCP | Claude Code |
| `training-rubric` | Generate session-specific eval rubric | None | All |
| `training-design-qa` | Validate against Catalyst design principles | None | All |

### Meta & Process

| Skill | Description | External Tools | Platform |
|-------|-------------|----------------|----------|
| `find-skills` | Discover and install skills | None | All |
| `context-continuity-code` | Context transfer for development workflows | None | Claude Code |
| `process-mapper` | Map workflows and identify automation opportunities | None | All |
| `second-brain` | Personal intelligence system (Obsidian vault) | Obsidian MCP | All |
| `goals-graph` | Query/update goals graph | goals_query.py | Claude Code |
| `fabric-patterns` | Run fabric CLI patterns for content analysis | fabric | Claude Code |
| `excel-auditor` | Analyze inherited Excel files | None | All |
| `silicon-doppelganger` | Build personal proxy agents for PAIRL | None | All |

### Superpowers (Plugin)

| Skill | Description |
|-------|-------------|
| `using-superpowers` | Skill discovery and invocation protocol |
| `brainstorming` | Creative exploration before implementation |
| `writing-plans` | Multi-step task planning |
| `executing-plans` | Plan execution with review checkpoints |
| `test-driven-development` | TDD workflow |
| `systematic-debugging` | Bug investigation protocol |
| `dispatching-parallel-agents` | Parallel task orchestration |
| `using-git-worktrees` | Git worktree isolation for feature work |
| `finishing-a-development-branch` | Branch completion and integration |
| `verification-before-completion` | Pre-commit verification protocol |
| `subagent-driven-development` | Implementation with parallel subagents |
| `writing-skills` | Creating and editing skills |
| `requesting-code-review` | Code review dispatch |
| `receiving-code-review` | Handling review feedback |

## Dependency Map

```
research-brief ──→ write-script ──→ render-video
       │                                  │
       ▼                                  ▼
research-to-essay ──→ essay-to-speech → claude-speak
                            │
                            ▼
                      slide-builder ──→ produce-show

prose-polish ──→ prose-polish-redline

training-brainstorm ──→ module-build ──→ training-review
                            │                  │
                            ▼                  ▼
                      training-build    training-rubric
                            │
                            ▼
                       sand-table
```

## Platform Key

- **All** — Works in any Claude environment (API, Claude.ai, Claude Code)
- **Claude Code** — Requires Claude Code CLI (file access, bash, parallel agents)
- **Apple Silicon** — Requires M-series Mac (Kokoro TTS, MLX)
