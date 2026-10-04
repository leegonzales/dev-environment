#!/bin/sh
# Tests for trim-log.sh. Run: sh launchd/bin/test-trim-log.sh
# Each check is a single-quoted string that check() evals later, so variables
# look unused/unexpanded to shellcheck; cleanup runs via trap.
# shellcheck disable=SC2016,SC2034,SC2329
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
TRIM="$HERE/trim-log.sh"
T=$(mktemp -d)
cleanup() {
    rm -f "$T/big.log" "$T/big.log.1" "$T/small.log" "$T/small.log.1" \
        "$T/a.log" "$T/a.log.1" "$T/b.log" "$T/b.log.1"
    rmdir "$T" 2>/dev/null
}
trap cleanup EXIT
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
mb() { echo $(( $1 * 1024 * 1024 )); }

# Over the limit: keep only the tail in .1, empty the live file in place.
f="$T/big.log"
awk 'BEGIN{for(i=0;i<60000;i++) printf "line %06d padding-padding-padding-padding\n", i}' > "$f"
ino=$(stat -f %i "$f")
last=$(tail -n 1 "$f")
sh "$TRIM" 1 1 "$f"
check "live log emptied"                         '[ "$(stat -f %z "$f")" -eq 0 ]'
check "same inode (append writers keep working)" '[ "$(stat -f %i "$f")" = "$ino" ]'
check ".1 holds at most the keep size"           '[ "$(stat -f %z "$f.1")" -le "$(mb 1)" ]'
check ".1 ends with the newest line"             '[ "$(tail -n 1 "$f.1")" = "$last" ]'
check ".1 starts on a whole line"                'head -n 1 "$f.1" | grep -q "^line [0-9]\{6\} "'

# Under the limit: untouched.
s="$T/small.log"; printf 'tiny\n' > "$s"
sh "$TRIM" 1 1 "$s"
check "small log untouched"                      '[ "$(cat "$s")" = "tiny" ]'
check "no .1 for small log"                      '[ ! -e "$s.1" ]'

# Missing file: no error.
sh "$TRIM" 1 1 "$T/nope.log"; rc=$?
check "missing file exits 0"                     '[ "$rc" -eq 0 ]'

# Several files in one run: each is capped on its own; a missing one is skipped.
a="$T/a.log"; b="$T/b.log"
awk 'BEGIN{for(i=0;i<60000;i++) printf "a %06d padding-padding-padding-padding\n", i}' > "$a"
printf 'tiny\n' > "$b"
sh "$TRIM" 1 1 "$a" "$T/nope.log" "$b"; rc=$?
check "multi-file run exits 0"                   '[ "$rc" -eq 0 ]'
check "big file in the list is capped"           '[ "$(stat -f %z "$a")" -eq 0 ] && [ -s "$a.1" ]'
check "small file after a missing one untouched" '[ "$(cat "$b")" = "tiny" ] && [ ! -e "$b.1" ]'

# Bad arguments: refuse.
sh "$TRIM" 1 2 "$f" >/dev/null 2>&1; rc=$?
check "keep > max is rejected"                   '[ "$rc" -ne 0 ]'
sh "$TRIM" 1 1 >/dev/null 2>&1; rc=$?
check "no files is rejected"                     '[ "$rc" -ne 0 ]'

exit $fail
