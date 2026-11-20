from pathlib import Path
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
    'client_secret = "' + "x" * 32 + '"',
])
def test_scanner_rejects_tracked_secret_without_printing_it(repository, value):
    track(repository, "app.py", value)
    result = run_script(repository, "check-secrets.sh")
    assert result.returncode == 1
    assert value not in result.stdout + result.stderr


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
            or Path(name).suffix in {".pem", ".key", ".dump"}
            for name in names
        )
