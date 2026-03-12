# Sand Table — Multi-Agent Training Simulation

## What It Does

Stress-tests training sessions before live delivery by simulating 6 diverse participant personas. Each persona is an independent Claude agent that reacts to the training content differently — the skeptic pushes back, the quiet one disengages, the expert challenges depth. Produces a structured evaluation report.

## Prerequisites

- Claude Code with agent teams enabled (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`)
- `sand-table` skill installed
- A completed training module (talk track + facilitator guide)

## Skill Chain

1. **`sand-table`** — Orchestrates the simulation
   - Spawns 6 participant agents with distinct personas
   - Feeds training content through simulated delivery
   - Each agent responds in-character
   - Collects reactions, questions, and engagement signals
2. (Input from) **`module-build`** or **`training-build`** — The training content being tested

## How to Run

```
"Run a sand table simulation on this training module"
```

Claude Code will:
1. Read the training module's talk track and facilitator guide
2. Spawn 6 participant agents with predefined personas
3. Simulate the session flow, collecting per-persona feedback
4. Produce a structured evaluation report

### Personas

| Persona | Behavior |
|---------|----------|
| **The Skeptic** | Challenges premises, asks "why should I care?" |
| **The Expert** | Tests depth, asks advanced follow-ups |
| **The Quiet One** | Minimal engagement, tests if facilitator draws them out |
| **The Enthusiast** | Over-engages, tests if facilitator manages airtime |
| **The Confused** | Misunderstands concepts, tests clarity of explanations |
| **The Practical** | Demands concrete examples and takeaways |

## Artifact Flow

```
Training module (talk track + facilitator guide)
  │
  ▼ sand-table skill
Simulation session
  ├── Per-persona reaction logs
  ├── Questions generated
  ├── Engagement scores
  └── Structured eval report
       ├── Strengths
       ├── Risk areas
       ├── Suggested facilitator adjustments
       └── Content gaps identified
```

## Tips

- Run after `training-build` but before live delivery
- The eval report often surfaces gaps that aren't obvious from reading the content
- Re-run after making adjustments to verify fixes
- Each simulation takes 3-5 minutes with parallel agents
- The personas are intentionally adversarial — real audiences are usually easier
