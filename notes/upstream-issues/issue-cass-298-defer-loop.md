# `index --watch` spins a core forever: the #298 defer path has no terminal state

**Repo:** Dicklesworthstone/coding_agent_session_search
**Version:** cass 0.6.22 (`upstream/main`), fsqlite 0.1.19
**Platform:** macOS 25.4 (Darwin), Apple M5, 128 GB RAM
**Symptom:** `cass index --watch` pins one core continuously (97 min CPU over
4h21m elapsed), RSS grows to ~20 GB, and `~/Library/Logs/cass-index.log`
reached 609 MB of repeated warnings.

## What happens

The watcher repeats this cycle roughly every 16 seconds, indefinitely:

```
watch_scan kind=Claude conversations=20
  -> watch ingest batch ran out of memory; retrying as smaller batches (6 -> 3 -> 1)
  -> per conversation: error=out of memory
  -> "deferring (not quarantining) for later retry (#298)"  x18
  -> preserving final watch watermark so quarantined/deferred source can be retried
  -> rescan, identical result
```

18 conversations fail, are deferred, the watermark is deliberately not
advanced, and the next scan retries the same 18. Forever, with no delay.

## Root cause

`src/indexer/mod.rs`, `ingest_watch_batch_with_oom_split_inner` (~L21820):

```rust
let should_quarantine = match real_pressure {
    Some(true)  => true,
    Some(false) => !small_conversation,
    None        => !small_conversation,
};
if !should_quarantine { /* warn; */ deferred_conversations: 1 }
```

With the shipped defaults:

| Gate | Default | This host |
|---|---|---|
| `WATCH_OOM_SMALL_CONVERSATION_DEFAULT_BYTES` | 8 MiB | failing conversations are 525 B - 260 KB -> all "small" |
| `WATCH_OOM_REAL_PRESSURE_RESERVE_DEFAULT_BYTES` | 512 MiB | ~4.3 GB available -> `Some(false)` -> "ample" |

So `should_quarantine` is permanently `false`. Deferral does not advance the
watermark, and there is **no attempt counter, no backoff, and no escalation
ceiling**. Quarantine is the only terminal state, and the gate is constructed
to never reach it for a small conversation on a large-memory host.

#298 correctly identified that a typed `FrankenError::OutOfMemory` is not proof
of host memory exhaustion. The fix replaced a wrong terminal state (spurious
quarantine) with *no* terminal state.

The same gate is used on the non-watch path (~L21490), which is safe only
because those runs exit.

## The premise that does not hold

The code comment states: *"retry it solo (which the reporter confirmed
succeeds)"*. On this host the solo retry **also** fails. The underlying limit is
the process-wide `PageBufPool` ceiling in fsqlite, so isolating a single
conversation changes nothing. `ingested cleanly solo` never appears in 609 MB
of log; every hit takes the deferral branch.

## Why the pool limit is reached

fsqlite's `DEFAULT_PAGE_BUFFER_MAX` is 262,144 buffers ~= **1 GiB** at 4 KiB
pages. This database is **2.40 GiB / 628,926 pages** — the page-buffer ceiling
is under half the database, so bulk ingest with FTS5 lexical updates cannot fit
its working set. Filed separately against fsqlite.

## Suggested fixes

1. Give the defer path an attempt counter persisted with the watermark,
   exponential backoff, and a ceiling that escalates to quarantine. "Retry
   immediately, forever" should be unreachable regardless of what the storage
   layer reports.
2. Distinguish *retryable* from *structurally impossible*. Pool-ceiling
   exhaustion will not resolve on retry with identical inputs; it should raise a
   configuration diagnostic naming `FSQLITE_PAGE_BUFFER_MAX`.
3. Scale the default page-buffer ceiling with database size, or warn at startup
   when `db_page_count > page_buffer_max`.
4. Rate-limit the warning. 609 MB of identical lines is its own failure.

## Workarounds that work today

Both paths read the same gate, so forcing quarantine ends the loop:

```
CASS_WATCH_OOM_SMALL_CONVERSATION_BYTES=0
```

Better, removing the cause rather than the loop:

```
FSQLITE_PAGE_BUFFER_MAX=1048576    # 4 GiB, vs a 2.4 GiB database
```

With the ceiling raised, no OOM fires, previously-poisoned records log
`cleared poison quarantine records after successful ingest retry`, and CPU
drops from a pegged core to 0.0% once the backlog clears.
