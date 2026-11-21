"""Política de custo e critérios de QA (domínio puro)."""
import math
from dataclasses import dataclass

from .contracts import VideoFormat
from .render import MediaQaResult

DEFAULT_MONTHLY_CAP_USD = 15.0
LOUDNESS_TARGET, LOUDNESS_TOLERANCE = -16.0, 1.5
MAX_SILENCE_S, MAX_BLACK_S = 4.0, 2.0
LIMITS = {VideoFormat.short: (175.0, 1080, 1920), VideoFormat.long: (1800.0, 1920, 1080)}


class CostRefused(ValueError):
    pass


def check_cost(estimated_usd: float | None, spent_usd: float, cap_usd: float,
               spent_month_usd: float = 0.0, cap_month_usd: float = DEFAULT_MONTHLY_CAP_USD) -> None:
    """Recusa antes da chamada paga. Estimativa ausente/negativa/NaN nunca vale como zero."""
    if estimated_usd is None or not math.isfinite(estimated_usd) or estimated_usd < 0:
        raise CostRefused(f"invalid cost estimate: {estimated_usd!r}")
    for label, value in (("spent", spent_usd), ("cap", cap_usd), ("monthly spent", spent_month_usd), ("monthly cap", cap_month_usd)):
        if value is None or not math.isfinite(value) or value < 0:  # NaN/inf/negativo nunca liberam gasto
            raise CostRefused(f"invalid {label} value: {value!r}")
    if cap_usd == 0 and estimated_usd != 0.0:
        raise CostRefused("per-video cap is 0: paid providers are disabled")
    if spent_usd + estimated_usd > cap_usd:
        raise CostRefused("per-video cost cap exceeded")
    if spent_month_usd + estimated_usd > cap_month_usd:
        raise CostRefused("monthly cost cap exceeded")


@dataclass(frozen=True)
class QaMetrics:
    duration_s: float
    width: int
    height: int
    loudness_lufs: float | None
    max_silence_s: float
    max_black_s: float
    has_audio: bool
    disclosure_in_video: bool
    disclosure_in_description: bool
    unsourced_claims: int
    paid_assets_without_cap: int


def evaluate_qa(m: QaMetrics, fmt: VideoFormat) -> MediaQaResult:
    max_duration, width, height = LIMITS[fmt]
    failures: list[str] = []
    def bad(value: float | None) -> bool:  # NaN/inf/negativo é medição quebrada: reprova, nunca passa
        return value is None or not math.isfinite(value) or value < 0

    if bad(m.duration_s) or m.duration_s > max_duration:
        failures.append("duration")
    if (m.width, m.height) != (width, height):
        failures.append("resolution")
    if not m.has_audio:
        failures.append("no_audio")
    elif m.loudness_lufs is None or not math.isfinite(m.loudness_lufs) or abs(m.loudness_lufs - LOUDNESS_TARGET) > LOUDNESS_TOLERANCE:
        failures.append("loudness")
    if bad(m.max_silence_s) or m.max_silence_s > MAX_SILENCE_S:
        failures.append("silence")
    if bad(m.max_black_s) or m.max_black_s > MAX_BLACK_S:
        failures.append("black")
    if not (m.disclosure_in_video and m.disclosure_in_description):
        failures.append("disclosure")
    if m.unsourced_claims > 0:
        failures.append("unsourced_claim")
    if m.paid_assets_without_cap > 0:
        failures.append("paid_asset")
    return MediaQaResult(passed=not failures, failures=failures,
                         metrics={"duration_s": m.duration_s, "loudness_lufs": m.loudness_lufs,
                                  "max_silence_s": m.max_silence_s, "max_black_s": m.max_black_s})
