# Falhas pré-existentes no baseline (registro, não corrigidas)

Levantado em 21/11/2026, HEAD `e254b61`, suíte completa com PostgreSQL descartável:
**2625 passed, 63 failed, 58 skipped, 400 s**. As 63 falhas são **anteriores** às mudanças da
F02 (a suíte só as executa quando existe banco; sem `STUDIO_TEST_DSN` elas viram skip — por
isso o problema ficou escondido).

Regra aplicada: bug pré-existente não é corrigido nesta tarefa; fica registrado com evidência,
impacto e referência para avaliação (AGENTS.md do workspace).

## 1. Testes de tela desatualizados após o port para a UX V3 — 42 falhas

Os testes esperam a casca/navegação antiga (V2, `render_panel_page`), mas as telas foram
portadas para a casca V3 e para a IA aprovada. Exemplos medidos:

- `tests/test_panel_page.py` (26): `AssertionError: botão «Criar Vídeo deste Tema» sem destino
  real`, ausência de `#novo-projeto`, paleta escura antiga, âncoras da home única.
- `tests/test_channels_page.py` (5): `card do YouTube ausente`; `assert 'class="advanced"'`.
- `tests/test_analytics_page.py` (4), `test_panel_production_page.py` (3),
  `test_connections_page.py` (1), `test_script_page.py` (1), `test_styles_page.py` (1),
  `test_publishing.py::test_preview_page_renders_sidebar_navigation` (1).

**Impacto:** o contrato de UX real (V3) é coberto por `test_*_v3.py` e `test_ux_contract.py`;
os arquivos acima ficaram para trás e dão falsa segurança contra regressão de casca.
**Referência:** commits do port V3 (`ad2ab7f`..`1621dd9`). **Sugestão:** reescrevê-los na fase
F02.T03/T04 ou aposentá-los quando o conteúdo for coberto pelos testes V3.

## 2. Testes que dependem de FFmpeg — 17 falhas

`ffmpeg`/`ffprobe` não existem no host desta execução (o CI/reports usam a imagem
`faceless-v2-hygiene-test-local`, que os traz).

- `tests/test_render_plan_executor.py` (11), `tests/test_render_reuse.py` (5),
  `tests/test_render_plan_repo.py` (1, cenário que executa o executor).

**Impacto:** nenhum para o código; é ambiente. **Sugestão:** rodar a suíte de render na imagem
documentada (F07) e registrar o comando no gate G0/G7.

## 3. Contrato gerado com outra versão de pydantic — 2 falhas

- `tests/test_contracts_snapshot.py::test_committed_contracts_match_code`:
  `contracts/v1/project.schema.json` traz `"minimum": 0.0`; gerado localmente com pydantic
  2.5.0 sai `"minimum": 0`. O pin do projeto é 2.11.4.
- `tests/test_secrets_hygiene.py::test_extracted_starter_runs_contract_snapshot_and_backup_import`:
  falha em cascata, porque roda o snapshot dentro do pacote extraído.

**Impacto:** o contrato publicado diverge de quem gera com 2.5.0 — regerar com a versão pinada
antes de release. **Sugestão:** validar o ambiente no F07 e não regerar contrato com versão
diferente da pinada.

## 4. Teste sensível à ordem — 2 falhas

- `tests/test_port_contracts.py::test_every_registered_provider_satisfies_its_port` e
  `::test_catalog_and_registry_have_no_drift` falham na suíte completa e **passam isolados**
  (6/6, com ou sem banco). Algum teste anterior mexe no registry global de providers.

**Impacto:** a suíte completa pode acusar drift inexistente — precisa de isolamento.
**Sugestão:** investigar em F06 (roteamento/providers), que mexe no registry.

## Como reproduzir

Ver [06-validation](../06-validation.md#postgresql-descartável-receita-validada-na-f00). Os
comandos e a classificação acima usam a mesma DSN descartável e a mesma prova de 64 hex.