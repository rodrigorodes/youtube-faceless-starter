import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.contracts import VideoFormat  # noqa: E402
from app.studio.domain.policy import CostRefused, QaMetrics, check_cost, evaluate_qa  # noqa: E402

GOOD = QaMetrics(duration_s=100, width=1080, height=1920, loudness_lufs=-16.0, max_silence_s=1.0, max_black_s=0.0,
                 has_audio=True, disclosure_in_video=True, disclosure_in_description=True, unsourced_claims=0, paid_assets_without_cap=0)


def test_zero_cap_accepts_only_free():
    check_cost(0.0, 0.0, 0.0)
    with pytest.raises(CostRefused):
        check_cost(0.01, 0.0, 0.0)


@pytest.mark.parametrize("bad", [None, -1.0, float("nan"), float("inf")])
def test_bad_estimate_is_refused_never_zero(bad):
    with pytest.raises(CostRefused):
        check_cost(bad, 0.0, 5.0)


def test_video_cap_and_monthly_cap():
    with pytest.raises(CostRefused):
        check_cost(1.0, 4.5, 5.0)
    with pytest.raises(CostRefused):  # estoura os US$ 15 do mês
        check_cost(1.0, 0.0, 5.0, spent_month_usd=14.5)
    check_cost(0.5, 0.0, 5.0, spent_month_usd=14.0)


def test_monthly_cap_alone_never_allows_spending():
    with pytest.raises(CostRefused):
        check_cost(0.5, 0.0, 0.0, spent_month_usd=0.0, cap_month_usd=15.0)


def test_good_short_passes():
    r = evaluate_qa(GOOD, VideoFormat.short)
    assert r.passed and r.failures == []


@pytest.mark.parametrize("change,code", [
    ({"duration_s": 176}, "duration"),
    ({"width": 1920, "height": 1080}, "resolution"),
    ({"loudness_lufs": -20.0}, "loudness"),
    ({"loudness_lufs": None}, "loudness"),
    ({"max_silence_s": 4.5}, "silence"),
    ({"max_black_s": 2.5}, "black"),
    ({"disclosure_in_video": False}, "disclosure"),
    ({"disclosure_in_description": False}, "disclosure"),
    ({"unsourced_claims": 1}, "unsourced_claim"),
    ({"paid_assets_without_cap": 1}, "paid_asset"),
])
def test_each_failure_code(change, code):
    r = evaluate_qa(replace(GOOD, **change), VideoFormat.short)
    assert not r.passed and r.failures == [code]


def test_silent_video_fails_only_no_audio():
    r = evaluate_qa(replace(GOOD, has_audio=False, loudness_lufs=None), VideoFormat.short)
    assert r.failures == ["no_audio"]


def test_long_format_limits():
    ok = replace(GOOD, duration_s=900, width=1920, height=1080)
    assert evaluate_qa(ok, VideoFormat.long).passed
    assert evaluate_qa(replace(ok, duration_s=1801), VideoFormat.long).failures == ["duration"]
    assert evaluate_qa(GOOD, VideoFormat.long).failures == ["resolution"]


NAN = float("nan")


@pytest.mark.parametrize("kw", [{"spent_usd": NAN}, {"spent_usd": -1.0}, {"cap_usd": NAN}, {"cap_usd": float("inf")},
                                {"spent_month_usd": NAN}, {"spent_month_usd": -1.0}, {"cap_month_usd": NAN}])
def test_non_finite_or_negative_inputs_are_refused(kw):
    args = {"estimated_usd": 0.5, "spent_usd": 0.0, "cap_usd": 5.0, "spent_month_usd": 0.0, "cap_month_usd": 15.0} | kw
    with pytest.raises(CostRefused):
        check_cost(**args)


@pytest.mark.parametrize("field,code", [("duration_s", "duration"), ("loudness_lufs", "loudness"),
                                        ("max_silence_s", "silence"), ("max_black_s", "black")])
def test_nan_metrics_fail_qa_instead_of_passing(field, code):
    assert evaluate_qa(replace(GOOD, **{field: NAN}), VideoFormat.short).failures == [code]
