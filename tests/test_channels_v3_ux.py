import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.api.panel_channels import render_channels
from app.studio.application.channels_page import ChannelsPageView
from app.studio.domain.channel import ChannelProfile
from app.studio.domain.contracts import ProductionMode, Project, VideoFormat
from app.studio.domain.visual_style import VisualStyle


def _extract_html(res) -> str:
    return res[0] if isinstance(res, tuple) else res


def test_channels_page_renders_transactional_form_and_preferences():
    view = ChannelsPageView(project=None, profile=None, channels=[])
    html = render_channels(view)
    assert 'id="form-novo-canal-v3"' in html or 'id="new-channel-form"' in html
    assert 'name="default_mode"' in html or 'name="modo-padrao"' in html
    assert 'name="default_format"' in html or 'name="formato-padrao"' in html
    assert "/studio/channels/transactional" in html


def test_channel_creation_form_renders_essential_fields():
    pid = "a" * 32
    project = Project(id=pid, name="Canal Teste", niche="Finanças", language="pt-BR")
    profile = ChannelProfile(
        id="b" * 32,
        project_id=pid,
        name="Canal Teste",
        default_mode=ProductionMode.piloto,
        default_format=VideoFormat.short,
    )
    style = VisualStyle(id="c" * 32, name="Estilo Moderno")
    view = ChannelsPageView(
        project=project,
        profile=profile,
        projects=((pid, "Canal Teste"),),
        styles=(style,),
    )
    html = _extract_html(render_channels(view))

    # Form and essential fields
    assert 'id="new-channel-form"' in html or 'id="form-novo-canal-v3"' in html
    assert 'name="name"' in html and 'id="novo-canal-nome"' in html
    assert 'name="niche"' in html and 'id="novo-canal-nicho"' in html
    assert 'name="language"' in html and 'id="novo-canal-idioma"' in html

    # Mode selector with piloto and diretor
    assert 'name="default_mode"' in html
    assert 'value="piloto"' in html and 'value="diretor"' in html

    # Format selector with short and long
    assert 'name="default_format"' in html
    assert 'value="short"' in html and 'value="long"' in html

    # Style selector
    assert 'name="style_id"' in html
    assert "Estilo Moderno" in html


def test_channel_creation_form_renders_progressive_disclosure_sections():
    pid = "a" * 32
    project = Project(id=pid, name="Canal Teste", niche="Finanças", language="pt-BR")
    profile = ChannelProfile(
        id="b" * 32,
        project_id=pid,
        name="Canal Teste",
        default_mode=ProductionMode.piloto,
        default_format=VideoFormat.short,
    )
    view = ChannelsPageView(project=project, profile=profile, projects=((pid, "Canal Teste"),))
    html = _extract_html(render_channels(view))

    # Progressive disclosure details with class "diag"
    assert '<details class="diag"' in html

    # Editorial customization fields
    assert 'name="strategy"' in html and 'id="novo-canal-estrategia"' in html
    assert 'name="audience"' in html and 'id="novo-canal-publico"' in html
    assert 'name="pillars"' in html and 'id="novo-canal-pilares"' in html
    assert 'name="narrative"' in html and 'id="novo-canal-narrativa"' in html
    assert 'name="cta"' in html and 'id="novo-canal-cta"' in html

    # Budget customization fields
    assert 'name="economic_profile"' in html and 'id="novo-canal-perfil-economico"' in html
    assert 'name="hard_monthly_usd"' in html and 'id="novo-canal-teto-mensal"' in html
    assert 'name="hard_video_usd"' in html and 'id="novo-canal-teto-video"' in html


def test_channel_creation_script_uses_transactional_endpoint():
    pid = "a" * 32
    project = Project(id=pid, name="Canal Teste", niche="Finanças", language="pt-BR")
    profile = ChannelProfile(
        id="b" * 32,
        project_id=pid,
        name="Canal Teste",
        default_mode=ProductionMode.piloto,
        default_format=VideoFormat.short,
    )
    view = ChannelsPageView(project=project, profile=profile, projects=((pid, "Canal Teste"),))
    html = _extract_html(render_channels(view))

    assert "/studio/channels/transactional" in html
    assert "/studio/canais?project_id=" in html
    assert "new-channel-feedback" in html


def test_channel_profile_card_displays_and_edits_default_mode_and_format():
    pid = "a" * 32
    project = Project(id=pid, name="Canal Teste", niche="Finanças", language="pt-BR")
    profile = ChannelProfile(
        id="b" * 32,
        project_id=pid,
        name="Canal Teste",
        default_mode=ProductionMode.diretor,
        default_format=VideoFormat.long,
    )
    view = ChannelsPageView(project=project, profile=profile, projects=((pid, "Canal Teste"),))
    html = _extract_html(render_channels(view))

    # Profile card renders default mode & format with profile values selected
    assert 'id="canal-modo"' in html or 'name="default_mode"' in html
    assert 'id="canal-formato"' in html or 'name="default_format"' in html
    # Verification that profile values are selected in profile section
    assert '<option value="diretor" selected>' in html or ('value="diretor"' in html and "selected" in html)
    assert '<option value="long" selected>' in html or ('value="long"' in html and "selected" in html)

    # JS script reads canal-modo and canal-formato and sends them
    assert "canal-modo" in html
    assert "canal-formato" in html
    assert "default_mode" in html
    assert "default_format" in html
