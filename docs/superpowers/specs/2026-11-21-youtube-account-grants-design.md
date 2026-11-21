# Conta Google → autorizações → canais do YouTube (identidade de publicação)

**Projeto:** Faceless Studio V2 — fundação de publicação (F8/F10-06)
**Versão:** 1.0
**Status:** Desenhado; fatia YT-01 em implementação
**Data:** 2026-11-21

---

## 1. Problema

O modelo atual de conexão com o YouTube assume uma equivalência que **não está provada**:

| Hoje | Onde |
| --- | --- |
| 1 projeto = 1 canal do YouTube | `channel_youtube_channels` — `PRIMARY KEY (project_id)` |
| A credencial é do projeto | vault, escopo `youtube:{project_id}` |
| A publicação usa o token do projeto do vídeo | `RunPublication` → `tokens.execute(video.project_id)` |

Isso embute três pressupostos frágeis:

1. **Que uma autorização serve a vários canais.** Não está provado. A doc do Google
   descreve `channels.list(mine=true)` como "o canal do usuário autenticado" — **não** como
   a enumeração de todos os canais administrados pelo mesmo e-mail. Escopos
   `youtube.upload`/`youtube.readonly` **não** garantem poder escolher livremente entre canais.
2. **Que a Conta Google é a unidade.** Uma conta pode administrar muitos canais (Contas de
   Marca, até ~100); a conta não é o canal.
3. **Que o projeto é a fronteira.** O produto quer **1 conta → N canais**, cada canal com sua
   configuração e sua publicação.

## 2. Decisão (do usuário)

**Não pressupor token universal.** Cada canal que o SaaS publica precisa ter uma
autorização **efetivamente validada** para aquele canal. Não é necessário *provar* que o
Google exige um refresh token por canal — basta **não presumir** que uma autorização é
intercambiável entre canais.

Modelo (contrato V1):

```
GoogleAccount        — identidade da conta (e-mail). Não guarda a autorização como propriedade única.
OAuthGrant           — autorização independente: escopos, tokens e ciclo de vida próprios.
YouTubeChannel       — identidade oficial do canal (o `UC...`).
ChannelAuthorization — vínculo **validado** entre uma autorização e um canal.
ChannelProfile       — configuração editorial + referência ao canal de publicação.
```

```
Estúdio
 └── GoogleAccount (1)
      └── OAuthGrant (N)          ── tokens no vault, escopo próprio
           └── ChannelAuthorization (N) ── vínculo validado
                └── YouTubeChannel (1)   ── identidade oficial
                     ↑
      Canal do estúdio (ChannelProfile) referencia o canal de publicação
           └── Vídeo → publica ali (estilo herdado do canal)
```

## 3. Regra obrigatória de publicação

**Antes de publicar, o `YouTubePublishingProvider` deve garantir que a autorização resolve
para o `youtubeChannelId` esperado.** Se houver divergência, **bloqueia o upload**.

Essa é a regra que torna o modelo seguro mesmo se o Google mudar o comportamento: em vez de
confiar que o token "é do canal certo", o provider **verifica** — e a verificação é sobre a
identidade do canal e a capacidade real de publicação, não sobre os valores dos tokens
(dois tokens diferentes, isoladamente, não provam restrição a um canal).

## 4. Invariantes

- **Reconexão isolada:** reconectar um canal cria/atualiza a *autorização* daquele canal, sem
  tocar nas autorizações dos outros.
- **Tokens fora do banco:** só o vault; o banco guarda metadados (escopos, status, expiração).
- **Proteção contra sobrescrever autorização:** conectar outro canal **não** pode reescrever
  uma autorização existente de outro canal (o erro é do usuário, não silencioso).
- **Nada inventado:** sem credencial no vault → `DISCONNECTED`; token vencido → `EXPIRED`;
  revogado → `REVOKED`.

## 5. Teste que resolve a incerteza (não a arquitetura)

O teste ao vivo **valida o adapter YouTube**, não determina o domínio. Com uma conta que
administre dois canais A e B:

1. Autorizar selecionando **A** → `channels.list(mine=true)` → registrar o canal.
2. Renovar o access token pelo refresh → confirmar que continua **A**.
3. Repetir a autorização selecionando **B**.
4. Comparar as duas autorizações e seus canais.
5. Publicar vídeos **privados** de teste em A e B.

Se um dia provar-se que um grant cobre vários canais, o modelo **absorve**: um grant passa a
ter várias `channel_authorizations` — sem migração estrutural.

## 6. Fatias

| Fatia | Entrega |
| --- | --- |
| **YT-01** | Schema (`google_accounts`, `oauth_grants`, `youtube_channels`, `channel_authorizations`) + domínio + repositórios. Aditiva: não remove o caminho atual. |
| **YT-02** | O canal do estúdio referencia o canal de publicação; a publicação resolve a autorização a partir do canal, não do projeto. |
| **YT-03** | `YouTubePublishingProvider`: verifica que a autorização resolve para o canal esperado; **bloqueia** a divergência. |
| **YT-04** | UX: conectar a conta, escolher/validar o canal, revogar — por canal, com a conta agrupando. |
| **YT-05** | Teste ao vivo (A/B) como teste de adapter, em ambiente controlado. |

## 7. Fora de escopo

- Provar/exigir token por canal: o modelo é **robusto aos dois casos**, e não depende da prova.
- Multi-tenant da conta (organização) — a conta é do estúdio; o `organization_id` entra quando a
  multi-tenancy ligar.

## 8. Relação com os estilos

Nenhuma mudança: o estilo é do canal e a biblioteca é compartilhada. O canal do estúdio passa a
reunir **identidade + estilo + destino**, o que torna o modelo de estilos ainda mais coerente.
