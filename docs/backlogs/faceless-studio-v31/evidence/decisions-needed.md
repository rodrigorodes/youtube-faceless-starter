# Decisões requeridas — validação técnica dos ADRs (F00.T02)

Validação de código em 21/11/2026, HEAD `e254b61`. Nenhum ADR foi **aprovado** nesta
execução: a aprovação é do responsável técnico. Abaixo, para cada ADR, o que o código
mostra, o que ainda falta decidir e a recomendação técnica.

Legenda de estado: **aderente** (código já comporta a decisão), **parcial** (há parte do
caminho), **ausente** (nada implementado).

---

## ADR-001 — Identidade YouTube (G02/G03)

**Estado: parcial.**

- Existe o modelo novo conta → grants → canais → autorizações
  (`domain/youtube_identity.py`, `adapters/postgres/youtube_identity_repo.py`) e o gate
  `RunPublication._authorization_gate` compara o canal do token com o destino vinculado
  antes de qualquer upload.
- O token usado no upload **não** vem do grant: `composition.py` monta
  `FallbackTokenProvider(EnsureAccessToken(youtube_repo, …), EnvRefreshTokenProvider(...))`,
  ou seja, cofre legado por projeto com queda para o token do ambiente.
- O n8n (`workflows/03-publish-approved.json`, nó `Upload`) faz o PUT no `upload_uri` com a
  credencial própria `youTubeOAuth2Api` (`predefinedCredentialType`), fora do Core.

**Recomendação:** aprovar a decisão proposta e tratá-la em F01.T01/F01.T02.

**Pendências que exigem decisão humana antes de F01:**

1. O upload HTTP continua no n8n (com sessão emitida pelo Core) ou migra para o Core?
2. Como migrar tokens legados (`EnvRefreshTokenProvider`, cofre por projeto) sem fallback cruzado?
3. Canal sem destino: bloqueia publicação ou mantém o caminho legado explícito e restrito?
4. Política para resultado externo ambíguo (hoje: `UNCERTAIN` + reconciliação) — quem reconcilia?

---

## ADR-002 — Escopo de orçamento (G01)

**Estado: parcial (e contraditório).**

- `composition.channel_guard_limits` liga os limites hard do canal ao `PaidOperationGuard`.
- `_ChannelBudgetFloor.project` (modo guardado do coordenador) compara o gasto **global**
  `usage.spent_month()` com o teto soft **do canal** — o teto de A é consumido pelo gasto de B.
- `GetChannelBudget` (painel) soma o uso por canal (`usage.month_summary(p_id)`): o painel e a
  pausa humana medem escopos diferentes.

**Recomendação:** aprovar a decisão proposta (tetos global e por canal independentes, com
atribuição explícita e reserva atômica).

**Pendências:**

1. Operações sem vídeo/projeto: qual escopo consome?
2. Migração das linhas antigas de `budget_reservations` sem atribuição.
3. Ordem de locks entre orçamento global e de canal.
4. Política de custo desconhecido (reservar estimativa, bloquear ou teto conservador).

---

## ADR-003 — Configuração efetiva e snapshot (G06/G05)

**Estado: ausente.**

- `ProductionRun` (`domain/production_run.py`) não carrega configuração criativa congelada.
- `RunRender` recebe `style_for`/`voice_for` como callables resolvidos **na execução**
  (`composition.py`), então mudar estilo/perfil entre o start e o TTS muda o resultado.
- O Render Plan persiste `StyleSnapshot` (id + versão) — referência a perfil mutável, sem os
  valores necessários nem revalidação de que a revisão ainda é a mesma.

**Recomendação:** aprovar; resolver o schema em F03.T01 com canonicalização e versão de schema.

**Pendências:**

1. Schema do snapshot (valores x referência imutável) e canonicalização determinística.
2. Atomicidade: snapshot e run na mesma transação.
3. Runs legados: política explícita (não fabricar snapshot histórico).
4. `retry`/`resume`/`regenerate`: o que é congelado e o que é re-resolvido.
5. Cache de assets por fingerprint — validade quando a configuração muda.

---

## ADR-004 — Precedência e ciclo de vida de estilos (G07/G08/G15)

**Estado: parcial.**

- Seleção de estilo inteiro: `effective_style_id(video, canal, default)` e `resolve_style`
  — não existe patch parcial (G07 confirmado).
- `PostgresVisualStyleRepository.archive` → `_clear_links` zera `channel_profiles.style_id`
  **e** `videos.style_id` dos vinculados, numa transação, sem auditoria dos runs afetados
  (G08 confirmado).
- Create (G15) exibe estilos fictícios e não persiste a escolha.

**Recomendação:** aprovar. G15 não depende de patches; pode ser fechado em F02.T02.

**Pendências:**

1. Patch de canal quando o vídeo troca de base: herdar campos compatíveis ou descartar?
2. Pin de versão do estilo no run (hoje só id+versão no plano).
3. Desvincular no arquivamento com auditoria/revisão transacional — ou bloquear.
4. Enquanto F05 não concluir: impedir arquivamento que afete run ativo (mitigação).

---

## ADR-005 — Escopo mono-operador e SaaS (G04/G10)

**Estado: aderente como restrição de produto; o modelo SaaS existe e não opera.**

- `domain/saas.py` tem organização, papéis, permissões, BYOK e auditoria; `studio.byok_keys`
  guarda máscara/fingerprint (nunca o valor em claro).
- Nenhum provider consome a chave BYOK: `composition.py`/`application/providers.py` não leem
  BYOK; `saas_repo.touch_key_usage` só marca uso. G10 confirmado: cadastrado, não utilizado.
- `project_id` é a identidade do canal; não há escopo autenticado por tenant nas queries de
  produção.

**Recomendação:** aprovar a decisão; projeto C permanece fora do aceite A.

**Pendências:**

1. Responsável e gate comercial do projeto C.
2. Quais controles de Equipe/BYOK ficam visíveis na V3.1 (hoje a tela promete gestão de chaves
   que não é usada na execução — risco de promessa vazia).

---

## ADR-006 — Perfis e roteamento (G09)

**Estado: ausente na execução.**

- `ProviderService.route`/`route_provider` calculam decisão com ranking, disponibilidade e teto.
- Os únicos chamadores são o endpoint `/studio/projects/{id}/providers/route` e a página de
  Canais: o roteamento é **consultivo**.
- A execução usa `composition.provider_for`, que lê `ProjectConfig` direto; `EconomicProfile`
  não influencia a escolha.

**Recomendação:** aprovar e implementar em F06.T02.

**Pendências:**

1. Ranking por perfil (ECONOMY/BALANCED/PREMIUM) e qualidade mínima por capacidade.
2. Fallback permitido é explícito (hoje `route` devolve cadeia; execução ignora).
3. Custo desconhecido no roteamento.
4. Exclusão de demo/placeholder da produção.

---

## ADR-007 — Pilares e contexto editorial (G05/G13)

**Estado: ausente.**

- `ChannelProfile` persiste `language`, `audience`, `pillars`, `narrative`, `target_duration_s`,
  `cta`, `strategy`.
- `application/editorial.py::build_prompt` escreve "vídeo curto em português do Brasil" e usa
  só tema + claims; `longform.py` também fixa pt-BR e `DEFAULT_TARGET_SECONDS = 480`.
- Categorias de coleta (`domain/categories.py`) são queries de tendências, sem relação com
  `pillars` — responsabilidades distintas (G13).

**Recomendação:** aprovar a separação; aplicar campos só quando tiverem contrato e teste.

**Pendências:**

1. Relação futura entre pilares editoriais e queries de coleta (Finder, fora de escopo).
2. Duração por formato (short x long) e origem do valor.
3. Quais campos valem para assets/metadados/thumbnail (não alegar thumbnail avançada).

---

## Decisões transversais (não cobertas por ADR)

1. **Local do pacote:** o README manda copiar para `docs/projects/faceless-studio-v31/`; o
   operador colocou em `docs/backlogs/faceless-studio-v31/`. Mantido onde está (decisão do
   operador); o README foi corrigido para o caminho real.
2. **Documento-fonte:** `docs/backlogs/Faceless Studio V3.1 — UX & Settings Redesign.md` está
   **não rastreado** e com nome não-ASCII (travessão). Arquiva-se por referência Git; sem
   commit ele não tem referência. Precisa de decisão: versionar (e com qual nome) ou manter
   fora do repositório.
3. **Pin de dependência:** pydantic instalado 2.5.0 x pin 2.11.4. Validar no ambiente de
   release; não alterar pin em F00.