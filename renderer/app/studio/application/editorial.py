"""Casos de uso editoriais: fontes, roteiro restrito a claims e checagem factual (gate determinístico)."""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ..domain.channel import clean_pillars, validate_duration, validate_language
from ..domain.claims import extract_claims
from ..domain.contracts import (Claim, FactCheckReport, SceneFactCheck, Script, SourceSnapshot, UnsupportedItem,
                                Video, VideoStatus)
from ..domain.effective_config import EDITORIAL_DEFAULTS, EDITORIAL_FIELDS, EffectiveConfig
from ..domain.creative_director import CreativeBrief
from ..domain.facts import check_names, check_narration
from ..domain.policy import check_cost
from .budget import PaidOperationGuard, paid_key, provider_settlement
if TYPE_CHECKING:
    from .creative_director import CreateCreativeBrief
    from .ideas import ScoreIdeas
    from .longform import (AddScriptScene, ApproveScriptVersion, EditScriptScene, GenerateLongScript,
                           GetScriptRevision, ListScriptRevisions, RemoveScriptScene, ReorderScriptScenes,
                           RestoreScriptRevision)
    from .scene_narration import RegenerateSceneNarration, SceneNarration
from .ports import (FactCheckRepository, ScriptRepository, SceneDraft, SnapshotRepository, SourceFetcher, TextModel,
                    UsageRepository, VideoRepository)

MAX_SOURCE_CHARS = 200_000
MIN_SCENES, MAX_SCENES = 2, 20
MAX_PROMPT_CHARS = 3900  # o bridge recusa prompt acima de 4000 caracteres

# Defaults legados: os mesmos do motor em `domain/effective_config` (`EDITORIAL_DEFAULTS`), para
# que "sem perfil" continue sendo exatamente o comportamento anterior (F04).
DEFAULT_LANGUAGE = EDITORIAL_DEFAULTS["language"]
DEFAULT_DURATION_S = EDITORIAL_DEFAULTS["duration_s"]

# Rótulo legível só para o idioma padrão: os demais códigos entram como vieram do canal. Assim o
# prompt sem perfil continua idêntico ao de hoje, e um canal em outro idioma pede outro texto.
_LANGUAGE_LABELS = {"pt-br": "português do Brasil"}
# O bloco editorial divide o limite do prompt com os fatos: o que não couber é cortado aqui, nunca
# a exigência de citar claims.
_CONTEXT_TEXT_LIMIT = 300
_CONTEXT_PILLARS_LIMIT = 300
_CONTEXT_NARRATIVE_LIMIT = 600


def language_label(language: str) -> str:
    """Nome legível do idioma declarado pelo canal; sem tradução conhecida, o próprio código."""
    cleaned = language.strip()
    return _LANGUAGE_LABELS.get(cleaned.lower(), cleaned)


@dataclass(frozen=True)
class EditorialContext:
    """Contexto editorial tipado, derivado da configuração efetiva (F04.T01). Puro.

    É um **retrato** de ``EffectiveConfig.editorial``: não relê fonte paralela (o perfil já está
    congelado na configuração) e não persiste nada. Cada campo preserva a proveniência de origem
    (``channel``/``engine_default``); ``legacy`` diz que o retrato é o default do motor, o que
    mantém prompts e durações de hoje quando não há perfil.
    """

    language: str = DEFAULT_LANGUAGE
    audience: str = ""
    pillars: tuple[str, ...] = ()
    narrative: str = ""
    cta: str = ""
    duration_s: int = DEFAULT_DURATION_S
    provenance: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "language", validate_language(self.language))
        for name in ("audience", "narrative", "cta"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise ValueError(f"{name} must be a string")
            object.__setattr__(self, name, value.strip())
        object.__setattr__(self, "pillars", clean_pillars(self.pillars))
        object.__setattr__(self, "duration_s", validate_duration(self.duration_s))
        object.__setattr__(self, "provenance", MappingProxyType(
            {str(key): str(value) for key, value in self.provenance.items()}))

    @property
    def legacy(self) -> bool:
        """Sem perfil: todos os campos vieram do default do motor (proveniência completa)."""
        return len(self.provenance) == len(EDITORIAL_FIELDS) and all(
            self.provenance.get(f"editorial.{name}") == "engine_default" for name in EDITORIAL_FIELDS)

    @property
    def declared_duration_s(self) -> int | None:
        """Duração declarada por um perfil; ``None`` no retrato legado (default do motor)."""
        return None if self.legacy else self.duration_s

    @classmethod
    def from_effective_config(cls, config: EffectiveConfig) -> "EditorialContext":
        """Único caminho de derivação: lê o editorial congelado e mantém a proveniência por campo."""
        if not isinstance(config, EffectiveConfig):
            raise TypeError("config must be an EffectiveConfig")
        return cls(
            language=config.language,
            audience=config.audience,
            pillars=tuple(config.pillars),
            narrative=config.narrative,
            cta=config.cta,
            duration_s=config.duration_s,
            provenance={f"editorial.{name}": config.provenance.get(f"editorial.{name}", "engine_default")
                        for name in EDITORIAL_FIELDS},
        )

    @classmethod
    def coerce(cls, value: EffectiveConfig | "EditorialContext" | None) -> "EditorialContext | None":
        """Aceita o já derivado ou a configuração efetiva; ``None`` continua "sem perfil"."""
        if value is None or isinstance(value, cls):
            return value
        if isinstance(value, EffectiveConfig):
            return cls.from_effective_config(value)
        raise TypeError("editorial source must be an EffectiveConfig, an EditorialContext or null")


def context_for_video(source: EffectiveConfig | EditorialContext | None, video: Video) -> "EditorialContext | None":
    """Normaliza a fonte de contexto do vídeo atual e recusa configuração de outro vídeo.

    A configuração efetiva carrega ``video_id``/``project_id``; aplicá-la a outro vídeo seria um
    vazamento silencioso de canal, então a fiação errada falha em vez de gerar com o perfil errado.
    """
    if isinstance(source, EffectiveConfig) and (source.video_id != video.id
                                                or source.project_id != video.project_id):
        raise ValueError("the effective configuration belongs to another video")
    return EditorialContext.coerce(source)


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def context_guidance(context: EditorialContext | None) -> str:
    """Bloco de orientação editorial para o prompt; vazio sem perfil (texto legado intacto).

    Orienta estilo e idioma, mas nunca substitui a instrução de usar SOMENTE os fatos: a
    exigência de claims e fontes continua no mesmo lugar do prompt.
    """
    if context is None:
        return ""
    lines: list[str] = []
    if context.declared_duration_s is not None:
        lines.append(f"Duração alvo ~{context.duration_s}s.")
    if context.audience:
        lines.append(f"Público-alvo: {_clip(context.audience, _CONTEXT_TEXT_LIMIT)}.")
    if context.narrative:
        lines.append(f"Linha narrativa: {_clip(context.narrative, _CONTEXT_NARRATIVE_LIMIT)}.")
    if context.pillars:
        lines.append(f"Pilares editoriais: {_clip('; '.join(context.pillars), _CONTEXT_PILLARS_LIMIT)}.")
    if context.cta:
        lines.append(f"Encerre com o CTA: {_clip(context.cta, _CONTEXT_TEXT_LIMIT)}.")
    return "".join(f"{line}\n" for line in lines)


def _usd(value) -> Decimal:
    """Converte a estimativa float do provedor em Decimal exato do texto, nunca por arredondamento binário."""
    return Decimal(str(value))


class VideoNotFound(LookupError):
    pass


class SourceRefused(ValueError):
    pass


class StateConflict(RuntimeError):
    pass


class ScriptRejected(ValueError):
    pass


class SourceUnavailable(RuntimeError):
    """A fonte não pôde ser baixada (rede, HTTP de erro): a API responde 502."""


_HOST = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*")


def _http_host(url: str) -> str | None:
    """Host em minúsculas de uma URL http(s) bem formada (ASCII estrito, porta 80/443, sem credenciais), ou None.
    A regex estrita evita hosts que parsers diferentes leem de formas diferentes (`evil.com\\.dominio`)."""
    if not isinstance(url, str) or any(c in url for c in "\\\r\n\t\x00 "):
        return None
    try:
        parts = urlsplit(url)
        host, port = (parts.hostname or "").lower(), parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or "@" in parts.netloc or port not in (None, 80, 443):
        return None
    return host if _HOST.fullmatch(host) else None


def host_allowed(url: str, allowlist: tuple[str, ...] | list[str]) -> bool:
    """Só http(s) bem formado, sem credenciais; o host precisa ser um domínio da lista ou subdomínio dele."""
    host = _http_host(url)
    return host is not None and any(host == d.lower() or host.endswith("." + d.lower()) for d in allowlist)


def _is_http(url: str) -> bool:
    return _http_host(url) is not None


class CostGuard:
    def __init__(self, usage: UsageRepository, cap_video: float, cap_month: float):
        self.usage, self.cap_video, self.cap_month = usage, cap_video, cap_month

    def check(self, video_id: str | None, estimate: float | None) -> None:
        """Sem vídeo (ex.: pontuar ideias), só o teto do vídeo em zero e o mensal valem para gasto pago."""
        spent = self.usage.spent_video(video_id) if video_id else 0.0
        check_cost(estimate, spent, self.cap_video, self.usage.spent_month(), self.cap_month)


def _require_video(videos: VideoRepository, video_id: str):
    video = videos.get_video(video_id)
    if video is None:
        raise VideoNotFound(video_id)
    return video


def _claims(snapshots: list[SourceSnapshot]) -> list[Claim]:
    seen: dict[str, Claim] = {}
    for snap in snapshots:
        for claim in extract_claims(snap.id, snap.text):
            seen.setdefault(claim.id, claim)
    return list(seen.values())


class IngestSource:
    def __init__(self, fetcher: SourceFetcher, snaps: SnapshotRepository, videos: VideoRepository, allowlist: tuple[str, ...]):
        self.fetcher, self.snaps, self.videos, self.allowlist = fetcher, snaps, videos, allowlist

    def execute_url(self, video_id: str, url: str) -> SourceSnapshot:
        _require_video(self.videos, video_id)
        if not host_allowed(url, self.allowlist):
            raise SourceRefused("url host is not in the allowlist")
        page = self.fetcher.fetch(url)  # o adaptador revalida cada redirect
        if not host_allowed(page.final_url, self.allowlist):
            raise SourceRefused("redirect left the allowlist")
        return self._store(video_id, page.final_url, page.text)

    def execute_text(self, video_id: str, url: str, text: str) -> SourceSnapshot:
        """Texto colado pelo humano (fallback para sites que bloqueiam raspagem); a URL é só a referência."""
        if not _is_http(url):
            raise SourceRefused("reference url must be http(s)")
        _require_video(self.videos, video_id)
        return self._store(video_id, url, text)

    def _store(self, video_id: str, url: str, text: str) -> SourceSnapshot:
        text = text.strip()
        if not text:
            raise SourceRefused("source text is empty")
        if len(text) > MAX_SOURCE_CHARS:
            raise SourceRefused(f"source text exceeds {MAX_SOURCE_CHARS} characters")
        return self.snaps.add(video_id, url, text)


class ListSources:
    """Lista as fontes já registradas de um vídeo (URL e tamanho); vídeo inexistente é 404."""

    def __init__(self, snaps: SnapshotRepository, videos: VideoRepository):
        self.snaps, self.videos = snaps, videos

    def execute(self, video_id: str) -> list[SourceSnapshot]:
        _require_video(self.videos, video_id)
        return self.snaps.list(video_id)


_SCHEMA = {"type": "object", "required": ["scenes"], "properties": {"scenes": {"type": "array", "items": {
    "type": "object", "required": ["narration", "image_prompt", "claim_ids"],
    "properties": {
        "narration": {"type": "string"}, "caption": {"type": "string"}, "label": {"type": "string"},
        "image_prompt": {"type": "string"}, "claim_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "visual_intent": {"type": "string"}, "recommended_asset_kind": {"type": "string"},
        "search_queries": {"type": "array", "items": {"type": "string"}},
    }}}}}


def build_prompt(topic: str, claims: list[Claim], scene_count: int, *,
                 context: EditorialContext | None = None,
                 brief: CreativeBrief | None = None) -> str:
    facts = "\n".join(f"[{c.id}] {c.text}" for c in claims)
    language = language_label(context.language if context is not None else DEFAULT_LANGUAGE)
    if brief is not None:
        brief_guidance = (
            "DIRETRIZES DO DIRETOR CRIATIVO:\n"
            f"- Gancho (Hook): {brief.hook}\n"
            f"- Ritmo (Pacing): {brief.pacing}\n"
            f"- Direção Visual: {brief.visual_direction}\n"
        )
        schema_desc = (
            f"Responda apenas com JSON: {{\"scenes\": [{{\"narration\": str (5-400 caracteres), \"caption\": str (até 110), "
            f"\"label\": str (até 32), \"image_prompt\": str (cena genérica, sem pessoas reais, 10-500 caracteres), "
            f"\"claim_ids\": [ids dos fatos usados nesta cena], "
            f"\"visual_intent\": str (intenção visual da cena), "
            f"\"recommended_asset_kind\": \"image\" ou \"video\", "
            f"\"search_queries\": [termos de busca concisos]}}]}} com {scene_count} cenas."
        )
    else:
        brief_guidance = ""
        schema_desc = (
            f"Responda apenas com JSON: {{\"scenes\": [{{\"narration\": str (5-400 caracteres), \"caption\": str (até 110), "
            f"\"label\": str (até 32), \"image_prompt\": str (cena genérica, sem pessoas reais, 10-500 caracteres), "
            f"\"claim_ids\": [ids dos fatos usados nesta cena]}}]}} com {scene_count} cenas."
        )
    return (
        f"Escreva o roteiro de um vídeo curto em {language} sobre: {topic}.\n"
        f"{context_guidance(context)}"
        f"{brief_guidance}"
        f"Use SOMENTE os fatos abaixo. Não invente números, datas, nomes ou lugares. Evento encerrado: escreva no passado.\n"
        f"Não use fotos ou nomes de pessoas que não estejam nos fatos.\n"
        f"IMPORTANTE: Cada cena (inclusive a cena inicial/gancho) DEVE conter pelo menos um id de FATOS no array claim_ids. Nunca deixe claim_ids vazio.\n\n"
        f"FATOS:\n{facts}\n\n"
        f"{schema_desc}"
    )


_CLAIM_ID_MAX_EDITS = 2
_CLAIM_ID_MIN_LENGTH = 8


def _edit_distance(a: str, b: str) -> int:
    """Distância de Damerau-Levenshtein restrita (inserção, remoção, troca e transposição adjacente)."""
    rows = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        rows[i][0] = i
    for j in range(len(b) + 1):
        rows[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            rows[i][j] = min(rows[i - 1][j] + 1, rows[i][j - 1] + 1, rows[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                rows[i][j] = min(rows[i][j], rows[i - 2][j - 2] + 1)
    return rows[len(a)][len(b)]


def _resolve_claim_id(raw: str, valid_ids: set[str]) -> str | None:
    """O id que o modelo quis citar, ou `None` se não for inequívoco.

    Os ids de fato são hashes opacos que o modelo precisa copiar; ele erra a transcrição (troca de
    caracteres, colchetes, caixa). Só se resolve quando, depois de normalizar, existe **exatamente um**
    id válido a até `_CLAIM_ID_MAX_EDITS` edições — a citação continua apontando para um fato real das
    fontes. Id inventado ou ambíguo segue recusado (`None`).
    """
    if raw in valid_ids:
        return raw
    cleaned = raw.strip().strip("[]()").strip().lower()
    if cleaned in valid_ids:
        return cleaned
    if len(cleaned) < _CLAIM_ID_MIN_LENGTH:
        return None
    near = [v for v in valid_ids if _edit_distance(cleaned, v) <= _CLAIM_ID_MAX_EDITS]
    return near[0] if len(near) == 1 else None


def _parse_scenes(raw: str, valid_ids: set[str], *, min_scenes: int, max_scenes: int) -> list[SceneDraft]:
    try:
        start, end = raw.find("{"), raw.rfind("}")  # tolera texto ou cerca ```json ao redor
        data = json.loads(raw[start:end + 1])
        scenes = data["scenes"]
    except (ValueError, KeyError, TypeError, RecursionError) as exc:
        raise ScriptRejected("model output is not the expected JSON") from exc
    if not isinstance(scenes, list) or not min_scenes <= len(scenes) <= max_scenes:
        raise ScriptRejected(f"expected {min_scenes}-{max_scenes} scenes")
    drafts: list[SceneDraft] = []
    has_any_cited = any(bool(s.get("claim_ids")) for s in scenes if isinstance(s, dict))
    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            raise ScriptRejected(f"scene {i} is not an object")
        narration, prompt = scene.get("narration"), scene.get("image_prompt")
        caption, label, cited = scene.get("caption") or "", scene.get("label") or "", scene.get("claim_ids") or []
        if not (isinstance(narration, str) and 5 <= len(narration.strip()) <= 400):
            raise ScriptRejected(f"scene {i}: narration must have 5-400 characters")
        if not (isinstance(prompt, str) and 10 <= len(prompt.strip()) <= 500):
            raise ScriptRejected(f"scene {i}: image_prompt must have 10-500 characters")
        if not (isinstance(caption, str) and isinstance(label, str) and isinstance(cited, list) and all(isinstance(c, str) for c in cited)):
            raise ScriptRejected(f"scene {i}: caption/label/claim_ids have the wrong type")
        if "\x00" in narration + prompt + caption + label + "".join(cited):
            raise ScriptRejected(f"scene {i}: NUL byte in text")
        if not cited:
            if has_any_cited and valid_ids:
                # Recuperação robusta: se uma cena isolada (ex.: gancho da cena 0) não citou fato,
                # ancora no primeiro fato válido das fontes para não abortar a produção.
                cited = [sorted(valid_ids)[0]]
            else:
                raise ScriptRejected(f"scene {i}: claim_ids is required (cite the facts the scene uses)")
        resolved = {c: _resolve_claim_id(c, valid_ids) for c in cited}
        unknown = [c for c, found in resolved.items() if found is None]
        if unknown:
            raise ScriptRejected(f"scene {i}: unknown claim ids {unknown}")
        cited = [resolved[c] for c in cited]

        visual_intent = str(scene.get("visual_intent") or "").strip()
        recommended_asset_kind = str(scene.get("recommended_asset_kind") or "image").strip()
        raw_queries = scene.get("search_queries") or []
        search_queries = (
            [str(q).strip() for q in raw_queries if isinstance(q, str) and q.strip()]
            if isinstance(raw_queries, list)
            else []
        )

        drafts.append(
            SceneDraft(
                narration.strip(),
                caption.strip()[:110],
                label.strip()[:32],
                prompt.strip(),
                list(dict.fromkeys(cited)),
                visual_intent=visual_intent,
                recommended_asset_kind=recommended_asset_kind,
                search_queries=search_queries,
            )
        )
    return drafts


def parse_scene_drafts(raw: str, valid_ids: set[str], *, min_scenes: int, max_scenes: int) -> list[SceneDraft]:
    return _parse_scenes(raw, valid_ids, min_scenes=min_scenes, max_scenes=max_scenes)


def parse_drafts(raw: str, valid_ids: set[str]) -> list[SceneDraft]:
    return parse_scene_drafts(raw, valid_ids, min_scenes=MIN_SCENES, max_scenes=MAX_SCENES)


def _fit_prompt(topic: str, claims: list[Claim], scene_count: int,
                context: EditorialContext | None = None,
                brief: CreativeBrief | None = None) -> list[Claim]:
    """Mantém, na ordem, as claims que cabem no limite de prompt (só elas valem como claim_ids)."""
    kept: list[Claim] = []
    for claim in claims:
        if len(build_prompt(topic, kept + [claim], scene_count, context=context, brief=brief)) > MAX_PROMPT_CHARS:
            break
        kept.append(claim)
    return kept


class GenerateScript:
    def __init__(self, videos: VideoRepository, snaps: SnapshotRepository, scripts: ScriptRepository,
                 text_model: TextModel | None, guard: CostGuard, usage: UsageRepository,
                 model_for: Callable[[str], TextModel] | None = None, paid: PaidOperationGuard | None = None,
                 editorial_for: Callable[[Video], EffectiveConfig | EditorialContext | None] | None = None):
        """`model_for(project_id)` escolhe o modelo pela configuração do projeto; sem ele vale `text_model`.
        Com `paid`, a chamada paga só acontece sob reserva de orçamento e o custo é confirmado pelo guard.
        `editorial_for(video)` traz o contexto derivado da configuração efetiva; sem ele o roteiro mantém
        o comportamento legado (pt-BR), sem segunda leitura nem persistência."""
        self.videos, self.snaps, self.scripts = videos, snaps, scripts
        self.text_model, self.guard, self.usage, self.model_for = text_model, guard, usage, model_for
        self.paid = paid
        self.editorial_for = editorial_for

    def _editorial_context(self, video: Video) -> EditorialContext | None:
        if self.editorial_for is None:
            return None
        return context_for_video(self.editorial_for(video), video)

    def execute(self, video_id: str, scene_count: int = 6, *, brief: CreativeBrief | None = None) -> Script:
        if not MIN_SCENES <= scene_count <= MAX_SCENES:
            raise ValueError(f"scene_count must be between {MIN_SCENES} and {MAX_SCENES}")
        video = _require_video(self.videos, video_id)
        if video.status not in (VideoStatus.IDEA, VideoStatus.SCRIPTED):
            raise StateConflict(f"cannot write a script in state {video.status.value}")
        context = self._editorial_context(video)
        claims = _claims(self.snaps.list(video_id))
        if not claims:
            raise SourceRefused("no sources with checkable claims: add sources first")
        claims = _fit_prompt(video.topic, claims, scene_count, context, brief=brief)
        if not claims:
            raise SourceRefused("topic and claims do not fit the model prompt limit")
        prompt = build_prompt(video.topic, claims, scene_count, context=context, brief=brief)
        model = self.model_for(video.project_id) if self.model_for else self.text_model
        estimate = model.cost_estimate(prompt)
        if self.paid is None:
            self.guard.check(video_id, estimate)  # antes da chamada
            result = model.complete(prompt, json_schema=_SCHEMA)
            self.usage.record(video_id, result.usage)  # a chamada aconteceu: contabiliza mesmo se a resposta for recusada
            drafts = parse_drafts(result.text, {c.id for c in claims})
        else:
            key = paid_key("script", video_id, getattr(model, "model", ""), model.name, prompt)
            claim_ids = {c.id for c in claims}
            # valida a saída ANTES de encerrar o custo: roteiro inválido vira UNCERTAIN, não ACTUAL
            drafts = self.paid.run(key, video_id, _usd(estimate),
                                   call=lambda: model.complete(prompt, json_schema=_SCHEMA),
                                   validate=lambda res: parse_drafts(res.text, claim_ids),
                                   settle=lambda res: provider_settlement(res.usage, settled_by=f"studio:script:{model.name}"))
        cited = sorted({c for d in drafts for c in d.claim_ids})
        script = self.scripts.save_and_advance(video_id, "\n".join(d.narration for d in drafts), drafts, cited,
                                               video.status, VideoStatus.SCRIPTED)
        if script is None:
            raise StateConflict("video state changed while generating")
        return script


class RunFactCheck:
    def __init__(self, videos: VideoRepository, snaps: SnapshotRepository, scripts: ScriptRepository,
                 checks: FactCheckRepository, allow_names: frozenset[str] = frozenset()):
        self.videos, self.snaps, self.scripts, self.checks, self.allow_names = videos, snaps, scripts, checks, allow_names

    def execute(self, video_id: str, override_reason: str | None = None) -> FactCheckReport:
        if override_reason is not None and not override_reason.strip():
            raise ValueError("override reason must not be empty")
        video = _require_video(self.videos, video_id)
        if video.status != VideoStatus.SCRIPTED:
            raise StateConflict(f"fact-check needs state SCRIPTED, got {video.status.value}")
        snapshots, script = self.snaps.list(video_id), self.scripts.latest(video_id)  # a versão é lida ANTES das cenas
        scenes = self.scripts.scenes(video_id)
        if not snapshots or not scenes or script is None:
            raise SourceRefused("nothing to check: sources and scenes are required")
        by_id = {c.id: c.text for c in _claims(snapshots)}
        all_texts = [s.text for s in snapshots]
        flagged: list[SceneFactCheck] = []
        for scene in scenes:
            texts = [by_id[c] for c in scene.claim_ids if c in by_id] if scene.claim_ids else all_texts
            issues = check_narration(f"{scene.narration}\n{scene.caption}\n{scene.label}", texts, self.allow_names)  # tudo que aparece na tela
            issues += [i for i in check_names(scene.image_prompt, texts, self.allow_names) if i not in issues]  # sem pessoas reais no prompt
            if issues:
                flagged.append(SceneFactCheck(idx=scene.idx, unsupported=[UnsupportedItem(kind=i.kind, value=i.value) for i in issues]))
        override = override_reason.strip() if override_reason is not None else None
        report = FactCheckReport(passed=not flagged or override is not None, overridden=bool(flagged) and override is not None,
                                 override_reason=override if flagged else None, scenes=flagged)
        if not self.checks.save(video_id, report, advance=report.passed, script_version=script.version):
            raise StateConflict("video state changed during the fact-check")
        return report


class GetScript:
    def __init__(self, videos: VideoRepository, scripts: ScriptRepository):
        self.videos, self.scripts = videos, scripts

    def execute(self, video_id: str):
        _require_video(self.videos, video_id)
        script = self.scripts.latest(video_id)
        return None if script is None else (script, self.scripts.scenes(video_id))


@dataclass(frozen=True)
class Editorial:
    ingest: IngestSource
    generate: GenerateScript
    get_script: GetScript
    fact_check: RunFactCheck
    score_ideas: "ScoreIdeas | None" = None
    long_generate: "GenerateLongScript | None" = None  # F4: roteiro longo em duas passagens
    edit_script: "EditScriptScene | None" = None
    add_scene: "AddScriptScene | None" = None
    remove_scene: "RemoveScriptScene | None" = None
    reorder_scenes: "ReorderScriptScenes | None" = None
    approve_script: "ApproveScriptVersion | None" = None
    list_sources: "ListSources | None" = None
    # W4.3: pré-escuta e regeneração da narração de uma cena (opcionais; sem eles, nada muda).
    scene_narration: "SceneNarration | None" = None
    regenerate_narration: "RegenerateSceneNarration | None" = None
    # W4.5 (EDIT-04): histórico recuperável de revisões de cena.
    restore_revision: "RestoreScriptRevision | None" = None
    list_revisions: "ListScriptRevisions | None" = None
    get_revision: "GetScriptRevision | None" = None
    creative_director: "CreateCreativeBrief | None" = None
