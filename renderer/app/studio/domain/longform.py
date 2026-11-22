"""Long-form: estrutura por blocos, revisão determinística e invalidação (F4-02..F4-08).

Módulo puro: não chama provedor, não lê nem grava nada, não toca mídia. O hash de
conteúdo e a aprovação por versão são contratos; quem grava é a aplicação/adaptador.

Fronteiras deliberadas:

- **Estrutura é declarada, não inferida.** ``ScriptPlan`` diz em quais blocos
  (gancho, contexto, desenvolvimento, payoff/CTA) o roteiro longo se organiza e
  quantas cenas cada capítulo tem. ``validate_structure`` recusa plano sem gancho,
  sem fechamento ou fora da faixa de cenas do formato longo.
- **Revisão é medida, não presumida.** ``review_script`` mede continuidade
  (capítulos cobrindo exatamente as cenas), redundância (narração repetida),
  duração estimada contra o alvo (tolerância configurável) e ausência de invenção
  reutilizando o gate factual existente (``check_narration``). Ausência de achado
  não vira "aprovado": cada eixo tem resultado próprio.
- **Aprovação presa à versão e ao hash.** ``ScriptApproval`` só vale para o par
  (versão, hash) que a originou; qualquer edição gera outra versão e outro hash,
  então a aprovação anterior deixa de ser atual — nunca é transferida.
- **Invalidação é dependência, não cascata cega.** ``invalidated_outputs`` deriva
  do grafo quais artefatos dependem da mudança: regenerar imagens não invalida o
  fact-check; reescrever o texto não invalida o storyboard visual; trocar o
  roteiro invalida tudo que vem depois dele. Ninguém é invalidado por engano.

Limites explícitos: a duração é uma estimativa por palavras/minuto, **não** uma
medição de TTS (calibração real pendente); a invalidação descreve o que *deve* ser
recomputado, não reexecuta nada.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .contracts import Scene
from .facts import check_narration
from .narration_duration import estimate_text_durations

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Percent = Annotated[float, Field(gt=0, allow_inf_nan=False)]
ContentHash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

MIN_LONG_SCENES, MAX_LONG_SCENES = 8, 40


class Block(str, Enum):
    """Blocos narrativos do formato longo."""

    HOOK = "hook"
    CONTEXT = "context"
    DEVELOPMENT = "development"
    PAYOFF = "payoff"
    CTA = "cta"


CLOSING_BLOCKS = (Block.PAYOFF, Block.CTA)


class Chapter(BaseModel):
    """Capítulo do plano: bloco, número de cenas, alvo de duração e referências a cobrir."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: NonBlank
    block: Block
    scene_count: Annotated[int, Field(ge=1)]
    target_seconds: Percent
    references: tuple[NonBlank, ...] = ()

    @field_validator("scene_count", mode="before")
    @classmethod
    def _no_bool(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("scene_count must be an integer, not a boolean")
        return value


class ScriptPlan(BaseModel):
    """Plano de capítulos de um roteiro longo, com ritmo e alvo de duração declarados."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    words_per_minute: Percent
    target_seconds: Percent
    chapters: Annotated[tuple[Chapter, ...], Field(min_length=1)]

    @field_validator("words_per_minute", "target_seconds", mode="before")
    @classmethod
    def _no_bool(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("pacing and target must be numbers, not booleans")
        return value

    @property
    def scene_count(self) -> int:
        return sum(chapter.scene_count for chapter in self.chapters)


@dataclass(frozen=True)
class UnsupportedScene:
    """Invenção detectada: número ou nome próprio sem lastro nas fontes, na cena ``idx``."""

    idx: int
    kind: str
    value: str


@dataclass(frozen=True)
class ScriptReview:
    """Resultado medido da revisão. Cada eixo tem booleano ou lista própria."""

    structure_ok: bool
    continuity_ok: bool
    redundant_scene_idxs: tuple[int, ...]
    estimated_seconds: float
    target_seconds: float
    duration_ok: bool
    uncited_scene_idxs: tuple[int, ...]
    unknown_claim_ids: tuple[str, ...]
    unsupported: tuple[UnsupportedScene, ...]

    @property
    def passed(self) -> bool:
        return (
            self.structure_ok
            and self.continuity_ok
            and not self.redundant_scene_idxs
            and self.duration_ok
            and not self.uncited_scene_idxs
            and not self.unknown_claim_ids
            and not self.unsupported
        )


def validate_structure(plan: ScriptPlan) -> None:
    """Recusa plano fora do arco do formato longo (gancho → fechamento, com desenvolvimento)."""
    if not isinstance(plan, ScriptPlan):
        raise ValueError("plan must be a ScriptPlan")
    chapters = plan.chapters
    if not chapters:
        raise ValueError("a long script needs at least one chapter")
    if chapters[0].block is not Block.HOOK:
        raise ValueError("the first chapter must be the hook")
    if chapters[-1].block not in CLOSING_BLOCKS:
        raise ValueError("the last chapter must be payoff or call to action")
    if not any(chapter.block is Block.DEVELOPMENT for chapter in chapters):
        raise ValueError("a long script needs at least one development chapter")
    total = plan.scene_count
    if not MIN_LONG_SCENES <= total <= MAX_LONG_SCENES:
        raise ValueError(f"a long script needs {MIN_LONG_SCENES}-{MAX_LONG_SCENES} scenes, got {total}")
    titles = [chapter.title.casefold() for chapter in chapters]
    if len(set(titles)) != len(titles):
        raise ValueError("chapter titles must be unique")


def _structure_ok(plan: object) -> bool:
    if not isinstance(plan, ScriptPlan):
        return False
    try:
        validate_structure(plan)
    except (ValueError, TypeError):
        return False
    return True


def _redundant(narrations: Sequence[str]) -> tuple[int, ...]:
    seen: dict[str, int] = {}
    redundant: list[int] = []
    for idx, narration in enumerate(narrations):
        key = " ".join(narration.casefold().split())
        if key in seen:
            redundant.append(idx)
        else:
            seen[key] = idx
    return tuple(redundant)


def review_script(
    plan: ScriptPlan,
    scenes: Sequence[Scene],
    *,
    sources: Sequence[str],
    known_claim_ids: set[str] | frozenset[str],
    allow_names: frozenset[str] = frozenset(),
    tolerance: float = 0.15,
) -> ScriptReview:
    """Mede estrutura, continuidade, redundância, duração, citações e invenção.

    ``tolerance`` é a fração do alvo aceita para mais ou para menos (ex.: 0,15 = ±15%).
    Não recalcula a duração de TTS: usa a contagem de palavras existente.
    """
    if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool) or not math.isfinite(tolerance):
        raise ValueError("tolerance must be a finite number")
    if tolerance < 0:
        raise ValueError("tolerance must not be negative")

    narrations = [scene.narration for scene in scenes]
    estimated = estimate_text_durations(narrations, plan.words_per_minute).total_seconds
    duration_ok = abs(estimated - plan.target_seconds) <= plan.target_seconds * tolerance

    known = set(known_claim_ids)
    uncited = tuple(scene.idx for scene in scenes if not scene.claim_ids)
    unknown = tuple(sorted({cid for scene in scenes for cid in scene.claim_ids if cid not in known}))

    unsupported: list[UnsupportedScene] = []
    for scene in scenes:
        for issue in check_narration(scene.narration, list(sources), allow_names):
            unsupported.append(UnsupportedScene(scene.idx, issue.kind, issue.value))

    expected_idx = list(range(len(scenes)))
    continuity_ok = (
        [scene.idx for scene in scenes] == expected_idx
        and plan.scene_count == len(scenes)
    )
    return ScriptReview(
        structure_ok=_structure_ok(plan),
        continuity_ok=continuity_ok,
        redundant_scene_idxs=_redundant(narrations),
        estimated_seconds=estimated,
        target_seconds=plan.target_seconds,
        duration_ok=duration_ok,
        uncited_scene_idxs=uncited,
        unknown_claim_ids=unknown,
        unsupported=tuple(unsupported),
    )


def plan_content_hash(plan: ScriptPlan, scenes: Sequence[Scene]) -> str:
    """sha256 canônico do plano e das narrações: mesma entrada, mesmo hash; qualquer mudança, outro."""
    payload = json.dumps(
        {"plan": plan.model_dump(mode="json"), "scenes": [scene.narration for scene in scenes]},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def chapter_for_position(plan: ScriptPlan, position: int) -> int:
    """Índice do capítulo que contém a posição de cena (posição de inserção no fim fica no último)."""
    if position < 0:
        raise ValueError("scene position must not be negative")
    cumulative = 0
    for index, chapter in enumerate(plan.chapters):
        cumulative += chapter.scene_count
        if position < cumulative:
            return index
    return len(plan.chapters) - 1


def with_chapter_scene_delta(plan: ScriptPlan, chapter_index: int, delta: int) -> ScriptPlan:
    """Ajusta a contagem de cenas de um capítulo e redistribui os alvos proporcionalmente.

    Inserir/remover cena muda a contagem total; o plano precisa continuar somando o total de cenas
    para a revisão de continuidade. O alvo de cada capítulo é redistribuído sem mudar o alvo global.
    """
    if delta not in (-1, 0, 1):
        raise ValueError("scene count delta must be -1, 0 or 1")
    if not 0 <= chapter_index < len(plan.chapters):
        raise ValueError("chapter index is out of range")
    chapters = list(plan.chapters)
    new_count = chapters[chapter_index].scene_count + delta
    if new_count < 1:
        raise ValueError("a chapter must keep at least one scene")
    chapters[chapter_index] = chapters[chapter_index].model_copy(update={"scene_count": new_count})
    total = sum(chapter.scene_count for chapter in chapters)
    adjusted = tuple(
        chapter.model_copy(update={"target_seconds": plan.target_seconds * chapter.scene_count / total})
        for chapter in chapters
    )
    return plan.model_copy(update={"chapters": adjusted})


class ScriptApproval(BaseModel):
    """Aprovação humana de roteiro, presa à versão e ao hash que a originaram."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    video_id: NonBlank
    script_version: Annotated[int, Field(ge=1)]
    content_hash: ContentHash
    decision: Literal["approved", "rejected"]
    reason: str = ""
    approved_by: NonBlank
    approved_at: datetime | None = None

    @field_validator("script_version", mode="before")
    @classmethod
    def _no_bool(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("script_version must be an integer, not a boolean")
        return value

    @field_validator("approved_at")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("approved_at must be timezone-aware")
        return value

    def model_post_init(self, _context: object) -> None:
        if self.decision == "rejected" and not self.reason.strip():
            raise ValueError("rejection requires a non-empty reason")


def approval_is_current(approval: ScriptApproval, *, version: int, content_hash: str) -> bool:
    """A aprovação só vale para a versão e o hash exatos; editar cria outro par e invalida esta."""
    return (
        isinstance(approval, ScriptApproval)
        and approval.decision == "approved"
        and approval.script_version == version
        and approval.content_hash == content_hash
    )


class DownstreamOutput(str, Enum):
    """Artefatos do fluxo que dependem do roteiro (direta ou indiretamente)."""

    SOURCES = "sources"
    SCRIPT = "script"
    SCENE_TEXT = "scene_text"
    FACT_CHECK = "fact_check"
    STORYBOARD = "storyboard"
    ASSETS = "assets"
    RENDER = "render"
    QA = "qa"
    APPROVAL = "approval"
    PUBLISHING = "publishing"


# Cada artefato declara de que artefatos depende diretamente. Reescrever só o texto
# da cena não muda o prompt visual (o storyboard segue válido); trocar o roteiro
# invalida tudo depois dele; regenerar imagens não invalida o fact-check.
DEPENDENCIES: dict[DownstreamOutput, frozenset[DownstreamOutput]] = {
    DownstreamOutput.SOURCES: frozenset(),
    DownstreamOutput.SCRIPT: frozenset(),
    DownstreamOutput.SCENE_TEXT: frozenset(),
    DownstreamOutput.FACT_CHECK: frozenset({DownstreamOutput.SCRIPT, DownstreamOutput.SCENE_TEXT}),
    DownstreamOutput.STORYBOARD: frozenset({DownstreamOutput.SCRIPT}),
    DownstreamOutput.ASSETS: frozenset({DownstreamOutput.STORYBOARD}),
    DownstreamOutput.RENDER: frozenset({DownstreamOutput.FACT_CHECK, DownstreamOutput.ASSETS,
                                        DownstreamOutput.SCENE_TEXT}),
    DownstreamOutput.QA: frozenset({DownstreamOutput.RENDER}),
    DownstreamOutput.APPROVAL: frozenset({DownstreamOutput.QA}),
    DownstreamOutput.PUBLISHING: frozenset({DownstreamOutput.APPROVAL}),
}


def invalidated_outputs(changed: DownstreamOutput) -> frozenset[DownstreamOutput]:
    """Artefatos que dependem transitivamente de ``changed`` (excluindo o próprio)."""
    if not isinstance(changed, DownstreamOutput):
        raise ValueError("changed must be a DownstreamOutput")
    invalidated: set[DownstreamOutput] = set()
    frontier = {changed}
    while frontier:
        current = frontier.pop()
        for output, deps in DEPENDENCIES.items():
            if current in deps and output not in invalidated:
                invalidated.add(output)
                frontier.add(output)
    return frozenset(invalidated)
