import gzip
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import backup  # noqa: E402

NOW = datetime(2026, 11, 19, 10, 0, 0)


def test_write_and_verify_roundtrip(tmp_path):
    p = backup.write_backup(b"SELECT 1;", tmp_path, NOW)
    assert p.name == "faceless-20261119-100000.sql.gz" and backup.verify_backup(p)
    assert gzip.decompress(p.read_bytes()) == b"SELECT 1;"
    assert (tmp_path / (p.name + ".sha256")).exists()


def test_verify_detects_corruption(tmp_path):
    p = backup.write_backup(b"SELECT 1;", tmp_path, NOW)
    p.write_bytes(p.read_bytes() + b"x")
    assert not backup.verify_backup(p)


def test_verify_fails_without_checksum_or_file(tmp_path):
    p = backup.write_backup(b"SELECT 1;", tmp_path, NOW)
    (tmp_path / (p.name + ".sha256")).unlink()
    assert not backup.verify_backup(p)
    assert not backup.verify_backup(tmp_path / "nao-existe.sql.gz")


def test_empty_dump_is_refused(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        backup.write_backup(b"", tmp_path, NOW)


def test_restore_requires_yes_and_verified_file(tmp_path):
    p = backup.write_backup(b"SELECT 1;", tmp_path, NOW)
    assert backup.main(["restore", str(p)]) != 0  # sem --yes
    p.write_bytes(p.read_bytes() + b"x")
    assert backup.main(["restore", str(p), "--yes"]) != 0  # arquivo corrompido nunca é restaurado


def test_verify_command_exit_codes(tmp_path):
    p = backup.write_backup(b"SELECT 1;", tmp_path, NOW)
    assert backup.main(["verify", str(p)]) == 0
    p.write_bytes(b"lixo")
    assert backup.main(["verify", str(p)]) == 1
