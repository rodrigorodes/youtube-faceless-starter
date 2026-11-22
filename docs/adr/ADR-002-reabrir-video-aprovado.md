# ADR-002 — Reabrir vídeo aprovado para edição (P-04)

**Status:** Aceito pelo operador com condição (DECISIONS.md, P-04 / D-B).
**Data:** 22/11/2026.
**Decisão de origem:** `docs/backlogs/faceless-visual-evolution 2/phases/INTEGRATION-PLAN.md` P-04.

## Contexto

Hoje a máquina de estados do vídeo não tem volta depois da aprovação:

```
AWAITING_APPROVAL → APPROVED → PUBLISHED → (terminal)
```

`domain/states.py` só permite `APPROVED → PUBLISHED`. Um vídeo aprovado e **não publicado**
fica sem caminho para corrigir roteiro, cena, narração ou composição. O único contorno é
duplicar o vídeo, o que perde o histórico de revisões e o vínculo com o trabalho já feito.

A aprovação amarra identidade de conteúdo: `publish_repo.approve` grava `render_id`,
`media_checksum`, o QA da versão e uma `idempotency_key` na mesma transação. Publicação
também tem lease: `publish_repo.claim` marca `UPLOADING` com `attempt` e expiração; um
upload em andamento é um efeito externo que não pode ser simplesmente cancelado.

## Decisão

Permitir **reabrir para edição** um vídeo em `APPROVED` que **não** tenha publicação
concluída nem upload em andamento.

### Transição

`APPROVED → SCRIPTED` (nova transição em `domain/states.py`), com estas condições
verificadas **no servidor**, na mesma transação da mudança de estado:

1. **Sem publicação concluída.** `PUBLISHED` é terminal: editar um vídeo publicado exige
   **duplicar** (cria vídeo independente com nova revisão). O registro histórico da
   publicação original permanece intacto.
2. **Sem upload em andamento.** Se existe `publication` em `UPLOADING` com lease válido
   (ou `PENDING` com lease ativo), a reabertura é **recusada** com erro acionável
   (`PublicationInFlight`), informando que há upload em curso. Não se cancela lease por
   edição: o efeito externo já pode ter começado.
3. **Publicação pendente é invalidada.** Se existe intenção de publicação pendente (sem
   upload iniciado), ela é marcada como obsoleta na mesma transação. O `attempt` não é
   reaproveitado.
4. **Aprovação anterior vai para o histórico.** A aprovação deixa de valer para a nova
   revisão: `render_id`, `media_checksum` e QA antigos ficam registrados no histórico, mas
   não autorizam publicar a versão nova. Nova aprovação é obrigatória.
5. **Render/QA dependentes ficam obsoletos.** O render e o QA vinculados à versão anterior
   não são promovidos; a nova revisão precisa de novo render e novo QA antes de aprovar.

### O que **não** muda

- `PUBLISHED` continua terminal.
- A publicação histórica não é apagada nem reescrita.
- O gate de publicação continua fail-closed (`publication_execution.verify_publication_gate`).
- A idempotência da publicação continua por `idempotency_key` + checksum.

## Consequências

**Prós:** corrige o beco sem saída sem tocar no histórico de publicação; usa a menor
transição possível; mantém a aprovação como contrato de conteúdo por revisão.

**Trade-offs:** é uma transição a mais na máquina de estados; exige checagem de lease de
publicação na mesma transação (novo caminho de erro); o operador precisa entender que
reabrir invalida a aprovação anterior.

**Riscos e mitigação:**

| Risco | Mitigação |
|---|---|
| Reabrir com upload em andamento e duplicar efeito externo | recusa explícita com lease ativo; teste de concorrência |
| Aprovação antiga autorizar versão nova | aprovação vinculada à revisão/`render_id`; teste de que a antiga não libera a nova |
| Publicação histórica corrompida | `PUBLISHED` terminal; edição só por duplicação |

## Regras verificáveis

1. `APPROVED → SCRIPTED` só é permitido sem publicação concluída e sem lease de upload ativo.
2. Reabrir cria nova revisão e invalida aprovação, render, QA e intenção pendente na mesma
   transação.
3. Aprovação anterior não libera a versão nova (teste de tentativa de publicar sem nova
   aprovação).
4. `PUBLISHED` não reabre; duplicar cria vídeo independente.
5. Nenhum registro histórico de publicação é apagado ou reescrito.

## Implementação (quando entrar)

- `domain/states.py`: nova transição + guarda de publicação.
- `application/`: caso de uso `ReopenForEditing` (transação única com CAS por estado).
- `adapters/postgres/publish_repo.py`: consulta de lease ativo por vídeo.
- Testes: transição, recusa com lease, invalidação de aprovação, histórico preservado.
