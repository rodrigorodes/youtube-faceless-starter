"""F06.T03 — preferências de produção na tela de Canais.

O que esta suíte protege:
- custo desconhecido e provider indisponível são **estado explícito em texto humano**, nunca número;
- conexão (YouTube), configuração (provider escolhido) e credencial realmente utilizada são campos
  distintos — BYOK cadastrada não é BYOK usada (G10, ADR fs31-005);
- perfis econômicos e limites vigentes aparecem com origem explícita (canal × servidor);
- ausência de dado nunca vira zero e nenhum controle fictício é oferecido.
"""
import gc
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.api.panel_channels import _provider_cost, _route_failure_text  # noqa: E402
from app.studio.domain.provider import (  # noqa: E402
    Availability,
    CostEstimate,
    EconomicProfile,
    ProviderCard,
    ProviderKind,
)

from test_channels_page import (  # noqa: E402
    POST_HEADER,
    _app,
    _seed_profile,
    _seed_usage,
    page,
    page_text,
)


@pytest.fixture()
def env(conn, dsn, tmp_path):
    app = _app(conn, dsn, tmp_path)
    yield app
    # O TestClient mantém conexões físicas até o coletor rodar; liberar aqui evita esgotar o
    # Postgres descartável quando a suíte roda muitos casos no mesmo processo.
    app["client"].close()
    gc.collect()


# ------------------------------------------------------------------ custo/indisponibilidade


def _card(kind=ProviderKind.TEXT, *, cost=None, availability=Availability.AVAILABLE, reason=None):
    return ProviderCard(kind, "opencode:model-x", "opencode", "model-x", ("text.generate",),
                        cost or CostEstimate.unknown(), None, 4, availability, reason)


def test_unknown_provider_cost_is_a_human_state_not_a_number():
    text = _provider_cost(_card())
    assert "desconhecido" in text.lower()
    assert "US$" not in text, "custo desconhecido não pode ser renderizado como valor"
    assert "zero" in text.lower(), "a tela precisa dizer que desconhecido não é zero"


def test_route_failure_is_explained_without_the_raw_router_english():
    text = _route_failure_text(
        ProviderKind.TEXT, EconomicProfile.BALANCED,
        "no available text provider for BALANCED; excluded: unknown cost, quality 1 below the "
        "profile floor 2")
    assert "Roteiro" in text
    assert "custo desconhecido" in text
    assert "piso de qualidade 2" in text
    assert "excluded" not in text and "no available" not in text


def test_route_failure_without_categories_does_not_promise_a_provider():
    text = _route_failure_text(ProviderKind.IMAGE, EconomicProfile.ECONOMY, "catalog empty")
    assert "Imagens" in text
    assert "nenhum" in text.lower()
    assert "catalog empty" not in text  # motivo cru não é copy de tela


# ------------------------------------------------------- conexão × configuração × credencial


def test_page_shows_provider_unavailability_and_unknown_cost_as_human_text(env):
    html = page(env).text
    visible = page_text(html)
    assert "Indisponível" in visible  # provider sem sonda/implementação validada
    assert "OPENCODE_BRIDGE_TOKEN ausente" in visible  # motivo real, sem inventar disponibilidade
    assert "Custo desconhecido" in visible  # preço não confirmado é estado, nunca número
    assert "não é tratado como zero" in visible
    assert "US$ 0,00" not in html


def test_page_separates_connection_configuration_and_credential_used(env):
    _seed_profile(env)
    html = page(env).text
    visible = page_text(html)
    assert "Conexão, configuração e credencial" in visible
    for label in ("Conexão", "Configuração", "Credencial utilizada"):
        assert label in visible, label
    # Conexão: o estado real do canal do YouTube, em texto humano.
    assert "Sem associação" in visible
    # Configuração: o provider escolhido por tarefa, com o spec real.
    assert "opencode" in visible
    # Credencial: a execução usa a credencial do servidor; BYOK cadastrada não é BYOK usada.
    assert "BYOK" in visible
    assert "não é usada" in visible
    assert "Cadastro não é uso" in visible
    assert re.search(r'href="/studio/panel/equipe(?:\?project_id=[^"]+)?"', html)


def test_page_never_promises_byok_usage_when_only_registered(env):
    html = page(env).text
    visible = page_text(html)
    # Nenhuma frase do tipo "usando sua chave BYOK" pode existir: a execução não consulta BYOK.
    for promise in ("usando sua chave", "chave BYOK em uso", "BYOK ativa neste canal",
                    "credencial BYOK utilizada"):
        assert promise.lower() not in visible.lower(), promise
    assert "fora do caminho de execução" in visible


def test_prefs_card_escapes_a_hostile_youtube_title(env):
    r = env["client"].put(
        f"/studio/projects/{env['project'].id}/youtube-channel",
        json={"channel_id": "UC123", "title": "<script>alert(1)</script>",
              "refresh_token": "1//refresh-secret"},
        headers=POST_HEADER)
    assert r.status_code == 200, r.text
    html = page(env).text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


# --------------------------------------------------- perfis econômicos e limites vigentes


def _put_budget(client, project_id, *, profile="BALANCED"):
    r = client.put(f"/studio/projects/{project_id}/budget",
                   json={"hard_monthly_usd": "20", "soft_monthly_usd": "10",
                         "hard_video_usd": "4", "soft_video_usd": "2",
                         "economic_profile": profile},
                   headers=POST_HEADER)
    assert r.status_code == 200, r.text


def test_budget_card_offers_the_three_real_profiles_and_marks_the_active_one(env):
    html = page(env).text
    # UX (protótipo `settingsProduction`, `prototype/index.html:627`): o perfil é uma escolha em
    # cartões — radios nativos com o mesmo nome de campo, dentro do formulário de orçamento.
    values = re.findall(r'<input type="radio" name="economic_profile" value="(\w+)"[^>]*>', html)
    assert values == ["ECONOMY", "BALANCED", "PREMIUM"]
    assert re.search(r'<input type="radio" name="economic_profile" value="BALANCED" checked>', html)
    visible = page_text(html)
    assert "Perfil econômico" in visible
    assert "Perfil ativo" in visible
    # A escolha tem backend real (PUT .../budget) e é gravada com os limites.
    assert 'id="budget-form"' in html


def test_budget_limits_name_their_origin_and_never_render_absence_as_zero(env):
    html = page(env).text
    visible = page_text(html)
    assert "Limite soft mensal" in visible and "Limite hard mensal" in visible
    assert "padrão do servidor" in visible  # nada persistido para este canal
    assert "Sem registro de uso" in visible
    assert "Gasto do mês" in visible
    assert "US$ 0,00" not in html


def test_budget_month_spend_keeps_real_and_estimate_labelled(env):
    _seed_profile(env)
    _put_budget(env["client"], env["project"].id, profile="ECONOMY")
    _seed_usage(env)
    html = page(env).text
    visible = page_text(html)
    assert "ECONOMY" in visible
    assert "persistidos" in visible  # limites do canal, não o padrão do servidor
    assert "Real US$ 0,11" in visible
    assert "Estimado US$ 0,03" in visible
    assert "Desconhecido em 1 chamada(s)" in visible
    # Nenhum número inventado para custo desconhecido.
    assert "US$ 0,00" not in html


def test_profile_choice_is_a_real_control_not_a_placeholder(env):
    html = page(env).text
    form = re.search(r'<form id="budget-form".*?</form>', html, re.S)
    assert form is not None
    assert 'name="economic_profile"' in form.group(0)
    # Os três cartões de escolha são controles reais e habilitados (radio nativo, sem JS).
    radios = re.findall(r'<input type="radio" name="economic_profile" value="\w+"[^>]*>',
                        form.group(0))
    assert len(radios) == 3
    assert all("disabled" not in radio for radio in radios)
    # Sem handler inline: o envio é por addEventListener (CSP sem unsafe-inline).
    assert not re.search(r"\son[a-z]+=", html, re.I)