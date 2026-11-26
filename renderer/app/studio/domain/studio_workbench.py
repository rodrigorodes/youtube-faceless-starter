"""Contratos de domínio do Studio Workbench e Espaço de Trabalho Editorial (V4-10).

Define:
- Gestão de histórico com Undo / Redo determinístico e imutável (StudioHistoryManager).
- Estado unificado da bancada de storyboard e timeline (StudioWorkspaceState, SceneItem).
- Configuração de Channel Identity e estilo audiovisual do canal (ChannelIdentityProfile).
- Gate de aprovação humana para publicação (StudioApprovalDecision).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "SceneItem",
    "ChannelIdentityProfile",
    "StudioWorkspaceState",
    "StudioHistoryManager",
    "ApprovalDecisionKind",
    "StudioApprovalDecision",
]


class SceneItem(BaseModel):
    """Item de cena no storyboard integrado com texto, voz, asset e movimento."""

    model_config = ConfigDict(frozen=True)

    scene_id: str = Field(min_length=1)
    narration: str
    speech_seconds: float = Field(ge=0.0)
    asset_id: str = Field(min_length=1)
    motion: str = "none"
    transition_to_next: str = "fade"
    caption_override: str | None = None
    music_volume: float = Field(default=0.4, ge=0.0, le=1.0)


class ChannelIdentityProfile(BaseModel):
    """Perfil congelado de identidade de canal configurável na bancada."""

    model_config = ConfigDict(frozen=True)

    channel_id: str
    channel_name: str
    style_id: str = "studio-default"
    voice_profile: str = "default_neutral"
    caption_theme: str = "highlight_yellow"
    default_pacing: str = "moderate"
    safe_area_margin_v: int = 280
    human_approval_required: bool = True


class StudioWorkspaceState(BaseModel):
    """Estado snapshot imutável do projeto no Studio."""

    model_config = ConfigDict(frozen=True)

    project_id: str
    video_id: str
    channel_identity: ChannelIdentityProfile
    scenes: tuple[SceneItem, ...]
    selected_scene_id: str | None = None
    last_modified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def with_reordered_scenes(self, new_scene_ids: Sequence[str]) -> StudioWorkspaceState:
        """Reordena as cenas do projeto segundo a ordem especificada de IDs."""
        scene_map = {s.scene_id: s for s in self.scenes}
        ordered = [scene_map[sid] for sid in new_scene_ids if sid in scene_map]
        if len(ordered) != len(self.scenes):
            raise ValueError("All existing scene IDs must be present in reordering")
        return self.model_copy(update={"scenes": tuple(ordered)})

    def with_added_scene(self, scene: SceneItem, position: int | None = None) -> StudioWorkspaceState:
        """Adiciona uma nova cena na posição especificada ou ao final."""
        current = list(self.scenes)
        if any(s.scene_id == scene.scene_id for s in current):
            raise ValueError(f"Scene with id {scene.scene_id!r} already exists")
        if position is None or position >= len(current):
            current.append(scene)
        else:
            current.insert(max(0, position), scene)
        return self.model_copy(update={"scenes": tuple(current), "selected_scene_id": scene.scene_id})

    def with_removed_scene(self, scene_id: str) -> StudioWorkspaceState:
        """Remove uma cena existente da bancada."""
        current = [s for s in self.scenes if s.scene_id != scene_id]
        if len(current) == len(self.scenes):
            raise ValueError(f"Scene with id {scene_id!r} not found")
        new_selected = current[0].scene_id if current else None
        return self.model_copy(update={"scenes": tuple(current), "selected_scene_id": new_selected})

    def with_updated_scene(self, scene_id: str, updates: dict[str, Any]) -> StudioWorkspaceState:
        """Atualiza atributos de uma cena específica mantendo imutabilidade."""
        current = list(self.scenes)
        found_idx = -1
        for idx, s in enumerate(current):
            if s.scene_id == scene_id:
                found_idx = idx
                break
        if found_idx == -1:
            raise ValueError(f"Scene with id {scene_id!r} not found")
        curr_dict = current[found_idx].model_dump()
        curr_dict.update(updates)
        current[found_idx] = SceneItem.model_validate(curr_dict)
        return self.model_copy(update={"scenes": tuple(current)})


class StudioHistoryManager:
    """Gerenciador determinístico de Undo / Redo com limitação de profundidade."""

    def __init__(self, initial_state: StudioWorkspaceState, max_depth: int = 50) -> None:
        self._undo_stack: list[StudioWorkspaceState] = [initial_state]
        self._redo_stack: list[StudioWorkspaceState] = []
        self._max_depth = max(5, max_depth)

    @property
    def current_state(self) -> StudioWorkspaceState:
        return self._undo_stack[-1]

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 1

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def push_state(self, new_state: StudioWorkspaceState) -> None:
        """Registra uma nova modificação, limpando o redo stack."""
        self._undo_stack.append(new_state)
        if len(self._undo_stack) > self._max_depth:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> StudioWorkspaceState:
        """Desfaz a última alteração retornando ao estado anterior."""
        if not self.can_undo:
            raise ValueError("No actions to undo")
        state = self._undo_stack.pop()
        self._redo_stack.append(state)
        return self.current_state

    def redo(self) -> StudioWorkspaceState:
        """Refaz a alteração previamente desfeita."""
        if not self.can_redo:
            raise ValueError("No actions to redo")
        state = self._redo_stack.pop()
        self._undo_stack.append(state)
        return self.current_state


class ApprovalDecisionKind(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"


@dataclass(frozen=True)
class StudioApprovalDecision:
    """Decisão formal registrada pelo operador humano no Studio."""

    decision: ApprovalDecisionKind
    operator_id: str
    reason: str = ""
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_approved_for_publication(self) -> bool:
        return self.decision == ApprovalDecisionKind.APPROVED
