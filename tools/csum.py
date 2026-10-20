#!/usr/bin/env python3
"""Add/update |xx checksums on FOB lines. Header kept verbatim + \n."""
import sys, pathlib

def csum(data: bytes) -> int:
    h = 0
    for b in data:
        h ^= b
    return h

def process(path: str) -> bytes:
    data = pathlib.Path(path).read_bytes()
    lines = data.split(b'\n')
    if lines and lines[-1] == b'':
        lines = lines[:-1]
    out = []
    for idx, line in enumerate(lines):
        if idx == 0:
            # header — checksum never added, but \n is mandatory
            out.append(line + b'\n')
            continue
        bar, in_str, esc = -1, False, False
        for i, ch in enumerate(line):
            if esc:
                esc = False; continue
            if in_str:
                if ch == 0x5c:  esc = True
                elif ch == 0x22: in_str = False
            else:
                if ch == 0x3b: break           # comment
                if ch == 0x22: in_str = True
                elif ch == 0x7c: bar = i; break
        if bar >= 0:
            line = line[:bar]
        content = line.strip()
        if not content or content.startswith(b';'):
            out.append(line + b'\n')
            continue
        out.append(line + b'|' + f'{csum(line):02X}'.encode() + b'\n')
    return b''.join(out)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    t = sys.argv[-1]
    r = process(t)
    if '--stdout' in sys.argv:
        sys.stdout.buffer.write(r)
    else:
        pathlib.Path(t).write_bytes(r)
        print(f"updated {t}")
