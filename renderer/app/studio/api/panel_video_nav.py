"""Navegação por áreas do vídeo (W1.4) — fonte única, sem dependência da casca.

As áreas do vídeo são rotas de servidor com links e `aria-current`. Este módulo existe para que a
**página legada do vídeo** (`panel.py`) e o **workspace** (`panel_video_workspace.py`) usem a mesma
nav sem import circular (`panel_video_workspace` importa `panel`; `panel` não pode importá-lo).

Ordem e rótulos vêm do protótipo (`VIDEO_TABS`). O id é o segmento da rota.
"""
from __future__ import annotations

from html import escape as e

VIDEO_AREAS: tuple[tuple[str, str], ...] = (
    ("cenas", "Cenas & Storyboard"),
    ("composicao", "Composição & Legendas"),
    ("qualidade", "Qualidade & Aprovação"),
    ("publicacao", "Publicação YouTube"),
    ("fontes", "Fontes & Evidências"),
)
AREA_LABELS = dict(VIDEO_AREAS)
AREA_IDS = frozenset(AREA_LABELS)
ALL_VALID_AREAS = AREA_IDS | {"producao"}
ALL_AREA_IDS = ALL_VALID_AREAS
DEFAULT_AREA = "cenas"


def area_href(video_id: str, area: str) -> str:
    """Rota real da área. O `area` já chega normalizado (ver `normalize_area`)."""
    return f"/studio/panel/videos/{e(video_id)}/{area}"


def normalize_area(area: str | None) -> str:
    """Área desconhecida (ou legada) cai em `cenas` (DEFAULT_AREA).

    Decisão V3: o menu principal possui 5 abas canônicas. A rota 'producao' permanece
    válida e acessível via diagnóstico, mas áreas legadas ('visao-geral', 'narracao')
    ou inexistentes caem com segurança em DEFAULT_AREA ('cenas').
    """
    if area == "producao":
        return "producao"
    return area if area in AREA_IDS else DEFAULT_AREA


def video_area_nav(video_id: str, active: str) -> str:
    """Navegação por área: links de servidor, um único `aria-current="page"` na ativa."""
    items = []
    for area_id, label in VIDEO_AREAS:
        current = ' aria-current="page"' if area_id == active else ""
        cls = "tab ativa aba" if area_id == active else "tab aba"
        items.append(
            f'<a class="{cls}" href="{area_href(video_id, area_id)}"{current}>{e(label)}</a>'
        )
    return f'<nav class="abas-video" aria-label="Áreas do vídeo">{"".join(items)}</nav>'
