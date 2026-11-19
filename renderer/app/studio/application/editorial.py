"""Casos de uso editoriais: fontes, roteiro restrito a claims e checagem factual (gate determinístico)."""
import json
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from ..domain.claims import extract_claims
from ..domain.contracts import Claim, FactCheckReport, SceneFactCheck, Script, SourceSnapshot, UnsupportedItem, VideoStatus
from ..domain.facts import check_narration
from ..domain.policy import check_cost
from .ports import (FactCheckRepository, ScriptRepository, SceneDraft, SnapshotRepository, SourceFetcher, TextModel,
                    UsageRepository, VideoRepository)

MAX_SOURCE_CHARS = 200_000
MIN_SCENES, MAX_SCENES = 2, 20
MAX_PROMPT_CHARS = 3900  # o bridge recusa prompt acima de 4000 caracteres


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


def host_allowed(url: str, allowlist: tuple[str, ...] | list[str]) -> bool:
    """Só http(s), sem credenciais na URL; o host precisa ser um domínio da lista ou subdomínio dele."""
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not host or "@" in parts.netloc:
        return False
    return any(host == d.lower() or host.endswith("." + d.lower()) for d in allowlist)


def _is_http(url: str) -> bool:
    try:
        parts = urlsplit(url)
        return parts.scheme in ("http", "https") and bool(parts.hostname) and "@" not in parts.netloc
    except ValueError:
        return False


class CostGuard:
    def __init__(self, usage: UsageRepository, cap_video: float, cap_month: float):
        self.usage, self.cap_video, self.cap_month = usage, cap_video, cap_month

    def check(self, video_id: str, estimate: float | None) -> None:
        check_cost(estimate, self.usage.spent_video(video_id), self.cap_video, self.usage.spent_month(), self.cap_month)


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
    try:
        start, end = raw.find("{"), raw.rfind("}")  # tolera texto ou cerca ```json ao redor
        data = json.loads(raw[start:end + 1])
        scenes = data["scenes"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ScriptRejected("model output is not the expected JSON") from exc
    if not isinstance(scenes, list) or not MIN_SCENES <= len(scenes) <= MAX_SCENES:
        raise ScriptRejected(f"expected {MIN_SCENES}-{MAX_SCENES} scenes")
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
                 model_for: Callable[[str], TextModel] | None = None):
        """`model_for(project_id)` escolhe o modelo pela configuração do projeto; sem ele vale `text_model`."""
        self.videos, self.snaps, self.scripts = videos, snaps, scripts
        self.text_model, self.guard, self.usage, self.model_for = text_model, guard, usage, model_for

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
        self.guard.check(video_id, model.cost_estimate(prompt))  # antes da chamada
        result = model.complete(prompt, json_schema=_SCHEMA)
        self.usage.record(video_id, result.usage)  # a chamada aconteceu: contabiliza mesmo se a resposta for recusada
        drafts = parse_drafts(result.text, {c.id for c in claims})
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
        snapshots, scenes = self.snaps.list(video_id), self.scripts.scenes(video_id)
        if not snapshots or not scenes:
            raise SourceRefused("nothing to check: sources and scenes are required")
        by_id = {c.id: c.text for c in _claims(snapshots)}
        all_texts = [s.text for s in snapshots]
        flagged: list[SceneFactCheck] = []
        for scene in scenes:
            texts = [by_id[c] for c in scene.claim_ids if c in by_id] if scene.claim_ids else all_texts
            issues = check_narration(f"{scene.narration}\n{scene.caption}", texts, self.allow_names)
            if issues:
                flagged.append(SceneFactCheck(idx=scene.idx, unsupported=[UnsupportedItem(kind=i.kind, value=i.value) for i in issues]))
        override = override_reason.strip() if override_reason is not None else None
        report = FactCheckReport(passed=not flagged or override is not None, overridden=bool(flagged) and override is not None,
                                 override_reason=override if flagged else None, scenes=flagged)
        if not self.checks.save(video_id, report, advance=report.passed):
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
