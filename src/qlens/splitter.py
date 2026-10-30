"""Split q source into top-level statements the way q's script loader does.

Rules (SPEC section 4.2):
- a line starting in column 0 begins a statement; indented lines continue it
- a line `/` alone starts a block comment; a line `\\` alone ends it
- a lone `\\` outside a block comment ends the script
- `/ comment` lines and trailing ` /` comments are stripped
- backslash commands (`\\l f.q`, `\\d .ns`, `\\w`) are normalised to `system "..."`
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Statement:
    text: str  # comments stripped, continuation lines joined with "\n"
    line: int  # 1-based first line
    end_line: int  # 1-based last line


def strip_comment(line: str) -> str:
    """Remove a trailing ` /` comment, respecting string literals."""
    in_str = False
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "/" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
        i += 1
    return line.rstrip()


def normalise_backslash(text: str) -> str:
    r"""`\l f.q` -> `system "l f.q"`. Other text is returned unchanged."""
    if not text.startswith("\\") or len(text) < 2:
        return text
    body = text[1:]
    escaped = body.replace("\\", "\\\\").replace('"', '\\"')
    return f'system "{escaped}"'


def split_statements(source: str) -> list[Statement]:
    out: list[Statement] = []
    cur: list[str] = []
    start = 0
    last = 0
    in_block = False

    def flush() -> None:
        nonlocal cur
        if cur:
            text = "\n".join(cur).rstrip()
            if text.strip():
                out.append(Statement(normalise_backslash(text), start, last))
            cur = []

    for no, raw in enumerate(source.splitlines(), start=1):
        line = raw.rstrip("\r")
        if in_block:
            if line.rstrip() == "\\":
                in_block = False
            continue
        if line.rstrip() == "/" and line[:1] == "/":
            flush()
            in_block = True
            continue
        if line.rstrip() == "\\":
            break  # lone backslash outside a block ends the script
        if line.startswith("\\\\"):
            break  # `\\` exits the process; nothing after it loads
        if not line.strip():
            continue
        if line[0] in " \t":
            body = strip_comment(line)
            if not body.strip():
                continue
            if cur:
                cur.append(body)
                last = no
            else:
                # indented line with no open statement: q treats it as a new statement
                start = last = no
                cur = [body.lstrip()]
            continue
        if line[0] == "/":
            continue  # comment line
        flush()
        body = strip_comment(line)
        if not body.strip():
            continue
        start = last = no
        cur = [body]
    flush()
    return out
