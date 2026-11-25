"""Tela de Canais (F10) no painel: consome o backend da fatia H com honestidade.

Fonte de verdade visual: `produto/tela-canais.html` (aprovado em 2026-11-20). As regras canônicas
de UX vivem em `test_ux_contract.assert_ux_contract` e são aplicadas à tela inteira. Onde o mockup
mostra dado ilustrativo, a tela renderiza dado real do Studio ou estado vazio explícito.
"""
import base64
import html
import json
import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from psycopg.types.json import Jsonb  # noqa: E402

from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.api.routes import make_router  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.domain.contracts import VideoFormat  # noqa: E402
from test_ux_contract import assert_ux_contract  # noqa: E402

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}
POST_HEADER = {**AUTH_HEADER, "Origin": "http://testserver"}


def _app(conn, dsn, tmp_path, *, with_project: bool = True, with_oauth: bool = False):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal H", niche="História", language="pt-BR") if with_project else None
    oauth: dict = {}
    if with_oauth:
        # Client secret sintético: só o suficiente para a composição montar o app OAuth. Nunca
        # aparece em HTML; o teste de vazamento usa valores inequivocamente sintéticos.
        secret = tmp_path / "client-secret-synthetic.json"
        secret.write_text(json.dumps({"web": {
            "client_id": "client-id.apps.googleusercontent.com",
            "client_secret": "your_client_secret",
            "redirect_uris": ["http://localhost:8000/studio/oauth/callback"]}}), encoding="utf-8")
        oauth = {"google_client_secret_file": secret,
                 "google_oauth_redirect_uri": "http://localhost:8000/studio/oauth/callback"}
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path, paid_image_usd=0.31, **oauth),
                    environ={"STUDIO_TEXT": "demo"})
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return {"client": TestClient(app), "videos": videos, "project": project, "conn": conn,
            "dsn": dsn, "connect": connect, "with_oauth": with_oauth}


@pytest.fixture()
def env(conn, dsn, tmp_path):
    return _app(conn, dsn, tmp_path)


@pytest.fixture()
def env_empty(conn, dsn, tmp_path):
    return _app(conn, dsn, tmp_path, with_project=False)


@pytest.fixture()
def env_oauth(conn, dsn, tmp_path):
    return _app(conn, dsn, tmp_path, with_oauth=True)


def page(env, project_id=None):
    pid = project_id if project_id is not None else env["project"].id
    return env["client"].get(f"/studio/canais?project_id={pid}", headers=AUTH_HEADER)


def page_text(html: str) -> str:
    stripped = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", stripped).split())


def _without_style_and_script(html: str) -> str:
    return re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S | re.I)


def nav_items(html: str):
    """Itens da navegação principal da casca V3 (`<nav aria-label="Principal">`)."""
    markup = _without_style_and_script(html)
    match = re.search(r'<nav aria-label="Principal">(.*?)</nav>', markup, re.S)
    assert match is not None, "navegação principal ausente"
    return re.findall(r"<li>(.*?)</li>", match.group(1), re.S)


def settings_nav_items(html: str):
    """Itens da navegação da área de Configurações (Canais/Estilos/Conexões/Equipe)."""
    markup = _without_style_and_script(html)
    match = re.search(r'<nav aria-label="Seções de configuração">(.*?)</nav>', markup, re.S)
    assert match is not None, "navegação de configurações ausente"
    return re.findall(r"<li>(.*?)</li>", match.group(1), re.S)


def _nav_text(item: str) -> str:
    # Os glifos do protótipo são `aria-hidden`: não fazem parte do rótulo acessível.
    return " ".join(html.unescape(re.sub(r"<span aria-hidden.*?</span>|<[^>]+>", " ", item)).split())


def _seed_profile(env, **changes):
    payload = {"name": "História", "strategy": "Narrativa cronológica",
               "language": "pt-BR", "audience": "Adultos curiosos",
               "pillars": ["Roma", "Egito"], "visual_identity": "Grafite e âmbar",
               "voice": "piper:pt_BR-faber-medium"}
    payload.update(changes)
    r = env["client"].post(f"/studio/projects/{env['project'].id}/channels", json=payload,
                           headers=POST_HEADER)
    assert r.status_code == 201, r.text
    return r.json()


def _seed_usage(env):
    conn = env["conn"]
    video = env["videos"].create_video(env["project"].id, "Tema com custo", VideoFormat.short)
    rows = (
        ("ACTUAL", 0.11, 0.11),
        ("ESTIMATE", 0.03, 0.03),
        ("FREE", 0.0, 0.0),
    )
    for kind, cost, confirmed in rows:
        conn.execute(
            "INSERT INTO studio.usage_ledger (video_id, step, provider, model, cost_usd, "
            "cost_confirmation_kind, cost_confirmed_amount, cost_confirmation_reference, "
            "cost_confirmed_by, cost_confirmed_at) "
            "VALUES (%s, 'text', 'demo', 'demo', %s, %s, %s, 'ref', 'tester', now())",
            (video.id, cost, kind, confirmed),
        )
    conn.execute(
        "INSERT INTO studio.usage_ledger (video_id, step, provider, model, cost_usd) "
        "VALUES (%s, 'text', 'legado', 'legado', 0)",
        (video.id,),
    )
    conn.commit()


# ------------------------------------------------------------------ contrato UX


def test_channels_empty_state_satisfies_the_ux_contract(env):
    r = page(env)
    assert r.status_code == 200, r.text
    assert_ux_contract(r.text, page="canais/vazio")


def test_channels_page_with_real_data_satisfies_the_ux_contract(env):
    _seed_profile(env)
    env["client"].put(f"/studio/projects/{env['project'].id}/budget",
                      json={"hard_monthly_usd": "20", "soft_monthly_usd": "10",
                            "hard_video_usd": "4", "soft_video_usd": "2"},
                      headers=POST_HEADER)
    env["client"].put(f"/studio/projects/{env['project'].id}/youtube-channel",
                      json={"channel_id": "UC123", "title": "Canal H",
                            "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
                            "refresh_token": "1//refresh-secret"},
                      headers=POST_HEADER)
    _seed_usage(env)
    r = page(env)
    assert r.status_code == 200, r.text
    assert_ux_contract(r.text, page="canais/com-dados")


def test_channels_state_badges_carry_real_text_not_only_an_icon(env):
    _seed_profile(env)
    html = page(env).text
    bodies = re.findall(r'<span class="state s-[a-z]+"[^>]*>(.*?)</span>', html, re.S)
    assert bodies
    for body in bodies:
        assert re.search(r"[A-Za-zÀ-ÿ]{3,}", body), body


def test_channels_page_uses_the_approved_shell(env):
    html = page(env).text
    items = nav_items(html)
    # W1.5 + NAV: menu do protótipo (`prototype/index.html:583`) — **sete itens numa lista só**,
    # com "Configurações" como o 7º (deixou de ser um `<nav>` separado no rodapé da casca).
    assert [_nav_text(i) for i in items] == ["Início", "Criar vídeo", "Vídeos", "Tendências e ideias",
                                            "Desempenho", "Biblioteca", "Configurações"]
    config_item = next(i for i in items if "Configurações" in _nav_text(i))
    assert re.search(r'<a href="/studio/configuracoes/canais[^"]*" aria-current="page"', config_item)
    # Canais é a seção ativa dentro de Configurações.
    section_active = [i for i in settings_nav_items(html) if 'aria-current="page"' in i]
    assert len(section_active) == 1 and "Canais" in _nav_text(section_active[0])
    assert _without_style_and_script(html).count('aria-current="page"') == 2
    assert html.count("<h1") == 1
    # UX: o h1 é o do protótipo V4/V3; "Ajustes" fica no eyebrow.
    assert re.search(r'<p class="eyebrow">\s*Ajustes\s*</p>', html)
    assert re.search(r'<h1[^>]*>\s*Configurações\s*</h1>', html)


def test_settings_pages_never_repeat_an_element_id(env):
    """Regressão do bug "novo canal vem com o nome do perfil" (id duplicado).

    O diálogo do shell (`#dlg-canal`) e os cartões de Configurações usavam os **mesmos** ids
    (`canal-nome`, `canal-nicho`, `canal-idioma`, `btn-salvar-canal`). Em `/studio/canais` o cartão
    do perfil vem antes do diálogo, então `document.getElementById('canal-nome')` devolvia o campo
    do perfil: criar um canal pelo diálogo gravava o **nome do perfil** ("Musica") e o nicho
    literal "não informado". Nenhum id pode se repetir no documento.
    """
    from collections import Counter

    for path in ("/studio/canais", "/studio/configuracoes/estrategia", "/studio/configuracoes/producao"):
        response = env["client"].get(f"{path}?project_id={env['project'].id}", headers=AUTH_HEADER)
        assert response.status_code == 200, path
        ids = re.findall(r'\sid="([^"]+)"', response.text)
        duplicados = {i: n for i, n in Counter(ids).items() if n > 1}
        assert duplicados == {}, (path, duplicados)


def test_channels_page_marks_unavailable_nav_items_as_non_focusable(env):
    html = page(env).text
    for item in nav_items(html):
        if 'aria-disabled="true"' in item:
            assert not item.lstrip().startswith(("<a ", "<button")), item


# ------------------------------------------------------------------ identidade


def test_channels_without_profile_shows_explicit_empty_state(env):
    html = page(env).text
    visible = page_text(html)
    assert "Nenhum perfil de canal registrado" in visible
    assert "channel_v" not in visible
    for forbidden in ("Finanças pessoais explicadas sem jargão", "Adultos curiosos, sem formação técnica",
                      "Paleta grafite+violeta", "Educação long-form (8–12 min)",
                      "pt-BR · Piper"):
        assert forbidden not in visible


def test_channels_renders_real_profile_and_version(env):
    profile = _seed_profile(env)
    html = page(env).text
    visible = page_text(html)
    assert profile["id"][:4] in html  # id real só na seção avançada
    assert "História" in visible
    assert "channel_v1" in visible
    assert 'value="Narrativa cronológica"' in html
    assert 'value="Roma, Egito"' in html
    assert 'value="Grafite e âmbar"' in html
    assert 'value="piper:pt_BR-faber-medium"' in html
    assert "Cada alteração cria uma versão auditável" in visible

    patched = env["client"].patch(f"/studio/channels/{profile['id']}",
                                  json={"expected_version": 1, "changes": {'strategy': 'Diálogo comparado',
                                                                           'target_duration_s': 480}},
                                  headers=POST_HEADER)
    assert patched.status_code == 200, patched.text
    updated_html = page(env).text
    assert "channel_v2" in page_text(updated_html)
    assert 'value="Diálogo comparado"' in updated_html


def test_channels_shows_niche_as_read_only_and_does_not_fake_editable_field(env):
    html = page(env).text
    visible = page_text(html)
    assert "História" in visible  # nicho do projeto é real
    assert "Definido na criação do canal" in visible
    assert 'id="nicho"' not in html


# --------------------------- SET-01/W1.6: estratégia editorial exposta no perfil do canal


def test_profile_form_exposes_narrative_duration_and_cta_with_real_values(env):
    """SET-01 (A32): narrativa, duração padrão e CTA do canal ganham campo na tela.

    Os três já alimentam o prompt pelo perfil (`channel_profiles` → configuração efetiva);
    faltava o formulário. O campo mostra o valor real do perfil e os limites do domínio.
    """
    _seed_profile(env, narrative="Documentário em três atos", target_duration_s=480,
                  cta="Inscreva-se e ative o sino")
    html = page(env).text

    narrative = re.search(r'<input[^>]*id="canal-narrativa"[^>]*>', html)
    assert narrative is not None, "campo Estilo narrativo ausente"
    assert 'value="Documentário em três atos"' in narrative.group(0)
    assert 'maxlength="4000"' in narrative.group(0)

    duration = re.search(r'<input[^>]*id="canal-duracao"[^>]*>', html)
    assert duration is not None, "campo Duração padrão ausente"
    assert 'value="480"' in duration.group(0)
    assert 'min="1"' in duration.group(0) and 'max="36000"' in duration.group(0)

    cta = re.search(r'<input[^>]*id="canal-cta"[^>]*>', html)
    assert cta is not None, "campo Chamada para ação ausente"
    assert 'value="Inscreva-se e ative o sino"' in cta.group(0)
    assert 'maxlength="500"' in cta.group(0)

    for field_id, label in (("canal-narrativa", "Estilo narrativo"),
                            ("canal-duracao", "Duração padrão \\(segundos\\)"),
                            ("canal-cta", "Chamada para ação")):
        assert re.search(rf'<label for="{field_id}">\s*{label}\s*</label>', html), field_id

    assert_ux_contract(html, page="canais/estrategia-editorial")


def test_profile_form_sends_the_editorial_fields_to_the_same_profile_route(env):
    """Sem rota nova: o formulário existente passa a enviar os três campos no `changes`."""
    _seed_profile(env)
    html = page(env).text
    for field_id in ("canal-narrativa", "canal-duracao", "canal-cta"):
        assert f'getElementById(\'{field_id}\')' in html, field_id
    assert "narrative:" in html and "cta:" in html and "target_duration_s" in html


# ------------------------------------------ campos declarados que o core ainda não aplica


def test_voice_and_visual_identity_are_declared_not_applied(env):
    """R4: rótulo honesto para campos sem consumidor no core (nenhuma promessa sem consumidor).

    `channel_profiles.voice` é ignorada pelo render — a voz sai do estilo (`params.voice.model`)
    ou do projeto (`composition.py:218-260`) — e `visual_identity` não é consumida por nenhum
    estágio. Enquanto não houver consumidor, a tela declara isso em vez de prometer "voz usada" /
    "aplicada a thumbnail, cartelas e legendas".
    """
    _seed_profile(env)
    html = page(env).text
    visible = page_text(html)

    # As promessas antigas, sem consumidor, não podem sobreviver.
    assert "Voz usada nos vídeos novos deste canal" not in visible
    assert "Aplicada a thumbnail, cartelas e legendas" not in visible

    # A honestidade precisa ser visível (não só leitor de tela) e dizer onde o efeito não acontece.
    voice = re.search(r'<label for="canal-voz">.*?<small>(.*?)</small>', html, re.S)
    assert voice is not None, "campo Voz do narrador ausente"
    assert "declarado, ainda não aplicado" in voice.group(1).lower()
    # RF-01: o texto visível usa "canal"/"estúdio", nunca "projeto" (a voz sai do estilo ou do
    # padrão do estúdio; `channel_profiles.voice` é ignorada — `composition.py:218-260`).
    assert "estilo ou do padrão do estúdio" in voice.group(1).lower()

    identidade = re.search(r'<label for="canal-identidade">.*?<span class="hint">(.*?)</span>',
                           html, re.S)
    assert identidade is not None, "campo Identidade visual ausente"
    assert "declarado, ainda não aplicado" in identidade.group(1).lower()
    assert "thumbnail, cartelas" in identidade.group(1).lower()


# ------------------------------------------------------- menu de Configurações


def test_settings_menu_matches_the_prototype_and_keeps_the_active_channel(env):
    """Menu de Configurações na ordem do protótipo, com todos os destinos reais.

    Cada link carrega o canal ativo: trocar de seção não pode voltar para o primeiro canal.
    """
    html = page(env).text
    labels = [_nav_text(item) for item in settings_nav_items(html)]
    assert labels == ["Canais", "Marca & Editorial", "Produção & Orçamento",
                      "Conexões & Equipe"]
    for item in settings_nav_items(html):
        assert f"project_id={env['project'].id}" in item, item


# --------------------------------------------------------- canal ativo no topo


def test_active_channel_is_the_first_decision_and_lists_every_channel(env):
    """Pedido do operador: trocar de canal é a primeira decisão da tela e fica visível.

    O protótipo mostra a lista com selo ATIVO e botão Trocar; o seletor da topbar continua
    existindo como caminho nativo, e os dois precisam apontar para o mesmo conjunto real.
    """
    outro = env["videos"].create_project("Canal Secundário", niche="Tecnologia")
    html = page(env).text

    assert 'id="canal-ativo-card"' in html
    card = html[html.index('id="canal-ativo-card"'):html.index('id="painel-identidade"')]
    assert "Canal ativo" in card
    assert '<span class="selo">ATIVO</span>' in card
    assert f'data-trocar-canal="{outro.id}"' in card
    assert "Canal Secundário" in page_text(card)
    # o seletor nativo lista todos e marca o atual
    assert f'<option value="{env["project"].id}" selected>Canal H</option>' in card
    assert f'<option value="{outro.id}">Canal Secundário</option>' in card
    # o card vem antes da identidade — é a primeira decisão, não um detalhe escondido
    assert html.index('id="canal-ativo-card"') < html.index('id="painel-perfil"')
    assert_ux_contract(html, page="canais/canal-ativo")


# ------------------------------------------------------------------- aparência


def _seed_style(env, name, params=None):
    r = env["client"].post("/studio/styles", json={"name": name, "params": params or {}},
                           headers=POST_HEADER)
    assert r.status_code == 201, r.text
    return r.json()


def test_channel_appearance_marks_the_current_style_in_the_gallery(env):
    """UX V3: o estilo é escolhido em cartões (galeria), não em combo; o atual vem marcado."""
    style = _seed_style(env, "Documentário Cinemático")
    _seed_profile(env, style_id=style["id"])

    html = page(env).text
    bloco = re.search(r'<fieldset class="pills"[^>]*aria-describedby="canal-estilo-hint".*?</fieldset>',
                      html, re.S).group(0)
    assert bloco.count('class="cartao-estilo"') == 2   # padrão do estúdio + o estilo real
    assert '<span class="amostra" aria-hidden="true">DOCUMENTÁRIO CINEMÁTICO</span>' in bloco
    assert re.search(rf'name="style_id" value="{style["id"]}" checked>', bloco)
    # "seguir o padrão" continua sendo uma escolha possível, não marcada agora
    assert not re.search(r'name="style_id" value="" checked', bloco)
    assert re.search(r'href="/studio/panel/estilos(?:\?project_id=[^"]+)?"', html)
    assert "Criar novo estilo" in page_text(html)
    assert_ux_contract(html, page="canais/aparencia")


def test_channel_appearance_defaults_to_the_studio_default_without_a_style(env):
    _seed_style(env, "Cinemático")
    _seed_profile(env)

    html = page(env).text
    assert re.search(r'name="style_id" value="" checked', html)
    assert "Segue o padrão do estúdio" in page_text(html)
    assert_ux_contract(html, page="canais/aparencia-sem-estilo")


def test_channel_appearance_form_has_label_hint_and_live_feedback(env):
    _seed_profile(env)
    html = page(env).text
    assert "<legend>Estilo visual padrão</legend>" in html
    assert 'aria-describedby="canal-estilo-hint"' in html
    assert 'id="canal-estilo-hint"' in html
    assert 'id="appearance-feedback"' in html
    assert 'role="status"' in html and 'aria-live="polite"' in html
    assert "<details open" not in html  # nada de avançado aberto por padrão
    assert html.count("<h1") == 1


def test_channel_appearance_without_profile_teaches_the_next_step(env):
    visible = page_text(page(env).text)
    assert "Crie o perfil do canal para escolher um estilo" in visible
    assert "Criar novo estilo" in visible


# -------------------------------------------------------------------- providers


def test_providers_show_capability_cost_rate_limit_and_honest_availability(env):
    html = page(env).text
    visible = page_text(html)
    assert "Providers por tarefa" in visible
    # disponível de verdade: o catálogo registra a implementação local validada
    assert "Disponível" in visible
    assert "Capability" in visible
    assert "text.generate" in visible
    assert "Sem custo" in visible
    # sem implementação validada: UNAVAILABLE com motivo explícito, nunca fingindo
    assert "Indisponível" in visible
    assert "OPENCODE_BRIDGE_TOKEN ausente" in visible
    assert "Custo estimado não é preço cobrado" in visible


def test_unavailable_provider_test_command_is_not_focusable(env):
    html = page(env).text
    # o provider de imagem (opencode sem bridge) está indisponível: sem botão focável
    segment = re.search(r'data-provider-kind="image".*?(?=data-provider-kind="voice")', html, re.S)
    assert segment is not None
    assert "Testar conexão" in segment.group(0)
    assert "<button" not in segment.group(0)
    assert 'aria-disabled="true"' in segment.group(0)


def test_available_provider_has_a_real_connection_test_control(env):
    html = page(env).text
    segment = re.search(r'data-provider-kind="text".*?(?=data-provider-kind="image")', html, re.S)
    assert segment is not None
    assert 'data-test-provider="text"' in segment.group(0)
    assert "/providers/test" in html


def test_routing_is_derived_from_the_economic_profile(env):
    env["client"].put(f"/studio/projects/{env['project'].id}/budget",
                      json={"hard_monthly_usd": "20", "soft_monthly_usd": "10",
                            "hard_video_usd": "4", "soft_video_usd": "2",
                            "economic_profile": "ECONOMY"},
                      headers=POST_HEADER)
    visible = page_text(page(env).text)
    assert "ECONOMY" in visible
    assert "Escolha no perfil" in visible
    assert "demo" in visible


# ---------------------------------------------------------------------- budget


def test_budget_without_persisted_row_is_explicit_and_never_zero(env):
    html = page(env).text
    visible = page_text(html)
    assert "Nenhum limite de canal persistido" in visible
    assert "padrão do servidor" in visible
    assert "Sem registro de uso" in visible
    assert "US$ 0,00" not in html
    assert "role=\"progressbar\"" not in html


def test_budget_renders_real_limits_and_roundtrips(env):
    r = env["client"].put(f"/studio/projects/{env['project'].id}/budget",
                          json={"hard_monthly_usd": "20", "soft_monthly_usd": "10",
                                "hard_video_usd": "4", "soft_video_usd": "2"},
                          headers=POST_HEADER)
    assert r.status_code == 200, r.text
    html = page(env).text
    visible = page_text(html)
    assert "20,00" in visible and "10,00" in visible and "4,00" in visible and "2,00" in visible
    assert "Limite hard mensal" in visible and "Limite soft mensal" in visible
    assert "US$ 0,00" not in html


def test_budget_summary_keeps_real_estimate_free_and_unknown_apart(env):
    _seed_usage(env)
    visible = page_text(page(env).text)
    assert "Real US$ 0,11" in visible
    assert "Estimado US$ 0,03" in visible
    assert "Sem custo em 1 chamada(s)" in visible
    assert "Desconhecido em 1 chamada(s)" in visible


# --------------------------------------------------------------------- youtube


def youtube_segment(html: str) -> str:
    """Trecho do card 'Canal do YouTube', do cabeçalho até a seção avançada."""
    match = re.search(r'Canal do YouTube.*?(?=<details class="[^"]*\badvanced\b)', html, re.S)
    assert match is not None, "card do YouTube ausente"
    return match.group(0)


def test_youtube_disconnected_without_server_oauth_is_disabled_with_a_real_reason(env):
    html = page(env).text
    segment = youtube_segment(html)
    visible = page_text(segment)
    assert "Sem associação" in visible
    # UX V3: o estado aparece em texto humano; o enum cru não vaza para a tela.
    assert "DISCONNECTED" not in visible
    assert "OAuth" in visible
    # O fluxo existe desde a F8: a copy do card não pode mais negar o consentimento.
    assert "não está implementado" not in visible
    assert "não configurado no servidor" in visible
    # Desabilitado de verdade: sem botão focável e sem caminho de endpoint.
    assert 'id="youtube-reauth"' not in segment
    assert "data-authorize-path" not in segment
    assert 'aria-disabled="true"' in segment


def test_youtube_reauthorize_calls_the_real_oauth_endpoint_when_configured(env_oauth):
    pid = env_oauth["project"].id
    html = page(env_oauth).text
    segment = youtube_segment(html)
    visible = page_text(segment)
    assert "não está implementado" not in visible
    assert "não configurado no servidor" not in visible
    assert f'data-authorize-path="/studio/projects/{pid}/youtube-oauth/authorize"' in segment
    button = re.search(r'<button[^>]*id="youtube-reauth"[^>]*>(.*?)</button>', segment, re.S)
    assert button is not None, "botão de consentimento ausente com OAuth configurado"
    assert "Conectar" in button.group(1)
    assert "is-disabled" not in button.group(0)
    # O endpoint real devolve a URL de autorização do Google; montar a URL não toca a rede.
    r = env_oauth["client"].post(f"/studio/projects/{pid}/youtube-oauth/authorize", headers=POST_HEADER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["authorization_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "access_type=offline" in body["authorization_url"]
    assert "code_challenge_method=S256" in body["authorization_url"]
    # O state carrega o projeto para a página de callback saber para onde postar.
    assert body["state"].startswith(pid + ".")
    assert "your_client_secret" not in r.text


def test_youtube_connected_offers_reconnect_and_revoke(env_oauth):
    pid = env_oauth["project"].id
    env_oauth["client"].put(
        f"/studio/projects/{pid}/youtube-channel",
        json={"channel_id": "UC123", "title": "Canal H", "refresh_token": "1//refresh-secret"},
        headers=POST_HEADER)
    html = page(env_oauth).text
    visible = page_text(html)
    assert "Conectado" in visible
    assert 'id="youtube-reauth"' in html
    assert f'data-authorize-path="/studio/projects/{pid}/youtube-oauth/authorize"' in html
    assert "Reconectar" in visible
    assert 'id="youtube-revoke"' in html
    assert f'data-revoke-path="/studio/projects/{pid}/youtube-oauth/revoke"' in html


def test_youtube_expired_token_offers_reauthorize_when_configured(env_oauth):
    pid = env_oauth["project"].id
    env_oauth["client"].put(
        f"/studio/projects/{pid}/youtube-channel",
        json={"channel_id": "UC123", "title": "Canal H", "refresh_token": "1//refresh-secret",
              "token_expires_at": "2020-01-01T00:00:00+00:00"},
        headers=POST_HEADER)
    html = page(env_oauth).text
    visible = page_text(html)
    assert "Expirado" in visible
    button = re.search(r'<button[^>]*id="youtube-reauth"[^>]*>(.*?)</button>', html, re.S)
    assert button is not None and "Reautorizar" in button.group(1)
    assert "is-disabled" not in button.group(0)


def test_oauth_callback_page_carries_the_project_and_closes_the_loop(env_oauth):
    pid = env_oauth["project"].id
    state = env_oauth["client"].post(
        f"/studio/projects/{pid}/youtube-oauth/authorize", headers=POST_HEADER).json()["state"]
    r = env_oauth["client"].get(f"/studio/oauth/callback?code=SYNTHETIC-stub-code&state={state}",
                                headers=AUTH_HEADER)
    assert r.status_code == 200, r.text
    html = r.text
    assert "Consentimento do YouTube" in page_text(html)
    assert f'data-complete-path="/studio/projects/{pid}/youtube-oauth/callback"' in html
    assert f'href="/studio/canais?project_id={pid}"' in html
    # O código de autorização fica na URL para o browser; o servidor não o renderiza no HTML.
    assert "SYNTHETIC-stub-code" not in html


def test_oauth_callback_page_refuses_an_unknown_state_without_dead_end(env):
    r = env["client"].get("/studio/oauth/callback?code=SYNTHETIC-code&state=not-a-real-state",
                          headers=AUTH_HEADER, follow_redirects=False)
    assert r.status_code == 303
    location = r.headers["location"]
    assert location.startswith("/studio/panel/conexoes?")
    assert "state=not-a-real-state" in location
    # A tela de Conexões conclui o consentimento pelo browser e explica o erro; nada de beco sem saída.
    page = env["client"].get(location, headers=AUTH_HEADER)
    assert page.status_code == 200
    assert "connections/oauth/callback" in page.text
    assert "youtube-oauth/callback" not in page.text


def test_oauth_callback_page_renders_denied_consent_without_javascript(env):
    pid = env["project"].id
    r = env["client"].get(
        f"/studio/oauth/callback?error=access_denied&state={pid}.{'a' * 43}", headers=AUTH_HEADER)
    assert r.status_code == 200, r.text
    visible = page_text(r.text)
    assert "não autorizou" in visible
    assert "access_denied" in visible
    assert f'href="/studio/canais?project_id={pid}"' in r.text


def test_oauth_flow_never_renders_secrets_in_html(env_oauth):
    pid = env_oauth["project"].id
    env_oauth["client"].put(
        f"/studio/projects/{pid}/youtube-channel",
        json={"channel_id": "UC123", "title": "Canal H",
              "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
              "access_token": "ya29.synthetic-access-value",
              "refresh_token": "1//refresh-secret"},
        headers=POST_HEADER)
    state = env_oauth["client"].post(
        f"/studio/projects/{pid}/youtube-oauth/authorize", headers=POST_HEADER).json()["state"]
    pages = (
        page(env_oauth).text,
        env_oauth["client"].get(f"/studio/oauth/callback?code=SYNTHETIC-code&state={state}",
                                headers=AUTH_HEADER).text,
    )
    for html in pages:
        for secret in ("your_client_secret", "ya29.synthetic-access-value",
                       "1//refresh-secret", "SYNTHETIC-code", "••••"):
            assert secret not in html, f"segredo renderizado no HTML: {secret}"


def test_youtube_status_never_exposes_the_secret(env):
    assoc = env["client"].put(
        f"/studio/projects/{env['project'].id}/youtube-channel",
        json={"channel_id": "UC123", "title": "Canal H",
              "scopes": ["https://www.googleapis.com/auth/youtube.upload",
                         "https://www.googleapis.com/auth/yt-analytics.readonly"],
              "access_token": "ya29.synthetic-access-value",
              "refresh_token": "1//refresh-secret"},
        headers=POST_HEADER)
    assert assoc.status_code == 200, assoc.text
    html = page(env).text
    visible = page_text(html)
    assert "Conectado" in visible
    assert "UC123" in html and "Canal H" in visible
    assert "youtube.upload" in visible and "yt-analytics.readonly" in visible
    for secret in ("ya29.", "refresh-secret"):
        assert secret not in html
    # a máscara do mockup não existe no backend: nenhum valor de credencial é inventado
    assert "••••" not in html and "7f2a" not in html
    assert "nenhum valor de credencial" in visible.lower()


def test_youtube_expired_token_is_reported_by_state(env):
    env["client"].put(
        f"/studio/projects/{env['project'].id}/youtube-channel",
        json={"channel_id": "UC123", "title": "Canal H", "refresh_token": "1//refresh-secret",
              "token_expires_at": "2020-01-01T00:00:00+00:00"},
        headers=POST_HEADER)
    visible = page_text(page(env).text)
    assert "Expirado" in visible


# ------------------------------------------------------------------ config/segredos


def test_project_config_is_sanitized_and_advanced_details_is_closed(env):
    env["conn"].execute(
        "UPDATE studio.projects SET config = %s WHERE id = %s",
        (Jsonb({"text": "demo", "OPENAI_API_KEY": "sk-live-LEAK-VALUE"}), env["project"].id),
    )
    env["conn"].commit()
    html = page(env).text
    assert "sk-live-LEAK-VALUE" not in html and "OPENAI_API_KEY" not in html
    assert "demo" in html
    assert "<details open" not in html
    # UX V3: a sanfona avançada é `class="card advanced painel-sanfona"`.
    assert re.search(r'<details class="[^"]*\badvanced\b[^"]*"', html)


# ------------------------------------------------------------------ higiene/erros


def test_channels_page_escapes_xss_from_real_data(env):
    _seed_profile(env, name="Canal <script>alert(1)</script>", strategy="<b>forte</b>")
    html = page(env).text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<b>forte</b>" not in html


def test_channels_page_preserves_csp_and_no_store(env):
    r = page(env)
    assert r.status_code == 200
    assert "nonce-" in r.headers["Content-Security-Policy"]
    assert "no-store" in r.headers.get("Cache-Control", "")


def test_channels_page_without_any_project_is_explicit(env_empty):
    r = env_empty["client"].get("/studio/canais", headers=AUTH_HEADER)
    assert r.status_code == 200, r.text
    assert "Nenhum canal cadastrado" in page_text(r.text)
    assert_ux_contract(r.text, page="canais/sem-canal")


def test_channels_page_requires_authentication(env):
    assert env["client"].get("/studio/canais").status_code == 401


def test_unknown_project_id_is_404(env):
    r = env["client"].get("/studio/canais?project_id=" + "0" * 32, headers=AUTH_HEADER)
    assert r.status_code == 404


def test_channels_page_never_leaks_illustrative_mockup_text(env):
    _seed_profile(env)
    html = page(env).text
    for leaked in ("Finanças Descomplicadas", "1,2 mi views", "run_7f31", "840 mil views",
                   "8–12 min", "Educação long-form", "Shorts de descoberta",
                   "Finanças pessoais explicadas sem jargão", "Adultos curiosos, sem formação técnica",
                   "Paleta grafite+violeta", "pt-BR-faber-medium", "gpt-5-mini", "51 min", "7f2a"):
        assert leaked not in html, leaked