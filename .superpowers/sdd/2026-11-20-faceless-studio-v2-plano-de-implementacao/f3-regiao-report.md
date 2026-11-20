# F3-07 — origem regional das tendências

## Resultado

- `fetch_popular_trends` consulta `chart=mostPopular` para uma única região, sem agregação mundial. O rótulo anterior classificava toda região não BR como Global.
- A fonte agora é `YouTube Brasil (Em Alta)` para BR, `YouTube EUA (Em Alta)` para US e `YouTube <CÓDIGO> (Em Alta)` para outras regiões, com comparação case-insensitive. O `regionCode` enviado à API permanece exatamente como recebido.
- `RefreshTrends` consulta BR e US separadamente. `BuildPanel` mapeia Brasil para BR, EUA para US, e os demais rótulos com código de duas letras para seu respectivo código. O rótulo histórico `YouTube Global (Em Alta)`, que podia representar qualquer não BR, é classificado como `UNKNOWN`, sem inferência de EUA ou agregação global.
- A página mostra filtros e badges para Brasil, EUA, códigos presentes e origem desconhecida; o nome histórico exibido como fonte também é substituído por origem desconhecida. Não existe nesta coleta evidência de agregação mundial, portanto não há filtro Mundo. Os botões mantêm a interação existente, com `aria-pressed`, e o filtro considera as primeiras seis **correspondências**, não as seis primeiras tendências gerais.

## Validação

- TDD: antes da correção, `tests/test_youtube_popular_trends.py` falhou em três casos (US, `us` e JP) por receber Global; cinco passaram.
- Docker Python 3.12, sem rede, filesystem somente leitura, workspace montado somente leitura e sem DSN: `pytest -q -p no:cacheprovider tests/test_youtube_popular_trends.py tests/test_panel.py tests/test_panel_page.py` — 19 passaram, 22 ignorados, um aviso de depreciação.
- Mesmo isolamento, suíte completa `pytest -q -p no:cacheprovider` — 649 passaram, 309 ignorados, dois falharam e um aviso. Falhas: `tests/test_secrets_hygiene.py::test_real_starter_archive_is_safe_and_keeps_scripts_executable` e `tests/test_secrets_hygiene.py::test_extracted_starter_runs_contract_snapshot_and_backup_import`; ambos relatam `Secret hygiene check could not complete safely` no empacotamento. A montagem não disponibiliza os metadados Git externos deste worktree; o verificador usa comandos Git. Não foi demonstrada execução bem-sucedida desses testes neste ambiente.
- Execução local com Python 3.11 não coletou `test_panel_page.py` por `SyntaxError` preexistente em `renderer/app/studio/api/preview.py`; o projeto usa Python 3.12 no Dockerfile.
- Os testes de banco ficaram ignorados: não foi conectado banco compartilhado nem provisionado banco descartável.

## Revisão end-to-end

- Os novos testes falharam antes da correção por classificar o legado como GLOBAL, não mapear US/JP e oferecer Mundo sem agregação; agora cobrem adaptador → `BuildPanel` → página para BR, US e JP, além do legado. Foram atualizadas as assertions de página que atribuíam Mundo ao legado.
- Um teste executando o JavaScript real do filtro com Node.js reproduziu que um resultado após os seis primeiros permanecia oculto; após a correção, passou (1 teste; Node v26). Ele também verifica a atualização de `aria-pressed`. Na suíte Docker, esse teste é ignorado porque a imagem não tem Node.
- Com Python 3.12 em Docker, workspace e metadados Git montados somente para leitura, rede interna e PostgreSQL temporário sem porta publicada, protegido pela prova de conexão descartável: testes pertinentes — **45 passaram**; suíte completa — **895 passaram, 70 ignorados, um aviso** de depreciação de Starlette/AnyIO.
- As duas falhas anteriores de empacotamento passaram isoladamente quando o arquivo `.git` do worktree e o diretório Git comum foram montados no contêiner (2 passaram). A causa era a ausência desses metadados na montagem anterior; não houve alteração no empacotador. A suíte completa com metadados também passou nesses testes.
- Não foi feito teste manual de navegador ou leitor de tela. As fontes históricas são apresentadas como desconhecidas sem alterar registros persistidos.

## Revisão de expansão e fontes

- O cabeçalho lista os pares distintos de nome e URL de todas as tendências, identificando explicitamente esse escopo; a fonte histórica ambígua continua apresentada como origem desconhecida. O cabeçalho não afirma que uma única fonte representa a lista mista nem acompanha o filtro.
- A troca de filtro recolhe a lista. O botão de expansão fica oculto quando há até seis correspondências e, acima disso, exibe a quantidade adicional do filtro ativo; expansão, recolhimento e `aria-expanded` permanecem sincronizados.
- TDD: antes da correção, o teste da lista mista falhou porque apenas a primeira fonte era exibida, e o teste Node falhou porque o botão permanecia visível com dois resultados. Após a correção, `tests/test_panel.py tests/test_youtube_popular_trends.py` passou no host: **25 passaram**, incluindo o teste Node com zero, dois, seis, sete e nove resultados, troca de filtros e expansão/recolhimento. Aviso preexistente de configuração do pytest-asyncio.
- Suíte completa em Docker Python 3.12, com workspace e metadados Git somente leitura e PostgreSQL descartável protegido por prova, em rede interna sem porta publicada: **909 passaram, 70 ignorados e um aviso** de depreciação Starlette/AnyIO. O teste Node foi ignorado nessa imagem, que não contém Node; passou separadamente no host. Recursos temporários foram removidos.
- Não houve validação manual em navegador ou leitor de tela.

Esta entrega corresponde somente à F3-07; não indica conclusão da F3.
