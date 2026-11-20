# Narração e renderização (P04)

Depois das imagens (`ASSETS_READY`), o estúdio narra cada cena, monta o vídeo, mede a qualidade e entrega o MP4 com legenda.
Estados: `ASSETS_READY → RENDERED → AWAITING_APPROVAL`. O render é **assíncrono**: o vídeo longo estoura qualquer timeout síncrono.

```bash
B=http://localhost:8000/studio
curl -s -X POST $B/videos/$VID/render      # 202 {id, status: QUEUED...}; repetir devolve o mesmo job (não enfileira de novo)
curl -s $B/videos/$VID/render              # {"job": {status, attempt, error, output_asset_id}, "qa_report": {...}}
curl -s -o video.mp4 $B/videos/$VID/file   # MP4 final (só depois de RENDERED)
curl -s $B/videos/$VID/subtitles           # .srt
```

Erros: `404` vídeo inexistente · `409` estado errado (precisa `ASSETS_READY`, ou `RENDERED` para renderizar de novo; toda cena precisa ter asset) ·
`422` id inválido · `503` banco indisponível. O resultado do render (inclusive falha) vem pela consulta, não pela resposta do `POST`.

## O que é produzido
- **Narração**: porta `Voice` (`STUDIO_VOICE`, padrão `piper:pt_BR-faber-medium`). Voz que devolve silêncio é recusada (a trilha musical esconderia o defeito do QA).
- **Vídeo**: `short` 1080×1920 e `long` 1920×1080, 25 fps, H.264 + AAC; Ken Burns por cena, selo (`label`), aviso de imagem sintética
  (ou "Imagens ilustrativas" se algum asset for do `stock`) e fades. Trilha original sintetizada com ducking sob a voz e `loudnorm` (alvo −16 LUFS).
- **Legenda**: a **narração** dividida em trechos (até 42 caracteres, quebrando em frase, vírgula e palavra), com o tempo de cada trecho
  proporcional ao seu tamanho dentro da duração da fala (sem alinhamento forçado por modelo). Queimada no vídeo e exportada em `.srt`.
  O campo `caption` do roteiro não é mais desenhado: a legenda é o que foi narrado e checado pelo gate factual.
- Arquivos em `storage/projects/<projeto>/videos/<vídeo>/final.mp4|final.srt` (escrita atômica; intermediários em `work/` são apagados).
  O MP4 é registrado como `Asset(kind=video)`.

## QA (`qa_report`)
Medido com `ffprobe`, `ebur128`, `silencedetect` e `blackdetect`; a decisão é do domínio (`domain/render.py`). **Reprova** quando:
sem faixa de áudio · áudio mudo (< −45 LUFS) ou estourado (> −9 LUFS) · mais de 60% em silêncio · mais de 30% preto ·
duração fora do limite (**short 175 s**, **long 1200 s**) ou menor que 2 s · duração diferente da planejada (> 1 s) · resolução errada ·
métrica ausente (falha fechada). Um vídeo que passaria do limite de duração **nem é renderizado**: o job falha com a causa.

| Resultado | Job | Vídeo |
|---|---|---|
| QA aprova | `SUCCEEDED` | `AWAITING_APPROVAL` |
| QA reprova | `SUCCEEDED` (arquivo existe para inspeção) | fica `RENDERED` com `qa_report.passed=false`; dá para renderizar de novo |
| falha técnica (voz, ffmpeg, disco) ou acima do limite | `FAILED` + `error` | continua `ASSETS_READY` |

A P05 (aprovação) decide o que fazer com um vídeo `RENDERED` que reprovou no QA (override com motivo).

## Fila e reinício
`RENDER_CONCURRENCY` (padrão 1, máximo 4) limita os renders simultâneos; o resto espera na fila. Só existe **um job ativo por vídeo** (índice único
parcial no banco). Se o renderer reiniciar com jobs `QUEUED`/`RUNNING`, eles viram `FAILED` ("interrupted by a restart") na subida e o `POST /render` tenta de novo.
O `/transition` genérico recusa `RENDERED` e `AWAITING_APPROVAL` (403): só o render chega lá.

## Limites conhecidos
- O hash da entrada do job considera formato, narração, selo e assets (não a voz nem o renderer); não há reaproveitamento de vídeo já pronto.
- A retomada fina de jobs interrompidos e de `FAILED` é a P06.
- O `qa_report` não mede se a legenda está legível nem se a imagem combina com a fala; revisão humana na P05.
- O vídeo final é recodificado sempre inteiro; vídeos longos (muitos minutos) levam tempo proporcional (short de 40 s: ~13 s no Mac/Docker).
- Fala em outro idioma que o da voz (o demo narra o texto em inglês com voz pt-BR) sai com sotaque; o roteiro real é em pt-BR.

## Verificado (stack real, Piper)
Short de 5 cenas: 40,4 s, 1080×1920, −15,8 LUFS, QA aprovado, 13 s de render, `.srt` com trechos proporcionais, vídeo em `AWAITING_APPROVAL`.
Long de 5 cenas: 40,7 s, 1920×1080, −16,0 LUFS, QA aprovado. Nos testes automatizados (FFmpeg real): legenda presente nos quadros,
QA reprova vídeo sem áudio, mudo, preto e fora do limite; falha de renderer fica registrada e a nova tentativa vira `attempt 2`;
duas chamadas seguidas de `/render` enfileiram uma vez só; job órfão é encerrado na subida.
