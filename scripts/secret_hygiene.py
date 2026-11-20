#!/usr/bin/env python3
"""Scan tracked files and create a minimal starter archive without exposing matches."""
import re
import subprocess
import sys
import zipfile
from pathlib import Path


PATTERNS = (
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"AIzaSy[A-Za-z0-9_-]{30,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
TOKEN_PATTERNS = (
    re.compile(rb"Bearer\s+([A-Za-z0-9._~+/-]{12,})", re.I),
    re.compile(rb"""(?:client_secret|refresh_token)["']?\s*[:=]\s*["']?([A-Za-z0-9._~+/-]{12,})""", re.I),
)
SAFE_TOKENS = {b"test-worker-token", b"test-browser-password", b"your_client_secret",
               b"your_refresh_token", b"your_access_token", b"change_me_client_secret",
               b"change_me", b"placeholder"}
ALLOWED_FILES = {".env.example", ".gitignore", ".gitattributes", "README.md",
                 "requirements-dev.txt", "docker-compose.yml",
                 "docker-compose.test.yml", "docker-compose.vertex.yml",
                 "renderer/Dockerfile", "renderer/requirements.txt",
                 "examples/ade-2026-publish.json", "examples/ade-2026-rich-publish.json",
                 "examples/rich-smoke.json", "workflows/03-publish-approved.json",
                 "workflows/04-analytics-daily.json", "workflows/05-trends-daily.json"}
BLOCKED_DIRS = {".git", "credentials", "backups", "storage", "__pycache__", ".pytest_cache"}
KEEP_FILES = {"backups/.gitkeep", "storage/jobs/.gitkeep", "storage/output/.gitkeep"}


def git(*args):
    return subprocess.run(["git", *args], check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL).stdout


def blocked(path):
    p = Path(path)
    name = p.name.lower()
    return (bool(set(part.lower() for part in p.parts) & BLOCKED_DIRS)
            and path not in KEEP_FILES
            or name == ".env" or name.startswith(".env.") and name != ".env.example"
            or name.endswith((".pem", ".key", ".dump", ".credentials.json"))
            or "id_rsa" in name or name.startswith("client_secret"))


def has_secret(data):
    return (any(pattern.search(data) for pattern in PATTERNS)
            or any(match.group(1).lower() not in SAFE_TOKENS
                   for pattern in TOKEN_PATTERNS for match in pattern.finditer(data)))


def distributable(path):
    p = Path(path)
    if path in ALLOWED_FILES:
        return True
    if any(part.startswith(".") for part in p.parts):
        return False
    if re.search(r"(?:backup|archive|export|dump)", p.name, re.I):
        return False
    parts = p.parts
    suffix = p.suffix.lower()
    if parts[0] == "renderer":
        if len(parts) >= 3 and parts[1] == "app" and suffix == ".py":
            return True
        return (len(parts) == 7
                and parts[1:6] == ("app", "studio", "adapters", "postgres", "migrations")
                and re.fullmatch(r"[0-9]{4}_[a-z0-9_]+\.sql", p.name) is not None)
    if parts[:2] == ("contracts", "v1") and len(parts) == 3:
        return re.fullmatch(r"[a-z0-9_]+\.schema\.json", p.name) is not None
    allowed_extensions = {"docs": {".md"}, "scripts": {".py", ".sh", ".ps1"},
                          "tests": {".py"}}
    return len(parts) >= 2 and suffix in allowed_extensions.get(parts[0], set())


def tracked():
    root = Path(git("rev-parse", "--show-toplevel").decode().strip())
    entries = git("ls-files", "--stage", "-z").split(b"\0")
    result = []
    for entry in filter(None, entries):
        meta, raw_path = entry.split(b"\t", 1)
        mode, oid, stage = meta.split()
        if stage != b"0" or mode == b"120000":
            raise ValueError("Unmerged files or symlinks cannot be scanned safely")
        path = raw_path.decode("utf-8")
        index_data = git("cat-file", "blob", oid.decode())
        file = root / path
        relative_parents = list(file.parents)[:len(Path(path).parts) - 1]
        if file.is_symlink() or any(p.is_symlink() for p in relative_parents) or not file.is_file():
            raise ValueError("Tracked file missing or not a regular file")
        result.append((path, index_data, file.read_bytes()))
    return result


def scan(entries):
    failures = sum(blocked(path) or has_secret(index) or has_secret(worktree)
                   for path, index, worktree in entries)
    if failures:
        print(f"Secret hygiene check failed: {failures} tracked file(s) require review.",
              file=sys.stderr)
        return False
    return True


def main():
    try:
        if len(sys.argv) < 2 or sys.argv[1] not in {"scan", "package"}:
            raise ValueError("Usage: check-secrets.sh OR package-starter.sh OUTPUT.zip")
        if sys.argv[1] == "package" and len(sys.argv) != 3:
            raise ValueError("Usage: package-starter.sh OUTPUT.zip")
        entries = tracked()
        if not scan(entries):
            return 1
        if sys.argv[1] == "package":
            output = Path(sys.argv[2]).resolve()
            if output.exists():
                raise ValueError("Output already exists; choose a new path")
            selected = [(path, data) for path, _, data in entries
                        if distributable(path)]
            # Scan precisely the bytes written to the artifact, not just filenames.
            if any(blocked(path) or has_secret(data) for path, data in selected):
                raise ValueError("Unsafe artifact content")
            root = Path(git("rev-parse", "--show-toplevel").decode().strip())
            with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
                for path, data in selected:
                    info = zipfile.ZipInfo(path)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    permissions = 0o755 if (root / path).stat().st_mode & 0o111 else 0o644
                    info.external_attr = (0o100000 | permissions) << 16
                    archive.writestr(info, data)
        print("Secret hygiene check passed.")
        return 0
    except (ValueError, OSError, UnicodeError, subprocess.CalledProcessError):
        print("Secret hygiene check could not complete safely.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
