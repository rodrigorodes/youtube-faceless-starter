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

F04: idioma e orientação editorial vêm do ``EditorialContext`` derivado da
configuração efetiva; o alvo pode vir da duração declarada pelo canal (acima do
default curto), mas o ritmo continua o medido — não é campo do canal.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from ..domain.contracts import Scene, Script, Video, VideoStatus
from ..domain.effective_config import EffectiveConfig
from ..domain.facts import check_narration, supporting_claim_ids
from ..domain.longform import (
    MAX_LONG_SCENES,
    MIN_LONG_SCENES,
    Block,
    Chapter,
    ScriptApproval,
    ScriptPlan,
    ScriptReview,
    approval_is_current,
    chapter_for_position,
    plan_content_hash,
    review_script,
    validate_structure,
    with_chapter_scene_delta,
)
from ..domain.narration_duration import (
    MEASURED_EFFECTIVE_WORDS_PER_MINUTE,
    estimate_text_durations,
)
from .budget import PaidOperationGuard, paid_key, provider_settlement
from .editorial import (
    DEFAULT_DURATION_S,
    DEFAULT_LANGUAGE,
    MAX_PROMPT_CHARS,
    CostGuard,
    EditorialContext,
    ScriptRejected,
    SourceRefused,
    StateConflict,
    _claims,
    _require_video,
    _usd,
    build_prompt,
    context_for_video,
    context_guidance,
    language_label,
    parse_scene_drafts,
)
from .errors import InvalidInput, ScriptEditIdempotencyConflict, ScriptRevisionUnavailable
from .ports import (
    FactCheckReader,
    LongFormScriptRepository,
    SceneDraft,
    SceneRevision,
    ScriptEditOutcome,
    ScriptEditRecord,
    ScriptRecord,
    ScriptRepository,
    ScriptRevisionSummary,
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
    plan: ScriptPlan | None  # None: roteiro curto editado sem plano de capítulos
    scenes: tuple[Scene, ...]
    review: ScriptReview | None
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


def build_long_outline_prompt(topic: str, claims, target_seconds: float, words_per_minute: float, *,
                              context: EditorialContext | None = None) -> str:
    """Passagem 1: plano de capítulos por blocos narrativos."""
    language = language_label(context.language if context is not None else DEFAULT_LANGUAGE)
    return (
        f"Você planeja o roteiro de um vídeo LONGO em {language} sobre: {topic}.\n"
        f"Duração alvo ~{int(target_seconds)}s, ritmo ~{words_per_minute:.0f} palavras/minuto.\n"
        f"Organize em 3 a 6 capítulos cobrindo, nesta ordem, gancho, contexto, desenvolvimento e payoff/CTA.\n"
        f"{context_guidance(context)}"
        f"Use SOMENTE os fatos abaixo. Não invente números, datas, nomes ou lugares.\n\n"
        f"FATOS:\n{_facts_block(claims)}\n\n"
        f"Responda apenas com JSON: {{\"chapters\": [{{\"title\": str, \"block\": "
        f"\"hook|context|development|payoff|cta\", \"scene_count\": int, \"references\": [ids dos fatos usados]}}]}} "
        f"com {MIN_LONG_SCENES} a {MAX_LONG_SCENES} cenas no total."
    )


def build_long_scenes_prompt(topic: str, plan: ScriptPlan, claims, *,
                             context: EditorialContext | None = None) -> str:
    """Passagem 2: cenas do roteiro seguindo o plano de capítulos, com citações."""
    summary = "; ".join(
        f"{index + 1}. {chapter.title} ({block_label(chapter.block)}), {chapter.scene_count} cenas"
        for index, chapter in enumerate(plan.chapters)
    )
    language = language_label(context.language if context is not None else DEFAULT_LANGUAGE)
    return (
        f"Escreva as cenas do roteiro longo em {language} sobre: {topic}.\n"
        f"Siga o plano de capítulos: {summary}.\n"
        f"{context_guidance(context)}"
        f"Use SOMENTE os fatos abaixo. Não invente números, datas, nomes ou lugares. Evento encerrado: escreva no passado.\n"
        f"Não use fotos ou nomes de pessoas que não estejam nos fatos.\n\n"
        f"FATOS:\n{_facts_block(claims)}\n\n"
        f"Responda apenas com JSON: {{\"scenes\": [{{\"narration\": str (5-400 caracteres), \"caption\": str (até 110), "
        f"\"label\": str (até 32), \"image_prompt\": str (cena genérica, sem pessoas reais, 10-500 caracteres), "
        f"\"claim_ids\": [ids dos fatos usados nesta cena]}}]}} com {plan.scene_count} cenas."
    )


def build_prompt_for_format(fmt, topic: str, claims, scene_count: int, *, target_seconds: float = DEFAULT_TARGET_SECONDS,
                            words_per_minute: float = DEFAULT_WORDS_PER_MINUTE,
                            context: EditorialContext | None = None) -> str:
    """Separa explicitamente o prompt curto do longo (F4-02); o contexto editorial é o do canal."""
    if getattr(fmt, "value", fmt) == "long":
        return build_long_outline_prompt(topic, claims, target_seconds, words_per_minute, context=context)
    return build_prompt(topic, claims, scene_count, context=context)


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
                 target_seconds: float | None = None, tolerance: float = DEFAULT_DURATION_TOLERANCE,
                 allow_names: frozenset[str] = frozenset(),
                 editorial_for: Callable[[Video], EffectiveConfig | EditorialContext | None] | None = None):
        """`target_seconds` explícito (construtor ou chamada) vence o perfil; sem nenhum dos dois o
        alvo longo continua 480 s. `editorial_for(video)` traz idioma e contexto da configuração
        efetiva; `words_per_minute` continua o **medido** da voz, nunca um campo do canal."""
        self.videos, self.snaps, self.scripts, self.text_model = videos, snaps, scripts, text_model
        self.guard, self.usage, self.longform = guard, usage, longform
        self.model_for, self.paid = model_for, paid
        self.words_per_minute, self.target_seconds, self.tolerance = words_per_minute, target_seconds, tolerance
        self.allow_names = allow_names
        self.editorial_for = editorial_for

    def _editorial_context(self, video: Video) -> EditorialContext | None:
        if self.editorial_for is None:
            return None
        return context_for_video(self.editorial_for(video), video)

    def _target_for(self, context: EditorialContext | None, target_seconds: float | None) -> float:
        """Precedência: chamada > construtor > duração declarada pelo canal > 480 s do formato longo."""
        if target_seconds is not None:
            return target_seconds
        if self.target_seconds is not None:
            return self.target_seconds
        declared = context.declared_duration_s if context is not None else None
        # O perfil grava 60 s por default: um alvo de 60 s é indistinguível de "não configurado para
        # longo" e não pode encolher o formato. Só uma duração acima do default curto governa o longo.
        if declared is not None and declared > DEFAULT_DURATION_S:
            return float(declared)
        return DEFAULT_TARGET_SECONDS

    def execute(self, video_id: str, *, target_seconds: float | None = None,
                words_per_minute: float | None = None) -> LongScriptResult:
        video = _require_video(self.videos, video_id)
        if video.status not in (VideoStatus.IDEA, VideoStatus.SCRIPTED):
            raise StateConflict(f"cannot write a long script in state {video.status.value}")
        snapshots = self.snaps.list(video_id)
        claims = _claims(snapshots)
        if not claims:
            raise SourceRefused("no sources with checkable claims: add sources first")
        context = self._editorial_context(video)
        wpm = self.words_per_minute if words_per_minute is None else words_per_minute
        target = self._target_for(context, target_seconds)
        claim_ids = {c.id for c in claims}
        model = self.model_for(video.project_id) if self.model_for else self.text_model

        outline_claims = _fit_claims(video.topic, claims,
                                     lambda kept: build_long_outline_prompt(video.topic, kept, target, wpm,
                                                                            context=context))
        if not outline_claims:
            raise SourceRefused("topic and claims do not fit the model prompt limit")
        outline_prompt = build_long_outline_prompt(video.topic, outline_claims, target, wpm, context=context)
        outline, outline_cost = self._call(model, video_id, "longform-outline", outline_prompt,
                                           validate=lambda res: parse_outline(res.text, target_seconds=target,
                                                                              words_per_minute=wpm,
                                                                              valid_claim_ids=claim_ids))

        scenes_claims = _fit_claims(video.topic, outline_claims,
                                    lambda kept: build_long_scenes_prompt(video.topic, outline, kept,
                                                                          context=context))
        scenes_prompt = build_long_scenes_prompt(video.topic, outline, scenes_claims, context=context)
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


def _payload_digest(payload: dict) -> str:
    """sha256 canônico do payload da edição: replay idêntico = mesmo hash; mudança = outro hash."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_script_editable(video: Video) -> None:
    if video.status not in (VideoStatus.IDEA, VideoStatus.SCRIPTED):
        raise StateConflict(
            f"editing a script is only available in IDEA/SCRIPTED, got {video.status.value}; "
            "re-run production to rewind downstream outputs")


class _ScriptSceneMutation:
    """Base comum das mutações de cena: carrega a versão corrente, revisa e grava com CAS/idempotência."""

    def __init__(self, videos: VideoRepository, snaps: SnapshotRepository, scripts: ScriptRepository,
                 longform: LongFormScriptRepository, allow_names: frozenset[str] = frozenset(),
                 tolerance: float = DEFAULT_DURATION_TOLERANCE):
        self.videos, self.snaps, self.scripts = videos, snaps, scripts
        self.longform, self.allow_names, self.tolerance = longform, allow_names, tolerance

    def _load(self, video_id: str, expected_version: int):
        video = _require_video(self.videos, video_id)
        _require_script_editable(video)
        records = self.longform.list_script_records(video_id)
        if not records or records[-1].script.version != expected_version:
            latest = records[-1].script.version if records else None
            raise ScriptVersionStale(
                f"the requested version {expected_version} is not the latest script version ({latest})")
        # `plan` é None no roteiro curto gerado pelas fontes: ele é editável sem plano (sem revisão de capítulos).
        plan = records[-1].plan
        snapshots = self.snaps.list(video_id)
        claims = _claims(snapshots)
        drafts = _scenes_to_drafts(self.scripts.scenes(video_id))
        return video, plan, drafts, snapshots, claims

    def _citation(self, narration: str, claims, fallback: Sequence[str]) -> list[str]:
        """Citação da cena para o texto novo: o fact-check confere a cena só contra os fatos que ela cita.

        Sem derivar, editar o texto para outro fato das fontes passava na edição (que olha todas as fontes) e
        reprovava depois no fact-check. Sem número ou nome checável, ou sem fato que cubra todos, mantém a anterior.
        """
        derived = supporting_claim_ids(narration, [(c.id, c.text) for c in claims], self.allow_names)
        return derived if derived else list(fallback)

    def _review_planless(self, drafts: Sequence[SceneDraft], snapshots, changed: Sequence[int]) -> None:
        """Roteiro curto: só o texto novo ou editado precisa ter lastro nas fontes (o resto já foi checado antes)."""
        sources = [snap.text for snap in snapshots]
        problems = []
        for position in changed:
            for issue in check_narration(drafts[position].narration, sources, self.allow_names):
                problems.append(f"scene {position + 1}: {issue.kind} {issue.value!r}")
        if problems:
            raise ScriptRejected("edited script did not pass review: content not found in the sources ("
                                 + "; ".join(problems[:5]) + "). Add a source that supports it or rewrite the text")

    def _review_and_hash(self, video_id: str, plan: ScriptPlan, drafts: Sequence[SceneDraft],
                         snapshots, claims):
        scenes = _drafts_to_scenes(video_id, drafts)
        review = review_script(plan, scenes, sources=[s.text for s in snapshots],
                               known_claim_ids={c.id for c in claims},
                               allow_names=self.allow_names, tolerance=self.tolerance)
        if not review.passed:
            raise ScriptRejected(f"edited script did not pass review: {_review_reasons(review)}")
        content_hash = plan_content_hash(plan, scenes)
        text = "\n".join(d.narration for d in drafts)
        cited = sorted({c for d in drafts for c in d.claim_ids})
        return review, content_hash, text, cited

    def _result(self, script: Script, plan: ScriptPlan, drafts: Sequence[SceneDraft],
                review: ScriptReview) -> LongScriptResult:
        durations = estimate_text_durations([d.narration for d in drafts], plan.words_per_minute)
        return LongScriptResult(script=script, plan=plan, scenes=tuple(_drafts_to_scenes(script.video_id, drafts)),
                                review=review, cost_usd=0.0,
                                estimated_duration_seconds=durations.total_seconds,
                                word_count=sum(len(d.narration.split()) for d in drafts))

    def _result_from_outcome(self, outcome: ScriptEditOutcome, plan: ScriptPlan | None,
                             review: ScriptReview | None) -> LongScriptResult:
        durations = estimate_text_durations([s.narration for s in outcome.scenes],
                                            plan.words_per_minute if plan is not None else DEFAULT_WORDS_PER_MINUTE)
        return LongScriptResult(script=outcome.script, plan=plan, scenes=outcome.scenes, review=review,
                                cost_usd=0.0, estimated_duration_seconds=durations.total_seconds,
                                word_count=sum(len(s.narration.split()) for s in outcome.scenes))

    def _plan_for_version(self, video_id: str, version: int) -> ScriptPlan | None:
        for record in self.longform.list_script_records(video_id):
            if record.script.version == version:
                return record.plan  # None no roteiro curto, que não tem plano de capítulos
        raise ScriptVersionStale(f"the stored edit result for version {version} does not exist")

    def _replay(self, video_id: str, idempotency_key: str, digest: str) -> LongScriptResult | None:
        existing = self.longform.find_edit(video_id, idempotency_key)
        if existing is None:
            return None
        if existing.payload_sha256 != digest:
            raise ScriptEditIdempotencyConflict(
                "idempotency key already used with a different payload")
        plan = self._plan_for_version(video_id, existing.outcome.script.version)
        if plan is None:
            return self._result_from_outcome(existing.outcome, None, None)
        snapshots = self.snaps.list(video_id)
        claims = _claims(snapshots)
        review = review_script(plan, list(existing.outcome.scenes), sources=[s.text for s in snapshots],
                               known_claim_ids={c.id for c in claims},
                               allow_names=self.allow_names, tolerance=self.tolerance)
        return self._result_from_outcome(existing.outcome, plan, review)

    def _save(self, video: Video, plan: ScriptPlan | None, drafts: Sequence[SceneDraft], snapshots, claims,
              expected_version: int, idempotency_key: str, digest: str,
              changed: Sequence[int] = ()) -> LongScriptResult:
        if plan is None:
            self._review_planless(drafts, snapshots, changed)
            text = "\n".join(d.narration for d in drafts)
            cited = sorted({c for d in drafts for c in d.claim_ids})
            outcome = self.longform.save_edit(video.id, idempotency_key, digest, expected_version, text, drafts,
                                              cited, None, None, video.status, VideoStatus.SCRIPTED)
            if outcome is None:
                raise ScriptVersionStale(
                    f"the requested version {expected_version} is not the latest script version")
            return self._result_from_outcome(outcome, None, None)
        review, content_hash, text, cited = self._review_and_hash(video.id, plan, drafts, snapshots, claims)
        outcome = self.longform.save_edit(video.id, idempotency_key, digest, expected_version, text, drafts,
                                          cited, plan, content_hash, video.status, VideoStatus.SCRIPTED)
        if outcome is None:
            raise ScriptVersionStale(
                f"the requested version {expected_version} is not the latest script version")
        return self._result_from_outcome(outcome, plan, review)


class EditScriptScene(_ScriptSceneMutation):
    """Reescreve uma cena criando nova versão. A aprovação anterior deixa de ser atual."""

    def execute(self, video_id: str, scene_idx: int, narration: str, *, expected_version: int,
                caption: str | None = None, image_prompt: str | None = None,
                claim_ids: Sequence[str] | None = None) -> LongScriptResult:
        video, plan, drafts, snapshots, claims = self._load(video_id, expected_version)
        if plan is None:
            raise StateConflict("this script has no chapter plan: edit it with an idempotency key")
        if not 0 <= scene_idx < len(drafts):
            raise InvalidInput(f"scene index {scene_idx} is out of range")
        current = drafts[scene_idx]
        drafts[scene_idx] = SceneDraft(
            narration=narration.strip(), caption=(caption if caption is not None else current.caption),
            label=current.label, image_prompt=(image_prompt if image_prompt is not None else current.image_prompt),
            claim_ids=(list(claim_ids) if claim_ids is not None
                       else self._citation(narration.strip(), claims, current.claim_ids)
                       if narration.strip() != current.narration else current.claim_ids),
        )
        review, content_hash, text, cited = self._review_and_hash(video_id, plan, drafts, snapshots, claims)
        script = self.longform.save_planned_version(video_id, text, drafts, cited, plan, content_hash,
                                                    video.status, VideoStatus.SCRIPTED)
        if script is None:
            raise ScriptVersionStale("the script changed while editing")
        return self._result(script, plan, drafts, review)

    def execute_idempotent(self, video_id: str, scene_idx: int, narration: str, *, expected_version: int,
                           idempotency_key: str, caption: str | None = None,
                           image_prompt: str | None = None,
                           claim_ids: Sequence[str] | None = None) -> LongScriptResult:
        digest = _payload_digest({
            "kind": "edit", "scene": scene_idx, "expected_version": expected_version,
            "narration": narration.strip(),
            "caption": caption.strip() if caption is not None else None,
            "image_prompt": image_prompt.strip() if image_prompt is not None else None,
            "claim_ids": list(claim_ids) if claim_ids is not None else None,
        })
        replay = self._replay(video_id, idempotency_key, digest)
        if replay is not None:
            return replay
        video, plan, drafts, snapshots, claims = self._load(video_id, expected_version)
        if not 0 <= scene_idx < len(drafts):
            raise InvalidInput(f"scene index {scene_idx} is out of range")
        current = drafts[scene_idx]
        drafts[scene_idx] = SceneDraft(
            narration=narration.strip(), caption=(caption if caption is not None else current.caption),
            label=current.label, image_prompt=(image_prompt if image_prompt is not None else current.image_prompt),
            claim_ids=(list(claim_ids) if claim_ids is not None
                       else self._citation(narration.strip(), claims, current.claim_ids)
                       if narration.strip() != current.narration else current.claim_ids),
        )
        changed = [scene_idx] if drafts[scene_idx].narration != current.narration else []
        return self._save(video, plan, drafts, snapshots, claims, expected_version, idempotency_key, digest,
                          changed)


class AddScriptScene(_ScriptSceneMutation):
    """Adiciona uma cena em posição explícita (ou no fim) criando nova versão."""

    def execute_idempotent(self, video_id: str, *, expected_version: int, idempotency_key: str,
                           narration: str, image_prompt: str, position: int | None = None,
                           caption: str = "", label: str = "",
                           claim_ids: Sequence[str] = ()) -> LongScriptResult:
        digest = _payload_digest({
            "kind": "add", "expected_version": expected_version, "position": position,
            "narration": narration.strip(), "caption": caption.strip(), "label": label.strip(),
            "image_prompt": image_prompt.strip(), "claim_ids": list(claim_ids),
        })
        replay = self._replay(video_id, idempotency_key, digest)
        if replay is not None:
            return replay
        video, plan, drafts, snapshots, claims = self._load(video_id, expected_version)
        if position is None:
            position = len(drafts)
        if not 0 <= position <= len(drafts):
            raise InvalidInput(f"scene position {position} is out of range")
        if plan is not None:
            plan = with_chapter_scene_delta(plan, chapter_for_position(plan, position), 1)
        cited_ids = list(claim_ids) or self._citation(narration.strip(), claims, [])
        drafts.insert(position, SceneDraft(narration.strip(), caption.strip(), label.strip(),
                                           image_prompt.strip(), cited_ids))
        return self._save(video, plan, drafts, snapshots, claims, expected_version, idempotency_key, digest,
                          [position])


class RemoveScriptScene(_ScriptSceneMutation):
    """Remove uma cena criando nova versão; a cena removida não volta na versão seguinte."""

    def execute_idempotent(self, video_id: str, scene_idx: int, *, expected_version: int,
                           idempotency_key: str) -> LongScriptResult:
        digest = _payload_digest({
            "kind": "remove", "scene": scene_idx, "expected_version": expected_version,
        })
        replay = self._replay(video_id, idempotency_key, digest)
        if replay is not None:
            return replay
        video, plan, drafts, snapshots, claims = self._load(video_id, expected_version)
        if not 0 <= scene_idx < len(drafts):
            raise InvalidInput(f"scene index {scene_idx} is out of range")
        if plan is None:
            if len(drafts) <= 1:
                raise InvalidInput("a script needs at least one scene")
        else:
            try:
                plan = with_chapter_scene_delta(plan, chapter_for_position(plan, scene_idx), -1)
            except ValueError as exc:
                raise InvalidInput(str(exc)) from exc
        del drafts[scene_idx]
        return self._save(video, plan, drafts, snapshots, claims, expected_version, idempotency_key, digest)


class ReorderScriptScenes(_ScriptSceneMutation):
    """Reordena as cenas por uma permutação dos índices atuais, preservando a identidade de cada uma."""

    def execute_idempotent(self, video_id: str, order: Sequence[int], *, expected_version: int,
                           idempotency_key: str) -> LongScriptResult:
        digest = _payload_digest({
            "kind": "reorder", "order": list(order), "expected_version": expected_version,
        })
        replay = self._replay(video_id, idempotency_key, digest)
        if replay is not None:
            return replay
        video, plan, drafts, snapshots, claims = self._load(video_id, expected_version)
        if sorted(order) != list(range(len(drafts))):
            raise InvalidInput("scene order must be a permutation of the current scene indices")
        drafts = [drafts[index] for index in order]
        return self._save(video, plan, drafts, snapshots, claims, expected_version, idempotency_key, digest)


# ---------------------------------------------------------------------------
# W4.5 (EDIT-04): histórico recuperável de revisões de cena
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScriptRevisionView:
    """Revisão do roteiro: metadados e, opcionalmente, as cenas do snapshot recuperável."""

    version: int
    current: bool
    approved: bool
    superseded: bool
    restorable: bool
    scene_count: int
    media_pending: int
    content_hash: str | None = None
    scenes: tuple[SceneRevision, ...] = ()


def _revision_views(records: Sequence[ScriptRecord],
                    summaries: Sequence[ScriptRevisionSummary]) -> list[ScriptRevisionView]:
    by_version = {summary.version: summary for summary in summaries}
    latest = records[-1].script.version if records else None
    views: list[ScriptRevisionView] = []
    for record in records:
        summary = by_version.get(record.script.version)
        views.append(ScriptRevisionView(
            version=record.script.version,
            current=record.script.version == latest,
            approved=record.approval is not None and record.approval.decision == "approved"
            and approval_is_current(record.approval, version=record.script.version,
                                    content_hash=record.content_hash or ""),
            superseded=latest is not None and record.script.version < latest,
            restorable=summary is not None,
            scene_count=summary.scene_count if summary is not None else 0,
            media_pending=summary.media_pending if summary is not None else 0,
            content_hash=record.content_hash))
    return views


class ListScriptRevisions:
    """Lista as versões do roteiro com o que dá para restaurar; revisão legada não vira botão."""

    def __init__(self, videos: VideoRepository, longform: LongFormScriptRepository):
        self.videos, self.longform = videos, longform

    def execute(self, video_id: str) -> list[ScriptRevisionView]:
        _require_video(self.videos, video_id)
        return _revision_views(self.longform.list_script_records(video_id),
                               self.longform.revision_summaries(video_id))


class GetScriptRevision:
    """Lê uma revisão concreta: metadados + cenas do snapshot (erro explícito se não recuperável)."""

    def __init__(self, videos: VideoRepository, longform: LongFormScriptRepository):
        self.videos, self.longform = videos, longform

    def execute(self, video_id: str, version: int) -> ScriptRevisionView:
        _require_video(self.videos, video_id)
        records = self.longform.list_script_records(video_id)
        if not any(record.script.version == version for record in records):
            raise ScriptRevisionUnavailable(f"script revision {version} does not exist")
        scenes = tuple(self.longform.revision_scenes(video_id, version))
        if not scenes:
            raise ScriptRevisionUnavailable(
                f"script revision {version} has no recoverable scene snapshot")
        view = next(view for view in _revision_views(records, self.longform.revision_summaries(video_id))
                    if view.version == version)
        return ScriptRevisionView(version=view.version, current=view.current, approved=view.approved,
                                  superseded=view.superseded, restorable=view.restorable,
                                  scene_count=view.scene_count, media_pending=view.media_pending,
                                  content_hash=view.content_hash, scenes=scenes)


class RestoreScriptRevision(_ScriptSceneMutation):
    """Restaura uma revisão anterior como NOVA versão: texto, ordem e mídia da revisão escolhida.

    A nova revisão copia o snapshot da revisão escolhida (nunca o estado atual); mídia ausente vira
    ``media_review_required`` no repositório. A aprovação anterior continua presa à versão antiga e
    não vale para a nova. Nada é apagado.
    """

    def execute_idempotent(self, video_id: str, version: int, *, expected_version: int,
                           idempotency_key: str) -> LongScriptResult:
        digest = _payload_digest({"kind": "restore", "revision": version, "expected_version": expected_version})
        replay = self._replay(video_id, idempotency_key, digest)
        if replay is not None:
            return replay
        video = _require_video(self.videos, video_id)
        _require_script_editable(video)
        records = self.longform.list_script_records(video_id)
        if not records or records[-1].script.version != expected_version or records[-1].plan is None:
            latest = records[-1].script.version if records else None
            raise ScriptVersionStale(
                f"the requested version {expected_version} is not the latest script version ({latest})")
        source = next((record for record in records
                       if record.script.version == version and record.plan is not None), None)
        if source is None:
            raise ScriptRevisionUnavailable(f"script revision {version} has no long-form plan to restore")
        revisions = self.longform.revision_scenes(video_id, version)
        if not revisions:
            raise ScriptRevisionUnavailable(f"script revision {version} has no recoverable scene snapshot")
        drafts = [SceneDraft(r.narration, r.caption, r.label, r.image_prompt, list(r.claim_ids)) for r in revisions]
        snapshots = self.snaps.list(video_id)
        claims = _claims(snapshots)
        review, content_hash, text, cited = self._review_and_hash(video_id, source.plan, drafts, snapshots, claims)
        outcome = self.longform.save_restore(video_id, idempotency_key, digest, expected_version, version,
                                             text, cited, source.plan, content_hash, video.status,
                                             VideoStatus.SCRIPTED)
        if outcome is None:
            raise ScriptVersionStale("the script changed while restoring")
        return self._result_from_outcome(outcome, source.plan, review)


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
