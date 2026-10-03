# `PageBufPool` exhaustion is reported as `OutOfMemory`, and the 1 GiB default is smaller than many databases

**Repo:** Dicklesworthstone/frankensqlite
**Version:** fsqlite 0.1.19 (`fsqlite-pager`)
**Reported via:** cass / coding_agent_session_search 0.6.22 on macOS, 128 GB
RAM, 2.40 GiB database

## 1. Bounded-pool exhaustion is indistinguishable from host OOM

`fsqlite-pager/src/page_buf.rs:358`, `PageBufPool::acquire`:

```rust
loop {
    let current = self.inner.total_buffers.load(Ordering::Acquire);
    if current >= self.inner.max_buffers {
        return Err(FrankenError::OutOfMemory);   // size never consulted
    }
    ...
```

"My configured buffer ceiling is reached" and "the host is out of memory" return
the same typed error. These need different handling: the first is a
configuration problem that recurs identically on retry, the second is transient.

Downstream consumers cannot tell them apart, so they guess. In cass's case it
retries forever, reasoning that with 128 GB free the error cannot be real —
correct reasoning, wrong remedy, because the condition is deterministic.

Suggest a distinct variant, e.g.
`FrankenError::PageBufferPoolExhausted { max_buffers, page_size }`, so callers
can surface a configuration diagnostic instead of treating it as transient
pressure.

## 2. The default ceiling does not scale with database size

`DEFAULT_PAGE_BUFFER_MAX = 262_144` -> **1 GiB** at 4 KiB pages.

The reporting database is 628,926 pages (**2.40 GiB**) — 2.4x the ceiling. Bulk
ingest with FTS5 index writes in a single transaction cannot fit its working
set, so `acquire` fails on a workload that is otherwise entirely reasonable on a
128 GB machine.

Suggestions:
- Derive the default from database page count (with a sane cap), or
- Emit a warning at pager open when `page_count` materially exceeds
  `max_buffers`, naming `FSQLITE_PAGE_BUFFER_MAX`.

The env override works well once you know it exists; nothing points you to it.

## 3. The write path lacks the read path's graceful fallback

The read path degrades gracefully — `pager.rs:2187` catches `OutOfMemory` and
falls back to `read_page_copy_uncached`. `page_cache.rs:4042` handles it too.

The ingest/write path has no equivalent, so pool exhaustion surfaces as a hard
per-statement failure. If an uncached or spill path is feasible for writes, it
would turn a fatal error into a slow one.

## Note on `total_buffers`, to save the next reader a wrong lead

It looks suspicious on first read: `total_buffers` is incremented in `acquire`
and decremented nowhere. That is **correct** — it counts distinct buffers owned
by the pool (in-use + idle), and `return_buf` recycles through the `free` list,
which `acquire` consults first. There is no public path that extracts a pooled
buffer's backing, and `Drop` always returns it. So this is not an accounting
leak; reaching the ceiling genuinely means `max_buffers` pages are pinned at
once. The problem is the ceiling's default size and how its exhaustion is
reported, not the counter.
