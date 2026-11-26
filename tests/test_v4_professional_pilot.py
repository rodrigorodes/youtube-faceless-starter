"""Testes de Homologação da Fase V4-13 — Professional Pilot.

Valida as 14 atividades da fase V4-13 e as especificações de PROFESSIONAL-PILOT-SPEC:
- Roteiros de referência e comparação pareada (Econômico vs Equilibrado vs Premium)
- Métricas comparadas de voz, som (LUFS/Peak), sincronia áudio/legenda
- Custo por minuto e economia em regeneração pontual de cenas
- Bloqueio estrito de publicação externa via kill switch
- Emissão do relatório de conformidade consolidado para Avaliação Humana
"""
from decimal import Decimal
import pytest

from app.studio.domain.professional_pilot import (
    PilotBenchmarkMetrics,
    PilotComparisonReport,
    PilotComplianceError,
    PilotProfile,
    SceneRegenerationCost,
)
from app.studio.application.professional_pilot import (
    ProfessionalPilotOrchestrator,
)


def test_v4_13_reference_scripts_and_profile_cohesion():
    """Valida roteiro de referência e coerência das métricas do perfil Econômico."""
    orch = ProfessionalPilotOrchestrator(publication_kill_switch_enabled=True)

    metrics_econ = orch.run_benchmark_for_profile(
        profile=PilotProfile.ECONOMIC,
        video_format="short",
        total_duration_seconds=60.0,
        scenes_count=4,
        integrated_lufs=-14.2,
        true_peak_db=-1.5,
        sync_drift_ms=12.0,
        render_wall_time_seconds=18.0,
        total_cost_usd=Decimal("0.00"),
        human_intervention_minutes=3.5,
    )

    assert metrics_econ.profile == PilotProfile.ECONOMIC
    assert metrics_econ.cost_per_minute_usd == Decimal("0.00")
    assert metrics_econ.realtime_render_factor == 0.30
    assert metrics_econ.publication_blocked is True


def test_v4_13_paired_comparison_and_cost_per_minute():
    """Valida comparação pareada entre perfis Econômico e Equilibrado com cálculo de custo por minuto."""
    orch = ProfessionalPilotOrchestrator(publication_kill_switch_enabled=True)

    # Perfil Econômico (Local / Free Stock / TTS local)
    econ = orch.run_benchmark_for_profile(
        profile=PilotProfile.ECONOMIC,
        video_format="short",
        total_duration_seconds=75.0,
        scenes_count=5,
        integrated_lufs=-14.1,
        true_peak_db=-1.2,
        sync_drift_ms=8.5,
        render_wall_time_seconds=22.5,
        total_cost_usd=Decimal("0.00"),
        human_intervention_minutes=4.0,
    )

    # Perfil Equilibrado (Assets híbridos / Efeitos visuais avançados)
    balanced = orch.run_benchmark_for_profile(
        profile=PilotProfile.BALANCED,
        video_format="short",
        total_duration_seconds=75.0,
        scenes_count=5,
        integrated_lufs=-14.0,
        true_peak_db=-1.1,
        sync_drift_ms=5.0,
        render_wall_time_seconds=30.0,
        total_cost_usd=Decimal("0.25"),
        human_intervention_minutes=5.0,
    )

    assert econ.cost_per_minute_usd == Decimal("0.00")
    # 75s = 1.25 minutos -> 0.25 / 1.25 = 0.20 USD/min
    assert balanced.cost_per_minute_usd == Decimal("0.20")

    report = orch.build_comparison_report(
        script_reference_id="script_ref_historia_ia_01",
        script_topic="A História dos Sistemas Inteligentes",
        profiles_metrics={
            PilotProfile.ECONOMIC: econ,
            PilotProfile.BALANCED: balanced,
        },
    )

    assert report.get_profile(PilotProfile.ECONOMIC).total_duration_seconds == 75.0
    assert report.get_profile(PilotProfile.BALANCED).cost_per_minute_usd == Decimal("0.20")


def test_v4_13_audio_compliance_true_peak_gate():
    """Valida rejeição de True Peak acima de -1.0 dBFS para evitar clipping e distorção."""
    orch = ProfessionalPilotOrchestrator(publication_kill_switch_enabled=True)

    with pytest.raises(PilotComplianceError, match="risco de clipping"):
        orch.run_benchmark_for_profile(
            profile=PilotProfile.ECONOMIC,
            video_format="short",
            total_duration_seconds=60.0,
            scenes_count=4,
            integrated_lufs=-14.0,
            true_peak_db=-0.2,  # VIOLAÇÃO: > -1.0 dBFS!
            sync_drift_ms=10.0,
            render_wall_time_seconds=20.0,
            total_cost_usd=Decimal("0.00"),
            human_intervention_minutes=2.0,
        )


def test_v4_13_caption_sync_drift_gate():
    """Valida rejeição de dessincronia áudio/legenda superior a 50ms."""
    orch = ProfessionalPilotOrchestrator(publication_kill_switch_enabled=True)

    with pytest.raises(PilotComplianceError, match="excedeu o teto de 50ms"):
        orch.run_benchmark_for_profile(
            profile=PilotProfile.ECONOMIC,
            video_format="short",
            total_duration_seconds=60.0,
            scenes_count=4,
            integrated_lufs=-14.0,
            true_peak_db=-1.5,
            sync_drift_ms=65.0,  # VIOLAÇÃO: > 50ms!
            render_wall_time_seconds=20.0,
            total_cost_usd=Decimal("0.00"),
            human_intervention_minutes=2.0,
        )


def test_v4_13_publication_kill_switch_mandate():
    """Valida que a publicação externa deve estar estritamente bloqueada no piloto."""
    orch_unprotected = ProfessionalPilotOrchestrator(publication_kill_switch_enabled=False)

    with pytest.raises(PilotComplianceError, match="Publicação externa não foi bloqueada"):
        orch_unprotected.run_benchmark_for_profile(
            profile=PilotProfile.ECONOMIC,
            video_format="short",
            total_duration_seconds=60.0,
            scenes_count=4,
            integrated_lufs=-14.0,
            true_peak_db=-1.5,
            sync_drift_ms=10.0,
            render_wall_time_seconds=20.0,
            total_cost_usd=Decimal("0.00"),
            human_intervention_minutes=2.0,
        )


def test_v4_13_scene_regeneration_efficiency():
    """Valida registro e economia em regeneração pontual de cenas sem refazer o vídeo todo."""
    regen_scene_2 = SceneRegenerationCost(
        scene_id="scene_02",
        asset_cost_usd=Decimal("0.00"),
        render_time_seconds=3.2,
        full_pipeline_avoided_seconds=35.0,
    )

    orch = ProfessionalPilotOrchestrator(publication_kill_switch_enabled=True)
    metrics = orch.run_benchmark_for_profile(
        profile=PilotProfile.ECONOMIC,
        video_format="short",
        total_duration_seconds=60.0,
        scenes_count=4,
        integrated_lufs=-14.0,
        true_peak_db=-1.5,
        sync_drift_ms=15.0,
        render_wall_time_seconds=18.0,
        total_cost_usd=Decimal("0.00"),
        human_intervention_minutes=1.5,
        scene_regenerations=(regen_scene_2,),
    )

    assert len(metrics.scene_regenerations) == 1
    assert metrics.scene_regenerations[0].scene_id == "scene_02"
    assert metrics.scene_regenerations[0].full_pipeline_avoided_seconds == 35.0
