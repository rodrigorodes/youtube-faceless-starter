# Evidência de Integração e Testes: REC-03.01 & REC-03.02 (Rodada 3)

**Data:** 26/11/2026  
**Engenheiro / Agente:** `rec03-ux` (`Gemini 3.8 Flash High`)  
**Branch:** `develop` (HEAD `3ca1f8512eb4681b97c4e5ecf3ee9ba61fae95b8` + working tree)  
**Status:** PRONTO PARA RE-REVIEW INDEPENDENTE (RODADA 3) — NÃO MARCADO COMO VERIFIED  

---

## 1. Resumo Executivo das Correções para Rodada 3

Em resposta direta ao relatório de auditoria independente da Rodada 2 (`rec-03-01-02-independent-review-neon-high-round2.md`, decisão `REJECTED`), todos os 4 achados P1 e 4 achados P2 foram integralmente saneados seguindo TDD estrito e disciplina de testes primeiro:

### Achados P1 Saneados
1. **P1-1: Execução real do `STORYBOARD_JS` em Node.js (`tests/test_storyboard_js.py`):**
   - Eliminadas cópias e reimplementações manuais em JS simplificado.
   - O teste agora executa a string real de produção `STORYBOARD_JS` diretamente no ambiente Node.js com harness DOM leve (`FakeElement` / `document.createElement`), avaliando caching `?v=<asset_id>`, resolução dinâmica de aspecto (`16:9` / `9:16`), preservação de prompt sujo (`dirty` assisted prompt), aba de vídeo no modal e short-circuit de cenas temporárias `tmp-*`.
   - Realizado teste de mutação que falhou comprovadamente ao alterar `assetUrl` e foi restaurado antes da finalização. 6/6 testes passando.

2. **P1-2: Arquitetura Limpa e Validação de Escopo em `GET /studio/assets/{asset_id}/file`:**
   - Adicionado `list_by_project` à interface `VideoRepository` (`ports.py`) e implementado em `repo.py`.
   - Adicionado `belongs_to_scope` à interface `AssetRepository` (`ports.py`) e implementado em `media_repo.py` com checagem nas tabelas `scenes` e `scene_assets` unificadas por vídeo ou projeto.
   - O caso de uso `AssetFile` em `renderer/app/studio/application/media.py` valida primeiro a existência do escopo (`VideoNotFound` -> 404), verifica autorização de escopo antes de consultar `self.assets.get()`, rejeita assets inexistentes com 403 (eliminando existence oracle / timing oracle), e previne path traversal que escape o root (`resolve()` + `relative_to(root)` -> 404).

3. **P1-3: Eliminação de Chamadas Diretas de Repositório nas Rotas:**
   - Extraído `GetSceneTiming` como caso de uso da camada de aplicação em `renderer/app/studio/application/media.py` e conectado em `wiring.py`. As rotas não chamam mais `uc.editorial.get_script.scripts.get_scene_assets`.
   - Gerenciamento de trim (`trim_start_s` e `trim_end_s`) delegado inteiramente para `ImportExternalMedia.execute()`, que salva atomicamente os recortes e remove linhas órfãs de `studio.scene_assets` em reimportações sem trim, revogando o acesso ao asset anterior.

4. **P1-4: Endurecimento Rigoroso de Asserções nos Testes:**
   - Em `tests/test_rec_03_studio_routes.py`:
     - Tuplas relaxadas (`in (404, 422)`, `in (415, 422)`) substituídas por códigos exatos (`== 404`, `== 422`).
     - Adicionados testes para `project_id` isolado (200), `project_id` cruzado (403), asset inexistente no escopo (403 sem vazamento de oráculo), escape de traversal por adulteração no banco (404), filename com NUL byte e dot-dot traversal (422), e ciclo completo de reimportação com e sem trim.
   - Em `tests/e2e_ux/test_rec_03_studio_browser.py`:
     - Removidos guards condicionais (`if btn_gerar_faltante.is_visible()...` e `if attribution_input.is_visible()`), tornando as checagens incondicionais e obrigatórias.
     - Substituído `or "?v=" in ...` por asserção estrita `assert f"?v={asset_id}" in src`.
     - Adicionada asserção de persistência da contagem de cenas no Passo 4 após `page.reload()`.

### Achados P2 Saneados
- **P2-1:** Normalização estrita de `Content-Type` na rota de importação direta (`.split(";")[0].strip()`) para ignorar parâmetros de MIME (como charset).
- **P2-2:** Validação com `math.isfinite()` em `trim_start_s` e `trim_end_s` nas rotas para rejeitar `NaN`, `+Inf` e `-Inf` com HTTP 422.
- **P2-3:** Substituído `0.0 or ...` por verificação explícita `is not None` em `panel_video_workspace.py` evitando falso negativo em ponto de corte zero.
- **P2-4:** No frontend `STORYBOARD_JS`: `commitText` agora reseta `m.asset_kind = null`, modal de arquivos respeita `custom_assisted_prompt`, e `doImportMedia` dá short-circuit imediato quando `scene_id` inicia com `tmp-*`.

---

## 2. Testes de Unidade de Rotas e Segurança (Container)

Comando executado:
```bash
./scripts/test-container.sh tests/test_rec_03_studio_routes.py
```

Saída:
```
============================= test session starts ==============================
platform linux -- Python 3.12.16, pytest-8.3.5, pluggy-1.7.0
rootdir: /w
plugins: anyio-4.16.0
collected 27 items

tests/test_rec_03_studio_routes.py ...........................           [100%]

======================== 27 passed, 1 warning in 15.85s ========================
== pytest saiu com código 0
```

---

## 3. Testes Unitários de Frontend no Host Node.js

Comando executado:
```bash
python3 -m pytest tests/test_storyboard_js.py -v
```

Saída:
```
============================= test session starts ==============================
platform darwin -- Python 3.11.9, pytest-8.2.0, pluggy-1.6.0
rootdir: /Users/rodrigomendes/youtube-faceless-starter
collected 6 items

tests/test_storyboard_js.py::test_storyboard_js_syntax_check PASSED      [ 16%]
tests/test_storyboard_js.py::test_storyboard_js_executes_in_node_and_renders_thumbs_and_urls PASSED [ 33%]
tests/test_storyboard_js.py::test_storyboard_js_aspect_ratio_and_dirty_assisted_prompt_preserved PASSED [ 50%]
tests/test_storyboard_js.py::test_storyboard_js_modal_files_and_video_tab PASSED [ 66%]
tests/test_storyboard_js.py::test_storyboard_js_do_import_media_short_circuit_on_tmp_scene PASSED [ 83%]
tests/test_storyboard_js.py::test_storyboard_js_asset_kind_and_trim_preservation PASSED [100%]

============================== 6 passed in 5.60s ===============================
```

Suíte de painéis e workflows do host (101 testes):
```bash
python3 -m pytest tests/test_erro_js.py tests/test_storyboard_js.py tests/test_panel.py tests/test_falha_producao.py \
  tests/test_publicacao_acao.py tests/test_workflow_analytics.py tests/test_workflow_publish.py \
  tests/test_workflow_trends.py -v
```
Saída:
```
============================= 101 passed in 8.76s ==============================
```

---

## 4. Testes de Integração e Arquitetura do Container (90 testes)

Comando executado:
```bash
./scripts/test-container.sh \
  tests/test_rec_03_studio_routes.py tests/test_media_api.py tests/test_media_swap_api.py \
  tests/test_video_storyboard_v3.py tests/test_panel_scene_multimedia.py tests/test_v4_studio_ux.py \
  tests/test_ux_contract.py tests/test_studio_browser_security.py tests/test_architecture.py
```

Saída:
```
============================= test session starts ==============================
platform linux -- Python 3.12.16, pytest-8.3.5, pluggy-1.7.0
rootdir: /w
plugins: anyio-4.16.0
collected 90 items

tests/test_rec_03_studio_routes.py ...........................           [ 30%]
tests/test_media_api.py ............                                     [ 43%]
tests/test_media_swap_api.py ..........                                  [ 54%]
tests/test_video_storyboard_v3.py .......                                [ 62%]
tests/test_panel_scene_multimedia.py ...                                 [ 65%]
tests/test_v4_studio_ux.py ......                                        [ 72%]
tests/test_ux_contract.py .............                                  [ 86%]
tests/test_studio_browser_security.py ...                                [ 90%]
tests/test_architecture.py .........                                     [100%]

======================== 90 passed, 1 warning in 29.59s ========================
== pytest saiu com código 0
```

---

## 5. Suíte E2E Browser com Playwright (Desktop + Mobile)

Execução isolada na porta 8100 contra stack efêmera (`docker-compose.e2e.yml`):
```bash
E2E_PORT=8100 docker compose -p faceless-e2e-rec03y -f docker-compose.e2e.yml up -d --build --wait

STUDIO_E2E_BASE_URL="http://127.0.0.1:8100" \
STUDIO_PUBLICATION_ENABLED=0 \
python3 -m pytest tests/e2e_ux/test_rec_03_studio_browser.py -v -s

docker compose -p faceless-e2e-rec03y -f docker-compose.e2e.yml down -v
```

Saída da execução Playwright:
```
============================= test session starts ==============================
platform darwin -- Python 3.11.9, pytest-8.2.0, pluggy-1.6.0 -- /Users/rodrigomendes/.pyenv/versions/3.11.9/bin/python3
rootdir: /Users/rodrigomendes/youtube-faceless-starter
plugins: asyncio-1.1.0, playwright-0.10.0, anyio-3.7.1, cov-3.0.0
collected 1 item

tests/e2e_ux/test_rec_03_studio_browser.py::test_rec_03_studio_browser_desktop_and_mobile_e2e[chromium] PASSED

============================== 1 passed in 9.29s ===============================
```

Teardown e descarte dos volumes:
```bash
docker compose -p faceless-e2e-rec03y -f docker-compose.e2e.yml down -v
# Containers e volumes purgados. Portas 8000 e 5678 permaneceram intocadas.
```

---

## 6. Governança, Orçamento e Segurança

- **Portas de DEV:** `8000` e `5678` permaneceram 100% intocadas.
- **Git:** Não houve commits nem pushes na branch `develop`.
- **Custo financeiro:** R$ 0,00 / US$ 0.00 (`STUDIO_PUBLICATION_ENABLED=0`, sem chamadas pagas).
- **Segurança:** CSP estrito sem handlers inline; validação de traversal e escopo cruzado; sanitização de cabeçalhos contra CRLF injection; verificação de existência prévia contra oráculos.
