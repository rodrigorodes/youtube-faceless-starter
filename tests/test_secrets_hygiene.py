from pathlib import Path
import re
import shutil
import subprocess
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repository(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "scripts").mkdir()
    for name in ("check-secrets.sh", "package-starter.sh"):
        source = ROOT / "scripts" / name
        if source.exists():
            shutil.copy(source, tmp_path / "scripts" / name)
    return tmp_path


def run_script(repo, name, *args):
    return subprocess.run(
        ["bash", str(ROOT / "scripts" / name), *map(str, args)],
        cwd=repo, text=True, capture_output=True,
    )


def track(repo, name, content):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-f", "--", name], cwd=repo, check=True)


def test_scanner_ignores_local_untracked_credentials(repository):
    track(repository, "app.py", "print('ok')\n")
    (repository / "credentials").mkdir()
    (repository / "credentials" / "client_secret.json").write_text("local")
    result = run_script(repository, "check-secrets.sh")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("value", [
    "sk-" + "x" * 32,
    "AIzaSy" + "x" * 33,
    "Bearer " + "x" * 32,
    "Bearer " + "x" * 19,
    'client_secret = "' + "x" * 32 + '"',
    'client_secret = "' + "x" * 15 + '"',
    '"refresh_token": "' + "y" * 15 + '"',
])
def test_scanner_rejects_tracked_secret_without_printing_it(repository, value):
    track(repository, "app.py", value)
    result = run_script(repository, "check-secrets.sh")
    assert result.returncode == 1
    assert value not in result.stdout + result.stderr


@pytest.mark.parametrize("value", [
    'client_secret = ""',
    'client_secret = "YOUR_CLIENT_SECRET"',
    'client_secret = "CHANGE_ME_CLIENT_SECRET"',
    '"refresh_token": "<refresh_token>"',
    'refresh_token = "YOUR_REFRESH_TOKEN"',
    "Authorization: Bearer <token>",
    "Authorization: Bearer YOUR_ACCESS_TOKEN",
])
def test_scanner_accepts_safe_placeholders(repository, value):
    track(repository, "example.txt", value)
    result = run_script(repository, "check-secrets.sh")
    assert result.returncode == 0, result.stderr


def test_scanner_rejects_tracked_sensitive_filename(repository):
    track(repository, "backups/example.sql", "not a secret")
    assert run_script(repository, "check-secrets.sh").returncode == 1


def test_scanner_rejects_gitkeep_under_credentials(repository):
    track(repository, "renderer/credentials/.gitkeep", "private")
    assert run_script(repository, "check-secrets.sh").returncode == 1


def test_scanner_refuses_symlinked_parent_directory(repository):
    track(repository, "app/file.py", "clean")
    (repository / "app" / "file.py").unlink()
    (repository / "app").rmdir()
    (repository / "elsewhere").mkdir()
    (repository / "elsewhere" / "file.py").write_text("clean")
    (repository / "app").symlink_to(repository / "elsewhere", target_is_directory=True)
    assert run_script(repository, "check-secrets.sh").returncode == 1


def test_scanner_checks_staged_version_even_if_worktree_was_cleaned(repository):
    track(repository, "app.py", "sk-" + "x" * 32)
    (repository / "app.py").write_text("clean")
    assert run_script(repository, "check-secrets.sh").returncode == 1


def test_scanner_accepts_schema_migration_and_test_bearer(repository):
    track(repository, "renderer/migrations/001.sql", "CREATE TABLE example (id INT);")
    track(repository, "tests/auth.py", '"Bearer test-' + 'worker-token"')
    assert run_script(repository, "check-secrets.sh").returncode == 0


def test_starter_zip_excludes_local_and_non_allowlisted_files(repository, tmp_path):
    track(repository, "renderer/app/main.py", "print('ok')\n")
    track(repository, ".env.example", "API_KEY=\n")
    track(repository, "other/private.txt", "not for distribution")
    (repository / "renderer" / "app" / "local.pem").write_text("local")
    (repository / ".env").write_text("private")
    archive = tmp_path / "starter.zip"
    result = run_script(repository, "package-starter.sh", archive)
    assert result.returncode == 0, result.stderr
    with zipfile.ZipFile(archive) as zf:
        assert set(zf.namelist()) == {"renderer/app/main.py", ".env.example"}


def test_packager_refuses_tracked_secret(repository, tmp_path):
    track(repository, "renderer/app/main.py", "sk-" + "x" * 32)
    archive = tmp_path / "starter.zip"
    result = run_script(repository, "package-starter.sh", archive)
    assert result.returncode != 0
    assert not archive.exists()


def test_package_excludes_data_backups_and_archives_even_when_tracked(repository, tmp_path):
    track(repository, "renderer/app/main.py", "print('ok')")
    for name in ("docs/customer-export.csv", "renderer/archive.sql", "tests/backup.zip",
                 "examples/customer.json", "docs/customer-export.md"):
        track(repository, name, "DISTRIBUTION_SENTINEL")
    archive = tmp_path / "starter.zip"
    result = run_script(repository, "package-starter.sh", archive)
    assert result.returncode == 0, result.stderr
    with zipfile.ZipFile(archive) as zf:
        assert set(zf.namelist()) == {"renderer/app/main.py"}
        assert all(b"DISTRIBUTION_SENTINEL" not in zf.read(name) for name in zf.namelist())


def test_package_keeps_only_explicit_schema_workflow_and_migration_formats(repository, tmp_path):
    track(repository, "contracts/v1/video.schema.json", "{}")
    track(repository, "workflows/03-publish-approved.json", "{}")
    track(repository, "renderer/app/studio/adapters/postgres/migrations/0001_init.sql", "CREATE TABLE x (id INT);")
    track(repository, "contracts/v1/customer.json", "{}")
    track(repository, "workflows/customer.json", "{}")
    archive = tmp_path / "starter.zip"
    assert run_script(repository, "package-starter.sh", archive).returncode == 0
    with zipfile.ZipFile(archive) as zf:
        assert set(zf.namelist()) == {
            "contracts/v1/video.schema.json", "workflows/03-publish-approved.json",
            "renderer/app/studio/adapters/postgres/migrations/0001_init.sql",
        }


def test_package_contains_expected_file_bytes_not_local_untracked_content(repository, tmp_path):
    track(repository, "renderer/app/main.py", "EXPECTED_SOURCE\n")
    (repository / "renderer/app/local.py").write_text("LOCAL_PRIVATE_SENTINEL")
    archive = tmp_path / "starter.zip"
    assert run_script(repository, "package-starter.sh", archive).returncode == 0
    with zipfile.ZipFile(archive) as zf:
        assert zf.read("renderer/app/main.py") == b"EXPECTED_SOURCE\n"
        assert all(b"LOCAL_PRIVATE_SENTINEL" not in zf.read(name) for name in zf.namelist())


def test_real_starter_archive_is_safe_and_keeps_scripts_executable(tmp_path):
    archive = tmp_path / "starter.zip"
    result = run_script(ROOT, "package-starter.sh", archive)
    assert result.returncode == 0, result.stderr
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        assert ".env.example" in names
        assert "scripts/check-secrets.sh" in names
        assert zf.getinfo("scripts/check-secrets.sh").external_attr >> 16 & 0o111
        assert not any(
            set(Path(name).parts) & {"credentials", "backups", "storage", ".git"}
            or Path(name).name == ".env"
            or Path(name).suffix in {".pem", ".key", ".dump", ".csv", ".zip", ".gz", ".tar"}
            or (name.endswith(".sql") and not name.startswith(
                "renderer/app/studio/adapters/postgres/migrations/"))
            for name in names
        )
        # Independently inspect decompressed bytes, without importing scanner rules
        # or including a matched value in a failure message.
        key = re.compile(rb"sk-[A-Za-z0-9_-]{20,}")
        google_key = re.compile(rb"AIzaSy[A-Za-z0-9_-]{30,}")
        private_key = b"-----BEGIN " + b"PRIVATE KEY-----"
        assert not any(
            key.search(data) or google_key.search(data) or private_key in data
            for data in (zf.read(name) for name in names)
        ), "A packaged file contains sensitive-looking content"
        env = zf.read(".env.example").decode("utf-8")
        assert re.search(r"(?m)^GEMINI_API_KEY=$", env)
        assert re.search(r"(?m)^PEXELS_API_KEY=$", env)
