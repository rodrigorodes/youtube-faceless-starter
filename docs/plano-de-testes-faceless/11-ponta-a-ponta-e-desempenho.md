# Ponta a ponta e desempenho

**Prefixo dos cenários:** `E2E`

> Arquivo gerado por `gerar.py` a partir de `dados/`. Não editar à mão; altere os dados e gere de novo.

## Como funciona

Jornadas existentes atravessam UI e conferem estado pela API. Início distingue piloto de diretor; piloto produz até aprovação; diretor edita antes de produzir. Stack E2E usa texto demo, imagem placeholder, Piper e FFmpeg locais e termina pendente de publicar.

## Regras desta funcionalidade

| Regra | O que exige | Fontes | Cenários |
|---|---|---|---|
| `E2E.R01` | Início piloto cria e inicia produção; diretor cria storyboard sem iniciar produção. | `tests/e2e_full/test_journey_inicio.py:26-57` | [E2E-01](#e2e-01), [E2E-03](#e2e-03) |
| `E2E.R02` | Piloto percorre produção, QA, aprovação e ajustes; diretor preserva edição, citações, ordem e desfazer antes da produção. | `tests/e2e_full/test_journey_piloto.py:88-158`, `tests/e2e_full/test_journey_diretor.py:29-92` | [E2E-02](#e2e-02), [E2E-03](#e2e-03), [E2E-04](#e2e-04), [E2E-06](#e2e-06) |
| `E2E.R03` | Suite completa requer flag de isolamento, recusa porta 8000 e coleta erros JS/5xx; não publica no YouTube. | `tests/e2e_full/conftest.py:1-8`, `tests/e2e_full/conftest.py:36-50`, `tests/e2e_full/conftest.py:66-78` | [E2E-01](#e2e-01), [E2E-02](#e2e-02), [E2E-05](#e2e-05), [E2E-06](#e2e-06), [E2E-07](#e2e-07), [E2E-08](#e2e-08) |
| `E2E.R04` | Coordenador tem testes de idempotência, pausa, falha, cancelamento e lease; jornada integrada deve preservar essas transições. | `tests/test_production_coordinator.py:133-198`, `tests/test_production_coordinator.py:258-331`, `renderer/app/studio/application/observability.py:101-128` | [E2E-04](#e2e-04), [E2E-05](#e2e-05), [E2E-06](#e2e-06), [E2E-08](#e2e-08) |
| `E2E.R05` | Medir cenários pequenos repetíveis antes de volume: Short local e long de 180 s/12 cenas; calibrar por hardware e comparar baseline equivalente. | `tests/e2e_full/test_journey_piloto.py:19`, `tests/test_pilot_video_e2e.py:68-113`, `tests/test_longform_480s.py:1-24` | [E2E-07](#e2e-07), [E2E-08](#e2e-08) |

## Resumo dos cenários

Total: 8 cenário(s), todos documentais nesta elaboração.

| ID | Cenário | Tipo | Regras | Status |
|---|---|---|---|---|
| [E2E-01](#e2e-01) | Início escolhe corretamente piloto ou diretor | feliz/regressao | E2E.R01, E2E.R03 | `A_PROJETAR` |
| [E2E-02](#e2e-02) | Piloto até aprovação e ciclo de ajustes | feliz/regressao | E2E.R02, E2E.R03 | `A_PROJETAR` |
| [E2E-03](#e2e-03) | Diretor edita, desfaz e só então produz | feliz/borda | E2E.R01, E2E.R02 | `A_PROJETAR` |
| [E2E-04](#e2e-04) | Fato sem lastro, falha e retomada controlada | erro/regressao | E2E.R02, E2E.R04 | `A_PROJETAR` |
| [E2E-05](#e2e-05) | Início repetido, lease e cancelamento | concorrencia/erro | E2E.R04, E2E.R03 | `A_PROJETAR` |
| [E2E-06](#e2e-06) | Publicação e aprendizado em circuito mockado | feliz/erro | E2E.R02, E2E.R03, E2E.R04 | `A_PROJETAR` |
| [E2E-07](#e2e-07) | Baseline de Short e long local | volume/desempenho | E2E.R05, E2E.R03 | `A_PROJETAR` |
| [E2E-08](#e2e-08) | Volume moderado sem bloquear navegação | volume/concorrencia | E2E.R05, E2E.R04, E2E.R03 | `A_PROJETAR` |

## Cenários

### E2E-01 — Início escolhe corretamente piloto ou diretor

- **Tipo:** feliz/regressao
- **Regras:** E2E.R01, E2E.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Preservar semântica das duas ações iniciais.
- **Pré-condições:** Stack isolada sem pesquisa automática; canal sintético; coletor de requests ativo.
- **Dados:** Tema A queda de Constantinopla; um vídeo por modo.
- **Passos:**
  1. No início selecionar piloto e gerar vídeo completo.
  2. Repetir em diretor com Abrir storyboard.
  3. Conferir production_mode e requests de production-runs.
- **Esperado:** Piloto inicia produção com resposta 202 e abre cenas; diretor abre cenas sem POST de produção; alternar modo restaura rótulos corretos; nenhum upload externo.
- **Limitações:** Com pesquisa desligada e sem fonte, piloto pode parar no primeiro passo; não chamar isso de render concluído.
- **Automação:** camada `browser`; referência `Existente: tests/e2e_full/test_journey_inicio.py:26-57.`

### E2E-02 — Piloto até aprovação e ciclo de ajustes

- **Tipo:** feliz/regressao
- **Regras:** E2E.R02, E2E.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Conectar criação, artefato, QA e invalidação de aprovação.
- **Pré-condições:** Stack isolada com Piper/FFmpeg locais e roteiro/fonte de fixture; sem destino YouTube.
- **Dados:** Short de Constantinopla com pelo menos três cenas; edição para fato já presente na fonte.
- **Passos:**
  1. Criar canal e vídeo piloto com roteiro colado.
  2. Continuar execução até QA e revisar preview.
  3. Aprovar, pedir ajustes, editar/reordenar, regerar e aprovar de novo.
- **Esperado:** Render SUCCEEDED e QA correspondente; aprovado permanece pendente sem publicação; ajustes retornam SCRIPTED, persistem após reload e exigem revisão nova; nenhum erro JS inesperado.
- **Limitações:** Provider demo/placeholder não comprova qualidade de produção com modelos pagos; tempo humano excluído da medição.
- **Automação:** camada `browser`; referência `Existente: tests/e2e_full/test_journey_piloto.py:88-158.`

### E2E-03 — Diretor edita, desfaz e só então produz

- **Tipo:** feliz/borda
- **Regras:** E2E.R01, E2E.R02
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Garantir controle editorial e persistência coerente.
- **Pré-condições:** Vídeo diretor com roteiro lastreado; execução ainda não iniciada.
- **Dados:** Incluir uma cena, excluir a criada, editar fato sobre Mehmed II, mover e desfazer.
- **Passos:**
  1. Editar storyboard e conferir cenas pela API.
  2. Recarregar para conferir persistência; mover/desfazer sem reload entre essas duas ações.
  3. Confirmar geração, continuar, revisar QA e aprovar.
- **Esperado:** Mudanças sobrevivem reload; citação acompanha texto alterado; demais citações preservadas; desfazer restaura ordem na API; produção começa somente após ação explícita; termina aprovado pendente.
- **Limitações:** Desfazer atual é histórico da sessão da página, não promessa após reload.
- **Automação:** camada `browser`; referência `Existente: tests/e2e_full/test_journey_diretor.py:29-92.`

### E2E-04 — Fato sem lastro, falha e retomada controlada

- **Tipo:** erro/regressao
- **Regras:** E2E.R02, E2E.R04
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Não propagar conteúdo recusado nem repetir etapas concluídas indevidamente.
- **Pré-condições:** Vídeo com fontes; fake de etapa que falha uma vez; snapshot de configuração persistido.
- **Dados:** Texto O cerco durou 987654 dias; falha transitória de imagem antes do render.
- **Passos:**
  1. Tentar salvar texto sem lastro e recarregar.
  2. Produzir texto válido com falha injetada.
  3. Repetir etapa pelo comando apropriado e comparar artefatos/configuração.
- **Esperado:** Texto recusado não persiste; erro fica visível; retry mantém snapshot e retoma etapa permitida; nenhuma aprovação/publicação automática; não mascarar recusa conhecida como sucesso.
- **Limitações:** Jornada atual aceita 409/422/502 para recusa editorial; o plano não inventa um status único. Reuso de artefato depende do hash e contrato da etapa.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/e2e_full/test_journey_piloto.py:140-148; tests/test_production_coordinator.py:274,564-580; integração proposta.`

### E2E-05 — Início repetido, lease e cancelamento

- **Tipo:** concorrencia/erro
- **Regras:** E2E.R04, E2E.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Evitar duas execuções efetivas do mesmo pedido e conclusão por dono obsoleto.
- **Pré-condições:** Dois clientes locais; barreiras determinísticas; relógio/worker controlados.
- **Dados:** Mesma chave idempotente em dois starts; lease expirado; cancelamento durante etapa mock bloqueada.
- **Passos:**
  1. Enviar starts concorrentes com mesma configuração.
  2. Simular worker antigo e recuperação após expiração.
  3. Cancelar variante independente e liberar resposta tardia.
- **Esperado:** Desejado na jornada: mesmo run para replay; fence impede conclusão de dono antigo; cancelamento mantém estado terminal e não aciona próxima etapa; efeitos externos ambíguos não são assumidos revertidos.
- **Limitações:** Cancelamento de processo/FFmpeg real merece verificação separada; teste de coordenador não comprova interrupção física imediata.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_production_coordinator.py:133,198,290,331,521-534; concorrência de jornada proposta.`

### E2E-06 — Publicação e aprendizado em circuito mockado

- **Tipo:** feliz/erro
- **Regras:** E2E.R02, E2E.R03, E2E.R04
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Validar integração após aprovação sem tocar no YouTube.
- **Pré-condições:** Jornada concluída com intenção privada; canal/token sintéticos coerentes; portas de upload/analytics fake.
- **Dados:** ID remoto de fixture com 11 caracteres; views=100.0; variante upload ambíguo.
- **Passos:**
  1. Executar publicação local com fake confirmando ID.
  2. Coletar métricas e abrir desempenho.
  3. Repetir coleta; em outro vídeo simular ambiguidade e tentar coleta.
- **Esperado:** Confirmado chega a PUBLISHED e medidas referenciam publicação/versão; retry não duplica observação; ambíguo não ganha ID fictício nem métricas autorizadas sem publicação confirmada.
- **Limitações:** Extensão proposta: suite E2E atual termina antes de publicar. Nenhuma validação de quota, OAuth real ou distribuição pública.
- **Automação:** camada `local-integrado`; referência `Bases: tests/test_publication_execution.py:266,363; tests/test_analytics_collection.py:133,205; circuito integrado proposto.`

### E2E-07 — Baseline de Short e long local

- **Tipo:** volume/desempenho
- **Regras:** E2E.R05, E2E.R03
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Medir custo temporal e recursos sem confundir timeout com SLA.
- **Pré-condições:** Máquina dedicada descrita por CPU/RAM; versões fixas; Postgres/arquivos descartáveis; sem concorrência externa.
- **Dados:** Short de seis cenas e long 180 s/12 cenas/1920x1080; uma execução fria e três aquecidas por perfil.
- **Passos:**
  1. Medir geração, render e QA separadamente excluindo espera humana.
  2. Registrar wall-clock, CPU, pico RSS e bytes por execução.
  3. Comparar artefatos e tempos com baseline do mesmo hardware.
- **Esperado:** Saídas mantêm duração/resolução/QA; propostas iniciais de triagem: Short até 150 s de processamento, long até 900 s; degradação mediana acima de 25% pede investigação, não flexibilização automática do QA.
- **Limitações:** 150 s é timeout de teste existente, não garantia do produto; 900 s e 25% são propostas a calibrar. Três amostras não sustentam p95 confiável; áudio sintético não prova qualidade de locução.
- **Automação:** camada `local-integrado`; referência `Bases: tests/e2e_full/test_journey_piloto.py:19,50-58; tests/test_pilot_video_e2e.py:51-68,112-113; instrumentação proposta.`

### E2E-08 — Volume moderado sem bloquear navegação

- **Tipo:** volume/concorrencia
- **Regras:** E2E.R05, E2E.R04, E2E.R03
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Detectar contenção, crescimento de recursos e duplicação sob carga local realista.
- **Pré-condições:** Baseline E2E-07 disponível; limite de dois renders simultâneos no ensaio; 100 vídeos sintéticos, sem rede.
- **Dados:** Fila de dez Shorts; dois workers; 30 leituras de lista/detalhe durante processamento após cinco aquecimentos.
- **Passos:**
  1. Submeter fila com chaves únicas e uma repetida.
  2. Navegar/listar enquanto dois renders trabalham.
  3. Comparar p50/p95 das leituras, memória, fila final e IDs de saída.
- **Esperado:** Desejado: nenhuma duplicação ou perda; fila termina ou aponta falhas recuperáveis; proposta p95 das leituras até 2 s; após esvaziar, memória estabiliza sem crescimento monotônico a cada vídeo.
- **Limitações:** Dois workers é perfil do ensaio, não capacidade garantida; medir tempo em fila separado do render; limites precisam de calibração por hardware e não valem como SLA.
- **Automação:** camada `local-integrado`; referência `Proposto; base funcional tests/test_production_coordinator.py:133-198 e tests/e2e_full/conftest.py:66-97.`

## Resumo do capítulo

Oito cenários A_PROJETAR. Nenhum teste, serviço, publicação ou benchmark foi executado; execução documental direta sem workflow.
