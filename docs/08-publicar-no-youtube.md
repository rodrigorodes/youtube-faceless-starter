# Publicar no YouTube (workflow V2)

> **Legado — não ative nem use para novos vídeos.** Este fluxo não consulta o
> Studio nem exige aprovação antes do upload e aceita visibilidade pública.
> Ele não cumpre a política atual do projeto. O workflow legado instalado
> anteriormente no n8n pode continuar ativo independentemente deste arquivo;
> desative-o no n8n antes de usar o Studio. O fluxo de substituição está em
> [15-publicacao.md](15-publicacao.md), mas também permanece inativo até as
> correções de segurança e concorrência indicadas nessa página.
>
> As instruções abaixo são histórico do V2, não um procedimento recomendado.

Workflow: `workflows/02-create-and-publish.json` (**Faceless V2 - Create and Publish Short (private)**).
Fluxo: **Webhook → Render Video → Init YouTube Upload → Download MP4 → Upload to YouTube → resposta** (com respostas de erro).

> **Padrão seguro:** o vídeo sobe **`private`**. `unlisted` ou `public` só se você enviar `privacy` explicitamente no pedido.

## 1. Preparar o Google Cloud (uma vez)

1. Crie um projeto **seu** e habilite a **YouTube Data API v3**.
2. **Google Auth Platform**: público **Externo**, nome do app e e-mail de suporte. Em modo *Testing*, adicione a conta que vai publicar em **Público-alvo → Usuários de teste**. Sem isso o consentimento falha com `Erro 403: access_denied`.
3. **Clientes → Criar cliente → Aplicativo da Web**. Em *URIs de redirecionamento autorizados* coloque exatamente:
   `http://localhost:5678/rest/oauth2-credential/callback`
4. Baixe o JSON do cliente. **Não o publique** e apague-o depois de configurar a credencial.

## 2. Credencial no n8n

*Credentials → Add credential → **YouTube OAuth2 API*** (nome sugerido: `youtube_videos_app`). Informe *Client ID* e *Client Secret* e clique em **Sign in with Google** com a conta dona do canal.

**Escopo mínimo.** Por padrão o n8n pede 5 escopos amplos (`youtube`, `youtubepartner`, `force-ssl`, `upload` e `youtubepartner-channel-audit`), que dão poder de gerenciar o canal. Para publicar basta `https://www.googleapis.com/auth/youtube.upload`. O campo *Scope* é oculto na tela, então:

- Pela interface: autorize normalmente (escopos amplos), **ou**
- Para o mínimo, abra o link de autorização trocando o parâmetro `scope=` por `https://www.googleapis.com/auth/youtube.upload` antes de aceitar.

Com só `youtube.upload` o token **não lê nem altera** vídeos depois do upload (só envia). Para ler status ou editar seria preciso outro escopo.

## 3. Importação histórica — não ativar

1. *Workflows → Import from File* → `workflows/02-create-and-publish.json`.
2. Nos nós **Init YouTube Upload** e **Upload to YouTube**, selecione a credencial `youtube_videos_app`.
3. Não ative o workflow legado; ele contorna a aprovação.

Nota: a importação **pela CLI** (`n8n import:workflow`) falha com esses JSONs (falta `id`/`versionId`). Use a interface.

## 4. Antes de publicar: provider de roteiro

O roteiro com fatos precisa de um modelo (o provider `demo` **não** usa o contexto e publicaria texto genérico). Use `AI_PROVIDER=opencode` (veja [07](07-openai-luna-oauth.md)) ou `gemini`/`vertex`, e com `opencode` deixe o bridge rodando:

- macOS: `python3 scripts/opencode-bridge.py`
- Windows: `py scripts\opencode-bridge.py`

Se o provider falhar, o workflow responde **502** e **não** publica nada.

## 5. Chamar

`POST http://localhost:5678/webhook/faceless-publish`

| Campo | Obrigatório | Padrão | Descrição |
|-------|-------------|--------|-----------|
| `topic` | sim | n/d | Tema (3 a 300 caracteres) |
| `context` | recomendado | vazio | **Fatos verificados** (até 3000). O modelo só pode usar isto. |
| `sources` | não | `[]` | Até 5 URLs `http(s)`, listadas na descrição |
| `duration_seconds` | não | 30 | 10 a 60 |
| `style` | não | `documentary` | |
| `footer` | não | `YOUTUBE FACELESS` | Texto do rodapé dos slides (até 40) |
| `privacy` | não | `private` | `private`, `unlisted` ou `public` |
| `category_id` | não | `24` | Categoria do YouTube (24 = Entretenimento) |

Valores fixos no workflow: idioma `pt-BR`, *made for kids* = **não**, conteúdo sintético (`containsSyntheticMedia`) = **sim**. Edite o nó *Init YouTube Upload* para mudar.

macOS:
```bash
curl -X POST http://localhost:5678/webhook/faceless-publish -H 'Content-Type: application/json' --data @examples/ade-2026-publish.json
```
Windows (PowerShell; o JSON do exemplo tem acentos, então envie em UTF-8):
```powershell
$bytes = [IO.File]::ReadAllBytes("examples\ade-2026-publish.json")
Invoke-RestMethod -Uri http://localhost:5678/webhook/faceless-publish -Method Post -ContentType 'application/json; charset=utf-8' -Body $bytes
```

Resposta de sucesso (HTTP 200):
```json
{"status":"UPLOADED","privacy":"private","video_id":"…","url":"https://www.youtube.com/watch?v=…","studio_url":"https://studio.youtube.com/video/…/edit","title":"…","render_id":"…"}
```
Resposta de erro (HTTP **502**): `{"status":"FAILED","stage":"render"|"upload","error":"…","details":…}`. Diferente do workflow V1, a falha **não** volta como 200 vazio.

`examples/ade-2026-publish.json` é um exemplo real, com fatos do comunicado oficial da ADE de 06/10/2026.

## 6. Como funciona o upload

O nó YouTube nativo do n8n **não expõe `containsSyntheticMedia`**. Por isso o upload usa a API de **upload resumível** com a mesma credencial:
1. `POST …/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status` com os metadados. A URL da sessão vem no cabeçalho `Location`.
2. O MP4 é baixado do renderer pela rede interna (`http://renderer:8000/videos/<id>/file`).
3. `PUT` do binário na URL da sessão.

## 7. Limites e cuidados

- **Cota**: `videos.insert` tem bucket próprio de 100 chamadas por dia (1 unidade cada), segundo a documentação. O canal pode ter limites próprios.
- **Modo *Testing***: o refresh token expira em **7 dias** (reconecte a credencial). Se o upload falhar com `invalid_grant`/401, é isso.
- **Sem idempotência**: chamar duas vezes publica dois vídeos. Não há fila nem deduplicação.
- **Sem aprovação no n8n**: a revisão é manual no YouTube Studio (por isso `private`).
- **Qualidade**: slides de texto sem áudio, 720×1280. Revise a política do YouTube sobre conteúdo repetitivo ou produzido em massa antes de publicar em volume ou com monetização.
- **Fatos**: o modelo é instruído a usar só o `context`, mas **você** responde pela veracidade do contexto. Confira o roteiro no Studio antes de tornar o vídeo público.
- O token de `youtube.upload` não permite ler o vídeo depois. A confirmação de privacidade e das declarações vem da resposta do upload (execução no n8n).

## 8. Erros comuns

| Sintoma | Causa |
|---------|-------|
| `Erro 403: access_denied` ao autorizar | Conta não está em *Usuários de teste* |
| `redirect_uri_mismatch` | Redirect URI do cliente OAuth diferente do exibido na credencial |
| 502 `stage: render` | Renderer ou provider falhou (veja `error`). Ex.: bridge parado, `duration_seconds` fora de 10–60 |
| 502 `stage: upload`, 401/403 | Credencial expirada (Testing), API desabilitada ou cota |
| 502 `stage: upload`, 400 | Metadados inválidos (título vazio ou longo, tags) |

## 9. Validado (macOS arm64, 19/11/2026)

- 29 testes. Renderer com `context`, `sources`, `footer` e metadados (título, descrição, tags).
- Credencial `youTubeOAuth2Api` conectada, com escopo concedido **somente `youtube.upload`** (confirmado no token).
- Erro: `duration_seconds=5` e pedido sem `topic` devolvem 502 com `stage: render`.
- **Upload real**: 1 vídeo de 28 s sobre a ADE 2026, em ~15 s fim a fim. Retorno do YouTube: `uploadStatus: uploaded`, `privacyStatus: private`, `selfDeclaredMadeForKids: false`, `containsSyntheticMedia: true`.
- **Não validado**: Windows; a interface do n8n (cliques de importação); `unlisted`/`public`; agendamento (`publishAt`); renovação do token após 7 dias; reprocessamento do vídeo pelo YouTube (resolução, avisos de direitos).
