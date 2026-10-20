; FOB — 0xF4CK 0xFF B1NʎRY
; Интерпретатор v0.1 — Linux x86-64
format ELF64 executable 3
entry _start

SRC_MAX    = 1048576
MEM_SIZE   = 65536
LABELS_MAX = 256

segment readable executable

_start:
    mov rax, [rsp]
    cmp rax, 2
    jb  usage
    mov rdi, [rsp+16]
    cmp byte [rdi], '-'
    jne .no_c_flag
    cmp byte [rdi+1], 'c'
    jne .no_c_flag
    cmp byte [rdi+2], 0
    jne .no_c_flag
    cmp rax, 3
    jb  usage
    mov byte [checksum_mode], 1
    mov rdi, [rsp+24]
.no_c_flag:

    mov eax, 2
    xor esi, esi
    xor edx, edx
    syscall
    test rax, rax
    js  err_open
    mov r12, rax

    xor eax, eax
    mov rdi, r12
    lea rsi, [src_buf]
    mov rdx, SRC_MAX - 1
    syscall
    test rax, rax
    js  err_open
    mov r13, rax

    mov eax, 3
    mov rdi, r12
    syscall

    lea rdi, [src_buf]
    mov byte [rdi + r13], 0

    call check_header
    test rax, rax
    jz  err_hdr

    call pass1
    call execute

    xor edi, edi
    mov eax, 60
    syscall

usage:
    lea rsi, [msg_usage]
    call write_str
    mov edi, 1
    mov eax, 60
    syscall

err_open:
    lea rsi, [msg_open]
    call write_str
    mov edi, 2
    mov eax, 60
    syscall

err_hdr:
    lea rsi, [msg_hdr]
    call write_str
    mov edi, 3
    mov eax, 60
    syscall

; =============================================================
check_header:
    lea rsi, [src_buf]
    lea rdi, [hdr_str]
    mov rcx, hdr_len
    rep cmpsb
    setz al
    movzx eax, al
    ret

; =============================================================
write_str:
    push rax
    push rcx
    push r11
    mov rdx, 0
.ws_len:
    cmp byte [rsi + rdx], 0
    je  .ws_go
    inc rdx
    jmp .ws_len
.ws_go:
    mov eax, 1
    mov edi, 1
    syscall
    pop r11
    pop rcx
    pop rax
    ret

; =============================================================
write_char:
    push rax
    push rcx
    push r11
    push rsi
    push rdi
    push rdx
    lea rsi, [tmp_char]
    mov [rsi], al
    mov eax, 1
    mov edi, 1
    mov rdx, 1
    syscall
    pop rdx
    pop rdi
    pop rsi
    pop r11
    pop rcx
    pop rax
    ret

; =============================================================
write_int:
    push rbx
    push rcx
    push rdx
    push rsi
    push rdi
    lea rdi, [tmp_num + 31]
    mov byte [rdi], 0
    mov rbx, 10
    xor ecx, ecx
    test rax, rax
    jns .wi_pos
    neg rax
    mov ecx, 1
.wi_pos:
.wi_loop:
    xor edx, edx
    div rbx
    add dl, '0'
    dec rdi
    mov [rdi], dl
    test rax, rax
    jnz .wi_loop
    test rcx, rcx
    jz  .wi_print
    dec rdi
    mov byte [rdi], '-'
.wi_print:
    mov rsi, rdi
    call write_str
    pop rdi
    pop rsi
    pop rdx
    pop rcx
    pop rbx
    ret

; =============================================================
next_line:
    mov rax, rsi
.nl_loop:
    mov dl, [rax]
    test dl, dl
    jz  .nl_ret
    cmp dl, 10
    je  .nl_ret_past
    inc rax
    jmp .nl_loop
.nl_ret_past:
    inc rax
.nl_ret:
    ret

; =============================================================
skip_ws:
.sw_loop:
    mov al, [rsi]
    cmp al, 0
    je  .sw_done
    cmp al, ' '
    je  .sw_adv
    cmp al, 9
    je  .sw_adv
    cmp al, 13
    je  .sw_adv
    cmp al, 10
    je  .sw_adv
    cmp al, ';'
    je  .sw_comment
    ret
.sw_adv:
    inc rsi
    jmp .sw_loop
.sw_comment:
    mov al, [rsi]
    test al, al
    jz  .sw_done
    inc rsi
    cmp al, 10
    jne .sw_comment
    jmp .sw_loop
.sw_done:
    ret

; =============================================================
hex_val:
    cmp al, '0'
    jb  .hv_bad
    cmp al, '9'
    jbe .hv_digit
    or  al, 0x20
    cmp al, 'a'
    jb  .hv_bad
    cmp al, 'f'
    ja  .hv_bad
    sub al, 'a' - 10
    ret
.hv_digit:
    sub al, '0'
    ret
.hv_bad:
    mov al, 16
    ret

; =============================================================
parse_hex:
    push r8
    xor r8, r8
.ph_loop:
    mov al, [rsi]
    call hex_val
    cmp al, 16
    jae .ph_done
    shl r8, 4
    movzx eax, al
    add r8, rax
    inc rsi
    jmp .ph_loop
.ph_done:
    mov rax, r8
    pop r8
    ret

; =============================================================
parse_reg:
    cmp byte [rsi], 'r'
    jne .pr_fail
    mov al, [rsi+1]
    call hex_val
    cmp al, 16
    jae .pr_fail
    movzx rax, al
    add rsi, 2
    ret
.pr_fail:
    mov rax, -1
    ret

; =============================================================
parse_labelref:
    cmp byte [rsi], ':'
    jne .plr_fail
    inc rsi
    mov rdi, rsi
    xor rdx, rdx
.plr_loop:
    mov al, [rsi]
    cmp al, 'a'
    jb  .plr_up
    cmp al, 'z'
    jbe .plr_ok
.plr_up:
    cmp al, 'A'
    jb  .plr_dig
    cmp al, 'Z'
    jbe .plr_ok
.plr_dig:
    cmp al, '0'
    jb  .plr_us
    cmp al, '9'
    jbe .plr_ok
.plr_us:
    cmp al, '_'
    je  .plr_ok
    jmp .plr_done
.plr_ok:
    inc rsi
    inc rdx
    jmp .plr_loop
.plr_done:
    test rdx, rdx
    jz  .plr_fail
    mov rax, 1
    ret
.plr_fail:
    xor eax, eax
    ret

; =============================================================
find_label:
    push rbx
    push r12
    mov r12, [label_count]
    xor rbx, rbx
.fl_loop:
    cmp rbx, r12
    jae .fl_notfound
    mov r8, rbx
    imul r8, 24
    lea r9, [label_table + r8]
    cmp qword [r9+8], rdx
    jne .fl_next
    mov r10, [r9]
    xor r8, r8
.fl_cmp:
    cmp r8, rdx
    jae .fl_match
    mov al, [r10 + r8]
    cmp al, [rdi + r8]
    jne .fl_next
    inc r8
    jmp .fl_cmp
.fl_match:
    mov rax, [r9+16]
    pop r12
    pop rbx
    ret
.fl_next:
    inc rbx
    jmp .fl_loop
.fl_notfound:
    mov rax, -1
    pop r12
    pop rbx
    ret

; =============================================================
add_label:
    push rbx
    mov rax, [label_count]
    cmp rax, LABELS_MAX
    jae .al_full
    mov rbx, rax
    imul rbx, 24
    lea rbx, [label_table + rbx]
    mov [rbx], rdi
    mov [rbx+8], rdx
    mov [rbx+16], rcx
    inc rax
    mov [label_count], rax
.al_full:
    pop rbx
    ret

; =============================================================
pass1:
    lea rsi, [src_buf]
    call next_line
    mov rsi, rax
.p1_loop:
    call skip_ws
    cmp byte [rsi], 0
    je  .p1_done
    cmp byte [rsi], '0'
    jne .p1_next
    cmp byte [rsi+1], 'x'
    jne .p1_next
    mov al, [rsi+2]
    call hex_val
    cmp al, 7
    jne .p1_next
    mov al, [rsi+3]
    call hex_val
    cmp al, 0
    jne .p1_next
    add rsi, 4
    call skip_ws
    call parse_labelref
    test rax, rax
    jz  .p1_next
    push rdi
    push rdx
    call next_line
    mov rcx, rax
    pop rdx
    pop rdi
    call add_label
    mov rsi, rcx
    jmp .p1_loop
.p1_next:
    call next_line
    mov rsi, rax
    jmp .p1_loop
.p1_done:
    ret

; =============================================================
; checksum_verify — проверка |xx в конце строки (если есть)
; вход: rbp = начало строки, rsi = указатель на начало строки
; выход: rsi восстановлен, при mismatch — exit 5
checksum_verify:
    mov rax, rsi
.cv_scan:
    mov dl, [rax]
    test dl, dl
    jz .cv_no_checksum
    cmp dl, 10
    je .cv_no_checksum
    cmp dl, ';'
    je .cv_no_checksum
    cmp dl, '|'
    je .cv_try_checksum
    cmp dl, '"'
    je .cv_skip_str
    inc rax
    jmp .cv_scan
.cv_skip_str:
    inc rax
.cv_str_loop:
    mov dl, [rax]
    test dl, dl
    jz .cv_no_checksum
    cmp dl, 10
    je .cv_no_checksum
    cmp dl, '"'
    je .cv_str_done
    cmp dl, 92
    jne .cv_str_adv
    inc rax
    mov dl, [rax]
    test dl, dl
    jz .cv_no_checksum
.cv_str_adv:
    inc rax
    jmp .cv_str_loop
.cv_str_done:
    inc rax
    jmp .cv_scan
.cv_try_checksum:
    push rax
    mov rcx, rax
    inc rcx
    mov al, [rcx]
    call hex_val
    cmp al, 16
    jae .cv_not_checksum
    inc rcx
    mov al, [rcx]
    call hex_val
    cmp al, 16
    jae .cv_not_checksum
    inc rcx
    mov al, [rcx]
    test al, al
    jz .cv_ok_format
    cmp al, 10
    je .cv_ok_format
    cmp al, 13
    je .cv_ok_format
    cmp al, ' '
    je .cv_ok_format
    cmp al, 9
    je .cv_ok_format
    cmp al, ';'
    je .cv_ok_format
.cv_not_checksum:
    pop rax
    inc rax
    jmp .cv_scan
.cv_ok_format:
    pop rax
    mov r10, rax
    mov rcx, rbp
    xor r8, r8
.cv_xor:
    cmp rcx, r10
    jae .cv_xor_done
    xor r8b, [rcx]
    inc rcx
    jmp .cv_xor
.cv_xor_done:
    lea rsi, [r10 + 1]
    call parse_hex
    cmp rax, r8
    je .cv_match
    lea rsi, [msg_csum]
    call write_str
    mov edi, 5
    mov eax, 60
    syscall
.cv_match:
    mov rsi, rbp
    ret
.cv_no_checksum:
    cmp byte [checksum_mode], 0
    je .cv_no_c_ok
    mov rax, rsi
.cv_chk_empty:
    mov dl, [rax]
    test dl, dl
    jz .cv_no_c_ok
    cmp dl, 10
    je .cv_no_c_ok
    cmp dl, ' '
    je .cv_chk_skip
    cmp dl, 9
    je .cv_chk_skip
    cmp dl, 13
    je .cv_chk_skip
    cmp dl, ';'
    je .cv_no_c_ok
    lea rsi, [msg_missing_csum]
    call write_str
    mov edi, 6
    mov eax, 60
    syscall
.cv_chk_skip:
    inc rax
    jmp .cv_chk_empty
.cv_no_c_ok:
    ret


; =============================================================
execute:
    lea rsi, [src_buf]
    call next_line
    mov rsi, rax
.exec_loop:
    mov rbp, rsi
    call checksum_verify
    call skip_ws
    cmp byte [rsi], 0
    je  .exec_done
    cmp byte [rsi], '0'
    jne .exec_bad
    cmp byte [rsi+1], 'x'
    jne .exec_bad
    add rsi, 2
    mov al, [rsi]
    call hex_val
    cmp al, 16
    jae .exec_bad
    mov bl, al
    mov al, [rsi+1]
    call hex_val
    cmp al, 16
    jae .exec_bad
    shl bl, 4
    or  bl, al
    add rsi, 2

    cmp bl, 0x00
    je  .op_nop
    cmp bl, 0x01
    je  .op_halt
    cmp bl, 0x10
    je  .op_load
    cmp bl, 0x11
    je  .op_loadm
    cmp bl, 0x12
    je  .op_store
    cmp bl, 0x13
    je  .op_storeb
    cmp bl, 0x14
    je  .op_push
    cmp bl, 0x15
    je  .op_pop
    cmp bl, 0x20
    je  .op_add
    cmp bl, 0x21
    je  .op_sub
    cmp bl, 0x22
    je  .op_mul
    cmp bl, 0x23
    je  .op_div
    cmp bl, 0x24
    je  .op_xor
    cmp bl, 0x25
    je  .op_mod
    cmp bl, 0x26
    je  .op_shl
    cmp bl, 0x27
    je  .op_shr
    cmp bl, 0x30
    je  .op_cmp
    cmp bl, 0x40
    je  .op_jmp
    cmp bl, 0x41
    je  .op_jz
    cmp bl, 0x42
    je  .op_jnz
    cmp bl, 0x43
    je  .op_call
    cmp bl, 0x44
    je  .op_ret
    cmp bl, 0x50
    je  .op_prints
    cmp bl, 0x51
    je  .op_printc
    cmp bl, 0x52
    je  .op_printi
    cmp bl, 0x60
    je  .op_syscall
    cmp bl, 0x70
    je  .op_label_def
    cmp bl, 0xA0
    je  .op_data
    jmp .exec_bad

.op_nop:
    jmp .next_instr
.op_halt:
    jmp .exec_done

.op_load:
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r14, rax
    call skip_ws
    cmp byte [rsi], '#'
    jne .exec_bad
    inc rsi
    call parse_hex
    lea rdi, [regs]
    mov [rdi + r14*8], rax
    jmp .next_instr

.op_loadm:
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r14, rax
    call skip_ws
    cmp byte [rsi], '@'
    jne .exec_bad
    inc rsi
    call parse_hex
    cmp rax, MEM_SIZE - 8
    ja  .exec_bad
    lea rdi, [mem]
    mov rcx, [rdi + rax]
    lea rdi, [regs]
    mov [rdi + r14*8], rcx
    jmp .next_instr

.op_store:
    call skip_ws
    cmp byte [rsi], '@'
    jne .exec_bad
    inc rsi
    call parse_hex
    cmp rax, MEM_SIZE - 8
    ja  .exec_bad
    mov r14, rax
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    lea rdi, [regs]
    mov rcx, [rdi + rax*8]
    lea rdi, [mem]
    mov [rdi + r14], rcx
    jmp .next_instr

.op_storeb:
    call skip_ws
    cmp byte [rsi], '@'
    jne .exec_bad
    inc rsi
    call parse_hex
    cmp rax, MEM_SIZE
    jae .exec_bad
    mov r14, rax
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    lea rdi, [regs]
    mov rcx, [rdi + rax*8]
    lea rdi, [mem]
    mov [rdi + r14], cl
    jmp .next_instr

.op_add:
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r14, rax
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    lea rdi, [regs]
    mov rcx, [rdi + rax*8]
    add [rdi + r14*8], rcx
    jmp .next_instr

.op_sub:
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r14, rax
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    lea rdi, [regs]
    mov rcx, [rdi + rax*8]
    sub [rdi + r14*8], rcx
    jmp .next_instr

.op_xor:
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r14, rax
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    lea rdi, [regs]
    mov rcx, [rdi + rax*8]
    xor [rdi + r14*8], rcx
    jmp .next_instr

.op_cmp:
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r14, rax
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    lea rdi, [regs]
    mov rcx, [rdi + r14*8]
    sub rcx, [rdi + rax*8]
    setz byte [zf]
    jmp .next_instr

.op_jmp:
    call skip_ws
    call parse_labelref
    test rax, rax
    jz  .exec_bad
    call find_label
    cmp rax, -1
    je  .exec_bad
    mov rsi, rax
    jmp .exec_loop

.op_jz:
    call skip_ws
    call parse_labelref
    test rax, rax
    jz  .exec_bad
    call find_label
    cmp rax, -1
    je  .exec_bad
    cmp byte [zf], 0
    je  .next_instr
    mov rsi, rax
    jmp .exec_loop

.op_jnz:
    call skip_ws
    call parse_labelref
    test rax, rax
    jz  .exec_bad
    call find_label
    cmp rax, -1
    je  .exec_bad
    cmp byte [zf], 0
    jne .next_instr
    mov rsi, rax
    jmp .exec_loop

.op_push:
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r14, rax
    mov rcx, [stk_ptr]
    cmp rcx, 8
    jb  .exec_bad
    sub rcx, 8
    mov [stk_ptr], rcx
    lea rdi, [regs]
    mov rax, [rdi + r14*8]
    lea rdi, [mem]
    mov [rdi + rcx], rax
    jmp .next_instr

.op_pop:
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r14, rax
    mov rcx, [stk_ptr]
    cmp rcx, MEM_SIZE
    jae .exec_bad
    lea rdi, [mem]
    mov rax, [rdi + rcx]
    lea rdi, [regs]
    mov [rdi + r14*8], rax
    add rcx, 8
    mov [stk_ptr], rcx
    jmp .next_instr

.op_call:
    call skip_ws
    call parse_labelref
    test rax, rax
    jz  .exec_bad
    call find_label
    cmp rax, -1
    je  .exec_bad
    mov r15, rax
    call next_line
    mov rcx, [stk_ptr]
    cmp rcx, 8
    jb  .exec_bad
    sub rcx, 8
    mov [stk_ptr], rcx
    lea rdi, [mem]
    mov [rdi + rcx], rax
    mov rsi, r15
    jmp .exec_loop

.op_ret:
    mov rcx, [stk_ptr]
    cmp rcx, MEM_SIZE
    jae .exec_bad
    lea rdi, [mem]
    mov rax, [rdi + rcx]
    add rcx, 8
    mov [stk_ptr], rcx
    mov rsi, rax
    jmp .exec_loop

.op_mul:
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r14, rax
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r15, rax
    lea rdi, [regs]
    mov rax, [rdi + r14*8]
    mul qword [rdi + r15*8]
    mov [rdi + r14*8], rax
    jmp .next_instr

.op_div:
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r14, rax
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r15, rax
    lea rdi, [regs]
    mov rcx, [rdi + r15*8]
    test rcx, rcx
    jz  .exec_bad
    xor edx, edx
    mov rax, [rdi + r14*8]
    div rcx
    mov [rdi + r14*8], rax
    jmp .next_instr

.op_mod:
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r14, rax
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r15, rax
    lea rdi, [regs]
    mov rcx, [rdi + r15*8]
    test rcx, rcx
    jz  .exec_bad
    xor edx, edx
    mov rax, [rdi + r14*8]
    div rcx
    mov [rdi + r14*8], rdx
    jmp .next_instr

.op_shl:
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r14, rax
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r15, rax
    lea rdi, [regs]
    mov rcx, [rdi + r15*8]
    mov rax, [rdi + r14*8]
    shl rax, cl
    mov [rdi + r14*8], rax
    jmp .next_instr

.op_shr:
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r14, rax
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    mov r15, rax
    lea rdi, [regs]
    mov rcx, [rdi + r15*8]
    mov rax, [rdi + r14*8]
    shr rax, cl
    mov [rdi + r14*8], rax
    jmp .next_instr

.op_syscall:
    push rsi
    lea rdi, [regs]
    mov rax, [rdi + 0*8]
    mov r10, [rdi + 4*8]
    mov r8,  [rdi + 5*8]
    mov r9,  [rdi + 6*8]
    mov rsi, [rdi + 2*8]
    cmp rsi, MEM_SIZE
    jae .sc_rsi_raw
    lea rbx, [mem]
    add rsi, rbx
.sc_rsi_raw:
    mov rdx, [rdi + 3*8]
    mov rdi, [rdi + 1*8]
    syscall
    pop rsi
    lea rdi, [regs]
    mov [rdi + 0*8], rax
    jmp .next_instr

.op_prints:
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    lea rdi, [regs]
    mov rax, [rdi + rax*8]
    cmp rax, MEM_SIZE
    jae .exec_bad
    push rsi
    lea rsi, [mem]
    add rsi, rax
    call write_str
    pop rsi
    jmp .next_instr

.op_printc:
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    lea rdi, [regs]
    mov rax, [rdi + rax*8]
    call write_char
    jmp .next_instr

.op_printi:
    call skip_ws
    call parse_reg
    cmp rax, -1
    je  .exec_bad
    lea rdi, [regs]
    mov rax, [rdi + rax*8]
    call write_int
    jmp .next_instr

.op_label_def:
    jmp .next_instr

.op_data:
    call skip_ws
    cmp byte [rsi], '@'
    jne .exec_bad
    inc rsi
    call parse_hex
    cmp rax, MEM_SIZE
    jae .exec_bad
    mov r14, rax
    call skip_ws
    cmp byte [rsi], '"'
    jne .exec_bad
    inc rsi
    lea rdi, [mem]
    add rdi, r14
.data_copy:
    mov al, [rsi]
    test al, al
    jz  .exec_bad
    cmp al, '"'
    je  .data_end
    cmp al, '\'
    jne .data_store
    inc rsi
    mov al, [rsi]
    cmp al, 'n'
    jne .data_t
    mov al, 10
    jmp .data_store
.data_t:
    cmp al, 't'
    jne .data_z
    mov al, 9
    jmp .data_store
.data_z:
    cmp al, '0'
    jne .data_store
    xor al, al
.data_store:
    lea rcx, [mem + MEM_SIZE]
    cmp rdi, rcx
    jae .exec_bad
    mov [rdi], al
    inc rdi
    inc rsi
    jmp .data_copy
.data_end:
    inc rsi
    jmp .next_instr

.next_instr:
    call next_line
    mov rsi, rax
    jmp .exec_loop

.exec_bad:
    lea rsi, [msg_bad]
    call write_str
    mov edi, 4
    mov eax, 60
    syscall

.exec_done:
    ret

; =============================================================
segment readable writeable

src_buf:     rb SRC_MAX
mem:         rb MEM_SIZE
regs:        rq 16
zf:          db 0
label_count: dq 0
label_table: rb LABELS_MAX * 24
tmp_char:    db 0
stk_ptr:     dq MEM_SIZE
checksum_mode: db 0
tmp_num:     rb 32

hdr_str: db '0xF4CK 0xFF B1N', 0xC7, 0x8E, 'RY'
hdr_len = $ - hdr_str

msg_usage: db 'FOB v0.3 | usage: fob [-c] <file.fob>', 10, 0
msg_open:  db 'FOB: cannot open file', 10, 0
msg_hdr:   db 'FOB: invalid header', 10, 0
msg_bad:   db 'FOB: syntax error', 10, 0
msg_csum:  db 'FOB: checksum mismatch', 10, 0
msg_missing_csum: db 'FOB: missing checksum (-c mode)', 10, 0
