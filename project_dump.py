#!/usr/bin/env python3
"""project_dump.py - bundle a project's tree + source into shareable text files."""
import argparse, re
from pathlib import Path

IGNORE_DIRS = {".git", ".venv", "venv", "env", "__pycache__", "node_modules", ".idea",
               ".vscode", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
               "site-packages", ".tox", "htmlcov", ".next"}
INCLUDE_EXT = {".py", ".pyi", ".toml", ".cfg", ".ini", ".txt", ".md", ".yml", ".yaml",
               ".json", ".sql", ".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".sh", ".bat"}
INCLUDE_NAMES = {"Dockerfile", "Makefile", "Procfile", ".env.example", ".gitignore"}
BLOCK_NAMES = {".env"}
BLOCK_EXT = {".pem", ".key", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3", ".lock", ".pyc"}

SECRET_RES = [
    re.compile(r'(?i)((?:api[_-]?key|secret|token|passw(?:or)?d|private[_-]?key|dsn)\w*\s*[:=]\s*)(["\']?)[^\s"\']{6,}\2'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'sk-[A-Za-z0-9_-]{20,}'),
    re.compile(r'(?i)(postgres|mysql|mongodb|redis)(\+\w+)?://[^\s"\']+'),
]

def redact(text):
    text = SECRET_RES[0].sub(r'\1\2<REDACTED>\2', text)
    for rx in SECRET_RES[1:]:
        text = rx.sub('<REDACTED>', text)
    return text

def walk(root):
    for p in sorted(root.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        if p.is_dir():
            if p.name in IGNORE_DIRS or p.name.endswith(".egg-info"):
                continue
            yield from walk(p)
        else:
            yield p

def wanted(p, max_bytes):
    if p.name in BLOCK_NAMES or p.suffix.lower() in BLOCK_EXT:
        return False
    if not (p.suffix.lower() in INCLUDE_EXT or p.name in INCLUDE_NAMES):
        return False
    return p.stat().st_size <= max_bytes

def tree(files, root):
    lines, seen = [], set()
    for f in files:
        parts = f.relative_to(root).parts
        for i in range(len(parts)):
            if parts[:i + 1] not in seen:
                seen.add(parts[:i + 1])
                lines.append("  " * i + parts[i] + ("/" if i < len(parts) - 1 else ""))
    return "\n".join(lines)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("-o", "--out", default="project_dump")
    ap.add_argument("--max-file-kb", type=int, default=200)
    ap.add_argument("--chunk-kb", type=int, default=120, help="split output into parts of this size")
    a = ap.parse_args()

    root = Path(a.root).resolve()
    files = list(walk(root))
    blocks = [f"# PROJECT: {root.name}\n\n## FILE TREE\n{tree(files, root)}\n\n## SOURCE\n"]
    skipped = []
    for f in files:
        if not wanted(f, a.max_file_kb * 1024):
            skipped.append(str(f.relative_to(root)))
            continue
        try:
            body = redact(f.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError):
            skipped.append(str(f.relative_to(root)))
            continue
        n = body.count("\n") + 1
        blocks.append(f"\n===== FILE: {f.relative_to(root).as_posix()} ({n} lines) =====\n{body}\n")
    blocks.append("\n## SKIPPED (binary/large/blocked)\n" + "\n".join(skipped) + "\n")

    parts, cur, size = [], [], 0
    for b in blocks:
        if cur and size + len(b) > a.chunk_kb * 1024:
            parts.append("".join(cur)); cur, size = [], 0
        cur.append(b); size += len(b)
    parts.append("".join(cur))

    for i, p in enumerate(parts, 1):
        out = Path(f"{a.out}_part{i}.txt")
        out.write_text(f"[PART {i}/{len(parts)}]\n{p}", encoding="utf-8")
        print(f"wrote {out} ({len(p)//1024} KB)")

if __name__ == "__main__":
    main()