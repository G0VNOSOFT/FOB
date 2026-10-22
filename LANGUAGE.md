# FOB Language Specification - v1.0

Formal specification of FOB: 0xF4CK 0xFF B1NʎRY.

---

## 1. Program file

A program is a UTF-8 text file. The first line must be exactly:

    0xF4CK 0xFF B1NʎRY

The byte sequence is:
0x30 0x78 0x46 0x34 0x43 0x4B 0x20 0x30 0x78 0x46 0x46 0x20 0x42 0x31 0x4E 0xC7 0x8E 0x52 0x59 0x0A

Without it, the interpreter and compiler refuse to process the file.

After the header, instructions follow, one per line.

---

## 2. Syntax

    <opcode> <arg1> <arg2> <arg3> [|XX]   ; comment

- opcode - a hex byte, exactly two hex characters, prefixed with 0x.
- Arguments are separated by spaces or tabs.
- A comment starts with ; and runs to end of line.
- Checksum is an optional |XX suffix (see section 8).
- Empty lines and comment-only lines are ignored.

Argument forms:

| Form      | Example    | Meaning                                              |
|-----------|------------|------------------------------------------------------|
| rN        | r0, rF     | register, N is 0 to F                                |
| #hex      | #1000, #A  | immediate value                                      |
| @hex      | @1000      | memory address                                       |
| :name     | :loop      | label, characters A-Z a-z 0-9 _                      |
| "string"  | "hi\n"     | literal; escapes: \n \t \r \0 \\ \"                   |

---

## 3. Execution model

- 16 registers r0 to rF, each 64-bit unsigned (treated as signed for signed operations).
- 64 KB of RAM at addresses 0x0000 to 0xFFFF, shared between data and stack.
- Stack grows downward from 0x10000, 8-byte slots.
- Flags are set only by CMP and CMPI, and consumed by Jcc (see section 4.5).
- The program is a linear list of instructions with labels.

---

## 4. Opcode table

### 4.1 Control flow

| Op   | Mnemonic | Example         | Action                            |
|------|----------|-----------------|-----------------------------------|
| 0x00 | NOP      | 0x00            | no operation                      |
| 0x01 | HALT     | 0x01            | exit (ELF) or return from efi_main (EFI) |
| 0x40 | JMP      | 0x40 :l         | unconditional jump                |
| 0x70 | LABEL    | 0x70 :l         | label declaration                 |

### 4.2 Data

| Op   | Mnemonic | Example            | Action                                        |
|------|----------|--------------------|-----------------------------------------------|
| 0x10 | LOAD     | 0x10 r0 #1000      | r0 = 0x1000                                   |
| 0x11 | LOADM    | 0x11 r0 @1000      | r0 = *(u64*)&mem[0x1000]                      |
| 0x12 | STORE    | 0x12 @1000 r0      | *(u64*)&mem[0x1000] = r0                      |
| 0x13 | STOREB   | 0x13 @1000 r0      | *(u8*)&mem[0x1000] = r0 & 0xFF                |
| 0x1A | LOADR    | 0x1A r1 r0         | r1 = *(u64*)&mem[r0]                          |
| 0x1B | STORER   | 0x1B r0 r1         | *(u64*)&mem[r0] = r1                          |
| 0x1C | LOADBR   | 0x1C r1 r0         | r1 = *(u8*)&mem[r0]                           |
| 0x1D | STOREBR  | 0x1D r0 r1         | *(u8*)&mem[r0] = r1 & 0xFF                    |
| 0xA0 | DATA     | 0xA0 @1000 "str"   | write string bytes and trailing NUL            |
| 0xA1 | DATA16   | 0xA1 @1000 "str"   | write UTF-16-LE bytes and trailing NUL (EFI)  |
| 0xA2 | STRL     | 0xA2 @1000 "str"   | mem[1000]=len; mem[1001..]=bytes; NUL after   |

### 4.3 Stack

| Op   | Mnemonic | Example    | Action                              |
|------|----------|------------|-------------------------------------|
| 0x14 | PUSH     | 0x14 r0    | sp -= 8; mem[sp] = r0               |
| 0x15 | POP      | 0x15 r0    | r0 = mem[sp]; sp += 8               |
| 0x43 | CALL     | 0x43 :f    | push(rip_next); jump                |
| 0x44 | RET      | 0x44       | pop(rip); jump                      |

### 4.4 Arithmetic and logic

| Op   | Mnemonic | Example      | Action                                  |
|------|----------|--------------|-----------------------------------------|
| 0x20 | ADD      | 0x20 r1 r2   | r1 += r2                                |
| 0x21 | SUB      | 0x21 r1 r2   | r1 -= r2                                |
| 0x22 | MUL      | 0x22 r1 r2   | r1 *= r2                                |
| 0x23 | DIV      | 0x23 r1 r2   | r1 /= r2 (unsigned; r2=0 runtime error) |
| 0x24 | XOR      | 0x24 r1 r2   | r1 ^= r2                                |
| 0x25 | MOD      | 0x25 r1 r2   | r1 %= r2                                |
| 0x26 | SHL      | 0x26 r1 r2   | r1 <<= r2                               |
| 0x27 | SHR      | 0x27 r1 r2   | r1 >>= r2 (logical)                     |
| 0x28 | NEG      | 0x28 r0      | r0 = -r0                                |
| 0x29 | NOT      | 0x29 r0      | r0 = ~r0                                |
| 0x2C | ADDI     | 0x2C r0 #100 | r0 += 0x100                             |
| 0x2D | SUBI     | 0x2D r0 #100 | r0 -= 0x100                             |

### 4.5 Comparison and conditional jumps

| Op   | Mnemonic | Example       | Condition                     |
|------|----------|---------------|-------------------------------|
| 0x30 | CMP      | 0x30 r1 r2    | set flags from r1 - r2        |
| 0x2E | CMPI     | 0x2E r0 #100  | set flags from r0 - 0x100     |
| 0x41 | JZ       | 0x41 :l       | jump if r1 == r2              |
| 0x42 | JNZ      | 0x42 :l       | jump if r1 != r2              |
| 0x45 | JL       | 0x45 :l       | jump if r1 <  r2 (signed)     |
| 0x46 | JG       | 0x46 :l       | jump if r1 >  r2 (signed)     |
| 0x47 | JLE      | 0x47 :l       | jump if r1 <= r2 (signed)     |
| 0x48 | JGE      | 0x48 :l       | jump if r1 >= r2 (signed)     |
| 0x49 | JB       | 0x49 :l       | jump if r1 <  r2 (unsigned)   |
| 0x4A | JA       | 0x4A :l       | jump if r1 >  r2 (unsigned)   |
| 0x4B | JBE      | 0x4B :l       | jump if r1 <= r2 (unsigned)   |
| 0x4C | JAE      | 0x4C :l       | jump if r1 >= r2 (unsigned)   |

Flag semantics: CMP and CMPI save the CPU flags into saved_flags. Jcc restores
saved_flags before testing. Any instruction may appear between CMP and Jcc as
long as it does not modify saved_flags. JZ and JNZ use a separate zero flag and
are not affected by other instructions (backward compatible with v0.1).

### 4.6 I/O (ELF and EFI)

| Op   | Mnemonic | Example     | Action                                             |
|------|----------|-------------|----------------------------------------------------|
| 0x50 | PRINTS   | 0x50 r0     | write(1, &mem[r0], strlen)                         |
| 0x51 | PRINTC   | 0x51 r0     | write(1, &r0, 1)                                   |
| 0x52 | PRINTI   | 0x52 r0     | write(1, decimal(r0), length)                      |
| 0x16 | INPUT    | 0x16 r0 r1  | read into mem[r0..r0+r1); stops at \n or \r; r1 = actual length |

INPUT reads byte-by-byte and stops at \n or \r or when r1-1 bytes have been read.
The actual length is stored in r1. The buffer is NUL-terminated.

### 4.7 System calls

| Op   | Target | Action                                                              |
|------|--------|---------------------------------------------------------------------|
| 0x60 | ELF    | rax=r0, rdi=r1, rsi=r2 (memory fixup), rdx=r3, r10=r4, r8=r5, r9=r6 -> syscall -> r0=rax |

Linux x86-64 syscall ABI. Pointers are interpreted as offsets into mem when their
value is less than 0x10000, otherwise as raw pointers.

### 4.8 UEFI

| Op   | Mnemonic    | Action                                                       |
|------|-------------|--------------------------------------------------------------|
| 0x90 | EFI_OUT     | SystemTable->ConOut->OutputString(mem + r)                    |
| 0x91 | EFI_STALL   | BootServices->Stall(#ms)                                      |
| 0x92 | EFI_WAIT_KEY| BootServices->WaitForEvent(ConIn->WaitForKey)                 |
| 0x93 | EFI_PRINTI  | ConOut->OutputString(decimal(r))                              |
| 0x94 | EFI_HANG    | infinite WaitForEvent loop (external exit required)           |

### 4.9 Hardware (UEFI only, ring 0)

| Op   | Mnemonic | Example         | Action                                |
|------|----------|-----------------|---------------------------------------|
| 0x80 | OUTB     | 0x80 #80 r0     | out 0x80, al                          |
| 0x81 | INB      | 0x81 r0 #60     | r0 = in al, 0x60 (zero-extended)      |
| 0x82 | OUTW     | 0x82 #CF8 r0    | out 0xCF8, ax                         |
| 0x83 | INW      | 0x83 r0 #CFC    | r0 = in ax, 0xCFC                     |
| 0x8A | OUTL     | 0x8A #CF8 r0    | out 0xCF8, eax (PCI config)           |
| 0x8B | INL      | 0x8B r0 #CFC    | r0 = in eax, 0xCFC                    |
| 0x84 | HLT      | 0x84            | hlt                                   |
| 0x85 | CLI      | 0x85            | disable interrupts                    |
| 0x86 | STI      | 0x86            | enable interrupts                     |
| 0x87 | RDMSR    | 0x87            | r0=index; on return r0=eax, r1=edx    |
| 0x88 | WRMSR    | 0x88            | r0=index, r1=eax, r2=edx              |

Using a hardware opcode with fobc --elf is a compile error.

---

## 5. Labels and jumps

A label is declared with the instruction 0x70 :name, where name is a sequence of
characters A-Z a-z 0-9 _. Forward references are allowed. The interpreter and the
compiler both run a first pass to collect labels and a second pass to execute or
emit code. The compiler verifies that every referenced label is defined.

Label scope is flat and global. There is one label namespace per program.

---

## 6. Checksum |XX

Every instruction line (not a comment, not an empty line) may carry a suffix:

    <instruction>|XX

where XX is the XOR of all bytes from the start of the line up to but not
including the | character, encoded as two hex digits.

Modes:

- Default: if |XX is present, it is verified; if absent, the line is not checked.
- fob -c file.fob: |XX is mandatory on every non-empty non-comment line;
  missing checksum produces exit code 6.
- Checksum mismatch produces exit code 5.

Generation: tools/csum.py file.fob (in place) or tools/csum.py --stdout file.fob.

---

## 7. Errors

| Code | Meaning                                                    |
|------|------------------------------------------------------------|
| 0    | success                                                    |
| 1    | invalid usage or missing arguments                         |
| 2    | file not found or cannot be opened                         |
| 3    | invalid header                                             |
| 4    | syntax error (with line number and opcode)                 |
| 5    | checksum mismatch                                          |
| 6    | missing |XX in -c mode                                     |

Error message formats:

    FOB: syntax error at line 7 (op=0x52)
    FOB: checksum mismatch
    FOB: missing checksum (-c mode)
    FOB: invalid header
    FOB: cannot open file

---

## 8. Examples

### 8.1 Hello World (ELF)

    0xF4CK 0xFF B1NʎRY
    0xA0 @100 "Hello, FOB!\n"
    0x10 r0 #100
    0x50 r0
    0x01

### 8.2 Factorial of 10 (iterative)

    0xF4CK 0xFF B1NʎRY
    0xA0 @0 "\n"
    0x10 r0 #A          ; N = 10
    0x10 r1 #1          ; acc = 1
    0x10 r2 #1
    0x70 :loop
    0x30 r0 r2          ; cmp N, 0
    0x41 :done
    0x22 r1 r0          ; acc *= N
    0x10 r3 #1
    0x21 r0 r3          ; N -= 1
    0x40 :loop
    0x70 :done
    0x52 r1             ; 3628800
    0x10 r4 #0
    0x50 r4
    0x01

### 8.3 UEFI hello

    0xF4CK 0xFF B1NʎRY
    0xA1 @100 "Hello, UEFI from FOB!\r\n"
    0x10 r0 #100
    0x90 r0
    0x94                ; hang

### 8.4 PCI device ID read (UEFI)

    0xF4CK 0xFF B1NʎRY
    ; config address 00:00.0, register 0 -> 0x80000000
    0x10 r0 #80000000
    0x8A #CF8 r0        ; OUTL 0xCF8
    0x10 r0 #0
    0x8B r0 #CFC        ; INL 0xCFC -> r0 = VendorID:DeviceID
    0x93 r0             ; EFI_PRINTI
    0x94

    0x12378086 corresponds to Intel 8086:1237 (i440FX host bridge).

---

## 9. HALT semantics

- ELF: calls exit(0).
- EFI: returns 0 from efi_main. The firmware proceeds to the next boot option
  or reboots. To keep the screen visible, use 0x94 EFI_HANG which enters an
  infinite WaitForEvent loop.

---

## 10. Limitations

- No macros. #DEFINE is not supported (reserved for 2.0).
- No INCLUDE. A program is a single file.
- 64 KB RAM and 16 registers are fixed.
- No type system. Everything is u64.
- No garbage collector and no automatic memory management.
- syscall ABI is Linux x86-64 only.
- UEFI Boot Services: only OutputString, Stall and WaitForEvent are wired.

---

## 11. Compatibility

- FASM 1.73 or newer, for building the interpreter and for native compilation.
- Python 3.8 or newer, for fobc and csum.py.
- Linux x86-64 for the ELF target.
- UEFI x86-64 (OVMF or real firmware) for the EFI target.

---

Specification v1.0. All changes are documented in CHANGELOG.md.
