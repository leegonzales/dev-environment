# Upstream issues: status

Checked against upstream on 2026-10-03, before filing anything.

| Draft | Status | Why |
|---|---|---|
| `issue-cass-298-defer-loop.md` | **Filed:** [cass #510](https://github.com/Dicklesworthstone/coding_agent_session_search/issues/510) | Still present on upstream `main` (306d6e25). Since #364, ample-memory hosts *always* defer, so the loop has no exit at all. Filed against current line numbers. |
| `issue-fsqlite-pool-oom.md` | **Not filed** | Duplicate. frankensqlite [#131](https://github.com/Dicklesworthstone/frankensqlite/issues/131) (false `OutOfMemory` at pool saturation, closed 2026-07-12) and [#326](https://github.com/Dicklesworthstone/frankensqlite/issues/326) (~96% CPU livelock at the pool ceiling, closed 2026-08-07) cover it. Our cass 0.6.22 pins fsqlite 0.1.19; current cass v0.10.0 pins 0.4.6. |

The drafts describe the installed versions (cass 0.6.22 / fsqlite 0.1.19) and
are kept for the analysis. They are not current upstream behavior.

## Upgrade notes for cass 0.6.22 → v0.10.0

- `FSQLITE_PAGE_BUFFER_MAX` **still works** in fsqlite 0.4.6 (default still
  262,144 buffers = 1 GiB). Keep it set; it is the real fix.
- `CASS_WATCH_OOM_SMALL_CONVERSATION_BYTES=0` **stops working** after upgrade.
  #364 made ample-memory hosts skip the size gate entirely, so it can no longer
  force a quarantine. It is a no-op, not harmful.
- Open upstream issues to read before upgrading a 2.4 GiB index:
  [#349](https://github.com/Dicklesworthstone/coding_agent_session_search/issues/349)
  (v0.6.22 macOS base-schema migration OOM) and
  [#320](https://github.com/Dicklesworthstone/coding_agent_session_search/issues/320)
  (full index peaks 13.4 GB on 16 GB macOS).
