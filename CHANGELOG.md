# Changelog

All notable changes to FOB are documented in this file.

## [1.0.0] - 2026-10-22

### Language
- Full set of low-level instructions: 40+ opcodes
- Direct and indirect memory addressing
- Stack with CALL/RET/PUSH/POP
- Arithmetic: ADD SUB MUL DIV MOD XOR SHL SHR
- Immediate arithmetic: ADDI SUBI CMPI
- Signed and unsigned conditional jumps: JL JG JLE JGE JB JA JBE JAE
- Pointers: LOADR STORER LOADBR STOREBR
- Strings: DATA (null-terminated), STRL (length-prefixed)
- I/O: PRINTS PRINTC PRINTI INPUT
- SYSCALL (Linux ABI) for the ELF target
- UEFI: EFI_OUT EFI_WAIT_KEY EFI_HANG
- Hardware (UEFI only): IN OUT (B/W/L) HLT CLI STI RDMSR WRMSR

### Tooling
- bin/fob - interpreter (FASM, ELF64)
- tools/fobc.py - FOB to native ELF64 / UEFI PE32+
- tools/csum.py - generate |XX checksums
- make test - differential tests (interpreter vs compiler)

### Infrastructure
- Line-numbered error messages with opcode
- --version and --help for fob and fobc
- Checksum mode (|XX on every instruction with -c flag)
- Makefile with build, native, test, install, clean
- 12 test files in tests/, all PASS

## [0.7c] - 2026-10-22
- INPUT (stdin/ConIn), STRL (length-prefixed strings)
- Byte-by-byte INPUT: stops at \n or \r, does not consume next line

## [0.7b] - 2026-10-22
- Indirect addressing: LOADR STORER LOADBR STOREBR

## [0.7a] - 2026-10-22
- NEG NOT ADDI SUBI CMPI
- Intel-style Jcc: JL JG JLE JGE JB JA JBE JAE
- saved_flags for the "CMP, then any instruction, then Jcc" semantics

## [0.6] - 2026-10-21
- Hardware opcodes: IN OUT (B/W/L) HLT CLI STI RDMSR WRMSR
- EFI_PRINTI
- Hardware opcodes only available in the EFI target; using them with --elf is a compile error

## [0.5.1] - 2026-10-21
- EFI_WAIT_KEY (BootServices->WaitForEvent)
- EFI_HANG (infinite WaitForEvent loop)

## [0.5] - 2026-10-21
- UEFI target (fobc --efi produces PE32+)
- EFI_OUT, DATA16 (UTF-16-LE strings)

## [0.4] - 2026-10-20
- fobc: FOB to native ELF64 compiler (through FASM)
- Differential testing: 8 tests, interpreter equals compiler

## [0.3.2] - 2026-10-20
- Fix csum.py: header no longer merges with the first instruction

## [0.3.1] - 2026-10-20
- Fix SYSCALL: memory-address fixup for rsi (pointers into mem are valid for the kernel)

## [0.3] - 2026-10-20
- MUL DIV MOD SHL SHR
- SYSCALL (0x60): Linux ABI through registers
- Checksum |XX per line, -c flag

## [0.2] - 2026-10-20
- Stack: PUSH POP
- CALL RET for recursion and functions
- Fixes: parse_hex accumulator, PRINTS rsi, jump src_buf offsets

## [0.1] - 2026-10-20
- First version: ELF64 interpreter
- 20 opcodes, 16 registers, 64 KB RAM
- Mandatory header: 0xF4CK 0xFF B1NʎRY
