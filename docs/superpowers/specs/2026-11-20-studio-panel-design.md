# Painel do Faceless Studio — desenho

Status: **planejamento** (nenhum código escrito). Planos de execução:
- A — `docs/superpowers/plans/2026-11-20-studio-panel-a-operational.md`
- B — `docs/superpowers/plans/2026-11-20-studio-panel-b-trends.md`

## Objetivo
Uma tela única no navegador para o operador: ver os vídeos por tema e por etapa, o custo (por vídeo, por tema e no mês contra o teto) e, na fase B, temas em alta dos últimos 7 dias com fonte e data da consulta. O n8n fica nos bastidores; ninguém precisa procurar IDs.

## Escopo
| Fase | Entrega | Depende de |
|---|---|---|
| **A — operacional** | Resumo; vídeos agrupados por tema e por etapa; custo por vídeo/tema/mês; detalhe do vídeo (progresso, erros, custo por chamada); criar vídeo; link para a prévia/aprovação existente. | Frente "aprovação ↔ render" (migração 0010) integrada na branch. |
| **B — temas em alta** | Coleta de tendências com fonte verificável; seção "Temas em alta" com filtro 7/14/30 dias; "Criar vídeo" a partir do tema. | A concluída; decisão de fonte (abaixo); chave de API de leitura do YouTube (ação do usuário). |

Fora de escopo (ambas): publicar/aprovar dentro do painel (continua na prévia, que já tem o vínculo com o render revisado); retry/reconciliação de publicação; multiusuário/papéis; gráficos; WebSocket; framework JS e build de front-end; pontuação editorial automática de tendências.

## Decisões
1. **HTML servido pelo próprio renderer**, sem Node/bundler: mesmo padrão e mesma autenticação de `api/preview.py` (Basic no navegador, CSP com nonce, todo texto escapado, `fetch` same-origin com `Origin`). Funciona igual em macOS e Windows (`http://localhost:8000/studio/panel`).
2. **Leitura por SQL agregado** (read model), sem novo estado em A: nenhuma migração. Escalas esperadas são pequenas (centenas de vídeos); revisar índices só se um teste de volume mostrar necessidade.
3. **"Tema" = `topic_key(video.topic)`**: NFKC + casefold + espaços colapsados + pontuação nas pontas removida. Vídeos com o mesmo tema normalizado agrupam juntos. Um vídeo criado a partir de uma tendência usa o texto do tema verbatim, logo agrupa sem chave estrangeira (YAGNI).
4. **Etapas exibidas** (derivadas, não persistidas): `PENDING`, `IN_PRODUCTION`, `AWAITING_APPROVAL`, `APPROVED`, `COMPLETED`, `FAILED`, `REJECTED`. Regra de precedência no Task A1.
5. **Custo honesto.** `usage_ledger.cost_usd` é `NOT NULL DEFAULT 0` e vários adaptadores gravam `0.0` fixo, então zero não prova gratuidade. A linha é *conhecida* se `cost_usd > 0`, ou se o modelo termina em `:free`, ou se o provedor é local/gratuito (`placeholder`, `demo`, `piper`, `stock`). Caso contrário é *desconhecida*. O painel mostra `US$ 0,00 (gratuito)` só quando todas as linhas são conhecidas; com linhas desconhecidas mostra `US$ x,xx + N chamadas sem custo informado`; sem linhas, `sem registro de uso`. Custos de FFmpeg/voz local não são contabilizados (custo de API apenas) e a tela diz isso.
6. **Teto mensal** vem de `Settings.max_cost_month` (o mesmo valor do `CostGuard`), não de `projects.budget_usd_month` (divergência preexistente, registrada em P02; não corrigida aqui). Mês e fuso usam a mesma definição de `PostgresUsageRepository.spent_month`.
7. **Segredos fora da tela.** Nunca exibir `upload_uri`, tokens, caminhos de arquivo internos nem `error` bruto sem truncar/escapar.
8. **Tendência é fato só com fonte.** B grava um item apenas com `source_name`, `source_url` (https, host permitido), `observed_at` e janela de tempo; sem isso o item é recusado e não aparece. A tela mostra a fonte, a data da consulta e marca "desatualizado" quando a consulta é mais antiga que o filtro.

## Fonte de tendências (decisão da fase B)
| Opção | Prós | Contras | Veredito |
|---|---|---|---|
| **YouTube Data API `search.list` + `videos.list`** (consultas curadas por projeto, `publishedAfter` = janela, `order=viewCount`) | API oficial, gratuita (cota diária), traz visualizações, fonte e data verificáveis | "Tema" é a consulta curada (não detecção automática); `search.list` custa 100 unidades/consulta; cota compartilhada com o upload (1.600/upload) | **Escolhida para a v1** |
| Páginas/feeds oficiais do ADE (domínio já na allowlist) | Fato editorial primário | Formato do site não verificado; sem métrica de popularidade | Spike opcional (Task B1) |
| Google Trends | Popularidade de busca | Sem API oficial estável verificada | Descartada até haver fonte oficial |
| LLM "sugerindo" tendências | Barato | Sem fonte; viola a regra 8 | Proibida |

Tema da v1 = termos de pesquisa curados na configuração do projeto (ex.: "ADE lineup"). A métrica exibida é a soma de visualizações dos vídeos publicados na janela, com os 3 principais como evidência (título, canal, URL, visualizações, data). A coleta roda no **n8n** (credencial de leitura fica lá, como no analytics) e envia ao renderer com o token do worker.

## Wireframe (exemplo, dados fictícios)
```text
FACELESS STUDIO   [+ Novo vídeo]                      Período: [7 dias ▾]
Resumo: Em produção 2 · Aguardando aprovação 1 · Falhos 0 · Mês: US$ 0,00 (gratuito) / US$ 15,00

Temas em alta (B)  — fonte: YouTube Data API · consultado 20/11 09:00
 ade lineup — 1,2 mi views na janela            [Criar vídeo]
   2 concluídos · 1 em produção · US$ 0,00 (gratuito)

Vídeos
 Tema | Etapa | Custo | Atualizado | Ação
 ...  | Aguardando aprovação | US$ 0,00 (gratuito) | há 5 min | [Ver prévia]
 ...  | Em produção          | sem registro de uso  | há 1 min | [Ver progresso]
 ...  | Falhou               | US$ 0,00 + 1 sem custo informado | ontem | [Ver motivo]
```

## Riscos
- Frente "aprovação ↔ render" altera `routes.py`, `preview.py`, `publish_repo.py`: A só começa depois de integrada, para evitar conflito.
- Painel ficaria inútil se mostrasse custo incorreto: a regra 5 tem testes dedicados.
- Cota do YouTube: B limita a ≤ 10 consultas/dia (≈ 1.000 unidades) e registra a cota gasta.
- XSS: temas e erros vêm de entradas externas (modelo/fonte); teste de escape é obrigatório.
- HTTP local sem TLS e Basic compartilhado: limitação já documentada em `docs/17-studio-auth.md`.
