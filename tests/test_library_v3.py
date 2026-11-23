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
    tabs = re.findall(r'<button class="tab"[^>]*>(.*?)</button>', html)
    assert tabs == ["Estilos visuais", "Vozes", "Músicas", "Modelos de roteiro"]
    assert html.count('aria-current="page"') >= 2  # menu + aba ativa
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


def test_library_without_catalogs_says_so_instead_of_inventing_mockup_items():
    html = _page(voice="Rodrigo")
    assert "Ainda não há catálogo de vozes" in html and "Rodrigo" in html
    assert "Ainda não há biblioteca de músicas" in html
    assert "Ainda não há modelos de roteiro cadastrados" in html
    for fake in ("Cinemática Sombria", "Marina Alves", "Mary Celeste", "Noir Poético\"" ):
        assert fake not in html.replace('placeholder="Ex.: Noir Poético"', "")


def test_library_create_dialog_has_exactly_the_prototype_fields():
    html = _page()
    dlg = html.split('id="novo-estilo-dialog"', 1)[1].split("</dialog>", 1)[0]
    assert re.findall(r"<label[^>]*>(.*?)</label>", dlg) == ["Nome", "Descrição curta", "Instrução de arte (prompt base)"]
    assert "Criar novo estilo" in dlg and "Cancelar" in dlg and "Salvar na biblioteca" in dlg


def test_library_escapes_real_names():
    html = _page([_item(ATIVO, "<script>alert(1)</script>")])
    assert "<script>alert(1)</script>" not in html
