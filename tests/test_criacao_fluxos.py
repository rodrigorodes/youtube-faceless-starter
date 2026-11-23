"""Criar vídeo (Piloto e Diretor) leva a uma ação real, não a uma tela vazia sem saída.

Bug: o Piloto criava o rascunho e abria "Sem cenas" sem produzir nada; o Diretor abria o storyboard com
"+ Nova cena" desabilitado e sem nenhum caminho para obter o roteiro (o roteiro nasce das fontes).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_video_workspace import _content, _render, _view  # noqa: E402

from app.studio.api.panel_new_video import NEW_VIDEO_JS  # noqa: E402
from app.studio.application.ports import SourceInfo  # noqa: E402

FONTE = SourceInfo("s1", "https://exemplo.test/artigo", 400)


def _texto(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)\b.*?</\1>", "", html, flags=re.S)).split())


def test_empty_storyboard_without_sources_points_at_sources_and_says_why():
    content = _content(_render("cenas", view=_view()))
    assert 'id="storyboard-vazio"' in content
    assert "Adicionar fonte" in _texto(content) and "/fontes" in content
    assert "btn-gerar-roteiro" not in content  # sem fonte não há o que gerar
    assert "Sem cenas. Adicione a primeira cena." not in content  # a frase que prometia algo impossível


def test_empty_storyboard_with_sources_offers_to_generate_the_script():
    html = _render("cenas", view=_view(sources=[FONTE]))
    tag = re.search(r'<button[^>]*id="btn-gerar-roteiro"[^>]*>', _content(html)).group(0)
    assert "disabled" not in tag and 'data-video-id="' in tag
    assert "/script" in html  # chama POST /studio/videos/{id}/script (já existente)


def test_dock_does_not_offer_to_render_when_there_is_nothing_to_produce_from():
    html = _render("cenas", view=_view())
    tag = re.search(r'<button[^>]*id="btn-render"[^>]*>', html).group(0)
    assert "disabled" in tag and "fonte" in tag.lower()
    ok = re.search(r'<button[^>]*id="btn-render"[^>]*>', _render("cenas", view=_view(sources=[FONTE]))).group(0)
    assert "disabled" not in ok


def test_generate_missing_is_disabled_when_there_are_no_scenes():
    tag = re.search(r'<button[^>]*id="btn-gerar-faltante"[^>]*>', _render("cenas", view=_view())).group(0)
    assert "disabled" in tag


def test_new_video_pilot_starts_production_and_director_generates_the_script_when_there_is_a_source():
    assert "/production-runs" in NEW_VIDEO_JS and "Idempotency-Key" in NEW_VIDEO_JS
    assert "/script'" in NEW_VIDEO_JS or '/script"' in NEW_VIDEO_JS
    # a falha de qualquer etapa após criar é mostrada, não engolida
    assert ".catch(function () {})" not in NEW_VIDEO_JS


def test_new_video_hint_does_not_claim_production_waits_for_the_user_in_pilot_mode():
    assert "a produ\\u00e7\\u00e3o s\\u00f3 come\\u00e7a quando voc\\u00ea pedir" not in NEW_VIDEO_JS


def test_pasted_script_asks_for_a_real_http_reference_instead_of_the_rejected_local_url():
    """O backend recusa `local://` ("reference url must be http(s)") e engolimos o 422 em silêncio."""
    assert "local://roteiro-inicial" not in NEW_VIDEO_JS
    assert "post('/sources', { url: scriptUrl" in NEW_VIDEO_JS
    assert "linkHttp(scriptUrl)" in NEW_VIDEO_JS  # valida antes de criar, com erro visível
    assert "Promise.resolve(false)" in NEW_VIDEO_JS  # sem fonte: não inicia produção nem gera roteiro


def test_new_video_page_has_the_reference_link_field_and_explains_where_it_shows_up():
    from app.studio.api.panel_new_video import render_new_video_v3
    from test_new_video_v3 import _view as new_view

    html, _ = render_new_video_v3(new_view())
    assert re.search(r'<input[^>]*type="url"[^>]*id="roteiro-url"', html)
    assert "descrição do vídeo publicado" in _texto(html)


def test_storyboard_script_does_not_paint_the_old_empty_card_over_the_guided_empty_state():
    from app.studio.api.panel_video_storyboard_js import STORYBOARD_JS
    assert "!document.getElementById('storyboard-vazio')" in STORYBOARD_JS


# ---- roteiro sem plano (Short): texto/ordem não são gravados pelo backend; a tela não finge ----

def _short_script_render(*, chapters):
    from test_video_workspace import VIDEO, _script_view
    from app.studio.api.panel_video_workspace import render_video_workspace
    from app.studio.domain.contracts import Scene, Script, VideoStatus
    from app.studio.domain.panel import Stage

    scenes = [Scene(id=f"{i:032x}", video_id=VIDEO, idx=i, narration=f"Narração da cena número {i}.",
                    image_prompt="uma imagem qualquer para a cena") for i in range(3)]
    script = Script(id="9" * 32, video_id=VIDEO, version=1, text="x")
    sv = _script_view()
    sv = sv.__class__(**{**sv.__dict__, "chapters": chapters}) if hasattr(sv, "__dict__") else sv
    html = render_video_workspace(_view(status=VideoStatus.SCRIPTED, stage=Stage.PENDING, sources=[FONTE]),
                                  "cenas", script_view=sv, script=script, scenes=scenes)[0]
    return html


def test_planless_script_locks_text_and_order_with_a_visible_reason_but_keeps_media_and_voice():
    html = _short_script_render(chapters=[])
    content = _content(html)
    assert 'id="storyboard-estrutura"' in content
    assert "plano de capítulos" in _texto(content)
    assert "disabled" in re.search(r'<button[^>]*id="btn-nova-cena"[^>]*>', content).group(0)
    assert re.search(r'<textarea[^>]*data-a="text"[^>]*readonly', content)
    assert re.search(r'<button[^>]*data-a="delscene"[^>]*disabled', content)
    assert not re.search(r'<button[^>]*data-a="media"[^>]*disabled', content)  # mídia segue editável
    assert '"structure": false' in html


def test_planned_script_keeps_everything_editable():
    html = _short_script_render(chapters=_chapters())
    content = _content(html)
    assert 'id="storyboard-estrutura"' not in content
    assert "disabled" not in re.search(r'<button[^>]*id="btn-nova-cena"[^>]*>', content).group(0)
    assert not re.search(r'<textarea[^>]*data-a="text"[^>]*readonly', content)
    assert '"structure": true' in html


def _chapters():
    from test_video_workspace import _script_view
    return _script_view().chapters


def test_stale_script_error_is_translated():
    from app.studio.api.erro_js import ERRO_JS
    assert "not the latest script version" in ERRO_JS
