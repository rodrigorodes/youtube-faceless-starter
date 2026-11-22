# S8 — Congelar a seleção de provider no snapshot do run: fechamento

**Status:** implementado e portado para o checkout principal. Nada commitado.
**Problema:** `provider_policy` só congelava `profile`/`version`; o retry re-resolvia do zero.
Com catálogo/perfil mudando entre criação e retry, o provider executado podia diferir do
exibido/aprovado.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `domain/effective_config.py` | `provider_selection: Mapping[str, str] | None` (aditivo); `provider_policy.selection` no documento; `PROVIDER_POLICY_VERSION = 2`; validação de capacidade conhecida, spec e ausência de segredo (`_clean_provider_selection`); snapshots antigos sem `selection` continuam válidos |
| `application/production.py` | `provider_selection_for` no `ProductionCoordinator.start`; `_frozen_selection` lê do snapshot; `_FROZEN_PROVIDER_SELECTION` ContextVar ligado em `_execute_claimed`; retry/resume usam a seleção congelada |
| `composition.py` | `_frozen_selection_for` resolve a seleção por capacidade na criação do run; `ProviderRouting` consulta a seleção congelada antes da política viva; `_frozen` recusa em vez de trocar em silêncio; `_voice_for_config` usa `selection["voice"]` |
| `tests/test_effective_config.py` | 4 testes: seleção opcional, documento legado, capacidade inválida, segredo |
| `tests/test_composition.py` | 2 testes: roteamento usa a seleção congelada; seleção indisponível falha em vez de trocar |
| `tests/test_production_coordinator.py` | 3 testes: retry não re-resolve; run legado sem `selection` mantém o roteamento vivo; worker liga o contexto |

## Evidência real

- Focados no worktree de origem: `test_effective_config.py test_composition.py
  test_production_coordinator.py test_production_flow_db.py test_production_api.py` →
  **133 passed**; testes novos filtrados → **22 passed**.
- Suíte completa no worktree: **3040 passed, 6 failed, 6 skipped** (execução única limpa); as 6
  falhas são pré-existentes (contrato defasado no HEAD, `test_port_contracts` dependente de
  ordem, `test_publish_api` e `test_secrets_hygiene` por limitação de worktree).
- **Portado para o checkout principal:** `test_effective_config.py test_composition.py
  test_production_coordinator.py` → **105 passed**; com produção
  (`test_production_flow_db.py test_production_api.py test_production_handlers.py`) →
  **150 passed**.

## Como o retry lê a seleção congelada

1. `Production._create` → `ProductionCoordinator.start(..., provider_selection_for=...)`.
2. `_resolve_config` grava `EffectiveConfig.provider_selection`; o snapshot persistido leva
   `provider_policy.selection`.
3. `retry`/`resume` não cria run novo nem re-resolve: `_execute_claimed` lê
   `_frozen_selection(run_id)` e liga o `ContextVar` durante a execução.
4. `ProviderRouting.__call__` consulta o `ContextVar` primeiro; `_frozen` constrói o provider do
   spec congelado e audita. Se o spec não construir, **recusa** (`ProviderNotFound`/
   `ProviderSpecInvalid`), nunca troca em silêncio.
5. Run legado (sem `selection`): `_frozen_selection` devolve `None` e o roteamento vivo continua
   exatamente como antes.

## Desvios e limitações

- **`search` fora do congelamento:** `ProviderKind.SEARCH` (W3.1) não tem chave em
  `Project.config` e não gera conteúdo no run; `_frozen_selection_for` o ignora. Sem esse ajuste,
  o `getattr(ProjectConfig, "search")` estourava em `test_production_flow_db`.
- **Chave de capacidade:** o exemplo do guia dizia `"render"`, mas o enum real é `"renderer"`; a
  seleção usa as chaves reais do `ProviderKind`.
- **Contrato:** não existe contrato versionado de `EffectiveConfig` em `contracts/`; nada a
  regenerar. O `renderplan.schema.json` não contém `provider_policy`.
- **Versão 2:** `PROVIDER_POLICY_VERSION` subiu para 2; documentos antigos com versão 1 continuam
  aceitos (`>= 1`), e a validação só exige `selection` quando presente.
