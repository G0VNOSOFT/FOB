#!/usr/bin/env python3
"""fobc — FOB to native x86-64 ELF compiler (via FASM).

Usage: fobc input.fob output
"""
import re
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
    for raw_no, raw in enumerate(body.split('\n'), start=2):
        toks = tokenize(strip_checksum(raw))
        if toks: instrs.append((raw_no, toks))
    return instrs

def collect_labels(instrs):
    labels = {}
    for line_no, toks in instrs:
        if toks[0] == ('tok', '0x70') and len(toks) >= 2 and toks[1][1].startswith(':'):
            labels[toks[1][1][1:]] = line_no
    return labels

def validate(instrs, labels):
    for line_no, toks in instrs:
        op = toks[0][1]
        if op in ('0x40','0x41','0x42','0x43','0x45','0x46','0x47','0x48',
                  '0x49','0x4A','0x4B','0x4C') and len(toks) >= 2 and toks[1][1].startswith(':'):
            ref = toks[1][1][1:]
            if ref not in labels:
                raise SystemExit(f"fobc: undefined label ':{ref}' at line {line_no}")

LBL = lambda s: 'fob_L_' + s

def emit(instrs, mode='elf'):
    out = []
    uid = [0]
    def U():
        uid[0] += 1; return uid[0]
    for line_no, toks in instrs:
        op = toks[0][1]; a = toks[1:]
        out.append(f"    ; --- line {line_no}: {op} ---")
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
        elif op == '0x16' and mode == 'efi':  # INPUT via ConIn
            u = U()
            rp = int(a[0][1][1:], 16); rl = int(a[1][1][1:], 16)
            out.append(f"    mov r14, {rp}")
            out.append(f"    mov r15, {rl}")
            out.append("    lea rdi, [regs]")
            out.append("    mov r13, [rdi + r14*8]")
            out.append("    lea rdi, [mem]")
            out.append("    add r13, rdi")
            out.append("    lea rdi, [regs]")
            out.append("    mov r14, [rdi + r15*8]")
            out.append("    test r14, r14")
            out.append(f"    jz .fobiepz{u}")
            out.append("    dec r14")
            out.append("    xor rbx, rbx")
            out.append(f".fobiepl{u}:")
            out.append("    sub rsp, 48")
            out.append("    mov rcx, [r12 + 0x30]")
            out.append("    mov rax, [rcx + 0x08]")
            out.append("    mov [rsp + 16], rax")
            out.append("    mov rcx, 1")
            out.append("    lea rdx, [rsp + 16]")
            out.append("    lea r8,  [rsp + 24]")
            out.append("    mov rax, [r12 + 0x60]")
            out.append("    call qword [rax + 0xE0]")
            out.append("    mov rcx, [r12 + 0x30]")
            out.append("    lea rdx, [rsp + 32]")
            out.append("    call qword [rcx + 0x10]")
            out.append("    movzx eax, word [rsp + 34]")
            out.append("    add rsp, 48")
            out.append("    cmp ax, 0x0D")
            out.append(f"    je .fobiepe{u}")
            out.append("    cmp ax, 0x08")
            out.append(f"    je .fobiepb{u}")
            out.append("    cmp rbx, r14")
            out.append(f"    jae .fobiepl{u}")
            out.append("    mov [r13 + rbx], al")
            out.append("    inc rbx")
            out.append(f"    jmp .fobiepl{u}")
            out.append(f".fobiepb{u}:")
            out.append("    test rbx, rbx")
            out.append(f"    jz .fobiepl{u}")
            out.append("    dec rbx")
            out.append(f"    jmp .fobiepl{u}")
            out.append(f".fobiepe{u}:")
            out.append("    mov byte [r13 + rbx], 0")
            out.append("    lea rdi, [regs]")
            out.append("    mov [rdi + r15*8], rbx")
            out.append(f"    jmp .fobiepd{u}")
            out.append(f".fobiepz{u}:")
            out.append("    lea rdi, [regs]")
            out.append("    mov qword [rdi + r15*8], 0")
            out.append(f".fobiepd{u}:")
        elif op == '0x16':  # INPUT r_ptr r_len (ELF: read syscall, byte-by-byte)
            u = U()
            rp = int(a[0][1][1:], 16); rl = int(a[1][1][1:], 16)
            out.append(f"    mov r14, {rp}")
            out.append(f"    mov r15, {rl}")
            out.append("    push rbx")
            out.append("    push rbp")
            out.append("    lea rdi, [regs]")
            out.append("    mov r10, [rdi + r14*8]")
            out.append("    mov rbp, [rdi + r15*8]")
            out.append("    test rbp, rbp")
            out.append(f"    jz .fobinpz{u}")
            out.append("    dec rbp")
            out.append("    lea rdi, [mem]")
            out.append("    add r10, rdi")
            out.append("    xor rbx, rbx")
            out.append(f".fobinpl{u}:")
            out.append("    cmp rbx, rbp")
            out.append(f"    jae .fobinpf{u}")
            out.append("    lea rsi, [r10 + rbx]")
            out.append("    xor eax, eax")
            out.append("    xor edi, edi")
            out.append("    mov rdx, 1")
            out.append("    syscall")
            out.append("    test rax, rax")
            out.append(f"    jle .fobinpf{u}")
            out.append("    cmp byte [r10 + rbx], 10")
            out.append(f"    je .fobinpf{u}")
            out.append("    cmp byte [r10 + rbx], 13")
            out.append(f"    je .fobinpf{u}")
            out.append("    inc rbx")
            out.append(f"    jmp .fobinpl{u}")
            out.append(f".fobinpf{u}:")
            out.append("    mov byte [r10 + rbx], 0")
            out.append("    lea rdi, [regs]")
            out.append("    mov [rdi + r15*8], rbx")
            out.append("    pop rbp")
            out.append("    pop rbx")
            out.append(f"    jmp .fobinpd{u}")
            out.append(f".fobinpz{u}:")
            out.append("    lea rdi, [regs]")
            out.append("    mov qword [rdi + r15*8], 0")
            out.append("    pop rbp")
            out.append("    pop rbx")
            out.append(f".fobinpd{u}:")
        elif op == '0xA2':  # STRL — length-prefixed string
            ad = int(a[0][1][1:], 16); s = a[1][1]
            if len(s) > 255:
                raise SystemExit(f"fobc: STRL string > 255 bytes at line {line_no}")
            out.append(f"    mov byte [mem + 0x{ad:x}], {len(s)}")
            for k, ch in enumerate(s):
                out.append(f"    mov byte [mem + 0x{ad+1+k:x}], 0x{ord(ch):x}")
            out.append(f"    mov byte [mem + 0x{ad+1+len(s):x}], 0")
        elif op == '0x1A':  # LOADR r_dst r_ptr
            r1 = int(a[0][1][1:], 16); r2 = int(a[1][1][1:], 16)
            out.append(f"    mov rcx, [regs + {r2}*8]")
            out.append("    lea r11, [mem]")
            out.append("    mov rax, [r11 + rcx]")
            out.append(f"    mov [regs + {r1}*8], rax")
        elif op == '0x1B':  # STORER r_ptr r_val
            r1 = int(a[0][1][1:], 16); r2 = int(a[1][1][1:], 16)
            out.append(f"    mov rcx, [regs + {r1}*8]")
            out.append(f"    mov rax, [regs + {r2}*8]")
            out.append("    lea r11, [mem]")
            out.append("    mov [r11 + rcx], rax")
        elif op == '0x1C':  # LOADBR r_dst r_ptr
            r1 = int(a[0][1][1:], 16); r2 = int(a[1][1][1:], 16)
            out.append(f"    mov rcx, [regs + {r2}*8]")
            out.append("    lea r11, [mem]")
            out.append("    movzx eax, byte [r11 + rcx]")
            out.append(f"    mov [regs + {r1}*8], rax")
        elif op == '0x1D':  # STOREBR r_ptr r_val
            r1 = int(a[0][1][1:], 16); r2 = int(a[1][1][1:], 16)
            out.append(f"    mov rcx, [regs + {r1}*8]")
            out.append(f"    mov rax, [regs + {r2}*8]")
            out.append("    lea r11, [mem]")
            out.append("    mov [r11 + rcx], al")
        elif op == '0x28':  # NEG
            r = int(a[0][1][1:], 16)
            out.append(f"    neg qword [regs + {r}*8]")
        elif op == '0x29':  # NOT
            r = int(a[0][1][1:], 16)
            out.append(f"    not qword [regs + {r}*8]")
        elif op == '0x2C':  # ADDI
            r = int(a[0][1][1:], 16); v = a[1][1][1:]
            out.append(f"    mov rax, 0x{v}")
            out.append(f"    add [regs + {r}*8], rax")
        elif op == '0x2D':  # SUBI
            r = int(a[0][1][1:], 16); v = a[1][1][1:]
            out.append(f"    mov rax, 0x{v}")
            out.append(f"    sub [regs + {r}*8], rax")
        elif op == '0x2E':  # CMPI
            r = int(a[0][1][1:], 16); v = a[1][1][1:]
            out.append(f"    mov rax, [regs + {r}*8]")
            out.append(f"    cmp rax, 0x{v}")
            out.append("    sete al")
            out.append("    mov [zf], al")
            out.append("    pushfq")
            out.append("    pop qword [saved_flags]")
        elif op == '0x30':  # CMP
            r1 = int(a[0][1][1:], 16); r2 = int(a[1][1][1:], 16)
            out.append(f"    mov rax, [regs + {r1}*8]")
            out.append(f"    cmp rax, [regs + {r2}*8]")
            out.append("    sete al")
            out.append("    mov [zf], al")
            out.append("    pushfq")
            out.append("    pop qword [saved_flags]")
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
        elif op == '0x45':  # JL
            out.append("    push qword [saved_flags]")
            out.append("    popfq")
            out.append(f"    jl {LBL(a[0][1][1:])}")
        elif op == '0x46':  # JG
            out.append("    push qword [saved_flags]")
            out.append("    popfq")
            out.append(f"    jg {LBL(a[0][1][1:])}")
        elif op == '0x47':  # JLE
            out.append("    push qword [saved_flags]")
            out.append("    popfq")
            out.append(f"    jle {LBL(a[0][1][1:])}")
        elif op == '0x48':  # JGE
            out.append("    push qword [saved_flags]")
            out.append("    popfq")
            out.append(f"    jge {LBL(a[0][1][1:])}")
        elif op == '0x49':  # JB
            out.append("    push qword [saved_flags]")
            out.append("    popfq")
            out.append(f"    jb {LBL(a[0][1][1:])}")
        elif op == '0x4A':  # JA
            out.append("    push qword [saved_flags]")
            out.append("    popfq")
            out.append(f"    ja {LBL(a[0][1][1:])}")
        elif op == '0x4B':  # JBE
            out.append("    push qword [saved_flags]")
            out.append("    popfq")
            out.append(f"    jbe {LBL(a[0][1][1:])}")
        elif op == '0x4C':  # JAE
            out.append("    push qword [saved_flags]")
            out.append("    popfq")
            out.append(f"    jae {LBL(a[0][1][1:])}")
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
        elif op == '0x80':  # OUTB #port rN
            if mode != 'efi':
                raise SystemExit("fobc: 0x80 OUTB requires --efi")
            port = int(a[0][1][1:], 16); r = int(a[1][1][1:], 16)
            out.append(f"    mov dx, 0x{port:x}")
            out.append(f"    mov al, [regs + {r}*8]")
            out.append("    out dx, al")
        elif op == '0x81':  # INB rN #port
            if mode != 'efi':
                raise SystemExit("fobc: 0x81 INB requires --efi")
            r = int(a[0][1][1:], 16); port = int(a[1][1][1:], 16)
            out.append(f"    mov dx, 0x{port:x}")
            out.append("    in al, dx")
            out.append("    movzx eax, al")
            out.append(f"    mov [regs + {r}*8], rax")
        elif op == '0x82':  # OUTW #port rN
            if mode != 'efi':
                raise SystemExit("fobc: 0x82 OUTW requires --efi")
            port = int(a[0][1][1:], 16); r = int(a[1][1][1:], 16)
            out.append(f"    mov dx, 0x{port:x}")
            out.append(f"    mov ax, [regs + {r}*8]")
            out.append("    out dx, ax")
        elif op == '0x83':  # INW rN #port
            if mode != 'efi':
                raise SystemExit("fobc: 0x83 INW requires --efi")
            r = int(a[0][1][1:], 16); port = int(a[1][1][1:], 16)
            out.append(f"    mov dx, 0x{port:x}")
            out.append("    in ax, dx")
            out.append("    movzx eax, ax")
            out.append(f"    mov [regs + {r}*8], rax")
        elif op == '0x8A':  # OUTL #port rN
            if mode != 'efi':
                raise SystemExit("fobc: 0x8A OUTL requires --efi")
            port = int(a[0][1][1:], 16); r = int(a[1][1][1:], 16)
            out.append(f"    mov dx, 0x{port:x}")
            out.append(f"    mov eax, [regs + {r}*8]")
            out.append("    out dx, eax")
        elif op == '0x8B':  # INL rN #port
            if mode != 'efi':
                raise SystemExit("fobc: 0x8B INL requires --efi")
            r = int(a[0][1][1:], 16); port = int(a[1][1][1:], 16)
            out.append(f"    mov dx, 0x{port:x}")
            out.append("    in eax, dx")
            out.append(f"    mov [regs + {r}*8], rax")
        elif op == '0x84':  # HLT
            if mode != 'efi':
                raise SystemExit("fobc: 0x84 HLT requires --efi")
            out.append("    hlt")
        elif op == '0x85':  # CLI
            if mode != 'efi':
                raise SystemExit("fobc: 0x85 CLI requires --efi")
            out.append("    cli")
        elif op == '0x86':  # STI
            if mode != 'efi':
                raise SystemExit("fobc: 0x86 STI requires --efi")
            out.append("    sti")
        elif op == '0x87':  # RDMSR: r0 = index -> r0 = eax, r1 = edx
            if mode != 'efi':
                raise SystemExit("fobc: 0x87 RDMSR requires --efi")
            out.append("    mov rcx, [regs + 0*8]")
            out.append("    rdmsr")
            out.append("    mov [regs + 0*8], rax")
            out.append("    mov [regs + 1*8], rdx")
        elif op == '0x88':  # WRMSR: r0 = index, r1 = lo, r2 = hi
            if mode != 'efi':
                raise SystemExit("fobc: 0x88 WRMSR requires --efi")
            out.append("    mov rcx, [regs + 0*8]")
            out.append("    mov rax, [regs + 1*8]")
            out.append("    mov rdx, [regs + 2*8]")
            out.append("    wrmsr")
        elif op == '0x93':  # EFI_PRINTI rN
            if mode != 'efi':
                raise SystemExit("fobc: 0x93 EFI_PRINTI requires --efi")
            r = int(a[0][1][1:], 16)
            out.append(f"    mov rax, [regs + {r}*8]")
            out.append("    call fob_efi_print_int")
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
        elif op == '0x80':  # OUTB #port rN
            if mode != 'efi':
                raise SystemExit("fobc: 0x80 OUTB requires --efi")
            port = int(a[0][1][1:], 16); r = int(a[1][1][1:], 16)
            out.append(f"    mov dx, 0x{port:x}")
            out.append(f"    mov al, [regs + {r}*8]")
            out.append("    out dx, al")
        elif op == '0x81':  # INB rN #port
            if mode != 'efi':
                raise SystemExit("fobc: 0x81 INB requires --efi")
            r = int(a[0][1][1:], 16); port = int(a[1][1][1:], 16)
            out.append(f"    mov dx, 0x{port:x}")
            out.append("    in al, dx")
            out.append("    movzx eax, al")
            out.append(f"    mov [regs + {r}*8], rax")
        elif op == '0x82':  # OUTW #port rN
            if mode != 'efi':
                raise SystemExit("fobc: 0x82 OUTW requires --efi")
            port = int(a[0][1][1:], 16); r = int(a[1][1][1:], 16)
            out.append(f"    mov dx, 0x{port:x}")
            out.append(f"    mov ax, [regs + {r}*8]")
            out.append("    out dx, ax")
        elif op == '0x83':  # INW rN #port
            if mode != 'efi':
                raise SystemExit("fobc: 0x83 INW requires --efi")
            r = int(a[0][1][1:], 16); port = int(a[1][1][1:], 16)
            out.append(f"    mov dx, 0x{port:x}")
            out.append("    in ax, dx")
            out.append("    movzx eax, ax")
            out.append(f"    mov [regs + {r}*8], rax")
        elif op == '0x8A':  # OUTL #port rN
            if mode != 'efi':
                raise SystemExit("fobc: 0x8A OUTL requires --efi")
            port = int(a[0][1][1:], 16); r = int(a[1][1][1:], 16)
            out.append(f"    mov dx, 0x{port:x}")
            out.append(f"    mov eax, [regs + {r}*8]")
            out.append("    out dx, eax")
        elif op == '0x8B':  # INL rN #port
            if mode != 'efi':
                raise SystemExit("fobc: 0x8B INL requires --efi")
            r = int(a[0][1][1:], 16); port = int(a[1][1][1:], 16)
            out.append(f"    mov dx, 0x{port:x}")
            out.append("    in eax, dx")
            out.append(f"    mov [regs + {r}*8], rax")
        elif op == '0x84':  # HLT
            if mode != 'efi':
                raise SystemExit("fobc: 0x84 HLT requires --efi")
            out.append("    hlt")
        elif op == '0x85':  # CLI
            if mode != 'efi':
                raise SystemExit("fobc: 0x85 CLI requires --efi")
            out.append("    cli")
        elif op == '0x86':  # STI
            if mode != 'efi':
                raise SystemExit("fobc: 0x86 STI requires --efi")
            out.append("    sti")
        elif op == '0x87':  # RDMSR: r0 = index -> r0 = eax, r1 = edx
            if mode != 'efi':
                raise SystemExit("fobc: 0x87 RDMSR requires --efi")
            out.append("    mov rcx, [regs + 0*8]")
            out.append("    rdmsr")
            out.append("    mov [regs + 0*8], rax")
            out.append("    mov [regs + 1*8], rdx")
        elif op == '0x88':  # WRMSR: r0 = index, r1 = lo, r2 = hi
            if mode != 'efi':
                raise SystemExit("fobc: 0x88 WRMSR requires --efi")
            out.append("    mov rcx, [regs + 0*8]")
            out.append("    mov rax, [regs + 1*8]")
            out.append("    mov rdx, [regs + 2*8]")
            out.append("    wrmsr")
        elif op == '0x93':  # EFI_PRINTI rN
            if mode != 'efi':
                raise SystemExit("fobc: 0x93 EFI_PRINTI requires --efi")
            r = int(a[0][1][1:], 16)
            out.append(f"    mov rax, [regs + {r}*8]")
            out.append("    call fob_efi_print_int")
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
            raise SystemExit(f"fobc: unsupported opcode {op} at line {line_no}")
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
        A.append("fob_efi_print_int:")
        A.append("    push rbx")
        A.append("    push rcx")
        A.append("    push rdx")
        A.append("    push rsi")
        A.append("    push rdi")
        A.append("    push r12")
        A.append("    lea rdi, [fob_efi_ibuf + 62]")
        A.append("    mov word [rdi], 0")
        A.append("    mov rbx, 10")
        A.append("    xor ecx, ecx")
        A.append("    test rax, rax")
        A.append("    jns .epos")
        A.append("    neg rax")
        A.append("    mov ecx, 1")
        A.append(".epos:")
        A.append(".eloop:")
        A.append("    xor edx, edx")
        A.append("    div rbx")
        A.append("    add dl, '0'")
        A.append("    sub rdi, 2")
        A.append("    mov [rdi], dx")
        A.append("    test rax, rax")
        A.append("    jnz .eloop")
        A.append("    test ecx, ecx")
        A.append("    jz .eprint")
        A.append("    sub rdi, 2")
        A.append("    mov word [rdi], '-'")
        A.append(".eprint:")
        A.append("    mov rdx, rdi")
        A.append("    mov rcx, [r12 + 0x40]")
        A.append("    sub rsp, 32")
        A.append("    call qword [rcx + 0x08]")
        A.append("    add rsp, 32")
        A.append("    pop r12")
        A.append("    pop rdi")
        A.append("    pop rsi")
        A.append("    pop rdx")
        A.append("    pop rcx")
        A.append("    pop rbx")
        A.append("    ret")
        A.append("")
        A.append("section '.data' data readable writeable")
        A.append("regs: rq 16")
        A.append("mem: rb 65536")
        A.append("zf: db 0")
        A.append("stk_ptr: dq 65536")
        A.append("efi_saved_rsp: dq 0")
        A.append("fob_efi_ibuf: rb 64")
        A.append("saved_flags: dq 0")
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
    A.append("saved_flags: dq 0")
    Path(asm_path).write_text('\n'.join(A) + '\n')

def main():
    args = sys.argv[1:]
    if '--version' in args or '-v' in args:
        print("fobc v0.8")
        sys.exit(0)
    if '--help' in args or '-h' in args:
        print("fobc v0.8 — FOB → native compiler (via FASM)")
        print("usage: fobc [--efi] input.fob output")
        print("  --efi        emit PE32+ UEFI application instead of ELF64")
        print("  -v, --version")
        print("  -h, --help")
        sys.exit(0)
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
