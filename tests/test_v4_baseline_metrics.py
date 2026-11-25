"""Testes unitários pequenos para os validadores e coleta de métricas da V4-00."""
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "renderer"))

from scripts.render_v4_baseline import (
    measure_dir_size_bytes,
    measure_resources_usage,
    sha256_file,
    validate_duration,
    validate_qa_criteria,
)


def test_validate_duration_accepts_valid_range():
    validate_duration(63.8, 60.0, 90.0, "Fixture")
    validate_duration(350.5, 300.0, 480.0, "Piloto")


def test_validate_duration_rejects_below_min():
    with pytest.raises(ValueError, match="fora do limite de homologação"):
        validate_duration(59.9, 60.0, 90.0, "Fixture Curta")

    with pytest.raises(ValueError, match="fora do limite de homologação"):
        validate_duration(266.64, 300.0, 480.0, "Piloto Insuficiente")


def test_validate_duration_rejects_above_max():
    with pytest.raises(ValueError, match="fora do limite de homologação"):
        validate_duration(90.1, 60.0, 90.0, "Fixture Longa")

    with pytest.raises(ValueError, match="fora do limite de homologação"):
        validate_duration(485.0, 300.0, 480.0, "Piloto Excessivo")


def test_validate_qa_criteria_accepts_valid():
    valid_qa = {
        "black_ratio": 0.0,
        "frozen_ratio": 0.05,
        "integrated_lufs": -15.5,
        "true_peak_dbtp": -1.2,
    }
    validate_qa_criteria(valid_qa, "Teste Valido")


def test_validate_qa_criteria_rejects_black_ratio():
    bad_qa = {
        "black_ratio": 0.02,
        "frozen_ratio": 0.0,
        "integrated_lufs": -16.0,
        "true_peak_dbtp": -1.0,
    }
    with pytest.raises(ValueError, match="black_ratio=0.02"):
        validate_qa_criteria(bad_qa, "Teste Black")


def test_validate_qa_criteria_rejects_high_frozen_ratio():
    bad_qa = {
        "black_ratio": 0.0,
        "frozen_ratio": 0.95,
        "integrated_lufs": -16.0,
        "true_peak_dbtp": -1.0,
    }
    with pytest.raises(ValueError, match="frozen_ratio=0.95"):
        validate_qa_criteria(bad_qa, "Teste Freeze")


def test_validate_qa_criteria_rejects_lufs_out_of_range():
    too_loud = {
        "black_ratio": 0.0,
        "frozen_ratio": 0.0,
        "integrated_lufs": -12.0,
        "true_peak_dbtp": -1.0,
    }
    with pytest.raises(ValueError, match="integrated_lufs=-12.0"):
        validate_qa_criteria(too_loud, "Teste Loud")

    too_quiet = {
        "black_ratio": 0.0,
        "frozen_ratio": 0.0,
        "integrated_lufs": -26.0,
        "true_peak_dbtp": -1.0,
    }
    with pytest.raises(ValueError, match="integrated_lufs=-26.0"):
        validate_qa_criteria(too_quiet, "Teste Quiet")


def test_validate_qa_criteria_rejects_positive_true_peak():
    clipping_qa = {
        "black_ratio": 0.0,
        "frozen_ratio": 0.0,
        "integrated_lufs": -16.0,
        "true_peak_dbtp": 0.5,
    }
    with pytest.raises(ValueError, match="true_peak_dbtp=0.5 dBTP"):
        validate_qa_criteria(clipping_qa, "Teste Clipping")


def test_measure_resources_usage_structure():
    usage = measure_resources_usage()
    assert "cpu_user_seconds" in usage
    assert "cpu_system_seconds" in usage
    assert "cpu_total_seconds" in usage
    assert "peak_rss_self_mb" in usage
    assert "peak_rss_combined_mb" in usage
    assert usage["cpu_total_seconds"] >= 0.0
    assert usage["peak_rss_combined_mb"] > 0.0


def test_measure_dir_size_and_sha256(tmp_path):
    sub = tmp_path / "subdir"
    sub.mkdir()
    f1 = sub / "file1.txt"
    f1.write_bytes(b"hello world")
    f2 = sub / "file2.bin"
    f2.write_bytes(b"\x00\x01\x02\x03")

    total_bytes = measure_dir_size_bytes(sub)
    assert total_bytes == len(b"hello world") + 4

    h = sha256_file(f1)
    # sha256 of "hello world" is b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9
    assert h == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
