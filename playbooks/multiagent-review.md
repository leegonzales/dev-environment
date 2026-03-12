# Multi-Agent Review — Fan-Out Code Review

## What It Does

Fans out to 5-8 parallel reviewers (Codex CLI, Gemini CLI, specialist Claude agents) for multi-perspective review of PRs, code, designs, or writing. Each reviewer focuses on a different dimension. Results are synthesized into a unified report.

## Prerequisites

- Claude Code with parallel agent capability
- `multiagent-review` skill installed
- Codex CLI installed (`npm install -g @anthropic-ai/codex`)
- Gemini CLI installed (`npm install -g @google/generative-ai-cli`)
- `gh` CLI authenticated

## Skill Chain

1. **`multiagent-review`** — Orchestrates the fan-out:
   - Spawns parallel reviewer agents
   - Each reviewer examines the code from a different angle
   - Results are collected and synthesized
   - Produces a unified review with severity-ranked findings

## Reviewer Dimensions

| Reviewer | Focus |
|----------|-------|
| **Security** | OWASP top 10, injection, auth, secrets |
| **Architecture** | Separation of concerns, coupling, patterns |
| **Performance** | Algorithmic complexity, resource usage, bottlenecks |
| **Correctness** | Logic errors, edge cases, error handling |
| **Style** | Naming, consistency, readability |
| **Testing** | Coverage gaps, test quality, edge case tests |
| **Cross-model** (Codex) | Independent verification from a different AI model |
| **Cross-model** (Gemini) | Third perspective for triangulation |

## How to Run

### Review a PR
```
"Review PR #123 with multi-agent review"
```

### Review local changes
```
"Run multi-agent review on the staged changes"
```

### Review a specific file
```
"Multi-agent review on src/auth/handler.ts"
```

## Artifact Flow

```
Code / PR / diff
  │
  ▼ multiagent-review (parallel agents)
Individual reviews
  ├── Security review
  ├── Architecture review
  ├── Performance review
  ├── Correctness review
  ├── Style review
  ├── Testing review
  ├── Codex cross-validation
  └── Gemini cross-validation
  │
  ▼ Synthesis
Unified review report
  ├── Critical findings (must fix)
  ├── Warnings (should fix)
  ├── Suggestions (nice to have)
  └── Cross-model agreement matrix
```

## Tips

- The fan-out takes 2-4 minutes depending on code size
- Cross-model reviews (Codex, Gemini) catch blindspots from model-specific biases
- For quick reviews, specify just 2-3 dimensions instead of the full fan-out
- Works on any text — not just code. Good for contract review, design docs, etc.
- The agreement matrix shows where multiple reviewers flagged the same issue (high confidence)
