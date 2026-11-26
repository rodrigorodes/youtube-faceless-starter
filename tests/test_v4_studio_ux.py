"""Testes de conformidade para V4-10 — Studio UX & Workbench.

Valida as atividades V4-10.01 a V4-10.20:
- V4-10.02 / V4-10.08: Storyboard integrado e manipulação estrutural de cenas (add, remove, reorder, update).
- V4-10.12: Mecanismo determinístico de Undo / Redo (StudioHistoryManager).
- V4-10.18: Perfil de Channel Identity integrado.
- V4-10.19: Gate de aprovação humana e proteção por kill switch de publicação (publication_enabled=False -> BLOCKED).
"""
from __future__ import annotations

import pytest

from app.studio.application.studio_workbench import StudioWorkbenchService
from app.studio.domain.studio_workbench import (
    ApprovalDecisionKind,
    ChannelIdentityProfile,
    SceneItem,
    StudioApprovalDecision,
    StudioHistoryManager,
    StudioWorkspaceState,
)


@pytest.fixture
def sample_scenes() -> list[SceneItem]:
    return [
        SceneItem(
            scene_id="sc_01",
            narration="Primeira cena com introdução envolvente.",
            speech_seconds=3.5,
            asset_id="asset_hero_01",
            motion="zoom_in",
            transition_to_next="fade",
        ),
        SceneItem(
            scene_id="sc_02",
            narration="Segunda cena com explicação detalhada.",
            speech_seconds=4.0,
            asset_id="asset_diagram_02",
            motion="pan_right",
            transition_to_next="wipe",
        ),
        SceneItem(
            scene_id="sc_03",
            narration="Terceira cena com clímax e conclusão.",
            speech_seconds=2.8,
            asset_id="asset_conclusion_03",
            motion="zoom_out",
            transition_to_next="none",
        ),
    ]


@pytest.fixture
def sample_channel_identity() -> ChannelIdentityProfile:
    return ChannelIdentityProfile(
        channel_id="chan_tech_01",
        channel_name="Tech Documentaries",
        style_id="cinema-noir",
        voice_profile="marcos_deep_narrator",
        caption_theme="bold_yellow",
        default_pacing="moderate",
        safe_area_margin_v=280,
        human_approval_required=True,
    )


class TestStudioStoryboardAndHistory:
    """V4-10.02, V4-10.08 e V4-10.12: Storyboard integrado, operações de timeline e Undo/Redo."""

    def test_reorder_scenes_and_undo_redo(self, sample_scenes, sample_channel_identity):
        manager = StudioWorkbenchService.create_workbench(
            project_id="proj_01",
            video_id="vid_01",
            channel_identity=sample_channel_identity,
            scenes=sample_scenes,
        )

        assert not manager.can_undo
        assert not manager.can_redo
        assert [s.scene_id for s in manager.current_state.scenes] == ["sc_01", "sc_02", "sc_03"]

        # 1. Operador inverte a ordem das cenas 1 e 2
        StudioWorkbenchService.reorder(manager, ["sc_02", "sc_01", "sc_03"])
        assert manager.can_undo
        assert not manager.can_redo
        assert [s.scene_id for s in manager.current_state.scenes] == ["sc_02", "sc_01", "sc_03"]

        # 2. Desfazer (Undo)
        manager.undo()
        assert not manager.can_undo
        assert manager.can_redo
        assert [s.scene_id for s in manager.current_state.scenes] == ["sc_01", "sc_02", "sc_03"]

        # 3. Refazer (Redo)
        manager.redo()
        assert manager.can_undo
        assert not manager.can_redo
        assert [s.scene_id for s in manager.current_state.scenes] == ["sc_02", "sc_01", "sc_03"]

    def test_add_and_remove_scene_with_history(self, sample_scenes, sample_channel_identity):
        manager = StudioWorkbenchService.create_workbench(
            project_id="proj_01",
            video_id="vid_01",
            channel_identity=sample_channel_identity,
            scenes=sample_scenes,
        )

        new_scene = SceneItem(
            scene_id="sc_04_extra",
            narration="Cena extra inserida na bancada.",
            speech_seconds=1.5,
            asset_id="asset_bonus",
        )

        # Adiciona na posição 1
        StudioWorkbenchService.add_scene(manager, new_scene, position=1)
        assert len(manager.current_state.scenes) == 4
        assert manager.current_state.scenes[1].scene_id == "sc_04_extra"

        # Remove a cena sc_03
        StudioWorkbenchService.remove_scene(manager, "sc_03")
        assert len(manager.current_state.scenes) == 3
        assert "sc_03" not in [s.scene_id for s in manager.current_state.scenes]

        # Undo da remoção
        manager.undo()
        assert len(manager.current_state.scenes) == 4
        assert "sc_03" in [s.scene_id for s in manager.current_state.scenes]

    def test_update_scene_in_workbench(self, sample_scenes, sample_channel_identity):
        manager = StudioWorkbenchService.create_workbench(
            project_id="proj_01",
            video_id="vid_01",
            channel_identity=sample_channel_identity,
            scenes=sample_scenes,
        )

        # Operador altera a narração e o movimento da cena 1
        StudioWorkbenchService.update_scene(
            manager,
            "sc_01",
            {"narration": "Texto atualizado pelo operador.", "motion": "pan_left"},
        )

        assert manager.current_state.scenes[0].narration == "Texto atualizado pelo operador."
        assert manager.current_state.scenes[0].motion == "pan_left"

        # Undo restaura os valores originais
        manager.undo()
        assert manager.current_state.scenes[0].narration == "Primeira cena com introdução envolvente."
        assert manager.current_state.scenes[0].motion == "zoom_in"


class TestHumanApprovalAndKillSwitch:
    """V4-10.19: Decisão humana do operador e proteção por kill switch de publicação."""

    def test_approval_blocked_by_kill_switch_when_disabled(self):
        decision = StudioApprovalDecision(
            decision=ApprovalDecisionKind.APPROVED,
            operator_id="operator_rodrigo",
            reason="Audiovisual em excelente padrão.",
        )

        # publication_enabled=False (padrão de segurança nos testes)
        res = StudioWorkbenchService.process_approval(decision, publication_enabled=False)
        assert res["status"] == "APPROVED"
        assert res["publication_action"] == "BLOCKED_BY_KILL_SWITCH"
        assert "bloqueada pelo kill switch" in res["message"]

    def test_approval_ready_for_upload_when_enabled(self):
        decision = StudioApprovalDecision(
            decision=ApprovalDecisionKind.APPROVED,
            operator_id="operator_rodrigo",
            reason="Tudo conferido.",
        )

        res = StudioWorkbenchService.process_approval(decision, publication_enabled=True)
        assert res["status"] == "APPROVED"
        assert res["publication_action"] == "READY_FOR_UPLOAD"

    def test_operator_rejection(self):
        decision = StudioApprovalDecision(
            decision=ApprovalDecisionKind.REJECTED,
            operator_id="operator_rodrigo",
            reason="Áudio ligeiramente estridente no final.",
        )

        res = StudioWorkbenchService.process_approval(decision, publication_enabled=False)
        assert res["status"] == "NOT_APPROVED"
        assert res["publication_action"] == "NONE"
