import datetime
import os
import re
import sys

OUTPUT = "project_dump.txt"

SKIP_DIRS = {
    ".git", "__pycache__", "venv", ".venv", "env", "node_modules", ".idea",
    ".vscode", "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "_backup_before_fix", "dashboard_OLD_streamlit",   # remove from here to include them
}
INCLUDE_EXT = {
    ".py", ".html", ".css", ".js", ".ts", ".json", ".yml", ".yaml", ".toml",
    ".ini", ".cfg", ".md", ".txt", ".sql", ".sh",
}
INCLUDE_NAMES = {"Dockerfile", "Procfile", "requirements.txt", "Makefile"}
SKIP_FILES = {"package-lock.json", "yarn.lock", "poetry.lock", OUTPUT,
              os.path.basename(__file__)}
MAX_FILE_BYTES = 200_000

# masks values like api_key = "abc123..." so secrets never reach the dump
SECRET_RE = re.compile(
    r"""(?i)((?:api[_-]?key|secret|token|password|client[_-]?id|client[_-]?secret)\w*\s*[=:]\s*)(["'])[^"'\n]{6,}\2"""
)


def should_include(name, path):
    if name in SKIP_FILES or name.startswith(".env") or name.startswith("debug_"):
        return False
    ext = os.path.splitext(name)[1].lower()
    if not (name in INCLUDE_NAMES or ext in INCLUDE_EXT):
        return False
    if os.path.getsize(path) == 0 and name != "__init__.py":
        return False   # skips stray empty files
    return True


def collect(root):
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for f in sorted(filenames):
            p = os.path.join(dirpath, f)
            if should_include(f, p):
                files.append(p)
    return files


def build_tree(root, files):
    rels = sorted(os.path.relpath(p, root).split(os.sep) for p in files)
    lines, printed = [], set()
    for parts in rels:
        for depth in range(len(parts) - 1):
            key = tuple(parts[: depth + 1])
            if key not in printed:
                printed.add(key)
                lines.append("    " * depth + parts[depth] + "/")
        lines.append("    " * (len(parts) - 1) + parts[-1])
    return "\n".join(lines)


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    files = collect(root)
    total_lines = 0

    with open(OUTPUT, "w", encoding="utf-8") as out:
        out.write(f"PROJECT: {os.path.basename(root)}\n")
        out.write(f"GENERATED: {datetime.datetime.now():%Y-%m-%d %H:%M}\n")
        out.write("=" * 70 + "\nSKELETON\n" + "=" * 70 + "\n")
        out.write(build_tree(root, files) + "\n")

        for path in files:
            rel = os.path.relpath(path, root)
            if os.path.getsize(path) > MAX_FILE_BYTES:
                out.write(f"\n{'=' * 70}\nFILE: {rel}  [SKIPPED: too large]\n")
                continue
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    content = fh.read()
            except (UnicodeDecodeError, OSError):
                continue
            content = SECRET_RE.sub(r"\1\2***REDACTED***\2", content)
            total_lines += content.count("\n")
            out.write(f"\n{'=' * 70}\nFILE: {rel}\n{'=' * 70}\n{content}\n")

    print(f"Done: {len(files)} files, ~{total_lines:,} lines -> {OUTPUT}")


if __name__ == "__main__":
    main()
