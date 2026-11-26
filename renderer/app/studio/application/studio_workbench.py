"""Serviço de aplicação para operações de bancada do Studio (V4-10).

Orquestra:
- Edições determinísticas com histórico e undo/redo.
- Modificações estruturais na timeline e storyboard.
- Gate de publicação humana com verificação estrita do kill switch (publication_enabled).
"""
from __future__ import annotations

from typing import Any, Sequence

from ..domain.studio_workbench import (
    ApprovalDecisionKind,
    ChannelIdentityProfile,
    SceneItem,
    StudioApprovalDecision,
    StudioHistoryManager,
    StudioWorkspaceState,
)

__all__ = [
    "StudioWorkbenchService",
]


class StudioWorkbenchService:
    """Serviço de aplicação que gerencia a bancada do Studio e suas operações."""

    @classmethod
    def create_workbench(
        cls,
        project_id: str,
        video_id: str,
        channel_identity: ChannelIdentityProfile,
        scenes: Sequence[SceneItem],
    ) -> StudioHistoryManager:
        """Inicializa uma bancada de trabalho para o projeto com histórico ativo."""
        initial_state = StudioWorkspaceState(
            project_id=project_id,
            video_id=video_id,
            channel_identity=channel_identity,
            scenes=tuple(scenes),
            selected_scene_id=scenes[0].scene_id if scenes else None,
        )
        return StudioHistoryManager(initial_state)

    @classmethod
    def reorder(cls, manager: StudioHistoryManager, new_scene_ids: Sequence[str]) -> StudioWorkspaceState:
        new_state = manager.current_state.with_reordered_scenes(new_scene_ids)
        manager.push_state(new_state)
        return new_state

    @classmethod
    def add_scene(
        cls,
        manager: StudioHistoryManager,
        scene: SceneItem,
        position: int | None = None,
    ) -> StudioWorkspaceState:
        new_state = manager.current_state.with_added_scene(scene, position)
        manager.push_state(new_state)
        return new_state

    @classmethod
    def remove_scene(cls, manager: StudioHistoryManager, scene_id: str) -> StudioWorkspaceState:
        new_state = manager.current_state.with_removed_scene(scene_id)
        manager.push_state(new_state)
        return new_state

    @classmethod
    def update_scene(
        cls,
        manager: StudioHistoryManager,
        scene_id: str,
        updates: dict[str, Any],
    ) -> StudioWorkspaceState:
        new_state = manager.current_state.with_updated_scene(scene_id, updates)
        manager.push_state(new_state)
        return new_state

    @classmethod
    def process_approval(
        cls,
        decision: StudioApprovalDecision,
        publication_enabled: bool = False,
    ) -> dict[str, Any]:
        """Processa a decisão do operador respeitando o kill switch de publicação."""
        if not decision.is_approved_for_publication:
            return {
                "status": "NOT_APPROVED",
                "decision": decision.decision.value,
                "operator_id": decision.operator_id,
                "reason": decision.reason,
                "publication_action": "NONE",
            }

        # Aprovado pelo operador humano
        if not publication_enabled:
            return {
                "status": "APPROVED",
                "decision": decision.decision.value,
                "operator_id": decision.operator_id,
                "publication_action": "BLOCKED_BY_KILL_SWITCH",
                "message": "Publicação externa bloqueada pelo kill switch de segurança.",
            }

        return {
            "status": "APPROVED",
            "decision": decision.decision.value,
            "operator_id": decision.operator_id,
            "publication_action": "READY_FOR_UPLOAD",
            "message": "Aprovado para publicação externa.",
        }
