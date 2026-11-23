"""Domínio puro de priorização, sinais e diagnósticos de risco para tendências (sem I/O)."""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

STOPWORDS = frozenset({
    "o", "a", "os", "as", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das", "em", "no", "na",
    "nos", "nas", "por", "para", "com", "que", "como",
    "qual", "quando", "onde", "quem", "mais", "menos",
    "outro", "outra", "outros", "outras", "muito", "muita",
    "seu", "sua", "seus", "suas", "meu", "minha",
    "ele", "ela", "eles", "elas", "este", "esta", "esse",
    "essa", "isto", "isso", "aquele", "aquela", "aquilo",
    "the", "and", "for", "with", "from", "that", "this",
    "what", "how", "why", "who", "was", "were", "are",
})

RISK_KEYWORDS = (
    # Violência extrema / Morte / Crime
    "assassinato", "assassino", "suicidio", "chacina", "massacre",
    "estupro", "terrorismo", "arma de fogo", "armas de fogo", "tiroteio",
    "sequestro", "tortura", "gore", "crime hediondo", "homicidio",
    "execucao sumaria", "execucao publica", "automutilacao", "pedofilia",
    # Drogas ilícitas / Explícito
    "cocaina", "heroina", "trafico de drogas", "drogas ilicitas",
    "porno", "sexo explicito",
    # Golpes / Fraude / Pirâmide
    "esquema piramide", "esquema de piramide", "lucro garantido",
    "renda garantida", "fique rico rapido", "golpe do pix",
    # Saúde falsa / Curas milagrosas extremas
    "cura do cancer", "cura milagrosa", "remedio milagroso",
)

_RISK_PATTERNS = tuple(re.compile(r"\b" + re.escape(kw) + r"\b") for kw in RISK_KEYWORDS)


@dataclass(frozen=True)
class PriorityBreakdown:
    velocity_score: int
    niche_ratio_score: int
    competition_score: int
    adherence_score: int
    variety_score: int
    total_score: int
    summary: str
    risk_status: str
    risk_level: str  # "ok" | "warn" | "danger"
    is_evergreen: bool


@dataclass(frozen=True)
class SavedTrendSnapshot:
    project_id: str
    video_id: str
    title: str
    channel_title: str | None = None
    thumbnail_url: str | None = None
    video_url: str | None = None
    duration: str = ""
    views: int = 0
    category_name: str | None = None
    score: int = 0
    created_at: datetime | None = None


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()


def _extract_tokens(text: str) -> set[str]:
    normalized = _normalize_text(text)
    raw_tokens = re.findall(r"\b[a-z0-9_]{3,}\b", normalized)
    return {token for token in raw_tokens if token not in STOPWORDS}


def calculate_priority(
    views: int,
    published_at: datetime | None,
    niche_median_views: float,
    is_trending_chart: bool,
    has_category: bool,
    recent_channel_titles: list[str],
    title: str,
    now: datetime,
) -> PriorityBreakdown:
    # Normalização de timezone de published_at
    pub: datetime | None = None
    if published_at is not None:
        pub = published_at
        if pub.tzinfo is None and now.tzinfo is not None:
            pub = pub.replace(tzinfo=timezone.utc)
        elif pub.tzinfo is not None and now.tzinfo is None:
            pub = pub.replace(tzinfo=None)

    # 1. Velocidade de views/hora (S_vel)
    if pub is not None:
        delta_s = max(0.0, (now - pub).total_seconds())
        hours = max(1.0, delta_s / 3600.0)
    else:
        hours = 24.0

    views_per_hour = max(0.0, float(views)) / hours
    if views_per_hour <= 0.0:
        velocity_score = 0
    else:
        # log10(1) = 0; log10(10001) = 4.0; 4.0 * 25 = 100
        score = math.log10(views_per_hour + 1.0) * 25.0
        velocity_score = max(0, min(100, int(round(score))))

    # 2. Excesso sobre o nicho (S_nicho)
    median = max(1.0, float(niche_median_views))
    ratio = max(0.0, float(views)) / median

    if views <= 0:
        niche_ratio_score = 0
    elif ratio < 0.5:
        niche_ratio_score = max(1, int(round(ratio * 20.0)))
    elif ratio < 1.0:
        niche_ratio_score = int(round(10.0 + (ratio - 0.5) * 80.0))
    elif ratio < 3.0:
        niche_ratio_score = int(round(50.0 + (ratio - 1.0) * 25.0))
    else:
        niche_ratio_score = 100
    niche_ratio_score = max(0, min(100, niche_ratio_score))

    # 3. Oportunidade de Concorrência (S_conc)
    if is_trending_chart:
        competition_score = 50
    else:
        competition_score = 80

    # 4. Aderência ao Canal (S_aderencia)
    if has_category:
        adherence_score = 95
    else:
        adherence_score = 70

    # 5. Variedade vs. últimos vídeos do canal (S_variedade)
    candidate_tokens = _extract_tokens(title)
    overlapping_count = 0
    if candidate_tokens and recent_channel_titles:
        for r_title in recent_channel_titles[:5]:
            r_tokens = _extract_tokens(r_title)
            if candidate_tokens & r_tokens:
                overlapping_count += 1

    if overlapping_count == 0:
        variety_score = 100
    elif overlapping_count == 1:
        variety_score = 70
    elif overlapping_count == 2:
        variety_score = 35
    else:
        variety_score = max(10, 35 - (overlapping_count - 2) * 10)

    # 6. Diagnóstico de risco e classificação perene
    norm_title = _normalize_text(title)
    has_risk = any(pattern.search(norm_title) is not None for pattern in _RISK_PATTERNS)

    raw_score = (
        0.20 * velocity_score
        + 0.20 * niche_ratio_score
        + 0.20 * competition_score
        + 0.20 * adherence_score
        + 0.20 * variety_score
    )

    if has_risk:
        risk_level = "danger"
        risk_status = "Risco de monetização"
        raw_score -= 30.0
    elif variety_score < 40:
        risk_level = "warn"
        risk_status = "Atenção: repetição"
    else:
        risk_level = "ok"
        risk_status = "Sem risco detectado"

    total_score = max(0, min(100, int(round(raw_score))))

    is_evergreen = False
    if pub is not None:
        age_days = (now - pub).total_seconds() / 86400.0
        if age_days > 180.0 and views >= 100_000:
            is_evergreen = True

    if risk_level == "danger":
        summary = "Risco de monetização: tema sensível detectado com penalidade aplicada"
    elif risk_level == "warn":
        summary = "Atenção: tema repetitivo em relação aos vídeos recentes do canal"
    elif is_evergreen and total_score >= 70:
        summary = "Alta prioridade (perene): tema com tração consolidada a longo prazo"
    elif total_score >= 80:
        summary = "Alta prioridade: forte tração e excelente oportunidade no nicho"
    elif total_score >= 60:
        summary = "Boa prioridade: tração consistente com boa aderência ao canal"
    elif total_score >= 40:
        summary = "Prioridade moderada: tração e concorrência equilibradas"
    else:
        summary = "Baixa prioridade: tração reduzida ou saturação de mercado"

    return PriorityBreakdown(
        velocity_score=velocity_score,
        niche_ratio_score=niche_ratio_score,
        competition_score=competition_score,
        adherence_score=adherence_score,
        variety_score=variety_score,
        total_score=total_score,
        summary=summary,
        risk_status=risk_status,
        risk_level=risk_level,
        is_evergreen=is_evergreen,
    )
