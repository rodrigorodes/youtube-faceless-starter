# Aprovação e publicação

**Prefixo dos cenários:** `PUB`

> Arquivo gerado por `gerar.py` a partir de `dados/`. Não editar à mão; altere os dados e gere de novo.

## Como funciona

A aprovação registra a versão revisada e uma intenção. Claim e executor verificam intenção, render, checksum e QA. O executor valida destino e autorização antes do upload; ambiguidade exige reconciliação. Aprovar não equivale a publicar.

## Regras desta funcionalidade

| Regra | O que exige | Fontes | Cenários |
|---|---|---|---|
| `PUB.R01` | Aprovação exige revisão renderizada; gate compara intenção, output, checksum e QA ou override registrado. | `renderer/app/studio/application/publishing.py:42-69`, `renderer/app/studio/application/publication_gate.py:37-60` | [PUB-01](#pub-01), [PUB-02](#pub-02), [PUB-03](#pub-03), [PUB-12](#pub-12) |
| `PUB.R02` | Intenção fixa metadados/destino; private é padrão e public exige confirmação adicional. | `renderer/app/studio/application/publication_gate.py:52-58`, `tests/test_publication_policy.py:55-99`, `tests/test_publication_api.py:94-108` | [PUB-03](#pub-03), [PUB-04](#pub-04), [PUB-05](#pub-05) |
| `PUB.R03` | Claims concorrentes usam locks; retry preserva sessão e UNKNOWN não entra em retry automático. | `renderer/app/studio/adapters/postgres/publish_repo.py:115-178`, `renderer/app/studio/application/publication_execution.py:298-345` | [PUB-07](#pub-07), [PUB-08](#pub-08), [PUB-09](#pub-09), [PUB-12](#pub-12) |
| `PUB.R04` | Rearm só aceita DLQ permanente sem sessão, ID remoto, offset, UNKNOWN ou lease vivo; reconciliação depende de resposta remota. | `renderer/app/studio/adapters/postgres/publish_repo.py:316-330`, `renderer/app/studio/application/publication_execution.py:361-395` | [PUB-09](#pub-09), [PUB-10](#pub-10), [PUB-11](#pub-11) |
| `PUB.R05` | Servidor com repositórios injetados exige destino e token do mesmo canal; flag desabilitada bloqueia antes do claim; agendamento vencido/próximo bloqueia. | `renderer/app/studio/application/publication_execution.py:205-242`, `renderer/app/studio/application/publication_execution.py:250-297` | [PUB-05](#pub-05), [PUB-06](#pub-06) |
| `PUB.R06` | Preview mostra versão revisada; pedir ajustes reabre edição e invalida aprovação anterior. | `tests/test_publish_api.py:215-292`, `tests/e2e_full/test_journey_piloto.py:115-158` | [PUB-01](#pub-01), [PUB-03](#pub-03) |

## Resumo dos cenários

Total: 12 cenário(s), todos documentais nesta elaboração.

| ID | Cenário | Tipo | Regras | Status |
|---|---|---|---|---|
| [PUB-01](#pub-01) | Preview e aprovação da versão exata | feliz | PUB.R01, PUB.R06 | `A_PROJETAR` |
| [PUB-02](#pub-02) | QA falho, override e versão obsoleta | erro/borda | PUB.R01 | `A_PROJETAR` |
| [PUB-03](#pub-03) | Ajuste e mudança posterior invalidam aprovação | regressao | PUB.R01, PUB.R02, PUB.R06 | `A_PROJETAR` |
| [PUB-04](#pub-04) | Visibilidade privada, não listada e pública | feliz/borda | PUB.R02 | `A_PROJETAR` |
| [PUB-05](#pub-05) | Agendamento e janela mínima | borda | PUB.R02, PUB.R05 | `A_PROJETAR` |
| [PUB-06](#pub-06) | Destinos YouTube e contingência desligada | erro/regressao | PUB.R05 | `A_PROJETAR` |
| [PUB-07](#pub-07) | Claim concorrente e lease expirado | concorrencia | PUB.R03 | `A_PROJETAR` |
| [PUB-08](#pub-08) | Retry usa mesma sessão e respeita limite | erro/volume | PUB.R03 | `A_PROJETAR` |
| [PUB-09](#pub-09) | Timeout e sucesso remoto sem gravação local | erro | PUB.R03, PUB.R04 | `A_PROJETAR` |
| [PUB-10](#pub-10) | Reconciliação confirma ou mantém ambiguidade | feliz/erro | PUB.R04 | `A_PROJETAR` |
| [PUB-11](#pub-11) | Rearm somente antes de qualquer envio | borda/concorrencia | PUB.R04 | `A_PROJETAR` |
| [PUB-12](#pub-12) | Duplo clique e rejeição não publicam novamente | regressao | PUB.R01, PUB.R03 | `A_PROJETAR` |

## Cenários

### PUB-01 — Preview e aprovação da versão exata

- **Tipo:** feliz
- **Regras:** PUB.R01, PUB.R06
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Vincular decisão ao artefato realmente revisado.
- **Pré-condições:** Banco descartável; vídeo AWAITING_APPROVAL; render r1 e output o1; QA aprovado.
- **Dados:** Título História de teste; r1/o1 e checksum c1.
- **Passos:**
  1. Abrir preview e conferir mídia e QA.
  2. Aprovar informando o1.
  3. Consultar decisão e intenção persistidas.
- **Esperado:** Estado APPROVED; intenção referencia r1/c1/o1; preview identifica o mesmo artefato; nenhum upload ocorre pela aprovação.
- **Limitações:** Verificação visual exige browser; leitura de teste não demonstra reprodução de mídia.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_publish_api.py:98,215; extensão proposta para comparar preview e intenção.`

### PUB-02 — QA falho, override e versão obsoleta

- **Tipo:** erro/borda
- **Regras:** PUB.R01
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Impedir aprovação silenciosa de QA falho ou artefato antigo.
- **Pré-condições:** Vídeo RENDERED com QA falho; outputs o1 e novo o2.
- **Dados:** override_reason vazio e depois Revisão humana do achado X; output o1 obsoleto.
- **Passos:**
  1. Aprovar o2 sem motivo.
  2. Repetir o2 com motivo explícito.
  3. Tentar aprovação com o1 após novo render.
- **Esperado:** Sem motivo há recusa sem decisão; override válido fica registrado; revisão obsoleta é recusada mesmo com estado de vídeo semelhante.
- **Limitações:** Override não comprova qualidade editorial; critérios humanos precisam ser definidos por achado.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_publish_api.py:59,196; tests/test_publication_execution.py:292-299.`

### PUB-03 — Ajuste e mudança posterior invalidam aprovação

- **Tipo:** regressao
- **Regras:** PUB.R01, PUB.R02, PUB.R06
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Não publicar decisão antiga após edição.
- **Pré-condições:** Vídeo aprovado e ainda não enviado; uploader mock conta chamadas.
- **Dados:** Alterar título de História A para História B; em variante pedir ajustes e trocar cena.
- **Passos:**
  1. Alterar metadado após aprovação e executar publicação.
  2. Reabrir outro vídeo aprovado para ajustes.
  3. Editar cena, regerar e aprovar a nova revisão.
- **Esperado:** Intenção antiga bloqueia upload; reabertura permite edição e exige nova aprovação; nova intenção corresponde ao novo render.
- **Limitações:** Concorrência entre edição e upload é ampliada em PUB-07; não supor cancelamento remoto.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_publication_execution.py:659-682; tests/test_publish_api.py:263-292.`

### PUB-04 — Visibilidade privada, não listada e pública

- **Tipo:** feliz/borda
- **Regras:** PUB.R02
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Preservar escolha explícita sem tornar público por omissão.
- **Pré-condições:** Três vídeos elegíveis; transporte YouTube mockado.
- **Dados:** visibility ausente, unlisted, public; public_confirmed false/true.
- **Passos:**
  1. Aprovar sem visibilidade e com unlisted.
  2. Tentar public sem confirmação.
  3. Confirmar public e inspecionar corpos de upload.
- **Esperado:** Omissão gera private; unlisted é preservado; public sem confirmação retorna 422 sem decisão; confirmação válida gera corpo public.
- **Limitações:** Corpo mockado não prova visibilidade aplicada pelo YouTube; live futuro só em conta teste autorizada.
- **Automação:** camada `mock`; referência `Existentes: tests/test_publication_api.py:94-108; tests/test_publication_execution.py:307.`

### PUB-05 — Agendamento e janela mínima

- **Tipo:** borda
- **Regras:** PUB.R02, PUB.R05
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Evitar envio com janela vencida ou próxima demais.
- **Pré-condições:** Relógio fixo com timezone; uploader mock; intenção válida.
- **Dados:** Agora 12:00 UTC; horários 11:59, 12:14:59, 12:15:00 e 13:00.
- **Passos:**
  1. Avaliar fronteira da política para cada horário.
  2. Executar publicação agendada elegível.
  3. Inspecionar privacyStatus e publishAt.
- **Esperado:** Vencido e abaixo da antecedência de 15 minutos bloqueiam; fronteira segue contrato da política; envio agendado usa private com publishAt correto, sem deslocamento de timezone.
- **Limitações:** Processamento remoto não garante disponibilidade no horário; a fronteira exata deve ser afirmada pelo teste de domínio.
- **Automação:** camada `mock`; referência `Existentes: tests/test_publication_policy.py:130-150; tests/test_publication_execution.py:313-322.`

### PUB-06 — Destinos YouTube e contingência desligada

- **Tipo:** erro/regressao
- **Regras:** PUB.R05
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Falhar fechado para destino ausente ou autorização incompatível.
- **Pré-condições:** Executor com repositórios de canal/autorizações injetados, como servidor.
- **Dados:** Destino UC_TEST_A; token UC_TEST_B; variantes sem destino, grant revogado e enabled=false.
- **Passos:**
  1. Executar cada variante e contar claims/uploads.
  2. Corrigir token para UC_TEST_A e grant conectado.
  3. Executar controle positivo.
- **Esperado:** Incompatibilidades bloqueiam antes do upload; desabilitado nem reivindica; controle válido pode enviar ao mock; não há fallback cruzado para outro canal.
- **Limitações:** Construção legada sem repositórios dispensa gate e não representa a garantia do servidor.
- **Automação:** camada `mock`; referência `Existentes: tests/test_publication_execution.py:397-471,620-636.`

### PUB-07 — Claim concorrente e lease expirado

- **Tipo:** concorrencia
- **Regras:** PUB.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Uma tentativa dona do efeito e recuperação conservadora.
- **Pré-condições:** Postgres descartável; dois workers sincronizados por barreira; upload mock bloqueável.
- **Dados:** Uma publicação pendente; attempt 1; lease vivo e depois expirado.
- **Passos:**
  1. Disparar dois claims simultâneos.
  2. Tentar gravar sessão com tentativa antiga.
  3. Simular expiração durante envio e duas recuperações concorrentes.
- **Esperado:** Um vencedor por claim e CAS de recuperação; tentativa antiga não grava sessão; lease expirado em envio vira UNKNOWN, sem segundo upload automático.
- **Limitações:** Não prova exatamente uma entrega remota; timeout local não é rollback do YouTube.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_publication_resilience_repo.py:152-186,221-244.`

### PUB-08 — Retry usa mesma sessão e respeita limite

- **Tipo:** erro/volume
- **Regras:** PUB.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Retomar envio sem abrir uploads duplicados.
- **Pré-condições:** Relógio controlado; uploader retorna sessão incompleta; política de tentativas conhecida.
- **Dados:** Sessão https://upload.example.test/session/1; offset 4096; falhas transitórias até max_attempts.
- **Passos:**
  1. Responder INCOMPLETE com sessão e offset.
  2. Avançar relógio até retry devido.
  3. Repetir falhas até limite e tentar claim adicional.
- **Esperado:** Sessão persistida é reutilizada; backoff impede antecipação; ao limite há DLQ e nenhum novo claim elegível; resultado confirmado não reenvia.
- **Limitações:** Offset e retomada efetiva precisam de teste do adaptador, não apenas do executor.
- **Automação:** camada `mock`; referência `Existentes: tests/test_publication_execution.py:331-354,519-550; tests/test_publication_resilience_repo.py:135.`

### PUB-09 — Timeout e sucesso remoto sem gravação local

- **Tipo:** erro
- **Regras:** PUB.R03, PUB.R04
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Não converter resposta desconhecida em sucesso ou retry cego.
- **Pré-condições:** Uploader e repositório mockáveis; publicação sem ID confirmado.
- **Dados:** TimeoutError; sucesso sem ID; sucesso com ID e falha de mark_uploaded.
- **Passos:**
  1. Injetar cada falha separadamente.
  2. Consultar estado persistido.
  3. Tentar nova execução automática.
- **Esperado:** RECONCILE/UNKNOWN ou DLQ ambígua conforme limite; nenhum sucesso inventado e nenhum reenvio automático; erro não expõe token ou sessão na API.
- **Limitações:** Desconhecido não prova falha do upload; captura de sessão pelo adaptador tem cobertura própria.
- **Automação:** camada `mock`; referência `Existentes: tests/test_publication_execution.py:564-590; tests/test_publication_api.py:111-124.`

### PUB-10 — Reconciliação confirma ou mantém ambiguidade

- **Tipo:** feliz/erro
- **Regras:** PUB.R04
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Resolver efeito remoto apenas com resposta verificável.
- **Pré-condições:** Publicação UNKNOWN com sessão; porta reconcile mockada.
- **Dados:** Resultados UPLOADED com ID, INCOMPLETE e AMBIGUOUS em fixtures separadas.
- **Passos:**
  1. Reconciliar cada fixture.
  2. Consultar publicação.
  3. Reconciliar novamente a já confirmada.
- **Esperado:** ID confirmado é persistido; sessão comprovadamente incompleta libera retry; ambígua continua exigindo revisão; reconciliar não chama upload e ID já salvo torna repetição inócua.
- **Limitações:** Comportamento com destino alterado durante reconciliação merece investigação adicional; não assumir o gate completo do upload.
- **Automação:** camada `mock`; referência `Existentes: tests/test_publication_execution.py:485-509,607.`

### PUB-11 — Rearm somente antes de qualquer envio

- **Tipo:** borda/concorrencia
- **Regras:** PUB.R04
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Reenfileirar bloqueio seguro sem apagar ambiguidade.
- **Pré-condições:** DLQ permanente; banco descartável; estado consultável.
- **Dados:** Caso base sem sessão/ID/offset/lease; variantes offset=1, UNKNOWN, lease vivo ou sessão existente.
- **Passos:**
  1. Solicitar rearm para todas as variantes.
  2. Concorrer duas chamadas para o caso seguro.
  3. Consultar attempt_base e estado.
- **Esperado:** Somente caso seguro volta a PENDING; atualização atômica admite um vencedor; casos inseguros recusam; attempt_base assume tentativa atual sem apagar histórico.
- **Limitações:** Concorrência do rearm é ampliação proposta; teste existente de serviço não prova atomicidade do SQL.
- **Automação:** camada `local-integrado`; referência `Existente: tests/test_publication_rearm.py:34-46; proposta de concorrência sobre adapters/postgres/publish_repo.py:316-330.`

### PUB-12 — Duplo clique e rejeição não publicam novamente

- **Tipo:** regressao
- **Regras:** PUB.R01, PUB.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Manter resultado verdadeiro diante de repetição humana.
- **Pré-condições:** API local com uploader mock; um vídeo aprovado e outro rejeitável.
- **Dados:** Dois POSTs publish para mesmo vídeo; rejeição com motivo Revisar conteúdo.
- **Passos:**
  1. Enviar os dois POSTs e consultar ID persistido.
  2. Repetir depois de confirmado.
  3. Rejeitar segundo vídeo e tentar publicar.
- **Esperado:** Um efeito de upload; demais respostas não alegam novo envio; ID confirmado permanece; rejeitado não é elegível e não ganha intenção de aprovação.
- **Limitações:** Proteção visual de clique não substitui idempotência backend; navegador é coberto em UX-05.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_publication_execution.py:519-529; tests/test_publish_api.py:187-208.`

## Resumo do capítulo

Plano documental; todos os cenários estão A_PROJETAR. Testes citados existem, mas não foram executados. Execução direta, sem runtime de workflow.
