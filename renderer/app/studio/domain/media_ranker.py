"""Motor de pontuação determinística e seleção de candidatos de mídia."""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from .media import MediaCandidate


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: MediaCandidate
    score: float
    reasons: tuple[str, ...]


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return {word for word in re.findall(r"[a-z0-9]+", normalized) if len(word) >= 3}


class MediaRanker:
    """Classificador de candidatos de mídia baseado em regras determinísticas e deduplicação."""

    @classmethod
    def rank(
        cls,
        candidates: list[MediaCandidate],
        *,
        visual_intent: str = "",
        queries: list[str] | None = None,
        target_format: str,
        min_duration_s: float | None = None,
        used_media_ids: set[str] | None = None,
    ) -> list[ScoredCandidate]:
        if not candidates:
            return []

        fmt = target_format.value if hasattr(target_format, "value") else str(target_format)
        fmt = fmt.lower()
        used_ids = set(used_media_ids) if used_media_ids else set()

        query_tokens: set[str] = set()
        for q in (queries or []):
            query_tokens.update(_tokenize(q))
        if visual_intent:
            query_tokens.update(_tokenize(visual_intent))

        scored: list[ScoredCandidate] = []
        for candidate in candidates:
            score = 0.0
            reasons: list[str] = []

            # 1. Orientation / Aspect
            if fmt in ("short", "9:16"):
                if candidate.width is not None and candidate.height is not None and candidate.height >= candidate.width:
                    score += 30.0
                    reasons.append("orientation match: vertical format (height >= width)")
            elif fmt in ("long", "16:9"):
                if candidate.width is not None and candidate.height is not None and candidate.width >= candidate.height:
                    score += 30.0
                    reasons.append("orientation match: horizontal format (width >= height)")

            # 2. Resolution
            w = candidate.width or 0
            h = candidate.height or 0
            if min(w, h) >= 1080:
                score += 20.0
                reasons.append("ideal resolution: min dimension >= 1080p")

            # 3. Term overlap / relevance
            cand_tokens: set[str] = set()
            for tag in getattr(candidate, "tags", ()):
                cand_tokens.update(_tokenize(tag))
            cand_tokens.update(_tokenize(candidate.url))
            cand_tokens.update(_tokenize(candidate.source_url))

            matches = query_tokens & cand_tokens
            if matches:
                match_count = min(len(matches), 3)
                overlap_score = match_count * 10.0
                score += overlap_score
                reasons.append(f"term overlap: {len(matches)} matching term(s)")

            # 4. Video duration
            if candidate.media_type == "video":
                if min_duration_s is not None:
                    if candidate.duration_s is not None and candidate.duration_s >= min_duration_s:
                        score += 20.0
                        reasons.append(f"video duration adequate: {candidate.duration_s}s >= {min_duration_s}s")
                    elif candidate.duration_s is not None and candidate.duration_s < min_duration_s:
                        score -= 30.0
                        reasons.append(f"video duration insufficient: {candidate.duration_s}s < {min_duration_s}s")

            # 5. Repetition penalty
            if candidate.media_id and candidate.media_id in used_ids:
                score -= 50.0
                reasons.append("repetition penalty: asset already used in video")

            scored.append(
                ScoredCandidate(
                    candidate=candidate,
                    score=float(score),
                    reasons=tuple(reasons),
                )
            )

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored
