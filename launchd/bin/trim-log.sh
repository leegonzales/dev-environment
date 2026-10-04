#!/bin/sh
# trim-log.sh MAX_MB KEEP_MB FILE...
#
# Cap logs that a long-running process writes in append mode (O_APPEND),
# such as a launchd StandardOutPath. When a FILE exceeds MAX_MB, its newest
# KEEP_MB (starting on a whole line) are saved to FILE.1 and FILE is emptied
# in place. Missing files are skipped.
#
# Emptying in place keeps the inode, so an append-mode writer's next line
# lands at offset 0. Do NOT use this on a log whose writer did not open it
# with O_APPEND: the writer would keep its old offset and leave a hole.
# Check with `lsof +fg -p <pid>` (look for AP in FILE-FLAG).
set -eu

[ $# -ge 3 ] || { echo "usage: trim-log.sh MAX_MB KEEP_MB FILE..." >&2; exit 2; }
max_mb=$1
keep_mb=$2
shift 2

case "$max_mb" in '' | *[!0-9]*) echo "MAX_MB must be an integer" >&2; exit 2 ;; esac
case "$keep_mb" in '' | *[!0-9]*) echo "KEEP_MB must be an integer" >&2; exit 2 ;; esac
[ "$keep_mb" -le "$max_mb" ] || { echo "KEEP_MB must not exceed MAX_MB" >&2; exit 2; }

for f in "$@"; do
    [ -f "$f" ] || continue
    size=$(stat -f %z "$f")
    [ "$size" -gt $((max_mb * 1024 * 1024)) ] || continue

    # Drop the first (likely partial) line so FILE.1 starts on a line boundary.
    tail -c $((keep_mb * 1024 * 1024)) "$f" | sed '1d' > "$f.1"
    : > "$f"
done
