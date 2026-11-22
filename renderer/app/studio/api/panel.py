"""Agregador das páginas HTML do painel do Studio (ver CORE-ISOLATION-GUIDE, S5).

A divisão por área de tela vive nos módulos `panel_*`; este arquivo preserva a superfície
pública usada por `routes.py`, pelos testes e pelos demais `panel_*` (reexport). Sem mudança
de comportamento: cada nome continua resolvendo para a mesma função/constante.
"""
from .panel_operacional import (
    _PANEL_PATHS,
    _PANEL_SKIP_HREFS,
    _PANEL_TITLES,
    _render_panel_page,
    render_panel,
    render_producao,
    render_tendencias,
)
from .panel_script import _fact_check_text, _mark, _version_row, render_script
from .panel_shell import (
    ACTION_STAGES,
    CSS,
    LIGHT_TOKENS,
    STAGE_LABELS,
    STATE_BY_STAGE,
    THEME_CSS,
    _ICON_FLAME,
    _ICON_REFRESH,
    _ICON_SLIDERS,
    _LIGHT_EXTRAS,
    _NAV_ALIASES,
    _NAV_ICONS,
    _NAV_UNAVAILABLE,
    _THEME_JS,
    _cost_html,
    _duration_text,
    _headers,
    _light_rules,
    _state_badge,
    _ui_icon,
    budget_side_card,
    build_sidebar_nav,
    cost_breakdown_rows,
    e,
    render_sidebar,
    theme_toggle_html,
)
from .panel_video import (
    _PRODUCTION_STAGE_LABELS,
    _RUN_STATE_LABELS,
    _START_OVER_HINT,
    _TERMINAL_RUN_STATES,
    _new_production_button,
    _video_run_card,
    _video_sources_card,
    _video_style_card,
    render_video,
)

__all__ = [
    "ACTION_STAGES",
    "CSS",
    "LIGHT_TOKENS",
    "STAGE_LABELS",
    "STATE_BY_STAGE",
    "THEME_CSS",
    "budget_side_card",
    "build_sidebar_nav",
    "cost_breakdown_rows",
    "e",
    "render_panel",
    "render_producao",
    "render_script",
    "render_sidebar",
    "render_tendencias",
    "render_video",
    "theme_toggle_html",
]
