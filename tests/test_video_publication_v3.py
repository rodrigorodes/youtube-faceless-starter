import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.api.panel_video_workspace import render_video_workspace
from app.studio.application.panel import VideoDetailView
from app.studio.application.ports import PubInfo
from app.studio.domain.contracts import Video, VideoFormat, VideoStatus, PublicationStatus
from app.studio.domain.panel import Stage


def test_v3_publication_tab_renders_schedule_and_timezone_notice():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.APPROVED)
    html, _ = render_video_workspace(video, active_area="publicacao", script=None, scenes=[], sources=[])

    # Timezone notice
    assert "Horário de Brasília · UTC−03:00. Agendar não publica agora." in html
    assert "Horário de Brasília" in html
    assert "UTC−03:00" in html

    # Publication mode selector (Publicar agora vs Agendar publicação / Publicar imediatamente vs Agendar para depois)
    assert 'name="tipo-publicacao"' in html
    assert 'id="agendar-publicacao"' in html
    assert 'id="publicar-agora"' in html
    assert "Publicar agora" in html or "Publicar imediatamente" in html
    assert "Agendar publicação" in html or "Agendar para depois" in html

    # Datetime-local field
    assert 'type="datetime-local"' in html
    assert 'id="agendamento-data"' in html


def test_v3_publication_tab_status_card_differentiates_scheduled_from_published():
    video_id = "v" * 32
    video_published = Video(id=video_id, project_id="p" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.PUBLISHED)
    pub_published = PubInfo(status=PublicationStatus.UPLOADED, attempt=1, error=None)
    view_published = VideoDetailView(
        video=video_published,
        stage=Stage.COMPLETED,
        cost_text="R$ 0,00",
        steps=[],
        usage=[],
        render_error=None,
        publication=pub_published,
        sources=[],
        latest_run=None,
    )
    html_pub, _ = render_video_workspace(view_published, active_area="publicacao")

    # Published status check
    assert "Publicado" in html_pub

    # Scheduled video
    tz_br = timezone(timedelta(hours=-3))
    future_date = datetime(2026, 12, 1, 18, 0, tzinfo=tz_br)
    video_scheduled = SimpleNamespace(
        id=video_id,
        title="Tema",
        topic="Tema",
        format=VideoFormat.short,
        status=VideoStatus.APPROVED,
        publish_at=future_date,
    )
    pub_scheduled = PubInfo(status=PublicationStatus.PENDING, attempt=0, error=None)
    view_scheduled = VideoDetailView(
        video=video_scheduled,
        stage=Stage.APPROVED,
        cost_text="R$ 0,00",
        steps=[],
        usage=[],
        render_error=None,
        publication=pub_scheduled,
        sources=[],
        latest_run=None,
    )
    html_sched, _ = render_video_workspace(view_scheduled, active_area="publicacao")

    # Scheduled status check
    assert "Agendado" in html_sched
    # Card clearly differentiates:
    assert "Publicado" not in html_sched or "Ainda não publicado" in html_sched


def test_v3_publication_tab_scheduled_intent_renders_scheduled_notice_and_update_button():
    video_id = "v" * 32
    tz_br = timezone(timedelta(hours=-3))
    dt = datetime(2026, 12, 1, 18, 0, tzinfo=tz_br)

    video = SimpleNamespace(
        id=video_id,
        title="Tema",
        topic="Tema",
        format=VideoFormat.short,
        status=VideoStatus.APPROVED,
        publish_at=dt,
    )
    view = VideoDetailView(
        video=video,
        stage=Stage.APPROVED,
        cost_text="R$ 0,00",
        steps=[],
        usage=[],
        render_error=None,
        publication=None,
        sources=[],
        latest_run=None,
    )
    html, _ = render_video_workspace(view, active_area="publicacao")

    assert "aviso aviso-info" in html
    assert "Agendado para" in html
    assert "Brasília. Ainda não publicado." in html
    assert "Atualizar agendamento" in html


def test_v3_publication_tab_scheduled_state_with_dirty_flag_warns_re_review():
    video_id = "v" * 32
    video = SimpleNamespace(
        id=video_id,
        title="Tema",
        topic="Tema",
        format=VideoFormat.short,
        status=VideoStatus.APPROVED,
        publish_at="01/12/2026 às 18:00",
        dirty=True,
    )
    view = VideoDetailView(
        video=video,
        stage=Stage.APPROVED,
        cost_text="R$ 0,00",
        steps=[],
        usage=[],
        render_error=None,
        publication=None,
        sources=[],
        latest_run=None,
    )
    html, _ = render_video_workspace(view, active_area="publicacao")

    assert "Edições pendentes: o agendamento precisa ser revisado após novas alterações." in html


def test_v3_publication_tab_client_side_validation_script():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.APPROVED)
    html, _ = render_video_workspace(video, active_area="publicacao")

    # Script contains Brasília timezone validation
    assert "Escolha uma data futura no horário de Brasília." in html
    assert "-03:00" in html


def test_v3_qa_tab_waiting_rendering_pill_when_stage_not_in_preview_stages():
    # Video in SCRIPTED status -> classifies to Stage.PENDING (not in _PREVIEW_STAGES)
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.SCRIPTED)
    html, _ = render_video_workspace(video, active_area="qualidade")

    assert '<span class="pill pill-espera">Aguardando renderização</span>' in html
    assert "Pronto para sua revisão" not in html
