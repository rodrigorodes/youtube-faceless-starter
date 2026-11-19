# Faceless Studio — desenho e roteiro das 8 fases (P00–P07)

Data: 2026-11-19 · Status: **proposta para revisão** (nada foi construído a partir deste documento).

## 1. Intenção

Transformar o starter atual (n8n + renderer FastAPI/FFmpeg) em uma linha de produção local e recuperável de vídeos para YouTube, do tema até a métrica: **tema → roteiro verificado → mídia rastreável → vídeo com áudio e legenda → aprovação humana → upload → analytics → novos temas**.

Por que agora: o starter já publica um Short de verdade (modo `rich`, 13 cenas, `oNQ2KN37sfQ`), mas cada etapa é um passo solto num único endpoint síncrono, sem estado, sem custo medido e sem retomada. Uma falha na cena 12 refaz tudo; reenviar o pedido cria outro vídeo.

## 2. Objetivos, não-objetivos e anti-objetivos

**Objetivos**
- Entidades e estados explícitos, persistidos, com contratos JSON versionados.
- Cada etapa idempotente e retomável; assets reaproveitados por hash.
- Aprovação humana obrigatória antes de qualquer publicação; upload sempre `private` até o humano mudar.
- Custo e tokens medidos por etapa (entrada, saída e cache **separados**), com teto duro.
- Rodar igual no Lenovo e neste Mac.

**Não-objetivos**
- Monetização, receita e relatórios monetários (não pedimos esse escopo OAuth).
- Multi-canal/multi-usuário, painel web sofisticado, fila distribuída.
- Edição manual de vídeo, legendas traduzidas, upload de legendas (`captions.insert` exigiria escopo mais amplo).

**Anti-objetivos (falha mesmo que "funcione")**
- Publicar sem aprovação humana, ou duas vezes o mesmo vídeo.
- Afirmar fato que não está numa fonte guardada.
- Gastar dinheiro sem teto explícito (modelo de imagem/vídeo pago ligado por engano).
- Usar mídia ou música com direito de terceiros, ou esconder que é conteúdo sintético.
- Expandir o escopo OAuth do upload para acomodar analytics.

## 3. Restrições herdadas (valem para todas as fases)

- Conta e canal pessoais; `privacy=private` por padrão; `selfDeclaredMadeForKids=false`; `containsSyntheticMedia=true`; idioma pt-BR.
- Fatos só de fontes oficiais, guardadas como snapshot. Evento encerrado → texto no passado.
- Só modelos `:free` por padrão (o bridge recusa o resto); voz Piper CC0; trilha sintetizada por código.
- Não usar o projeto GCP corporativo `cerc2-book-stg-01`.
- `git push`, merge de PR e remoção via GitHub são bloqueados para o agente; o humano publica o código.
- Documentação para macOS e Windows.

## 4. Onde estamos × as 8 fases

| Fase | Já existe | Falta |
|---|---|---|
| P00 contratos | Modelos Pydantic soltos (`VideoRequest`, `Scene`) e manifest JSON | Entidades persistidas, estados, schemas versionados, política de orçamento/aprovação |
| P01 infra | Compose (n8n, Postgres, renderer), `.env`, docs macOS/Windows, credencial OAuth | Banco de domínio e migrações, layout de storage, `doctor`, backup, **validação real no Lenovo** (Windows nunca foi executado) |
| P02 editorial | Storyboard por IA a partir de `context` manual; metadados | Ingestão de fontes com snapshot, ideias com nota, checagem factual determinística |
| P03 mídia | Imagens por IA (bridge `/image`, `:free`), placeholder | Cache por hash, provedores plugáveis (stock, Veo opcional), licença/custo por asset |
| P04 render | Piper, trilha, Ken Burns, selo, legenda por cena, mixagem | Legenda sincronizada por trecho, formato longo, QA automático, render assíncrono |
| P05 publicação | Upload resumable privado via HTTP Request | Prévia e aprovação, thumbnail, agendamento, idempotência e registro do ID |
| P06 observabilidade | Erros 502 com `stage` | Logs estruturados, execução por etapa, retries, ledger de custo, retomada |
| P07 analytics | — | Credencial separada, coleta diária, relatório, sugestões de tema |

## 5. Decisões de arquitetura (minhas — marcadas como chamadas, para você revisar)

1. **Dono único do estado.** O serviço `renderer` (renomeado conceitualmente "studio API", mesmo container) é o único que escreve no banco de domínio. O n8n só orquestra por HTTP. Evita dois escritores e corrida entre eles.
2. **Mesmo Postgres, schema `studio`.** O volume do Postgres já existe, então um `CREATE DATABASE` por script de init não rodaria. Schema separado dentro do banco atual, com migrações SQL numeradas (`psycopg` 3, sem ORM). Um `pg_dump` cobre n8n e domínio.
3. **Contratos = Pydantic v2 → JSON Schema versionado** em `contracts/v1/`, com teste de snapshot que falha em mudança não declarada. Todo JSON persistido leva `schema_version`.
4. **Máquina de estados com atualização condicional** (`UPDATE … WHERE status = :esperado`): verificar e agir numa operação só; quem perde a corrida recebe 409 em vez de esperar.
5. **Aprovação por API + página estática** servida pelo renderer (`<video>`, relatório de QA, roteiro, fontes, botões). O n8n **consulta periodicamente** (`status=APPROVED` sem publicação) em vez de ficar com execução parada em `Wait`: sobrevive a reinício.
6. **Publicação idempotente**: `publications.video_id` UNIQUE; o `upload_uri` do upload resumable fica gravado, e retry retoma em vez de recriar.
7. **Pesquisa de temas v1 sem API paga**: lista de URLs/RSS permitidas + semente manual. Busca web por API entra só se você fornecer chave.
8. **Veo desligado por padrão**: exige teto de custo > 0, estimativa antes da chamada e projeto GCP pessoal.
9. **Lenovo = Windows 11 + Docker Desktop (WSL2), suposição minha.** Se for Linux, o plano só fica mais simples. Confirmar na P01.

Decisões adicionais, resolvidas na revisão independente do documento:

10. **Papel do banco.** O renderer usa o mesmo usuário e banco do n8n, com schema `studio`. Um papel separado não pode ser criado por script de init num volume que já existe, e o ganho de isolamento não compensa para uso pessoal. A regra "só o renderer escreve em `studio`" é de convenção, não de permissão. Risco aceito e registrado.
11. **Convivência com o que existe.** `/studio/*` roda ao lado de `/videos/*`. Os endpoints antigos, o workflow V2 e os 48 testes atuais ficam **inalterados**. Os diretórios `storage/jobs` e `storage/output` não são importados para o layout novo; o `PT7Yfify8hU` e o `oNQ2KN37sfQ` continuam como estão. A migração do fluxo V2 para o `/studio` acontece na P05, com o V2 mantido até lá.
12. **Caminho de LLM.** O bridge do OpenCode é o único caminho de texto previsto. Gemini e Vertex continuam no código como opção, mas fora do plano e nunca com o projeto corporativo. A revisão por LLM na P02 é **só consultiva**; o gate real é a checagem determinística.
13. **Rigor da checagem factual.** Reprovação bloqueia `AWAITING_APPROVAL`. O humano pode liberar com um *override* explícito, registrando o motivo. O casamento normaliza maiúsculas, acentos e formatos numéricos (`1.500`, `1,5 mil`) e converte número por extenso em pt-BR de 0 a 100 ("três" = 3). Valores derivados, como "três dias", precisam citar os dois números da fonte ou passam por override.
14. **Credenciais e analytics.** A coleta da P07 roda **no n8n**, com credencial própria no mesmo projeto Google, e entrega os números ao renderer por `POST /studio/metrics`. Os tokens ficam só no n8n. O renderer nunca guarda segredo do YouTube. O estado atual do app é *Testing* (token de 7 dias); a verificação do canal para miniaturas fica para a P05.
15. **Lenovo e paralelismo.** A Task 11 da P01 é um ponto de controle **executado por você**. Ela bloqueia o fechamento da P01 e a P05, mas não bloqueia o código da P02 e da P03, que só dependem dos contratos e da persistência (Tasks 1–8).

## 6. Entidades

`Project` (nicho, idioma, estilo padrão, orçamento mensal) · `Video` (tema, formato `short|long`, estado, título, descrição, tags, privacidade, `qa_report`) · `Script` (versão, texto, `claim_ids`) · `Scene` (índice, narração, legenda, rótulo, `image_prompt`, `asset_id`, duração) · `Asset` (tipo, `cache_key`, caminho, provedor, modelo, **licença**, custo) · `RenderJob` (tentativa, estado, hash de entrada, saída) · `Publication` (`youtube_video_id`, `upload_uri`, agendamento, miniatura aplicada) · apoio: `SourceSnapshot`, `StepRun`, `UsageLedger`, `VideoMetric`.

Estados do `Video`: `IDEA → SCRIPTED → FACT_CHECKED → STORYBOARDED → ASSETS_READY → RENDERED → AWAITING_APPROVAL → APPROVED → PUBLISHED`; laterais `REJECTED` e `FAILED` (com a etapa que falhou; retomável).

## 7. Orçamento e custo

- **Operação do pipeline:** hoje US$ 0 (modelos `:free`, Piper, trilha local). Teto por vídeo `MAX_COST_USD_PER_VIDEO` (padrão **0**) e mensal por projeto; qualquer provedor com custo > 0 é recusado antes da chamada se estourar.
- **Tokens:** `UsageLedger` guarda `input`, `output`, `cache_read`, `cache_write` em colunas separadas. A API de texto do OpenCode só devolve `input`/`output`, e só quando o provider reporta; cache e ausências ficam `NULL` e o relatório marca o valor como estimado, nunca como medido.
- **Custo de construir** (agentes de código reenviam arquivos, histórico e saída de testes): tarefas pequenas com contexto curto, um plano por fase, e o mesmo controle de entrada/saída/cache separados ao reportar o consumo das sessões.

## 8. Critérios de aprovação automáticos (`qa_report`, P00/P04)

Bloqueiam o estado `AWAITING_APPROVAL` se falharem: duração dentro do formato (Short ≤ 175 s); resolução correta; loudness −16 LUFS ± 1,5; sem silêncio ou quadro preto longos; aviso de IA presente no vídeo e na descrição; todo número/data da narração presente na fonte citada; fontes listadas; nenhum asset pago sem teto liberado. A decisão final continua humana.

## 9. Roteiro por fase

Esforço: S ≈ meio dia, M ≈ 1–2 dias, L ≈ 3–5 dias de trabalho com agente. Cada fase ganha **seu próprio plano** antes de começar, escrito contra os contratos reais das anteriores.

### P00 — Arquitetura e contratos (M)
Entrega: `contracts/v1/*.schema.json`, enums de estado e tabela de transições, `policy.py` (orçamento e QA), diagramas Mermaid em `docs/`.
Pronto quando: snapshot de schema passa; transições inválidas são rejeitadas por teste; política recusa asset pago com teto 0.
**Plano detalhado:** `docs/superpowers/plans/2026-11-19-p00-p01-contracts-and-persistence.md`.

### P01 — Workspace e infraestrutura (M)
Entrega: migrações SQL e runner idempotente; layout `storage/projects/<p>/videos/<v>/…` e `storage/cache/<sha>`; `scripts/doctor.py` (ambiente, portas, ffmpeg, voz, escopo da credencial); `scripts/backup.py` (`pg_dump` + manifesto); healthchecks; **execução real no Lenovo**.
Pronto quando: clone limpo no Lenovo → `docker compose up` + `doctor` verde + vídeo de teste com `IMAGE_PROVIDER=placeholder`; restore do backup testado.
**Plano detalhado:** mesmo arquivo da P00.

### P02 — Discovery e geração editorial (L)
Entrega: `ingest_source(url) → SourceSnapshot` (texto + hash + data, lista de domínios permitidos); `score_ideas` com rubrica em JSON; `generate_script` restrito a *claims* extraídas do snapshot; `fact_check` em duas camadas — **determinística** (todo número, data e nome próprio da narração tem que aparecer no texto da fonte citada) e revisão por LLM; título e descrição com aviso de IA e fontes.
Pronto quando: roteiro com um número inventado é reprovado por teste; roteiro correto passa; cada cena aponta `claim_ids`.
Risco: sites que bloqueiam raspagem → fallback para texto colado pelo humano.

### P03 — Storyboard e produção de mídia (L)
Entrega: `AssetProvider` (protocolo) com `opencode_free`, `placeholder`, `stock` (Pexels/Pixabay: chave, licença e atribuição gravadas) e `veo` (off por padrão); `cache_key = sha256(tipo|provedor|modelo|prompt|parâmetros)`; cada `Scene` aponta para o `Asset`.
Pronto quando: segundo render do mesmo vídeo gera 0 imagens novas; asset sem licença registrada é recusado; Veo recusado com teto 0.
Risco: preço e limites do Veo mudam — conferir a documentação na hora de implementar, não agora.

### P04 — Narração e renderização (L)
Entrega: legendas por trecho (tempo proporcional ao texto dentro da duração da fala; sem alinhamento forçado por modelo, para não somar dependência pesada); `.srt` exportado; templates `short` (1080×1920) e `long` (1920×1080); `qa_report` com `ebur128`, `silencedetect`, `blackdetect`; **render assíncrono** (`POST /videos/{id}/render` → 202 + consulta), porque vídeo longo estoura o timeout síncrono atual de 900 s; `RENDER_CONCURRENCY=1` para não saturar o Lenovo.
Pronto quando: MP4 curto e longo com áudio e legenda; QA reprova vídeo mudo e vídeo estourado em duração.

### P05 — Aprovação e publicação (L)
Entrega: página de prévia/aprovação; `POST /videos/{id}/approve|reject` com transição atômica; workflow n8n que busca `APPROVED` sem `Publication`; upload resumable com `upload_uri` persistido; `publishAt` para agendar (o vídeo sobe `private` e o YouTube publica na hora); miniatura via `thumbnails.set` com espera e retry, pois o Short precisa terminar de processar e **ler esse status exigiria `youtube.readonly`**, que não vamos adicionar.
Verificar na implementação (não assumido): miniatura personalizada exige canal verificado; app OAuth em produção deixa de expirar o token em 7 dias.
Pronto quando: aprovar duas vezes publica uma só; matar o n8n no meio do upload e reiniciar retoma sem duplicar; ID registrado em `publications`.
Observação: puxei a idempotência da publicação para cá (o roteiro original deixava para a P06), porque publicar sem ela é o risco mais caro.

### P06 — Observabilidade e recuperação (M)
Entrega: logs JSON com `video_id`, `step`, `attempt`; `step_runs` com hash de entrada; `run_step()` que pula etapa já bem-sucedida com a mesma entrada; retry com backoff e jitter **só** para 429/5xx/timeout (nunca para 4xx); `POST /videos/{id}/resume` a partir da primeira etapa não concluída; checagem de teto de custo antes de cada chamada paga; alerta de bridge fora do ar e de token OAuth perto de expirar.
Pronto quando: derrubar o renderer no meio do render e retomar reaproveita 100% dos assets e refaz só o que faltou; 4xx não gera retry.
Atenção: ACK de envio não prova sucesso. Upload só conta como concluído quando a resposta final traz o ID.

### P07 — Analytics e otimização (M)
Entrega: **segunda credencial** com `yt-analytics.readonly` + `youtube.readonly` (a página de `reports.query` informa que ambos são exigidos), separada da de upload; coleta diária idempotente em `video_metrics(video_id, date, …)` (upsert); relatório semanal gerado a partir de agregados, não de linhas brutas; sugestões de tema que citam as linhas de métrica usadas e realimentam a P02.
Pronto quando: relatório com dados reais de ≥ 1 vídeo; amostra pequena é declarada como tal em vez de gerar recomendação.
Atenção: as métricas chegam com atraso de dias; os dias mais recentes podem vir vazios.

## 10. Ordem e dependências

`P00 → P01 → {P02, P03 em paralelo, só dependem dos contratos e da persistência} → P04 → P05 → P06 → P07`. Só P00 e P01 têm plano detalhado agora; P02–P07 ganham plano próprio no início de cada fase, para não planejar às cegas contra contratos que ainda não existem.
Marcos úteis: **M1** (fim da P01) ambiente reproduzível no Lenovo; **M2** (fim da P04) vídeo completo local; **M3** (fim da P05) publicação segura com aprovação; P06 e P07 são melhoria contínua.

## 11. Riscos transversais

| Risco | Efeito | Resposta |
|---|---|---|
| Windows nunca executado | P01 pode quebrar no Lenovo | Rodar a P01 de verdade lá antes de seguir |
| Token OAuth de 7 dias (modo *Testing*) | Publicação falha silenciosa | Alerta na P06; avaliar produção na P05 |
| Modelos `:free` instáveis/limitados | Render falha por cena | Cache + retry + `placeholder` como degradação explícita (marcada no QA) |
| Cota `videos.insert` (100/dia) e 50 unidades por miniatura | Teto de volume | Registrar uso; fora de escopo ampliar |
| Fonte factual muda ou some | Fact check não reproduz | Snapshot com hash guardado |
| Troca do login OpenAI do OpenCode | Custo/identidade errados | `doctor` mostra o provider efetivo; você confirma o pessoal |

## 12. O que fica para quem constrói

Nomes internos de módulos além dos listados, formato exato do HTML de prévia, rubrica numérica de ideias, estilo visual da miniatura.
