"""Biblioteca (`pgLibrary` do protótipo v4-v3) renderizada sem banco: estrutura e dados reais."""
import re

from app.studio.api.panel_styles import render_styles
from app.studio.application.styles_page import StyleListItem, StylesPageView
from app.studio.domain.visual_style import VisualStyle

PID = "p" * 32
ATIVO = "a" * 32


def _page(items=(), **kw):
    html, _ = render_styles(StylesPageView(items=tuple(items)), projects=[(PID, "Canal H")], project_id=PID,
                            channel_name="Canal H", channel_style_id=kw.get("style_id"),
                            channel_version=3, channel_voice=kw.get("voice", ""))
    return html


def _item(style_id, name, params=None):
    return StyleListItem(VisualStyle(id=style_id, name=name, params=params or {}), 0)


def test_library_header_and_tabs_follow_the_prototype():
    html = _page()
    assert "Recursos reutilizáveis" in html and "Canal ativo: Canal H" in html
    tabs = re.findall(r'<button class="tab[^"]*"[^>]*>(.*?)</button>', html)
    assert tabs == ["Estilos visuais", "Vozes", "Músicas", "Mídias & Stock (Pixabay)", "Modelos de roteiro"]
    assert html.count('aria-current="page"') == 1  # menu: página atual
    assert html.count('aria-selected="true"') == 1  # aba ativa
    assert "O estilo vinculado ao canal é herdado por todos os novos vídeos." in html
    assert "+ Criar novo estilo" in html


def test_library_marks_the_channel_style_and_offers_to_link_the_others():
    html = _page([_item(ATIVO, "Cinemática", {"extra": {"description": "Luz dramática."}}),
                  _item("b" * 32, "Neon")], style_id=ATIVO)
    assert html.count("✓ Ativo no canal") == 1
    assert "Padrão herdado para novos vídeos" in html
    assert html.count("data-vincular-estilo=") == 1 and f'data-vincular-estilo="{"b" * 32}"' in html
    assert "Luz dramática." in html
    assert "border:2px solid var(--accent);background:var(--accentbg);padding:17px" in html


def test_library_shows_real_catalogs_and_never_invents_mockup_items():
    """A Biblioteca passou a exibir catálogos reais (vozes, trilhas CC0, modelos de roteiro e
    busca Pixabay). O teste garante que itens de mockup do protótipo continuam ausentes."""
    html = _page(voice="Rodrigo")
    assert "Piper Faber (pt-BR)" in html
    assert "6 trilhas disponíveis" in html
    assert "3 modelos disponíveis" in html
    assert "PIXABAY_API_KEY ausente no .env" in html
    for fake in ("Cinemática Sombria", "Marina Alves", "Mary Celeste", "Noir Poético\""):
        assert fake not in html.replace('placeholder="Ex.: Noir Poético"', "")


def test_library_create_dialog_has_exactly_the_prototype_fields():
    html = _page()
    dlg = html.split('id="novo-estilo-dialog"', 1)[1].split("</dialog>", 1)[0]
    assert re.findall(r"<label[^>]*>(.*?)</label>", dlg) == ["Nome", "Descrição curta", "Instrução de arte (prompt base)"]
    assert "Criar novo estilo" in dlg and "Cancelar" in dlg and "Salvar na biblioteca" in dlg


def test_library_escapes_real_names():
    html = _page([_item(ATIVO, "<script>alert(1)</script>")])
    assert "<script>alert(1)</script>" not in html


# ---- diálogos no tema: sem `window.confirm` e com o formulário de edição formatado ------------------------------


def test_library_archive_confirms_in_a_themed_dialog_not_the_browser_confirm():
    """Bug: "Arquivar" abria `window.confirm`, o modal nativo do navegador, fora do tema."""
    html = _page([_item(ATIVO, "View")])
    assert "window.confirm" not in html and "confirm(" not in html
    dlg = re.search(r'<dialog[^>]*id="dlg-arquivar-estilo"[^>]*>.*?</dialog>', html, re.S)
    assert dlg and 'class="modal"' in dlg.group(0)
    assert 'id="btn-confirmar-arquivar"' in dlg.group(0) and "voltam ao padrão do estúdio" in dlg.group(0)
    assert "data-fechar-dialogo" in dlg.group(0)
    assert "data-archive-style" in html  # o botão de cada estilo continua existindo


def test_library_edit_dialog_has_a_header_and_themed_form_parts():
    html = _page([_item(ATIVO, "View", {"motion": ["zoom_in"], "extra": {"lut": "x"}})])
    dlg = re.search(r'<dialog[^>]*id="editar-' + ATIVO + r'"[^>]*>.*?</dialog>', html, re.S).group(0)
    assert 'class="modal-header"' in dlg and 'class="modal-close"' in dlg and "Editar estilo" in dlg
    assert 'class="motion-option"' in dlg and 'class="advanced"' in dlg and 'class="form-actions"' in dlg
    for rule in (".hint {", "details.advanced", ".advanced-summary", ".motion-option:has(input:checked)", ".form-actions"):
        assert rule in html, rule  # estilos próprios do formulário, não os padrões do navegador
