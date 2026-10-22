# FOB - 0xF4CK 0xFF B1NʎRY

![version](https://img.shields.io/badge/version-1.0-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![platform](https://img.shields.io/badge/platform-Linux%20%7C%20UEFI-orange)
![tests](https://github.com/G0VNOSOFT/FOB/actions/workflows/test.yml/badge.svg)

A low-level programming language. Hex opcodes. 16 registers. Direct memory access.
Compiles to native x86-64 ELF or to UEFI PE32+ .efi.

## Contents

- [What it is](#what-it-is)
- [Requirements](#requirements)
- [Build](#build)
- [Quick start](#quick-start)
- [Examples](#examples)
- [Install](#install)
- [Tools](#tools)
- [Status](#status)
- [Philosophy](#philosophy)
- [Documentation](#documentation)
- [License](#license)


- version: 1.0
- license: MIT
- platforms: Linux x86-64, UEFI x86-64

---

## What it is

FOB is a small but real low-level language. Each instruction is one hex opcode
(0x10, 0x52, 0x60, ...), a program has exactly 16 registers r0 to rF, 64 KB of RAM,
and two backends:

| Backend      | Output                                    | Use case                        |
|--------------|-------------------------------------------|---------------------------------|
| ELF64        | Native Linux binary, syscall in r0..r6    | Linux without libc              |
| PE32+        | UEFI application .efi, loaded by firmware | UEFI utilities                  |

There is an interpreter (bin/fob) and a compiler (fobc). The compiler expands each
FOB instruction into native x86-64 through FASM. The command `make test` verifies
that both backends produce identical output (differential testing).

---

## Requirements

- fasm 1.73 or newer
- python3 3.8 or newer
- qemu-system-x86_64 and ovmf (optional, for UEFI examples)

Ubuntu / Debian:

    sudo apt install -y fasm python3 qemu-system-x86 ovmf

---

## Build

    git clone <repository> fob
    cd fob
    make build     # bin/fob (interpreter)
    make native    # build/native/* (native binaries from tests/*.fob)
    make test      # run all tests

---

## Quick start

    cat > hello.fob << 'FOB'
    0xF4CK 0xFF B1NʎRY
    0xA0 @100 "Hello, FOB!\n"
    0x10 r0 #100
    0x50 r0
    0x01
    FOB

    ./bin/fob hello.fob            # interpreter
    ./tools/fobc.py hello.fob h    # native ELF64
    chmod +x h && ./h              # same output

Output:

    Hello, FOB!

---

## Examples

### Recursive sum 1..N

    0xF4CK 0xFF B1NʎRY
    0xA0 @0 "\n"
    0x10 r0 #5             ; N = 5
    0x10 r1 #0             ; sum = 0
    0x43 :sum
    0x52 r1                ; print sum
    0x10 r3 #0
    0x50 r3
    0x01

    0x70 :sum
    0x10 r2 #0
    0x30 r0 r2             ; cmp N, 0
    0x41 :done
    0x14 r0                ; push N
    0x10 r4 #1
    0x21 r0 r4             ; N -= 1
    0x43 :sum              ; recurse
    0x15 r5                ; pop N
    0x20 r1 r5             ; sum += N
    0x44

    0x70 :done
    0x44

`./bin/fob tests/sum.fob` prints `15`.

### UEFI hello

    cat > hello_efi.fob << 'FOB'
    0xF4CK 0xFF B1NʎRY
    0xA1 @100 "Hello, UEFI from FOB!\r\n"
    0x10 r0 #100
    0x90 r0
    0x94
    FOB

    ./tools/fobc.py --efi hello_efi.fob BOOTX64.EFI

    mkdir -p esp/EFI/BOOT
    cp BOOTX64.EFI esp/EFI/BOOT/

    qemu-system-x86_64 \
        -bios /usr/share/ovmf/OVMF.fd \
        -drive file=fat:rw:$PWD/esp,format=raw \
        -net none -nographic

Screen shows `Hello, UEFI from FOB!`. Exit with Ctrl-A X.

### Reading stdin

    0xF4CK 0xFF B1NʎRY
    0x10 r0 #1000     ; buf
    0x10 r1 #80       ; maxlen
    0x16 r0 r1        ; INPUT
    0x10 r2 #1000
    0x50 r2           ; PRINTS buf
    0x01

---

## Install

    sudo make install                   # /usr/local/bin/fob, /usr/local/bin/fobc
    make install PREFIX=$HOME/.local    # alternative

---

## Tools

| Command                          | Purpose                                              |
|----------------------------------|------------------------------------------------------|
| bin/fob file.fob                 | interpreter                                          |
| bin/fob -c file.fob              | interpreter with checksum mode (|XX required)        |
| bin/fob --version                | print version                                        |
| bin/fob --help                   | print help                                           |
| tools/fobc.py in.fob out         | FOB to native ELF64                                  |
| tools/fobc.py --efi in.fob out   | FOB to UEFI PE32+                                    |
| tools/csum.py file.fob           | compute or update |XX checksums                       |
| make test                        | run the full test suite                              |

---

## Status

Implemented:

- Interpreter (ELF64) and native compiler (ELF64)
- UEFI PE32+ compiler
- 16 registers, 64 KB RAM, stack with CALL/RET/PUSH/POP
- Pointers: LOADR / STORER / LOADBR / STOREBR
- Arithmetic: ADD SUB MUL DIV MOD XOR SHL SHR ADDI SUBI NEG NOT
- Signed and unsigned conditional jumps: JZ JNZ JL JG JLE JGE JB JA JBE JAE
- I/O: PRINTI PRINTS PRINTC INPUT DATA STRL
- SYSCALL (Linux ABI), EFI_OUT, EFI_WAIT_KEY, EFI_HANG
- Hardware opcodes (UEFI only): IN OUT HLT CLI STI RDMSR WRMSR
- Checksum mode with |XX suffix
- Line-numbered error messages

Not implemented on purpose (reserved for 2.0):

- Macros, INCLUDE
- MBR/BIOS bootloader target
- Debugger
- Register allocation optimizations

---

## Philosophy

    Right hand of the processor. Memory enthusiast. Extremely precise.

- Hex-only. All numbers are hex. #A is 10, @1000 is 0x1000.
- 16 registers. r0 to rF. Exactly one hex digit per name.
- Mandatory header. 0xF4CK 0xFF B1NʎRY is the first line of every file.
  Without it, the interpreter and compiler refuse to run.
- Direct memory access. @addr for addresses, LOADR/STORER for pointer-based access.
- Differential testing. `make test` verifies that interpreter and compiler
  produce identical output on every test.

---

## Documentation

- LANGUAGE.md - full language specification
- CHANGELOG.md - version history
- CONTRIBUTING.md - contribution guidelines
- LICENSE - MIT

---

## License

MIT. See LICENSE.

---

Maintained by G0VNOSOFT (founded 2019).
