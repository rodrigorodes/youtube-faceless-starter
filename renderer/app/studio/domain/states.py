"""Transições válidas do estado do vídeo (domínio puro)."""
from .contracts import VideoStatus as S

_LINEAR = [S.IDEA, S.SCRIPTED, S.FACT_CHECKED, S.STORYBOARDED, S.ASSETS_READY, S.RENDERED, S.AWAITING_APPROVAL]
_PRE_APPROVAL = frozenset(_LINEAR[:-1])  # etapas que podem falhar e ser retomadas

VIDEO_TRANSITIONS: dict[S, frozenset[S]] = {
    **{cur: frozenset({nxt, S.FAILED}) for cur, nxt in zip(_LINEAR, _LINEAR[1:])},
    S.RENDERED: frozenset({S.AWAITING_APPROVAL, S.FAILED, S.SCRIPTED}),  # SCRIPTED: pedir ajustes antes da revisão
    # "Pedir ajustes": a versão renderizada (ainda não aprovada) volta a ser editável, como na reabertura de APPROVED.
    S.AWAITING_APPROVAL: frozenset({S.APPROVED, S.REJECTED, S.SCRIPTED}),
    S.APPROVED: frozenset({S.PUBLISHED, S.SCRIPTED}),  # reabrir: a guarda de publicação fica no caso de uso (ADR-002)
    S.PUBLISHED: frozenset(),
    S.REJECTED: frozenset(),
    S.FAILED: _PRE_APPROVAL,  # a origem exata da retomada é validada na P06
}


class InvalidTransition(ValueError):
    pass


def can_transition(old: S, new: S) -> bool:
    return new in VIDEO_TRANSITIONS[old]


def assert_transition(old: S, new: S) -> None:
    if not can_transition(old, new):
        raise InvalidTransition(f"{old.value} -> {new.value} is not allowed")


def to_mermaid() -> str:
    lines = ["stateDiagram-v2", f"    [*] --> {S.IDEA.value}"]
    for cur in S:
        for nxt in S:
            if nxt in VIDEO_TRANSITIONS[cur]:
                lines.append(f"    {cur.value} --> {nxt.value}")
    for terminal in (S.PUBLISHED, S.REJECTED):
        lines.append(f"    {terminal.value} --> [*]")
    return "\n".join(lines)
