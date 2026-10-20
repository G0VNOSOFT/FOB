#!/usr/bin/env python3
"""fobc — FOB to native x86-64 ELF compiler (via FASM).

Usage: fobc input.fob output
"""
import sys, subprocess, tempfile
from pathlib import Path

MEM_SIZE = 0x10000

def strip_checksum(line):
    in_str = False; esc = False
    for i, ch in enumerate(line):
        if esc: esc = False; continue
        if in_str:
            if ch == '\\': esc = True
            elif ch == '"': in_str = False
        else:
            if ch == '"': in_str = True
            elif ch == ';': return line[:i]
            elif ch == '|': return line[:i]
    return line

def tokenize(line):
    out = []; i = 0; n = len(line)
    while i < n:
        while i < n and line[i] in ' \t': i += 1
        if i >= n: break
        if line[i] == '"':
            j = i + 1; buf = []
            while j < n:
                if line[j] == '\\' and j+1 < n:
                    e = line[j+1]
                    buf.append({'n':'\n','t':'\t','r':'\r','0':'\0','\\':'\\','"':'"'}.get(e, e))
                    j += 2
                elif line[j] == '"':
                    j += 1; break
                else:
                    buf.append(line[j]); j += 1
            out.append(('str', ''.join(buf)))
            i = j
        else:
            j = i
            while j < n and line[j] not in ' \t': j += 1
            out.append(('tok', line[i:j]))
            i = j
    return out

def parse_fob(path):
    data = Path(path).read_bytes()
    nl = data.find(b'\n')
    if nl < 0:
        raise SystemExit(f"fobc: {path} has no header line")
    header = data[:nl]
    if not (header.startswith(b'0xF4CK 0xFF B1N') and header.endswith(b'RY')):
        raise SystemExit(f"fobc: invalid header in {path}")
    body = data[nl+1:].decode('latin-1')
    instrs = []
    for raw in body.split('\n'):
        toks = tokenize(strip_checksum(raw))
        if toks: instrs.append(toks)
    return instrs

def collect_labels(instrs):
    labels = {}
    for idx, toks in enumerate(instrs):
        if toks[0] == ('tok', '0x70') and len(toks) >= 2 and toks[1][1].startswith(':'):
            labels[toks[1][1][1:]] = idx
    return labels

def validate(instrs, labels):
    for idx, toks in enumerate(instrs):
        op = toks[0][1]
        if op in ('0x40','0x41','0x42','0x43') and len(toks) >= 2 and toks[1][1].startswith(':'):
            ref = toks[1][1][1:]
            if ref not in labels:
                raise SystemExit(f"fobc: undefined label ':{ref}' at line {idx}")

LBL = lambda s: 'fob_L_' + s

def emit(instrs, mode='elf'):
    out = []
    uid = [0]
    def U():
        uid[0] += 1; return uid[0]
    for idx, toks in enumerate(instrs):
        op = toks[0][1]; a = toks[1:]
        out.append(f"    ; --- line {idx}: {op} ---")
        if mode == 'efi' and op in ('0x50','0x51','0x52','0x60'):
            raise SystemExit(f"fobc: {op} not available in EFI mode (use 0x90 EFI_OUT + 0xA1 DATA16)")
        if op == '0x00':
            out.append("    nop")
        elif op == '0x01':
            out.append("    jmp fob_exit")
        elif op == '0x10':  # LOAD r #imm
            r = int(a[0][1][1:], 16); v = a[1][1][1:]
            out.append(f"    mov rax, 0x{v}")
            out.append(f"    mov [regs + {r}*8], rax")
        elif op == '0x11':  # LOADM r @addr
            r = int(a[0][1][1:], 16); ad = int(a[1][1][1:], 16)
            out.append(f"    mov rax, [mem + 0x{ad:x}]")
            out.append(f"    mov [regs + {r}*8], rax")
        elif op == '0x12':  # STORE @addr r
            ad = int(a[0][1][1:], 16); r = int(a[1][1][1:], 16)
            out.append(f"    mov rax, [regs + {r}*8]")
            out.append(f"    mov [mem + 0x{ad:x}], rax")
        elif op == '0x13':  # STOREB
            ad = int(a[0][1][1:], 16); r = int(a[1][1][1:], 16)
            out.append(f"    mov rax, [regs + {r}*8]")
            out.append(f"    mov [mem + 0x{ad:x}], al")
        elif op == '0x14':  # PUSH
            r = int(a[0][1][1:], 16)
            out.append("    mov rcx, [stk_ptr]")
            out.append("    sub rcx, 8")
            out.append("    mov [stk_ptr], rcx")
            out.append(f"    mov rax, [regs + {r}*8]")
            out.append("    mov [mem + rcx], rax")
        elif op == '0x15':  # POP
            r = int(a[0][1][1:], 16)
            out.append("    mov rcx, [stk_ptr]")
            out.append("    mov rax, [mem + rcx]")
            out.append(f"    mov [regs + {r}*8], rax")
            out.append("    add rcx, 8")
            out.append("    mov [stk_ptr], rcx")
        elif op == '0x20':  # ADD
            r1 = int(a[0][1][1:], 16); r2 = int(a[1][1][1:], 16)
            out.append(f"    mov rax, [regs + {r2}*8]")
            out.append(f"    add [regs + {r1}*8], rax")
        elif op == '0x21':
            r1 = int(a[0][1][1:], 16); r2 = int(a[1][1][1:], 16)
            out.append(f"    mov rax, [regs + {r2}*8]")
            out.append(f"    sub [regs + {r1}*8], rax")
        elif op == '0x22':  # MUL
            r1 = int(a[0][1][1:], 16); r2 = int(a[1][1][1:], 16)
            out.append(f"    mov rax, [regs + {r1}*8]")
            out.append(f"    mul qword [regs + {r2}*8]")
            out.append(f"    mov [regs + {r1}*8], rax")
        elif op == '0x23':  # DIV
            r1 = int(a[0][1][1:], 16); r2 = int(a[1][1][1:], 16)
            out.append("    xor edx, edx")
            out.append(f"    mov rax, [regs + {r1}*8]")
            out.append(f"    div qword [regs + {r2}*8]")
            out.append(f"    mov [regs + {r1}*8], rax")
        elif op == '0x24':  # XOR
            r1 = int(a[0][1][1:], 16); r2 = int(a[1][1][1:], 16)
            out.append(f"    mov rax, [regs + {r2}*8]")
            out.append(f"    xor [regs + {r1}*8], rax")
        elif op == '0x25':  # MOD
            r1 = int(a[0][1][1:], 16); r2 = int(a[1][1][1:], 16)
            out.append("    xor edx, edx")
            out.append(f"    mov rax, [regs + {r1}*8]")
            out.append(f"    div qword [regs + {r2}*8]")
            out.append(f"    mov [regs + {r1}*8], rdx")
        elif op == '0x26':  # SHL
            r1 = int(a[0][1][1:], 16); r2 = int(a[1][1][1:], 16)
            out.append(f"    mov rcx, [regs + {r2}*8]")
            out.append(f"    mov rax, [regs + {r1}*8]")
            out.append("    shl rax, cl")
            out.append(f"    mov [regs + {r1}*8], rax")
        elif op == '0x27':  # SHR
            r1 = int(a[0][1][1:], 16); r2 = int(a[1][1][1:], 16)
            out.append(f"    mov rcx, [regs + {r2}*8]")
            out.append(f"    mov rax, [regs + {r1}*8]")
            out.append("    shr rax, cl")
            out.append(f"    mov [regs + {r1}*8], rax")
        elif op == '0x30':  # CMP
            r1 = int(a[0][1][1:], 16); r2 = int(a[1][1][1:], 16)
            out.append(f"    mov rax, [regs + {r1}*8]")
            out.append(f"    cmp rax, [regs + {r2}*8]")
            out.append("    sete al")
            out.append("    mov [zf], al")
        elif op == '0x40':  # JMP
            out.append(f"    jmp {LBL(a[0][1][1:])}")
        elif op == '0x41':  # JZ
            u = U()
            out.append("    cmp byte [zf], 0")
            out.append(f"    je .fobsk{u}")
            out.append(f"    jmp {LBL(a[0][1][1:])}")
            out.append(f".fobsk{u}:")
        elif op == '0x42':  # JNZ
            u = U()
            out.append("    cmp byte [zf], 0")
            out.append(f"    jne .fobsk{u}")
            out.append(f"    jmp {LBL(a[0][1][1:])}")
            out.append(f".fobsk{u}:")
        elif op == '0x43':  # CALL
            out.append(f"    call {LBL(a[0][1][1:])}")
        elif op == '0x44':  # RET
            out.append("    ret")
        elif op == '0x50':  # PRINTS r
            r = int(a[0][1][1:], 16); u = U()
            out.append(f"    mov rax, [regs + {r}*8]")
            out.append("    lea rsi, [mem]")
            out.append("    add rsi, rax")
            out.append("    xor edx, edx")
            out.append(f".fobps{u}:")
            out.append("    cmp byte [rsi + rdx], 0")
            out.append(f"    je .fobpd{u}")
            out.append("    inc rdx")
            out.append(f"    jmp .fobps{u}")
            out.append(f".fobpd{u}:")
            out.append("    mov eax, 1")
            out.append("    mov edi, 1")
            out.append("    syscall")
        elif op == '0x51':  # PRINTC r
            r = int(a[0][1][1:], 16)
            out.append(f"    lea rsi, [regs + {r}*8]")
            out.append("    mov rdx, 1")
            out.append("    mov eax, 1")
            out.append("    mov edi, 1")
            out.append("    syscall")
        elif op == '0x52':  # PRINTI r
            r = int(a[0][1][1:], 16)
            out.append(f"    mov rax, [regs + {r}*8]")
            out.append("    call fob_print_int")
        elif op == '0x60':  # SYSCALL
            u = U()
            out.append("    mov rax, [regs + 0*8]")
            out.append("    mov rdi, [regs + 1*8]")
            out.append("    mov rsi, [regs + 2*8]")
            out.append(f"    cmp rsi, {MEM_SIZE}")
            out.append(f"    jae .fobsf{u}")
            out.append("    lea r11, [mem]")
            out.append("    add rsi, r11")
            out.append(f".fobsf{u}:")
            out.append("    mov rdx, [regs + 3*8]")
            out.append("    mov r10, [regs + 4*8]")
            out.append("    mov r8,  [regs + 5*8]")
            out.append("    mov r9,  [regs + 6*8]")
            out.append("    syscall")
            out.append("    mov [regs + 0*8], rax")
        elif op == '0x90':  # EFI_OUT r
            if mode != 'efi':
                raise SystemExit("fobc: 0x90 EFI_OUT requires --efi")
            r = int(a[0][1][1:], 16)
            out.append("    mov rcx, [r12 + 0x40]")          # ST->ConOut
            out.append(f"    mov rax, [regs + {r}*8]")
            out.append("    lea rdx, [mem]")
            out.append("    add rdx, rax")
            out.append("    sub rsp, 32")
            out.append("    call qword [rcx + 0x08]")          # ConOut->OutputString
            out.append("    add rsp, 32")
        elif op == '0x91':  # EFI_STALL #ms
            if mode != 'efi':
                raise SystemExit("fobc: 0x91 EFI_STALL requires --efi")
            ms = int(a[0][1][1:], 16)
            out.append(f"    mov rcx, 0x{ms:x}")
            out.append("    mov rax, [r12 + 0x60]")            # ST->BootServices
            out.append("    sub rsp, 32")
            out.append("    call qword [rax + 0xF8]")          # BS->Stall
            out.append("    add rsp, 32")
        elif op == '0xA1':  # DATA16 — UTF-16-LE
            ad = int(a[0][1][1:], 16); s = a[1][1]
            for k, ch in enumerate(s):
                out.append(f"    mov word [mem + 0x{ad+k*2:x}], 0x{ord(ch):04x}")
            out.append(f"    mov word [mem + 0x{ad+len(s)*2:x}], 0")
        elif op == '0x92':  # EFI_WAIT_KEY
            if mode != 'efi':
                raise SystemExit("fobc: 0x92 EFI_WAIT_KEY requires --efi")
            u = U()
            # ST->ConIn->WaitForKey
            out.append("    mov rcx, [r12 + 0x30]")          # ST->ConIn
            out.append("    mov rdx, [rcx + 0x08]")          # ConIn->WaitForKey
            out.append("    sub rsp, 32")
            out.append("    lea rcx, [rsp + 16]")            # &event (index)
            out.append("    mov [rcx], rdx")
            out.append("    mov r8, [r12 + 0x60]")            # ST->BootServices
            out.append(f"    mov rcx, 1")                     # 1 event
            out.append("    lea rdx, [rsp + 16]")            # &events
            out.append("    lea r8, [rsp + 24]")             # &index (unused)
            out.append("    mov r9, [r12 + 0x60]")
            out.append("    mov r9, [r9 + 0xE0]")            # BS->WaitForEvent
            out.append("    mov rcx, 1")
            out.append("    lea rdx, [rsp + 16]")
            out.append("    lea r8, [rsp + 24]")
            out.append("    call r9")
            out.append("    add rsp, 32")
        elif op == '0x92':  # EFI_WAIT_KEY
            if mode != 'efi':
                raise SystemExit("fobc: 0x92 EFI_WAIT_KEY requires --efi")
            out.append("    sub rsp, 48")
            out.append("    mov rcx, [r12 + 0x30]")          # ST->ConIn
            out.append("    mov rax, [rcx + 0x08]")          # ConIn->WaitForKey
            out.append("    mov [rsp + 16], rax")            # events[0]
            out.append("    mov rcx, 1")
            out.append("    lea rdx, [rsp + 16]")
            out.append("    lea r8,  [rsp + 24]")
            out.append("    mov rax, [r12 + 0x60]")          # ST->BootServices
            out.append("    call qword [rax + 0xE0]")        # BS->WaitForEvent
            out.append("    add rsp, 48")
        elif op == '0x70':  # LABEL
            out.append(f"{LBL(a[0][1][1:])}:")
        elif op == '0xA0':  # DATA
            ad = int(a[0][1][1:], 16); s = a[1][1]
            for k, ch in enumerate(s):
                out.append(f"    mov byte [mem + 0x{ad+k:x}], 0x{ord(ch):x}")
            out.append(f"    mov byte [mem + 0x{ad+len(s):x}], 0")
        else:
            raise SystemExit(f"fobc: unsupported opcode {op} at line {idx}")
    return out

def build_asm(instrs, asm_path, mode='elf'):
    body = emit(instrs, mode=mode)
    A = []
    if mode == 'efi':
        A.append("format PE64 dll efi")
        A.append("entry efi_main")
        A.append(f"MEM_SIZE = {MEM_SIZE}")
        A.append("section '.text' code readable executable")
        A.append("efi_main:")
        A.append("    push rbx")
        A.append("    push rbp")
        A.append("    push rdi")
        A.append("    push rsi")
        A.append("    push r12")
        A.append("    push r13")
        A.append("    push r14")
        A.append("    push r15")
        A.append("    mov [efi_saved_rsp], rsp")
        A.append("    mov r12, rdx")               # SystemTable
        A.extend(body)
        A.append("fob_exit:")
        A.append("    mov rsp, [efi_saved_rsp]")
        A.append("    pop r15")
        A.append("    pop r14")
        A.append("    pop r13")
        A.append("    pop r12")
        A.append("    pop rsi")
        A.append("    pop rdi")
        A.append("    pop rbp")
        A.append("    pop rbx")
        A.append("    xor eax, eax")
        A.append("    ret")
        A.append("")
        A.append("section '.data' data readable writeable")
        A.append("regs: rq 16")
        A.append("mem: rb 65536")
        A.append("zf: db 0")
        A.append("stk_ptr: dq 65536")
        A.append("efi_saved_rsp: dq 0")
        Path(asm_path).write_text('\n'.join(A) + '\n')
        return

    A.append("format ELF64 executable 3")
    A.append("entry _start")
    A.append(f"MEM_SIZE = {MEM_SIZE}")
    A.append("segment readable executable")
    A.append("_start:")
    A.extend(body)
    A.append("fob_exit:")
    A.append("    xor edi, edi")
    A.append("    mov eax, 60")
    A.append("    syscall")
    A.append("")
    A.append("fob_print_int:")
    A.append("    push rbx")
    A.append("    push rcx")
    A.append("    push rdx")
    A.append("    push rsi")
    A.append("    push rdi")
    A.append("    lea rdi, [fob_ibuf + 31]")
    A.append("    mov byte [rdi], 0")
    A.append("    mov rbx, 10")
    A.append("    xor ecx, ecx")
    A.append("    test rax, rax")
    A.append("    jns .fp_pos")
    A.append("    neg rax")
    A.append("    mov ecx, 1")
    A.append(".fp_pos:")
    A.append(".fp_loop:")
    A.append("    xor edx, edx")
    A.append("    div rbx")
    A.append("    add dl, '0'")
    A.append("    dec rdi")
    A.append("    mov [rdi], dl")
    A.append("    test rax, rax")
    A.append("    jnz .fp_loop")
    A.append("    test rcx, rcx")
    A.append("    jz .fp_print")
    A.append("    dec rdi")
    A.append("    mov byte [rdi], '-'")
    A.append(".fp_print:")
    A.append("    mov rsi, rdi")
    A.append("    lea rdx, [fob_ibuf + 31]")
    A.append("    sub rdx, rsi")
    A.append("    mov eax, 1")
    A.append("    mov edi, 1")
    A.append("    syscall")
    A.append("    pop rdi")
    A.append("    pop rsi")
    A.append("    pop rdx")
    A.append("    pop rcx")
    A.append("    pop rbx")
    A.append("    ret")
    A.append("")
    A.append("segment readable writeable")
    A.append("regs: rq 16")
    A.append("mem: rb 65536")
    A.append("zf: db 0")
    A.append("stk_ptr: dq 65536")
    A.append("fob_ibuf: rb 32")
    Path(asm_path).write_text('\n'.join(A) + '\n')

def main():
    args = sys.argv[1:]
    mode = 'elf'
    if '--efi' in args:
        args.remove('--efi'); mode = 'efi'
    if len(args) != 2:
        print("fobc: usage: fobc [--efi] input.fob output"); sys.exit(1)
    inp, outp = args
    instrs = parse_fob(inp)
    labels = collect_labels(instrs)
    validate(instrs, labels)
    with tempfile.TemporaryDirectory() as td:
        asm = Path(td) / "out.asm"
        build_asm(instrs, asm, mode=mode)
        r = subprocess.run(["fasm", str(asm), outp], capture_output=True)
        if r.returncode != 0:
            sys.stdout.buffer.write(r.stdout)
            sys.stderr.buffer.write(r.stderr)
            sys.exit(r.returncode)
        print(f"fobc: [{mode}] {inp} -> {outp}")

if __name__ == '__main__':
    main()
