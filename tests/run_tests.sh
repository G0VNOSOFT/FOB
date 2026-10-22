#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.."

PASS=0
FAIL=0

fail() {
    FAIL=$((FAIL+1))
    printf 'FAIL %s\n' "$1"
    if [ -n "${2:-}" ]; then printf '  %s\n' "$2"; fi
}

pass() { PASS=$((PASS+1)); printf 'PASS %s\n' "$1"; }

run_stdout_test() {
    local name="$1" expect="$2" out
    out=$(./bin/fob "tests/$name.fob" 2>&1)
    if [ "$out" = "$expect" ]; then pass "$name"; else
        fail "$name" "expected: $(printf '%q' "$expect") got: $(printf '%q' "$out")"
    fi
}

run_native_test() {
    local name="$1" expect="$2" out
    local bin="build/native/$name"
    if [ ! -x "$bin" ]; then fail "$name/native" "binary missing: $bin"; return; fi
    out=$("$bin" 2>&1)
    if [ "$out" = "$expect" ]; then pass "$name/native"; else
        fail "$name/native" "expected: $(printf '%q' "$expect") got: $(printf '%q' "$out")"
    fi
}

run_stdin_test() {
    local name="$1" input="$2" expect="$3" out
    out=$(printf '%b' "$input" | ./bin/fob "tests/$name.fob" 2>&1)
    if [ "$out" = "$expect" ]; then pass "$name"; else
        fail "$name" "expected: $(printf '%q' "$expect") got: $(printf '%q' "$out")"
    fi
}

run_exit_test() {
    local name="$1" expect_exit="$2"; shift 2
    local out rc
    out=$(./bin/fob "$@" 2>&1); rc=$?
    if [ "$rc" = "$expect_exit" ]; then pass "$name"; else
        fail "$name" "expected exit=$expect_exit, got $rc (out: $(printf '%q' "$out"))"
    fi
}

echo "── interpreter ──"
run_stdout_test hello       'Hello, FOB!'
run_stdout_test factorial   '3628800'
run_stdout_test sum         '15'
run_stdout_test stack       '204
187
170'
run_stdout_test csum_ok     '42'
run_stdout_test jcc         '10
7
-5
-1
v0.7a ALL OK'
run_stdout_test ptr         'ABC
3735928559
65
66
v0.7b ALL OK'
run_stdout_test strl        '6
Hello!'

echo "── stdin ──"
run_stdin_test input 'abc\nhello world\n' '> len=3
you said: abc
> len=11
you said: hello world
> '

echo "── flags / exit codes ──"
run_exit_test version_flag     0 --version
run_exit_test help_flag        0 --help
run_exit_test missing_file     2 no_such_file.fob
run_exit_test csum_missing     6 -c tests/hello.fob

# checksum mismatch
cp tests/csum_ok.fob /tmp/fob_broken.fob
sed -i 's/#2A/#2B/' /tmp/fob_broken.fob
out=$(./bin/fob /tmp/fob_broken.fob 2>&1); rc=$?
if [ "$rc" = "5" ]; then pass checksum_mismatch; else fail checksum_mismatch "exit=$rc"; fi
rm -f /tmp/fob_broken.fob

echo "── native compiler (differential) ──"
run_native_test hello      'Hello, FOB!'
run_native_test factorial  '3628800'
run_native_test jcc        '10
7
-5
-1
v0.7a ALL OK'
run_native_test ptr        'ABC
3735928559
65
66
v0.7b ALL OK'
run_native_test strl       '6
Hello!'

echo
echo "─── results ───"
echo "PASS: $PASS"
echo "FAIL: $FAIL"
[ "$FAIL" = 0 ] || exit 1
