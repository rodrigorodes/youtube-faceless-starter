"""Casos de uso editoriais: fontes, roteiro restrito a claims e checagem factual (gate determinístico)."""
import json
import re
from collections.abc import Callable
from decimal import Decimal
from typing import TYPE_CHECKING
from dataclasses import dataclass
from urllib.parse import urlsplit

from ..domain.claims import extract_claims
from ..domain.contracts import Claim, FactCheckReport, SceneFactCheck, Script, SourceSnapshot, UnsupportedItem, VideoStatus
from ..domain.facts import check_names, check_narration
from ..domain.policy import check_cost
from .budget import PaidOperationGuard, paid_key, provider_settlement
if TYPE_CHECKING:
    from .ideas import ScoreIdeas
    from .longform import ApproveScriptVersion, EditScriptScene, GenerateLongScript
from .ports import (FactCheckRepository, ScriptRepository, SceneDraft, SnapshotRepository, SourceFetcher, TextModel,
                    UsageRepository, VideoRepository)

MAX_SOURCE_CHARS = 200_000
MIN_SCENES, MAX_SCENES = 2, 20
MAX_PROMPT_CHARS = 3900  # o bridge recusa prompt acima de 4000 caracteres


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


_SCHEMA = {"type": "object", "required": ["scenes"], "properties": {"scenes": {"type": "array", "items": {
    "type": "object", "required": ["narration", "image_prompt"],
    "properties": {"narration": {"type": "string"}, "caption": {"type": "string"}, "label": {"type": "string"},
                   "image_prompt": {"type": "string"}, "claim_ids": {"type": "array", "items": {"type": "string"}}}}}}}


def build_prompt(topic: str, claims: list[Claim], scene_count: int) -> str:
    facts = "\n".join(f"[{c.id}] {c.text}" for c in claims)
    return (
        f"Escreva o roteiro de um vídeo curto em português do Brasil sobre: {topic}.\n"
        f"Use SOMENTE os fatos abaixo. Não invente números, datas, nomes ou lugares. Evento encerrado: escreva no passado.\n"
        f"Não use fotos ou nomes de pessoas que não estejam nos fatos.\n\nFATOS:\n{facts}\n\n"
        f"Responda apenas com JSON: {{\"scenes\": [{{\"narration\": str (5-400 caracteres), \"caption\": str (até 110), "
        f"\"label\": str (até 32), \"image_prompt\": str (cena genérica, sem pessoas reais, 10-500 caracteres), "
        f"\"claim_ids\": [ids dos fatos usados nesta cena]}}]}} com {scene_count} cenas."
    )


def parse_drafts(raw: str, valid_ids: set[str]) -> list[SceneDraft]:
    return parse_scene_drafts(raw, valid_ids, min_scenes=MIN_SCENES, max_scenes=MAX_SCENES)


def parse_scene_drafts(raw: str, valid_ids: set[str], *, min_scenes: int, max_scenes: int) -> list[SceneDraft]:
    try:
        start, end = raw.find("{"), raw.rfind("}")  # tolera texto ou cerca ```json ao redor
        data = json.loads(raw[start:end + 1])
        scenes = data["scenes"]
    except (ValueError, KeyError, TypeError, RecursionError) as exc:
        raise ScriptRejected("model output is not the expected JSON") from exc
    if not isinstance(scenes, list) or not min_scenes <= len(scenes) <= max_scenes:
        raise ScriptRejected(f"expected {min_scenes}-{max_scenes} scenes")
    drafts: list[SceneDraft] = []
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
            raise ScriptRejected(f"scene {i}: claim_ids is required (cite the facts the scene uses)")
        unknown = [c for c in cited if c not in valid_ids]
        if unknown:
            raise ScriptRejected(f"scene {i}: unknown claim ids {unknown}")
        drafts.append(SceneDraft(narration.strip(), caption.strip()[:110], label.strip()[:32], prompt.strip(), list(dict.fromkeys(cited))))
    return drafts


def _fit_prompt(topic: str, claims: list[Claim], scene_count: int) -> list[Claim]:
    """Mantém, na ordem, as claims que cabem no limite de prompt (só elas valem como claim_ids)."""
    kept: list[Claim] = []
    for claim in claims:
        if len(build_prompt(topic, kept + [claim], scene_count)) > MAX_PROMPT_CHARS:
            break
        kept.append(claim)
    return kept


class GenerateScript:
    def __init__(self, videos: VideoRepository, snaps: SnapshotRepository, scripts: ScriptRepository,
                 text_model: TextModel | None, guard: CostGuard, usage: UsageRepository,
                 model_for: Callable[[str], TextModel] | None = None, paid: PaidOperationGuard | None = None):
        """`model_for(project_id)` escolhe o modelo pela configuração do projeto; sem ele vale `text_model`.
        Com `paid`, a chamada paga só acontece sob reserva de orçamento e o custo é confirmado pelo guard."""
        self.videos, self.snaps, self.scripts = videos, snaps, scripts
        self.text_model, self.guard, self.usage, self.model_for = text_model, guard, usage, model_for
        self.paid = paid

    def execute(self, video_id: str, scene_count: int = 6) -> Script:
        if not MIN_SCENES <= scene_count <= MAX_SCENES:
            raise ValueError(f"scene_count must be between {MIN_SCENES} and {MAX_SCENES}")
        video = _require_video(self.videos, video_id)
        if video.status not in (VideoStatus.IDEA, VideoStatus.SCRIPTED):
            raise StateConflict(f"cannot write a script in state {video.status.value}")
        claims = _claims(self.snaps.list(video_id))
        if not claims:
            raise SourceRefused("no sources with checkable claims: add sources first")
        claims = _fit_prompt(video.topic, claims, scene_count)
        if not claims:
            raise SourceRefused("topic and claims do not fit the model prompt limit")
        prompt = build_prompt(video.topic, claims, scene_count)
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
    approve_script: "ApproveScriptVersion | None" = None
