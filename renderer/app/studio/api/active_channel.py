"""Canal ativo (F02.T01/G11): propagar `project_id` pelas páginas do Estúdio.

A tela V3 guarda o canal ativo em `?project_id=`. Antes desta correção, só o seletor do topo
recarregava a tela com o parâmetro; qualquer link interno o perdia e a tela voltava ao primeiro
canal. Aqui fica a regra única, num lugar só:

- páginas do Estúdio (lista branca explícita) recebem `project_id` quando o link não traz query;
- a navegação lateral é montada com o parâmetro (por isso ela não perde o canal);
- páginas de vídeo (`/studio/panel/videos/<id>`, `/studio/videos/<id>/...`) **não** recebem nada:
  o vídeo mantém o projeto proprietário, derivado pelo Core — nunca do seletor;
- links externos, `#`, `mailto:` e endpoints de arquivo/download ficam intactos.

A função é pura (sem I/O) e não conhece HTML além do atributo `href` — o resto do documento
chega e volta como está.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

# Páginas que pertencem ao contexto do canal ativo (lista branca, nunca "qualquer /studio").
PAGES_WITH_CHANNEL: tuple[str, ...] = (
    "/studio/panel",
    "/studio/panel/novo-video",
    "/studio/panel/videos",
    "/studio/panel/producao",
    "/studio/panel/tendencias",
    "/studio/panel/analytics",
    "/studio/canais",
    "/studio/panel/estilos",
    "/studio/panel/conexoes",
    "/studio/panel/equipe",
    "/studio/configuracoes",
)

# Rotas de vídeo: o dono é o próprio vídeo (Core resolve); o seletor não manda aqui.
VIDEO_PAGES: tuple[str, ...] = ("/studio/panel/videos/", "/studio/videos/")

_HREF = re.compile(r'href="([^"]*)"')


def _is_page_with_channel(path: str) -> bool:
    if path.startswith(VIDEO_PAGES):
        return False
    return any(path == page or path.startswith(page + "/") for page in PAGES_WITH_CHANNEL)


def with_channel(url: str, project_id: str) -> str:
    """Devolve `url` apontando para o canal ativo; intocada fora das páginas do Estúdio."""
    if not project_id:
        return url
    parts = urlsplit(url)
    if parts.scheme or parts.netloc or not parts.path.startswith("/"):
        return url  # externo, relativo a âncora ou mailto
    if not _is_page_with_channel(parts.path):
        return url
    if "project_id=" in parts.query:
        return url
    query = f"{parts.query}&project_id={project_id}" if parts.query else f"project_id={project_id}"
    return urlunsplit(("", "", parts.path, query, parts.fragment))


def propagate(body_html: str, project_id: str) -> str:
    """Aplica `with_channel` a todo `href` do corpo da página (idempotente)."""
    if not project_id:
        return body_html
    return _HREF.sub(lambda m: f'href="{with_channel(m.group(1), project_id)}"', body_html)