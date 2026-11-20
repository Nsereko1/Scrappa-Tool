import os
import sys

OUTPUT = "project_dump.txt"

# Folders to skip
SKIP_DIRS = {
    ".git", "__pycache__", "venv", ".venv", "env", "node_modules",
    ".idea", ".vscode", "dist", "build", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "migrations_backup", "staticfiles", "media", ".next",
}

# Only include these file types
INCLUDE_EXT = {
    ".py", ".html", ".css", ".js", ".ts", ".jsx", ".tsx", ".json",
    ".yml", ".yaml", ".toml", ".ini", ".cfg", ".md", ".txt", ".sql",
    ".sh", ".bat", ".dockerfile",
}
INCLUDE_NAMES = {"Dockerfile", "Procfile", "requirements.txt", "Makefile"}

# Never include secrets or noise
SKIP_FILES = {".env", ".env.local", ".env.production", "secrets.json",
              "package-lock.json", "yarn.lock", "poetry.lock", OUTPUT,
              os.path.basename(__file__)}

MAX_FILE_BYTES = 200_000  # skip huge files


def should_include(name):
    if name in SKIP_FILES or name.startswith(".env"):
        return False
    ext = os.path.splitext(name)[1].lower()
    return name in INCLUDE_NAMES or ext in INCLUDE_EXT


def build_tree(root):
    lines = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        depth = os.path.relpath(dirpath, root).count(os.sep)
        if dirpath != root:
            lines.append("    " * (depth - 1) + f"{os.path.basename(dirpath)}/")
        indent = "    " * depth
        for f in sorted(filenames):
            if should_include(f):
                lines.append(f"{indent}{f}")
    return "\n".join(lines)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    root = os.path.abspath(root)
    files = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for f in sorted(filenames):
            if should_include(f):
                files.append(os.path.join(dirpath, f))

    with open(OUTPUT, "w", encoding="utf-8") as out:
        out.write(f"PROJECT: {os.path.basename(root)}\n")
        out.write("=" * 70 + "\nSKELETON\n" + "=" * 70 + "\n")
        out.write(build_tree(root) + "\n\n")

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
            out.write(f"\n{'=' * 70}\nFILE: {rel}\n{'=' * 70}\n{content}\n")

    print(f"Done: {len(files)} files written to {OUTPUT}")


if __name__ == "__main__":
    main()