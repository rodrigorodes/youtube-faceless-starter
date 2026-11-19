# Storyboard e mídia (P03)

Depois da checagem factual (`FACT_CHECKED`), cada cena ganha uma imagem. Estados: `FACT_CHECKED → STORYBOARDED → ASSETS_READY`.
Os dois passos têm endpoint próprio; o `/transition` genérico responde `403` para esses destinos.

```bash
B=http://localhost:8000/studio
curl -s -X POST $B/videos/$VID/storyboard            # congela as cenas: FACT_CHECKED → STORYBOARDED
curl -s -X POST $B/videos/$VID/assets                # {"generated": n, "reused": m}; STORYBOARDED → ASSETS_READY
curl -s $B/videos/$VID/assets                        # cena → asset (caminho, provedor, licença, atribuição)
```

Erros: `404` vídeo inexistente · `409` estado errado · `422` provedor desconhecido/sem chave · `403` teto de custo ·
`502` provedor indisponível ou imagem recusada · `503` banco indisponível.

## Provedores de imagem (`STUDIO_IMAGE=<provedor>:<modelo>`, ou `image` no `config` do projeto)

| Provedor | O que faz | Custo | Licença gravada |
|---|---|---|---|
| `opencode:<modelo>` | modelo de imagem via bridge local (login OAuth do OpenCode) | `0` se o modelo termina em `:free`; senão estimativa `STUDIO_PAID_IMAGE_USD` (0,05) e o `CostGuard` recusa com teto 0 | `ai-generated:<modelo>` |
| `placeholder:gradient` | degradê determinístico local, sem rede | 0 | `CC0-1.0` |
| `stock:pexels` | foto do Pexels buscada pelo tema do prompt (`PEXELS_API_KEY`) | 0 | `Pexels License` + atribuição + URL da foto |
| `veo:<modelo>` | clipe de vídeo do Veo | estimativa `STUDIO_VEO_USD_PER_SECOND` (0,40) × 8 s = US$ 3,20 | — |

## Cache e retomada
- `cache_key = sha256(tipo|provedor|modelo|prompt com estilo|aspecto)`. Mesmo prompt, provedor e aspecto: **0 imagens novas**,
  mesmo em outro vídeo. Prompt repetido em várias cenas gera uma vez só.
- `POST /assets` é retomável: cena já vinculada é pulada, imagem já em cache é reaproveitada. Se um provedor cair no meio,
  o vídeo continua `STORYBOARDED` e repetir a chamada gera só o que falta.
- O arquivo vai para `storage/cache/<2 primeiros hex>/<chave>.png`, normalizado para PNG no tamanho do aspecto
  (short 1080×1920, long 1920×1080), com escrita atômica. O caminho no banco é **relativo** à raiz de storage (vale no macOS e no Windows).
- Recusado (nada é gravado nem vinculado, mas a chamada fica no ledger): imagem sem licença (vazia ou só espaços), mime que não
  seja PNG/JPEG/WebP, arquivo que não abre como imagem, mais de 20 MB ou 50 milhões de pixels.

## Concorrência e falhas
- Uma produção por vídeo: o `POST /assets` toma um lock de sessão do Postgres (`pg_try_advisory_lock`); a segunda chamada
  simultânea recebe `409` sem chamar o provedor (cliente que deu timeout e repetiu não paga duas vezes). O lock cai sozinho
  se a conexão morrer. Dois vídeos **diferentes** com o mesmo prompt ainda podem gerar em paralelo (um asset vence, o outro é descartado).
- O vínculo cena→asset só vale se o vídeo continua `STORYBOARDED` e a cena mantém o mesmo prompt; senão `409` e nada avança.
- Arquivo em cache só é reaproveitado se abrir como PNG do tamanho do aspecto; corrompido ou de outro aspecto é regravado.
- Se `store.put` ou o banco falhar depois da chamada paga, o gasto fica no ledger, mas a próxima tentativa gera de novo (o arquivo
  órfão é sobrescrito). Falha do provedor **depois** de gerar (timeout de leitura) não é contabilizada: por isso modelo pago
  nunca é repetido automaticamente, e modelo `:free` só repete em 5xx ou falha de conexão.
- O adaptador `opencode` só gera se o `/health` do bridge declarar o mesmo `image_model` configurado (custo, licença e cache
  usam o rótulo; sem isso, `OPENCODE_ALLOW_PAID_IMAGES=1` no bridge geraria pago com custo registrado 0). Atualize o bridge.
- Limite de entrada do store: 20 MB e 25 milhões de pixels; a orientação EXIF é aplicada.

## Custo
Toda geração passa pelo `CostGuard` **antes** da chamada (teto por vídeo `MAX_COST_USD_PER_VIDEO`, padrão 0, e mensal
`MAX_COST_USD_PER_MONTH`, padrão 15). Com teto 0, Veo e qualquer modelo não `:free` voltam `403`.
Preço do Veo conferido em out/2026 (Veo 3.1: de US$ 0,05/s no Lite 720p a US$ 0,60/s em 4K); confira antes de liberar o teto.

## Limites conhecidos
- O bridge gera **sempre 9:16**. Em vídeo `long` a imagem é recortada para 16:9 (perde o topo e a base).
- `veo` só estima custo: a geração **não está implementada** (com o teto liberado devolve `502`).
- `stock` traz fotos reais e genéricas do tema, não do evento; não use para afirmar que algo aconteceu num lugar. Pexels
  exige citar o fotógrafo: a atribuição fica no asset e deve ir para a descrição (a P05 inclui os créditos).
- `gemini`/`vertex` de texto não viraram adaptadores do estúdio (o `/videos` legado continua intacto).
- A voz `PiperVoice` existe como adaptador, mas só entra no fluxo na P04.
- O teto de custo é conferido antes e o gasto gravado depois (vídeos diferentes gerando juntos passam juntos); hoje só `:free`,
  placeholder e stock custam 0.

## Verificado (stack real)
Placeholder: 1 imagem gerada e 3 reaproveitadas num vídeo de 4 cenas; segundo vídeo com o mesmo conteúdo, 0 geradas;
repetir `/assets` em `ASSETS_READY` deu `409`. Veo com teto 0: `403`, vídeo segue `STORYBOARDED`, 0 assets.
`opencode` com modelo `:free` pelo bridge: imagem 1080×1920 gravada, custo 0, licença `ai-generated:…` registrada.
- Retomada: `POST /assets` com o vídeo já em `ASSETS_READY` devolve `409`; use o `GET` para ler o resultado.
- Pré-existente (P04/P05): o `/transition` genérico ainda chega a `RENDERED` e `AWAITING_APPROVAL` a partir de `ASSETS_READY`.
