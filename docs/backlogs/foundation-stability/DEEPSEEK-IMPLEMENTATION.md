# Implementação da Foundation com DeepSeek

Base inspecionada em 25/11/2026: `182ec75e265cdb3b5b932a72d8777b45cbc6092d`. Leitura estática. RUN-08 é histórico de outro checkout. Use os IDs de [EXECUTION-BACKLOG](EXECUTION-BACKLOG.md), os gates de [QUALITY-GATES](QUALITY-GATES.md) e o registro do [plano de testes](../../plano-de-testes-faceless/CONTINUITY.md). Este guia detalha como produzir e revisar um diff por vez.

## Primeiro cartão — FS-02.01

**Resultado esperado.** Identificar quais campanhas podem rodar no checkout e impedir que uma suíte mutável comece contra destino de uso. O primeiro cartão admite uma conclusão parcial por suíte. A regressão de banco pode avançar com isolamento comprovado enquanto o browser aguarda FS-02.03.

| Entrada real | Comportamento na base | Decisão de implementação e prova |
|---|---|---|
| `scripts/test-container.sh` e `tests/conftest.py` | Rede por execução, PostgreSQL em tmpfs, dois DSNs, prova compartilhada de descartabilidade, checkout em `/w:ro`. A camada de teste instala pytest. | Reutilizar `verified_test_connect` e `verify_disposable_connection`. Localizar os testes existentes da prova com `rg -n 'verify_disposable_connection\|verified_test_connect' tests`. Verificar que divergência da prova impede escrita. Registrar só resultado, sem DSN, senha ou prova. |
| `scripts/run-e2e-tests.sh` e `tests/e2e_ux/conftest.py` | Shell e fixture aceitam `STUDIO_BASE_URL` e caem em localhost:8000. O shell verifica apenas /health. Acesso direto via pytest contorna o shell. | Validar destino também na entrada da fixture, antes de abrir o browser. Sem identidade da stack descartável, encerrar antes de qualquer navegação ou escrita. Preservar seleção de testes e modo headed. |
| `scripts/run-e2e-full.sh`, `tests/e2e_full/conftest.py`, `docker-compose.e2e.yml` | Projeto faceless-e2e e porta 8100 fixos, limpeza antes do up e no EXIT. A fixture lê outra variável, STUDIO_E2E_BASE_URL, e recusa porta 8000. O Compose usa tmpfs, guard desligado e omite o switch de publicação. | Ligar URL e identidade à instância criada pelo runner. Porta, flag de isolamento e HTTP 200 isoladamente são provas insuficientes. Configurar publicação desabilitada explicitamente no perfil E2E. Adiar execução do runner atual até resolver a propriedade dos recursos em FS-02.03. |

**Casos de aceite do preflight.** Exercitar a decisão com doubles de Docker/HTTP antes de subir serviços. Cobrir URL ausente, alvo de uso, alvo arbitrário respondendo 200, identidade divergente e execução descartável reconhecida. Nos casos recusados, verificar zero chamadas mutáveis, inclusive de limpeza. Preservar o contrato de invocação direta via pytest. Registrar por suíte o destino lógico, a prova, o resultado e o próximo ID. Se o mecanismo depender da criação da stack, manter browser bloqueado até FS-02.03 e testar o caminho positivo integrado nessa atividade.

## Sequência e provas por entrega

| Recorte | Onde trabalhar e qual decisão tomar | Evidência para revisão |
|---|---|---|
| FS-01.01–06 • regressão | Rodar o runner canônico sem browser após o preflight dessa suíte. Comparar node IDs com RUN-08. Para falha de UI, observar ação, estado e resultado que o usuário vê antes de mudar seletor ou expectativa. Isolar o node de TTS e repetir sob condições registradas. | Matriz por node com esperado, observado e decisão. Rodar o node antes/depois e a regressão completa. Classificar skips com motivo e cobertura. Contagem histórica de 23 falhas não é meta de correções. |
| FS-02.02–05 • ambiente browser | Fixar dependências de browser na camada de testes. Criar projeto por execução, obter a porta publicada da própria stack e passá-la para cada fixture. Tratar falha de startup, sinal e KEEP. Destinar relatórios a um diretório gravável específico. | Duas execuções simultâneas: interromper A, verificar B ainda utilizável. KEEP conserva só a execução pedida. Conferir JUnit fora do checkout RO, exit code do pytest e jornada até aprovação. Testar orçamento separadamente com guard ativo e fornecedor falso. |
| FS-04.01–04 • configuração | Partir de `renderer/app/studio/composition/settings.py`, `.env.example`, Compose e `tests/test_compose_env.py`. Conferir STUDIO_RENDER_PLAN_ENABLED, STUDIO_AUTO_RESEARCH, STUDIO_TREND_SOURCES e STUDIO_TOKEN_ENV_PATH até o consumidor. Para token path verificar acessibilidade no container com arquivo fictício. | Tabela ausente/explícito/resultado. Preservar defaults específicos de cada perfil. Reutilizar o teste do uploader com switch zero. Em modo produção demonstrar seleção válida ou erro explícito e, com teto zero, zero chamadas pagas. |
| FS-05.01–02 • saúde | Em `renderer/app/main.py`, /health retorna ffmpeg constante e usa Studio.ping. Em `composition/wiring.py`, ping possui TTL e _check passa por use_cases e SELECT 1. Especificar /live e /ready, preservar consumidores de /health. Evitar disparar migrações ou recuperação numa sondagem repetida. | Resposta rápida de liveness sob falha de DB. Readiness 503 para DB/schema/binário indisponível, 200 após recuperação dentro da janela declarada. Simular timeout e recuperação com relógio controlado. Atualizar o healthcheck Compose correspondente. |
| FS-06.01–04 • capacidade e recuperação | Começar por `tracked_submit` em wiring e `Production._enqueue` em production. Medir tempo na fila e em execução separadamente, com mesmo perfil de render e graus de concorrência registrados. Introduzir limite somente se houver saturação observada. | Falha no submit, reinício e worker antigo chegando após retomada: conferir estado persistido, direito de concluir e contagem de efeitos. Se o efeito externo ficar incerto, reconciliar antes de repetir. Sem medição, registrar limite como indeterminado. |
| FS-07.01–04 • referência | `scripts/render_benchmark.py` gera tom sintético. Usá-lo para comparação técnica. Para a fixture de 60 s usar Piper, FFmpeg, legenda, QA e aprovação. Rastrear leitores de MAX_DURATION_SECONDS antes de propor o perfil de 5–8 min. | Reabrir MP4, inspecionar início/meio/fim, sincronismo, inteligibilidade, relevância visual e duração. Registrar hash, tempos humano/máquina, licenças e custo conhecido por minuto. Piloto real requer os insumos e aprovação previstos em PLAN. |
| FS-08.01–07 • estrutura | Após regressão confiável, mapear consumidores de make_router, Production, Studio, contratos de ports e structure_render_plan. Escolher uma extração quando a próxima mudança funcional tocar a fronteira. Aplicar [STRUCTURAL-EVOLUTION](STRUCTURAL-EVOLUTION.md). | Por recorte: contrato HTTP e guards, identidade dos imports, instância única no wiring, estados e efeitos de produção ou timeline do RenderPlan conforme o módulo. Comparar antes/depois. Separar movimentação mecânica de mudança funcional. |

FS-03 permanece adiado. FS-05/06 e as extrações de FS-08 seguem a prioridade e as dependências de PLAN. A aprovação de um cartão cobre somente seus critérios.

## Comandos de verificação

Na raiz, para identificar a revisão e os pontos de entrada, sem subir serviços:

```bash
git rev-parse HEAD
git status --short
git diff 182ec75e265cdb3b5b932a72d8777b45cbc6092d HEAD -- scripts tests renderer/app docker-compose.yml docker-compose.e2e.yml
rg -n 'STUDIO_(E2E_BASE_URL|BASE_URL|E2E_ISOLATED)|down -v' scripts tests/e2e_full tests/e2e_ux
```

Com Docker disponível e preflight da suíte de banco aprovado, selecionar comandos conforme o cartão:

```bash
scripts/test-container.sh tests/test_architecture.py tests/test_compose_env.py -q
scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -q -rs
```

Os dois comandos cobrem o contrato arquitetural/configuração e a regressão sem browser. Para browser usar os runners do repositório após FS-02.03 com destino comprovado. Para shell alterado usar também `bash -n` nos scripts tocados. Validação sintática por si só deixa o comportamento pendente.

## Prompt para colar no DeepSeek

> Execute somente FS-02.01 nesta rodada. Leia START-HERE.md, este guia, a linha do cartão em EXECUTION-BACKLOG.md e o gate aplicável. Confirme o SHA e inspecione o diff desde a base. Mostre os chamadores e a proteção existente antes de editar. Implemente a menor mudança que cubra os pontos de entrada reais. Reutilize fixtures e funções existentes. Se a proteção já existir, demonstre com teste focado. Preserve o exit code e os padrões públicos dos perfis de uso. Use doubles nos testes negativos e comprove que a recusa acontece antes do primeiro efeito. Mantenha desligados uploads e chamadas pagas. Não execute os runners de browser enquanto a exclusividade estiver pendente. Ao terminar, informe arquivos/símbolos, comportamento observado antes e depois, comandos, exit codes, skips, lacunas e rollback. Indique quais suítes estão liberadas e qual cartão pode começar. Não avance automaticamente.

Para os cartões seguintes, substituir o ID e os cenários focados pelos da tabela. Na revisão, abrir o diff pelo chamador real, procurar estados parciais e repetição de efeitos e conferir se o teste falharia ao reintroduzir o defeito. Registrar uma falha de ambiente como bloqueio e manter a evidência histórica identificada pelo seu próprio SHA.
