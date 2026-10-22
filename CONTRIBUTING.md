# Contributing to FOB

## Build and test

    make build
    make native
    make test

A pull request is merged only if `make test` reports PASS: N, FAIL: 0.

## Adding a new opcode

The same functionality must be implemented in three places:

1. src/fob.asm - the interpreter:
   - cmp bl, 0xXX plus je .op_xxx in the dispatch chain
   - .op_xxx: implementation

2. tools/fobc.py - the compiler:
   - elif op == '0xXX': in emit()
   - if the feature is EFI-only, guard with: if mode != 'efi': raise SystemExit(...)

3. tests/xxx.fob - a test file, plus the expected output in tests/run_tests.sh

## Style

- Numbers are hex. Use 0x1000, not 4096.
- Operands are space-separated. Example: 0x10 r0 #1000.
- One opcode per line. No multi-line instructions.
- Comments start with ; and run to end of line.
- Header is mandatory. 0xF4CK 0xFF B1NʎRY must be the first line of every file.

## Before opening a pull request

    make clean && make test
    git diff --stat

Ensure no build artifacts, backup files, or runtime files are included.

## License

By opening a pull request you agree to release your contribution under the MIT
license (see LICENSE).
