# F3-07 — origem regional das tendências

## Resultado

- `fetch_popular_trends` consulta `chart=mostPopular` para uma única região, sem agregação mundial. O rótulo anterior classificava toda região não BR como Global.
- A fonte agora é `YouTube Brasil (Em Alta)` para BR, `YouTube EUA (Em Alta)` para US e `YouTube <CÓDIGO> (Em Alta)` para outras regiões, com comparação case-insensitive. O `regionCode` enviado à API permanece exatamente como recebido.
- `RefreshTrends` consulta BR e US separadamente. `BuildPanel` reconhece atualmente apenas o rótulo Brasil e o rótulo histórico Global; a página associa `GLOBAL` a “Em Alta Mundo”. Portanto, novos itens EUA não recebem a classificação/filtro regional existente, e registros antigos rotulados Global continuam podendo aparecer como Mundo. Esses registros não conservam informação suficiente para inferir sua região com segurança; correção de painel e tratamento de histórico não foram incluídos nesta fatia.

## Validação

- TDD: antes da correção, `tests/test_youtube_popular_trends.py` falhou em três casos (US, `us` e JP) por receber Global; cinco passaram.
- Docker Python 3.12, sem rede, filesystem somente leitura, workspace montado somente leitura e sem DSN: `pytest -q -p no:cacheprovider tests/test_youtube_popular_trends.py tests/test_panel.py tests/test_panel_page.py` — 19 passaram, 22 ignorados, um aviso de depreciação.
- Mesmo isolamento, suíte completa `pytest -q -p no:cacheprovider` — 649 passaram, 309 ignorados, dois falharam e um aviso. Falhas: `tests/test_secrets_hygiene.py::test_real_starter_archive_is_safe_and_keeps_scripts_executable` e `tests/test_secrets_hygiene.py::test_extracted_starter_runs_contract_snapshot_and_backup_import`; ambos relatam `Secret hygiene check could not complete safely` no empacotamento. A montagem não disponibiliza os metadados Git externos deste worktree; o verificador usa comandos Git. Não foi demonstrada execução bem-sucedida desses testes neste ambiente.
- Execução local com Python 3.11 não coletou `test_panel_page.py` por `SyntaxError` preexistente em `renderer/app/studio/api/preview.py`; o projeto usa Python 3.12 no Dockerfile.
- Os testes de banco ficaram ignorados: não foi conectado banco compartilhado nem provisionado banco descartável.

Esta entrega corresponde somente à F3-07; não indica conclusão da F3.
