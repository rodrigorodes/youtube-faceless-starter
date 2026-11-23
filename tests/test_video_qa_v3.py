import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.api.panel_video_workspace import render_video_workspace
from app.studio.application.panel import VideoDetailView
from app.studio.domain.contracts import Video, VideoFormat, VideoStatus
from app.studio.domain.panel import Stage


def test_v3_qa_tab_features_centered_preview_and_collapsible_checks():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.RENDERED)
    html = render_video_workspace(video, active_area="qualidade", script=None, scenes=[], sources=[])
    assert "Ver todas as verificações técnicas" in html
    assert "Aprovar e preparar publicação" in html or "Aprovar" in html
    assert "QA técnico não verifica fatos" in html or "veracidade factual" in html


def test_v3_qa_tab_renders_video_preview_centrally_at_top():
    video_id = "v" * 32
    video = Video(id=video_id, project_id="p" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.RENDERED)
    res = render_video_workspace(video, active_area="qualidade")
    html = str(res)

    # Player / preview rendered
    assert "<video" in html
    assert f'/studio/videos/{video_id}/thumbnail' in html
    assert f'/studio/videos/{video_id}/file' in html
    assert f'href="/studio/videos/{video_id}/preview"' in html

    # Preview card should appear before the collapsible technical checks details
    idx_preview = html.find("card-preview-destaque")
    idx_diag = html.find('<details class="diag">')
    assert idx_preview != -1
    assert idx_diag != -1
    assert idx_preview < idx_diag


def test_v3_qa_tab_collapsible_technical_checks_wraps_gates():
    class _Coverage:
        status = "verified"

    class _Qa:
        is_publishable = True
        coverage = _Coverage()
        findings = []

    fake_video = SimpleNamespace(
        id="v" * 32,
        title="Tema",
        topic="Tema",
        format=VideoFormat.short,
        status=VideoStatus.RENDERED,
        qa_report=_Qa()
    )
    view = VideoDetailView(
        video=fake_video,
        stage=Stage.AWAITING_APPROVAL,
        cost_text="R$ 0,00",
        steps=[],
        usage=[],
        render_error=None,
        publication=None,
        sources=[],
        latest_run=None,
    )
    res = render_video_workspace(view, active_area="qualidade")
    html = str(res)

    # Collapsible details element with expected summary
    assert '<details class="diag">' in html
    assert "<summary>Ver todas as verificações técnicas</summary>" in html

    # Checks/report inside the details
    details_start = html.find('<details class="diag">')
    details_end = html.find('</details>', details_start)
    assert details_start != -1 and details_end != -1
    details_content = html[details_start:details_end]
    assert "Relatório de QA do render" in details_content
    assert "Publicável" in details_content


def test_v3_qa_tab_review_card_displays_readiness_and_actionable_issues():
    # Case 1: Ready for review (no blocking issues)
    video_ok = Video(id="v" * 32, project_id="p" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.RENDERED)
    html_ok = render_video_workspace(video_ok, active_area="qualidade")
    assert "Pronto para sua revisão" in html_ok

    # Case 2: Actionable issues reported
    class _Finding:
        severity = "blocking"
        evidence = "Loudness excede -14 LUFS"
        check_id = "CHK_AUDIO"

    class _QaIssues:
        is_publishable = False
        coverage = SimpleNamespace(status="partial")
        findings = [_Finding()]

    fake_video_issues = SimpleNamespace(
        id="v" * 32,
        title="Tema",
        topic="Tema",
        format=VideoFormat.short,
        status=VideoStatus.RENDERED,
        qa_report=_QaIssues()
    )
    view_issues = VideoDetailView(
        video=fake_video_issues,
        stage=Stage.AWAITING_APPROVAL,
        cost_text="R$ 0,00",
        steps=[],
        usage=[],
        render_error=None,
        publication=None,
        sources=[],
        latest_run=None,
    )
    html_issues = render_video_workspace(view_issues, active_area="qualidade")
    assert "Loudness excede -14 LUFS" in html_issues
    assert "Pendências" in html_issues or "Atenção" in html_issues or "bloqueante" in html_issues


def test_v3_qa_tab_approval_button_and_redirection_contract():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.RENDERED)
    html = render_video_workspace(video, active_area="qualidade")

    # Button text and data attribute
    assert 'data-a="approve"' in html
    assert "✓ Aprovar e preparar publicação →" in html

    # Client-side script handles POST to /studio/videos/{id}/approve and advances to /publicacao
    assert "/approve" in html
    assert "/publicacao" in html


def test_v3_qa_tab_explicit_disclaimer():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.RENDERED)
    html = render_video_workspace(video, active_area="qualidade")

    assert "QA técnico não verifica fatos do roteiro" in html or "QA técnico não verifica fatos" in html
    assert "Verificações ilustrativas/técnicas" in html or "Verificações ilustrativas" in html
