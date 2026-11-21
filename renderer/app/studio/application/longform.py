"""Motor editorial long-form em duas passagens e aprovação de roteiro (F4-02..F4-06, F4-08).

Duas passagens explícitas: primeiro o **plano de capítulos** (gancho, contexto,
desenvolvimento, payoff/CTA) e só depois as **cenas**, cada uma citando os fatos
que usa. O plano e o hash de conteúdo são gravados junto com o roteiro, na mesma
transação: nunca existe versão sem hash.

A revisão (``review_script``, do domínio) mede continuidade, redundância, duração
estimada, citações e ausência de invenção — esta última reutilizando o gate
factual existente. O texto nunca é aprovado por omissão: um roteiro que não passa
é recusado como ``ScriptRejected``.

A aprovação humana é presa à (versão, hash): editar cria outra versão e outro
hash, então a aprovação anterior deixa de ser atual. Nada aqui apaga histórico nem
reescreve fontes.

Limite explícito: a duração continua sendo estimativa por palavras/minuto, não a
duração exata de cada síntese. O ritmo padrão é o **medido** na voz do produto
(``piper:pt_BR-faber-medium``): 172 palavras/minuto efetivas, contra a hipótese
antiga de 150. O ritmo e o alvo continuam configuráveis; para a estimativa com
pausas medidas do Piper use ``estimate_voice_durations`` (domínio).
"""
from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from ..domain.contracts import Scene, Script, VideoStatus
from ..domain.longform import (
    MAX_LONG_SCENES,
    MIN_LONG_SCENES,
    Block,
    Chapter,
    ScriptApproval,
    ScriptPlan,
    ScriptReview,
    plan_content_hash,
    review_script,
    validate_structure,
)
from ..domain.narration_duration import (
    MEASURED_EFFECTIVE_WORDS_PER_MINUTE,
    estimate_text_durations,
)
from .budget import PaidOperationGuard, paid_key, provider_settlement
from .editorial import (
    MAX_PROMPT_CHARS,
    CostGuard,
    ScriptRejected,
    SourceRefused,
    StateConflict,
    _claims,
    _require_video,
    _usd,
    build_prompt,
    parse_scene_drafts,
)
from .ports import (
    FactCheckReader,
    LongFormScriptRepository,
    SceneDraft,
    ScriptRepository,
    SnapshotRepository,
    TextModel,
    UsageRepository,
    VideoRepository,
)

# Ritmo padrão: o medido na voz do produto (Piper pt_BR-faber-medium), não a
# hipótese antiga de 150. Ver domain/narration_duration.py e o relatório de
# calibração. Continua configurável por chamada.
DEFAULT_WORDS_PER_MINUTE = MEASURED_EFFECTIVE_WORDS_PER_MINUTE
DEFAULT_TARGET_SECONDS = 480.0
DEFAULT_DURATION_TOLERANCE = 0.15
LONG_MIN_CHAPTERS = 3

_BLOCK_LABELS = {
    Block.HOOK: "Gancho",
    Block.CONTEXT: "Contexto",
    Block.DEVELOPMENT: "Desenvolvimento",
    Block.PAYOFF: "Payoff",
    Block.CTA: "CTA",
}
_BLOCK_ORDER = tuple(_BLOCK_LABELS)


def block_label(block: Block) -> str:
    return _BLOCK_LABELS[block]


class ScriptVersionStale(RuntimeError):
    """A versão/hash aprovada já não é a mais recente: outra edição criou uma versão nova."""


class ScriptApprovalRefused(ValueError):
    """A aprovação foi recusada porque o roteiro não passa na revisão ou no fact-check da versão."""


@dataclass(frozen=True)
class LongScriptResult:
    """Resultado do motor long-form: roteiro gravado, plano, cenas, revisão e custo somado."""

    script: Script
    plan: ScriptPlan
    scenes: tuple[Scene, ...]
    review: ScriptReview
    cost_usd: float
    estimated_duration_seconds: float
    word_count: int

    @property
    def scene_count(self) -> int:
        return len(self.scenes)


# ---------------------------------------------------------------------------
# Prompts: curto e longo são construções distintas, não um parâmetro a mais.
# ---------------------------------------------------------------------------


def _facts_block(claims) -> str:
    return "\n".join(f"[{c.id}] {c.text}" for c in claims)


def build_long_outline_prompt(topic: str, claims, target_seconds: float, words_per_minute: float) -> str:
    """Passagem 1: plano de capítulos por blocos narrativos."""
    return (
        f"Você planeja o roteiro de um vídeo LONGO em português do Brasil sobre: {topic}.\n"
        f"Duração alvo ~{int(target_seconds)}s, ritmo ~{words_per_minute:.0f} palavras/minuto.\n"
        f"Organize em 3 a 6 capítulos cobrindo, nesta ordem, gancho, contexto, desenvolvimento e payoff/CTA.\n"
        f"Use SOMENTE os fatos abaixo. Não invente números, datas, nomes ou lugares.\n\n"
        f"FATOS:\n{_facts_block(claims)}\n\n"
        f"Responda apenas com JSON: {{\"chapters\": [{{\"title\": str, \"block\": "
        f"\"hook|context|development|payoff|cta\", \"scene_count\": int, \"references\": [ids dos fatos usados]}}]}} "
        f"com {MIN_LONG_SCENES} a {MAX_LONG_SCENES} cenas no total."
    )


def build_long_scenes_prompt(topic: str, plan: ScriptPlan, claims) -> str:
    """Passagem 2: cenas do roteiro seguindo o plano de capítulos, com citações."""
    summary = "; ".join(
        f"{index + 1}. {chapter.title} ({block_label(chapter.block)}), {chapter.scene_count} cenas"
        for index, chapter in enumerate(plan.chapters)
    )
    return (
        f"Escreva as cenas do roteiro longo em português do Brasil sobre: {topic}.\n"
        f"Siga o plano de capítulos: {summary}.\n"
        f"Use SOMENTE os fatos abaixo. Não invente números, datas, nomes ou lugares. Evento encerrado: escreva no passado.\n"
        f"Não use fotos ou nomes de pessoas que não estejam nos fatos.\n\n"
        f"FATOS:\n{_facts_block(claims)}\n\n"
        f"Responda apenas com JSON: {{\"scenes\": [{{\"narration\": str (5-400 caracteres), \"caption\": str (até 110), "
        f"\"label\": str (até 32), \"image_prompt\": str (cena genérica, sem pessoas reais, 10-500 caracteres), "
        f"\"claim_ids\": [ids dos fatos usados nesta cena]}}]}} com {plan.scene_count} cenas."
    )


def build_prompt_for_format(fmt, topic: str, claims, scene_count: int, *, target_seconds: float = DEFAULT_TARGET_SECONDS,
                            words_per_minute: float = DEFAULT_WORDS_PER_MINUTE) -> str:
    """Separa explicitamente o prompt curto do longo (F4-02)."""
    if getattr(fmt, "value", fmt) == "long":
        return build_long_outline_prompt(topic, claims, target_seconds, words_per_minute)
    return build_prompt(topic, claims, scene_count)


# ---------------------------------------------------------------------------
# Parse da passagem 1 (plano de capítulos)
# ---------------------------------------------------------------------------


def parse_outline(raw: str, *, target_seconds: float, words_per_minute: float,
                  valid_claim_ids: set[str]) -> ScriptPlan:
    """Converte a saída do modelo no plano tipado; recusa plano fora do arco do formato longo."""
    try:
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start:end + 1])
        chapters = data["chapters"]
    except (ValueError, KeyError, TypeError, RecursionError) as exc:
        raise ScriptRejected("outline output is not the expected JSON") from exc
    if not isinstance(chapters, list) or not LONG_MIN_CHAPTERS <= len(chapters) <= 12:
        raise ScriptRejected(f"expected {LONG_MIN_CHAPTERS}-12 chapters")
    parsed: list[Chapter] = []
    for i, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            raise ScriptRejected(f"chapter {i} is not an object")
        title, block, count = chapter.get("title"), chapter.get("block"), chapter.get("scene_count")
        if not isinstance(title, str) or not title.strip():
            raise ScriptRejected(f"chapter {i}: title is required")
        try:
            block_value = Block(block)
        except (ValueError, TypeError) as exc:
            raise ScriptRejected(f"chapter {i}: unknown block {block!r}") from exc
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_LONG_SCENES:
            raise ScriptRejected(f"chapter {i}: scene_count must be an integer between 1 and {MAX_LONG_SCENES}")
        references = chapter.get("references") or []
        if not isinstance(references, list) or not all(isinstance(r, str) for r in references):
            raise ScriptRejected(f"chapter {i}: references must be a list of ids")
        parsed.append(Chapter(title=title.strip(), block=block_value, scene_count=count,
                              target_seconds=1.0, references=tuple(r for r in references if r in valid_claim_ids)))
    total = sum(chapter.scene_count for chapter in parsed)
    if not MIN_LONG_SCENES <= total <= MAX_LONG_SCENES:
        raise ScriptRejected(f"a long script needs {MIN_LONG_SCENES}-{MAX_LONG_SCENES} scenes, got {total}")
    # Distribui o alvo proporcionalmente às cenas (o modelo não precisa acertar segundos).
    with_seconds = tuple(
        chapter.model_copy(update={"target_seconds": target_seconds * chapter.scene_count / total})
        for chapter in parsed
    )
    plan = ScriptPlan(words_per_minute=words_per_minute, target_seconds=target_seconds, chapters=with_seconds)
    try:
        validate_structure(plan)
    except ValueError as exc:
        raise ScriptRejected(f"invalid chapter plan: {exc}") from exc
    return plan


# ---------------------------------------------------------------------------
# Geração em duas passagens (F4-04)
# ---------------------------------------------------------------------------


def _fit_claims(topic: str, claims, render: Callable[[list], str]) -> list:
    """Mantém, na ordem, os fatos que cabem no limite de prompt (só eles valem como claim_ids)."""
    kept: list = []
    for claim in claims:
        if len(render(kept + [claim])) > MAX_PROMPT_CHARS:
            break
        kept.append(claim)
    return kept


def _drafts_to_scenes(video_id: str, drafts: Sequence[SceneDraft]) -> list[Scene]:
    return [
        Scene(id=f"{i:032x}", video_id=video_id, idx=i, narration=d.narration, caption=d.caption,
              label=d.label, image_prompt=d.image_prompt, claim_ids=list(d.claim_ids))
        for i, d in enumerate(drafts)
    ]


class GenerateLongScript:
    """Gera roteiro longo em duas passagens e o grava com plano, hash e revisão."""

    def __init__(self, videos: VideoRepository, snaps: SnapshotRepository, scripts: ScriptRepository,
                 text_model: TextModel | None, guard: CostGuard, usage: UsageRepository,
                 longform: LongFormScriptRepository, model_for: Callable[[str], TextModel] | None = None,
                 paid: PaidOperationGuard | None = None, words_per_minute: float = DEFAULT_WORDS_PER_MINUTE,
                 target_seconds: float = DEFAULT_TARGET_SECONDS, tolerance: float = DEFAULT_DURATION_TOLERANCE,
                 allow_names: frozenset[str] = frozenset()):
        self.videos, self.snaps, self.scripts, self.text_model = videos, snaps, scripts, text_model
        self.guard, self.usage, self.longform = guard, usage, longform
        self.model_for, self.paid = model_for, paid
        self.words_per_minute, self.target_seconds, self.tolerance = words_per_minute, target_seconds, tolerance
        self.allow_names = allow_names

    def execute(self, video_id: str, *, target_seconds: float | None = None,
                words_per_minute: float | None = None) -> LongScriptResult:
        video = _require_video(self.videos, video_id)
        if video.status not in (VideoStatus.IDEA, VideoStatus.SCRIPTED):
            raise StateConflict(f"cannot write a long script in state {video.status.value}")
        snapshots = self.snaps.list(video_id)
        claims = _claims(snapshots)
        if not claims:
            raise SourceRefused("no sources with checkable claims: add sources first")
        wpm = self.words_per_minute if words_per_minute is None else words_per_minute
        target = self.target_seconds if target_seconds is None else target_seconds
        claim_ids = {c.id for c in claims}
        model = self.model_for(video.project_id) if self.model_for else self.text_model

        outline_claims = _fit_claims(video.topic, claims,
                                     lambda kept: build_long_outline_prompt(video.topic, kept, target, wpm))
        if not outline_claims:
            raise SourceRefused("topic and claims do not fit the model prompt limit")
        outline_prompt = build_long_outline_prompt(video.topic, outline_claims, target, wpm)
        outline, outline_cost = self._call(model, video_id, "longform-outline", outline_prompt,
                                           validate=lambda res: parse_outline(res.text, target_seconds=target,
                                                                              words_per_minute=wpm,
                                                                              valid_claim_ids=claim_ids))

        scenes_claims = _fit_claims(video.topic, outline_claims,
                                    lambda kept: build_long_scenes_prompt(video.topic, outline, kept))
        scenes_prompt = build_long_scenes_prompt(video.topic, outline, scenes_claims)
        drafts, scenes_cost = self._call(model, video_id, "longform-scenes", scenes_prompt,
                                         validate=lambda res: parse_scene_drafts(
                                             res.text, {c.id for c in scenes_claims},
                                             min_scenes=MIN_LONG_SCENES, max_scenes=MAX_LONG_SCENES))

        scenes = _drafts_to_scenes(video_id, drafts)
        review = review_script(outline, scenes, sources=[s.text for s in snapshots], known_claim_ids=claim_ids,
                               allow_names=self.allow_names, tolerance=self.tolerance)
        if not review.passed:
            raise ScriptRejected(f"long script did not pass review: {_review_reasons(review)}")

        content_hash = plan_content_hash(outline, scenes)
        text = "\n".join(d.narration for d in drafts)
        cited = sorted({c for d in drafts for c in d.claim_ids})
        script = self.longform.save_planned_version(video_id, text, drafts, cited, outline, content_hash,
                                                    video.status, VideoStatus.SCRIPTED)
        if script is None:
            raise StateConflict("video state changed while generating the long script")
        durations = estimate_text_durations([d.narration for d in drafts], wpm)
        return LongScriptResult(script=script, plan=outline, scenes=tuple(scenes), review=review,
                                cost_usd=outline_cost + scenes_cost,
                                estimated_duration_seconds=durations.total_seconds,
                                word_count=sum(len(d.narration.split()) for d in drafts))

    def _call(self, model: TextModel, video_id: str, kind: str, prompt: str, *, validate):
        """Uma passagem paga: reserva, chama uma vez, valida antes de confirmar o custo."""
        estimate = model.cost_estimate(prompt)
        if self.paid is None:
            self.guard.check(video_id, estimate)
            result = model.complete(prompt, json_schema=_LONG_SCHEMA)
            self.usage.record(video_id, result.usage)  # a chamada aconteceu: contabiliza mesmo se a saída for recusada
            return validate(result), result.usage.cost_usd
        key = paid_key(kind, video_id, getattr(model, "model", ""), model.name, prompt)
        result = self.paid.run(key, video_id, _usd(estimate),
                               call=lambda: model.complete(prompt, json_schema=_LONG_SCHEMA),
                               validate=validate,
                               settle=lambda res: provider_settlement(res.usage, settled_by=f"studio:{kind}:{model.name}"))
        return result, result.usage.cost_usd


_LONG_SCHEMA = {"type": "object", "properties": {"chapters": {"type": "array"}, "scenes": {"type": "array"}}}


def _review_reasons(review: ScriptReview) -> str:
    reasons: list[str] = []
    if not review.structure_ok:
        reasons.append("estrutura fora do arco gancho→fechamento")
    if not review.continuity_ok:
        reasons.append("capítulos não cobrem as cenas")
    if review.redundant_scene_idxs:
        reasons.append(f"cenas redundantes {list(review.redundant_scene_idxs)}")
    if not review.duration_ok:
        reasons.append(f"duração estimada {review.estimated_seconds:.0f}s fora da tolerância de {review.target_seconds:.0f}s")
    if review.uncited_scene_idxs:
        reasons.append(f"cenas sem citação {list(review.uncited_scene_idxs)}")
    if review.unknown_claim_ids:
        reasons.append(f"claims desconhecidas {list(review.unknown_claim_ids)}")
    if review.unsupported:
        reasons.append("invenção: " + ", ".join(f"{item.kind}={item.value}" for item in review.unsupported))
    return "; ".join(reasons) or "revisão reprovada"


# ---------------------------------------------------------------------------
# Edição: cria outra versão e invalida a aprovação por hash (F4-06/F4-08)
# ---------------------------------------------------------------------------


class EditScriptScene:
    """Reescreve uma cena criando nova versão. A aprovação anterior deixa de ser atual."""

    def __init__(self, videos: VideoRepository, snaps: SnapshotRepository, scripts: ScriptRepository,
                 longform: LongFormScriptRepository, allow_names: frozenset[str] = frozenset(),
                 tolerance: float = DEFAULT_DURATION_TOLERANCE):
        self.videos, self.snaps, self.scripts = videos, snaps, scripts
        self.longform, self.allow_names, self.tolerance = longform, allow_names, tolerance

    def execute(self, video_id: str, scene_idx: int, narration: str, *, expected_version: int,
                caption: str | None = None, image_prompt: str | None = None,
                claim_ids: Sequence[str] | None = None) -> LongScriptResult:
        video = _require_video(self.videos, video_id)
        if video.status not in (VideoStatus.IDEA, VideoStatus.SCRIPTED):
            raise StateConflict(
                f"editing a script is only available in IDEA/SCRIPTED, got {video.status.value}; "
                "re-run production to rewind downstream outputs")
        records = self.longform.list_script_records(video_id)
        if not records or records[-1].script.version != expected_version or records[-1].plan is None:
            raise ScriptVersionStale("the requested version is not the latest script version")
        plan = records[-1].plan
        snapshots = self.snaps.list(video_id)
        claims = _claims(snapshots)
        claim_ids_set = {c.id for c in claims}
        drafts = _scenes_to_drafts(self.scripts.scenes(video_id))
        if not 0 <= scene_idx < len(drafts):
            raise ValueError(f"scene index {scene_idx} is out of range")
        current = drafts[scene_idx]
        drafts[scene_idx] = SceneDraft(
            narration=narration.strip(), caption=(caption if caption is not None else current.caption),
            label=current.label, image_prompt=(image_prompt if image_prompt is not None else current.image_prompt),
            claim_ids=list(claim_ids) if claim_ids is not None else current.claim_ids,
        )
        scenes = _drafts_to_scenes(video_id, drafts)
        review = review_script(plan, scenes, sources=[s.text for s in snapshots], known_claim_ids=claim_ids_set,
                               allow_names=self.allow_names, tolerance=self.tolerance)
        if not review.passed:
            raise ScriptRejected(f"edited script did not pass review: {_review_reasons(review)}")
        content_hash = plan_content_hash(plan, scenes)
        text = "\n".join(d.narration for d in drafts)
        cited = sorted({c for d in drafts for c in d.claim_ids})
        script = self.longform.save_planned_version(video_id, text, drafts, cited, plan, content_hash,
                                                    video.status, VideoStatus.SCRIPTED)
        if script is None:
            raise ScriptVersionStale("the script changed while editing")
        durations = estimate_text_durations([d.narration for d in drafts], plan.words_per_minute)
        return LongScriptResult(script=script, plan=plan, scenes=tuple(scenes), review=review, cost_usd=0.0,
                                estimated_duration_seconds=durations.total_seconds,
                                word_count=sum(len(d.narration.split()) for d in drafts))


def _scenes_to_drafts(scenes: Sequence[Scene]) -> list[SceneDraft]:
    return [SceneDraft(s.narration, s.caption, s.label, s.image_prompt, list(s.claim_ids)) for s in scenes]


# ---------------------------------------------------------------------------
# Aprovação humana presa à versão e ao hash (F4-06)
# ---------------------------------------------------------------------------


class ApproveScriptVersion:
    """Registra a aprovação humana da versão exata, após revisão e fact-check passarem."""

    def __init__(self, videos: VideoRepository, snaps: SnapshotRepository, scripts: ScriptRepository,
                 longform: LongFormScriptRepository,
                 checks: FactCheckReader | None = None, allow_names: frozenset[str] = frozenset(),
                 tolerance: float = DEFAULT_DURATION_TOLERANCE, clock: Callable[[], datetime] | None = None):
        self.videos, self.snaps, self.scripts, self.longform = videos, snaps, scripts, longform
        self.checks = checks
        self.allow_names, self.tolerance = allow_names, tolerance
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def execute(self, video_id: str, *, version: int, content_hash: str, approved_by: str,
                decision: str = "approved", reason: str = "") -> ScriptApproval:
        _require_video(self.videos, video_id)
        records = self.longform.list_script_records(video_id)
        if not records or records[-1].script.version != version:
            raise ScriptVersionStale("only the latest script version can be decided")
        latest = records[-1]
        if latest.content_hash != content_hash or latest.plan is None:
            raise ScriptVersionStale("the content hash does not match the latest script version")
        if decision == "approved":
            self._require_review(video_id, latest.plan, version)
        ok = self.longform.approve(video_id, version, content_hash, decision, reason, approved_by.strip(),
                                   approved_at=self.clock())
        if not ok:
            raise ScriptVersionStale("the script version changed while approving")
        return ScriptApproval(video_id=video_id, script_version=version, content_hash=content_hash,
                              decision=decision, reason=reason, approved_by=approved_by.strip(),
                              approved_at=self.clock())

    def _require_review(self, video_id: str, plan: ScriptPlan, version: int) -> None:
        record = self.checks.latest(video_id) if self.checks is not None else None
        if record is None or record.script_version != version:
            raise ScriptApprovalRefused("the fact-check of this script version is missing")
        if not record.report.passed:
            raise ScriptApprovalRefused("the fact-check of this script version did not pass")
        snapshots = self.snaps.list(video_id)
        scenes = self.scripts.scenes(video_id)
        review = review_script(plan, scenes, sources=[s.text for s in snapshots],
                               known_claim_ids={c.id for c in _claims(snapshots)},
                               allow_names=self.allow_names, tolerance=self.tolerance)
        if not review.passed:
            raise ScriptApprovalRefused(f"the script did not pass review: {_review_reasons(review)}")
