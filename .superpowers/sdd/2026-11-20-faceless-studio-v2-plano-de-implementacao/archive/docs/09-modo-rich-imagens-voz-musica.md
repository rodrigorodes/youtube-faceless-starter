# Modo `rich`: imagens, narração, música e cobertura por dia

O modo padrão (`slides`) gera só texto sobre fundo liso e **sem áudio**. O modo `rich` gera um Short de verdade:

- **Imagens** por cena (geradas por IA, com Ken Burns, selo do dia, legenda e aviso "Ilustração gerada por IA");
- **Narração** em pt-BR (Piper, voz `pt_BR-faber-medium`, dataset CC0), rodando dentro do container;
- **Trilha** eletrônica original, sintetizada por código (numpy), sem samples nem músicas de terceiros;
- Mixagem com ducking (a música abaixa sob a voz) e normalização (loudnorm, -16 LUFS).

Saída: 1080×1920, 25 fps, H.264 + AAC. Limite: 175 s (Shorts aceitam até 180 s).

## Como usar

Envie `mode: "rich"` com `scenes` explícitas (controle total, recomendado para eventos com fatos):

```json
{ "topic": "...", "mode": "rich", "title": "...", "description": "...", "tags": ["..."],
  "sources": ["https://..."], "privacy": "private",
  "scenes": [ { "narration": "texto falado", "caption": "legenda na tela",
                "label": "QUA • 21/10", "image_prompt": "generic scene, in English" } ] }
```

Exemplo completo (ADE 2026, 13 cenas, quarta 21 a domingo 25): `examples/ade-2026-rich-publish.json`.

Sem `scenes`, o provider de roteiro (`AI_PROVIDER` diferente de `demo`) monta o storyboard a partir de `topic` + `context` (`scene_count` de 4 a 14). Ele só pode usar os fatos do `context`.

## Imagens: bridge `/image` e só modelos gratuitos

O renderer pede as imagens ao bridge local (`scripts/opencode-bridge.py`, no host), que usa o endpoint stateless de imagem do OpenCode.

- Modelo: `OPENCODE_IMAGE_MODEL` (padrão `openrouter/recraft/recraft-v4.1-flash-v2:free`).
- **Trava de custo**: o bridge recusa iniciar com modelo que não termine em `:free`, salvo `OPENCODE_ALLOW_PAID_IMAGES=1`.
- As imagens são geradas **uma por vez** (o bridge atende uma requisição por vez): ~2 s por cena. Um vídeo de 13 cenas leva ~1 min.
- `IMAGE_PROVIDER=placeholder` usa um degradê local, sem rede (útil para testes).
- Observado: `opencode/grok-imagine-image-2.0` retornou 401 (credencial inválida) e `flux-3-image-klein` retornou 402 (sem créditos). Por isso o padrão é o `:free`.

Subir o bridge (mantenha o terminal aberto):

```bash
# macOS
python3 scripts/opencode-bridge.py
# Windows (PowerShell)
py scripts\opencode-bridge.py
```

O `OPENCODE_BRIDGE_TOKEN` fica no `.env`. Não o exponha. O `docker-compose.yml` repassa `IMAGE_PROVIDER` ao renderer.

## Direitos e transparência

- **Não use** fotos/vídeos reais do evento (o material de imprensa pede crédito e tem termos próprios) **nem músicas** dos artistas.
- Os `image_prompt` não podem citar pessoas reais, artistas, marcas ou texto. O renderer acrescenta "no text, no logos, no recognizable real people".
- O vídeo exibe "Ilustração gerada por IA" e a descrição traz o aviso. O upload marca `containsSyntheticMedia=true` (o nó YouTube nativo do n8n não expõe esse campo; por isso o upload usa HTTP Request).
- Licença da voz: dataset CC0 (conferido no model card). O pacote `piper-tts` é GPL-3.0; ele só roda no container e não é redistribuído.
- Fatos: só de fontes oficiais, citadas em `sources`. Para eventos já encerrados, escreva no passado ("a programação anunciada previa").

## Sobre o Dockerfile

A voz (~61 MB) é baixada no build e conferida por SHA-256. O primeiro `docker compose build renderer` demora mais por causa disso e do `onnxruntime`.

## Ajustes comuns

- Música alta demais: reduza `volume=0.40` em `renderer/app/rich.py` (função `assemble`).
- Vídeo longo demais (HTTP 422): reduza cenas ou o tamanho das falas.
- Falha 502 `Image generation failed for scene N`: confira se o bridge está no ar e se o modelo `:free` responde.

## Limitações conhecidas

- Testado em macOS (Docker Desktop). No Windows a documentação foi escrita, mas **não foi executada**.
- Sem idempotência na publicação: enviar o mesmo pedido duas vezes cria dois vídeos.
- O app OAuth em modo *Testing* expira o refresh token em 7 dias; reconecte a credencial no n8n.
- As imagens por IA podem ter artefatos; revise o vídeo no Studio antes de torná-lo público.
