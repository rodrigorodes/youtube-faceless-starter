# Voz, render e qualidade

**Prefixo dos cenários:** `REN`

> Arquivo gerado por `gerar.py` a partir de `dados/`. Não editar à mão; altere os dados e gere de novo.

## Como funciona

StartRender cria/reutiliza job e despacha só o recém-criado. RunRender resolve configuração, narra ou reutiliza WAV íntegro, calcula durações, monta cues, renderiza e mede QA antes de publicar. RenderPlan separa plano, compilação e execução FFmpeg. Cache invalida dependentes e recompõe final quando alguma cena muda.

## Regras desta funcionalidade

| Regra | O que exige | Fontes | Cenários |
|---|---|---|---|
| `REN.R01` | Render aceita ASSETS_READY/RENDERED; enqueue repetido só dispara execução quando created; falha na fila marca job e retorna indisponibilidade. | `renderer/app/studio/application/render.py:138-154` | [REN-01](#ren-01) |
| `REN.R02` | Voz e estilo partem de configuração da execução; narração cacheada exige fingerprint texto/voz e SHA físico; duração de WAV reutilizado é medida. | `renderer/app/studio/application/render.py:238-334` | [REN-02](#ren-02), [REN-03](#ren-03) |
| `REN.R03` | Cenas incluem 0.30 s de lead e 0.50 s de tail arredondados a 25 fps; limites short=175 s e long=1200 s; cues são proporcionais, sem alinhamento forçado. | `renderer/app/studio/domain/render.py:8-22`, `renderer/app/studio/domain/render.py:50-109`, `renderer/app/studio/application/render.py:335-352` | [REN-04](#ren-04), [REN-05](#ren-05), [REN-07](#ren-07) |
| `REN.R04` | Áudio seleciona faixa por tags ou primeira como fallback; mix declara ganho/ducking/fades; compilador aplica sidechaincompress e loudnorm. | `renderer/app/studio/application/audio_director.py:28-88`, `renderer/app/studio/adapters/render_plan_compiler.py:46-83` | [REN-06](#ren-06) |
| `REN.R05` | Executor roda shots/concat/mix, admite reúso físico e timeout proporcional; checa quantidade de arquivos de fala. | `renderer/app/studio/adapters/render_plan_ffmpeg.py:678-746` | [REN-07](#ren-07), [REN-08](#ren-08), [REN-11](#ren-11) |
| `REN.R06` | QA incompleto declara not_verified; clipping acima de 0 dBTP bloqueia, codecs incompatíveis bloqueiam e congelamento acima de 20% gera warning. | `renderer/app/studio/domain/quality.py:227-332` | [REN-06](#ren-06), [REN-09](#ren-09) |
| `REN.R07` | Publicação exige job ainda vivo; complete precede prune; falhas técnicas viram FAILED e limpeza é tentada no finally. | `renderer/app/studio/application/render.py:198-236`, `renderer/app/studio/application/render.py:359-373` | [REN-08](#ren-08), [REN-10](#ren-10) |
| `REN.R08` | Regeneração compara fingerprints por nó e invalida final por dependência; decisão não executa FFmpeg nem verifica arquivo físico. | `renderer/app/studio/application/render_cache.py:7-15`, `renderer/app/studio/application/render_cache.py:65-91` | [REN-03](#ren-03), [REN-11](#ren-11) |
| `REN.R09` | Regeneração de narração individual usa temporário fixo por cena, salva duração e usa chave paga narration:video:scene, sem texto/voz na chave. | `renderer/app/studio/application/scene_narration.py:103-137` | [REN-12](#ren-12) |

## Resumo dos cenários

Total: 12 cenário(s), todos documentais nesta elaboração.

| ID | Cenário | Tipo | Regras | Status |
|---|---|---|---|---|
| [REN-01](#ren-01) | Enfileirar render uma única vez | feliz/concorrencia/erro | REN.R01 | `A_PROJETAR` |
| [REN-02](#ren-02) | Voz e estilo usam snapshot estável | feliz/regressao | REN.R02 | `A_PROJETAR` |
| [REN-03](#ren-03) | Cache de narração preserva duração real | feliz/erro/regressao | REN.R02, REN.R08 | `A_PROJETAR` |
| [REN-04](#ren-04) | Duração por quadros e teto de formato | borda/volume/erro | REN.R03 | `A_PROJETAR` |
| [REN-05](#ren-05) | Legendas proporcionais e texto narrado | feliz/borda/regressao | REN.R03 | `A_PROJETAR` |
| [REN-06](#ren-06) | Música, fallback e ducking sem mascarar voz | feliz/erro/regressao | REN.R04, REN.R06 | `A_PROJETAR` |
| [REN-07](#ren-07) | Plano multishot compilado e executado | feliz/regressao | REN.R03, REN.R05 | `A_PROJETAR` |
| [REN-08](#ren-08) | Falha e timeout FFmpeg não publicam sucesso | erro | REN.R05, REN.R07 | `A_PROJETAR` |
| [REN-09](#ren-09) | QA incompleto e métricas de fronteira | erro/borda | REN.R06 | `A_PROJETAR` |
| [REN-10](#ren-10) | Perda de posse antes de publicar resultado | concorrencia/erro | REN.R07 | `A_PROJETAR` |
| [REN-11](#ren-11) | Invalidar só dependências e recompor final | regressao/volume | REN.R08, REN.R05 | `A_PROJETAR` |
| [REN-12](#ren-12) | Regeneração individual de voz e colisões | feliz/concorrencia/erro | REN.R09 | `A_PROJETAR` |

## Cenários

### REN-01 — Enfileirar render uma única vez

- **Tipo:** feliz/concorrencia/erro
- **Regras:** REN.R01
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Separar aceitação do job de conclusão do vídeo.
- **Pré-condições:** Vídeo ASSETS_READY com assets; repository real em banco descartável futuro.
- **Dados:** Duas chamadas simultâneas para mesmo vídeo; enqueue espião.
- **Passos:**
  1. Disparar chamadas com barreira.
  2. Consultar job devolvido por ambas.
  3. Em fixture nova fazer enqueue levantar erro; tentar também SCRIPTED.
- **Esperado:** Mesmo job ativo e um despacho; erro de fila tenta marcar FAILED e informa indisponibilidade; estado inválido não cria job.
- **Limitações:** Aceitar/enfileirar não comprova arquivo pronto ou QA aprovado.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_render_repo.py e tests/test_render_api.py; concorrência por barreira proposta.`

### REN-02 — Voz e estilo usam snapshot estável

- **Tipo:** feliz/regressao
- **Regras:** REN.R02
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Evitar misturar revisões de configuração no mesmo render.
- **Pré-condições:** Run resolvido com voz A; provider TTS dublê; config_store espião.
- **Dados:** Snapshot h1/voz A/estilo azul; configuração viva muda para h2/voz B/vermelho.
- **Passos:**
  1. Iniciar render do run h1.
  2. Alterar configuração viva enquanto TTS está bloqueado e liberar.
  3. Comparar voz, estilo e config_snapshot do RenderSpec.
- **Esperado:** Render do run resolvido permanece em h1; voz e estilo correspondem ao mesmo snapshot; render avulso resolve uma vez.
- **Limitações:** Run legado tem caminho próprio; ausência de snapshot legível não deve ser tratada como reprodução comprovada.
- **Automação:** camada `mock`; referência `Existentes: tests/test_render.py e tests/test_effective_config.py; interleaving proposto.`

### REN-03 — Cache de narração preserva duração real

- **Tipo:** feliz/erro/regressao
- **Regras:** REN.R02, REN.R08
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Pular TTS somente com entrada e arquivo íntegros.
- **Pré-condições:** Duas cenas com entries e WAVs sintéticos; provider espião.
- **Dados:** WAV A de 6.8 s; texto/voz iguais; variantes SHA corrompido e voz alterada.
- **Passos:**
  1. Renderizar sem alteração.
  2. Modificar somente narração de B e repetir.
  3. Corromper WAV A ou alterar voz em fixtures separadas.
- **Esperado:** A inalterada não chama TTS e usa duração do WAV; B alterada sintetiza; corrupção/voz diferente impedem reúso.
- **Limitações:** Fingerprint aceito no plano não substitui integridade física; não usar áudios de produção.
- **Automação:** camada `local-integrado`; referência `Existente: tests/test_render_reuse.py:342-383.`

### REN-04 — Duração por quadros e teto de formato

- **Tipo:** borda/volume/erro
- **Regras:** REN.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Recusar vídeo acima do teto antes de executar renderer.
- **Pré-condições:** Voice dublê retorna durações controladas; renderer espião.
- **Dados:** Fala 6.8 s resulta cena 7.6 s; lotes cuja soma é 175/175.04 s e 1200/1200.04 s.
- **Passos:**
  1. Calcular duração por cena com lead/tail.
  2. Renderizar fixtures no teto e um quadro acima.
  3. Usar 100 cenas curtas para verificar acumulação e offsets.
- **Esperado:** Duração é múltipla de 1/25 s; acima do teto falha antes do renderer; no teto passa esta validação, sujeito às demais regras.
- **Limitações:** Tempo estimado por palavras não é duração final; lote não estabelece meta de desempenho.
- **Automação:** camada `mock`; referência `Existentes: tests/test_narration_duration.py, tests/test_render.py e tests/test_render_plan_timeline.py; matriz de limites proposta.`

### REN-05 — Legendas proporcionais e texto narrado

- **Tipo:** feliz/borda/regressao
- **Regras:** REN.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Manter cues dentro da fala e exportar SRT coerente.
- **Pré-condições:** Funções puras; cena com narration diferente de caption.
- **Dados:** Fala de 10 s, offset=7.6 s, palavra de 90 caracteres, acentos e vírgulas.
- **Passos:**
  1. Gerar chunks/cues e serializar SRT.
  2. Comparar início com offset+0.30 e fim com início+10.
  3. Verificar sequência, limite de 42 caracteres e origem do texto.
- **Esperado:** Trechos não vazios, sem sobreposição e proporcionais ao tamanho; palavra longa é partida; SRT usa narration e numeração crescente.
- **Limitações:** Não há alinhamento fonético/palavra a palavra; legibilidade e sincronismo percebido exigem revisão manual futura.
- **Automação:** camada `unit`; referência `Existentes: tests/test_render_domain.py e tests/test_captions_ass.py; matriz de texto longo proposta.`

### REN-06 — Música, fallback e ducking sem mascarar voz

- **Tipo:** feliz/erro/regressao
- **Regras:** REN.R04, REN.R06
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Verificar mix configurado e voz separadamente.
- **Pré-condições:** Catálogo sintético com faixas licenciadas; plano com AudioMix.
- **Dados:** Tom sci-fi; uma faixa scifi, outra calma; music_gain=0.35, ducking_ratio=12.
- **Passos:**
  1. Selecionar faixa por tag, por tom sem correspondência e catálogo vazio.
  2. Compilar mix e conferir parâmetros.
  3. Em integração futura misturar música audível com narração silenciosa e medir QA isolado da voz.
- **Esperado:** Tag seleciona faixa compatível; sem match usa primeira; vazio retorna None; mix contém ducking/loudnorm; música não deve fazer voz silenciosa parecer válida no QA.
- **Limitações:** Seleção por tags não comprova adequação artística nem licença do arquivo efetivamente usado.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_audio_director.py, tests/test_music_catalog.py e tests/test_quality_ffmpeg_v2.py; combinação proposta.`

### REN-07 — Plano multishot compilado e executado

- **Tipo:** feliz/regressao
- **Regras:** REN.R03, REN.R05
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Verificar que plano declarado corresponde ao vídeo produzido.
- **Pré-condições:** Futura instalação local de FFmpeg; imagens sintéticas vermelha/verde/azul; fala WAV local.
- **Dados:** Cena 7.6 s com shots 2/3/2.6 s e legenda com acento.
- **Passos:**
  1. Compilar e executar somente em diretório descartável.
  2. Amostrar quadros no meio de cada shot.
  3. Conferir ordem, dimensões, áudio e duração via probe.
- **Esperado:** Quadros mostram sequência declarada; áudio e legenda acompanham timeline; saída respeita formato short/long e tolerância de duração do QA.
- **Limitações:** Caso proposto não foi executado; validação de args isolada não prova render real.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_render_plan_multishot_e2e.py e tests/test_render_plan_ffmpeg_audiovisual.py.`

### REN-08 — Falha e timeout FFmpeg não publicam sucesso

- **Tipo:** erro
- **Regras:** REN.R05, REN.R07
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Conservar estado e diagnóstico diante de erro técnico.
- **Pré-condições:** Runner injetado, files/jobs espiões; vídeo ASSETS_READY.
- **Dados:** Plano de 480 s; timeout_floor=300; falhas no shot, concat e mix.
- **Passos:**
  1. Capturar timeout esperado 1740 s nos comandos.
  2. Simular erro/timeout em cada etapa.
  3. Inspecionar FAILED, cleanup, publish e prune.
- **Esperado:** Falha técnica não completa job nem publica sucesso; causa fica no job com caminho work sanitizado; limpeza é tentada; prune não apaga vencedor anterior.
- **Limitações:** Timeout do subprocesso não significa rollback de arquivos intermediários; falha simultânea do banco pode impedir registro de FAILED.
- **Automação:** camada `mock`; referência `Existentes: tests/test_render_plan_executor.py e tests/test_render.py; matriz de falhas proposta.`

### REN-09 — QA incompleto e métricas de fronteira

- **Tipo:** erro/borda
- **Regras:** REN.R06
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Distinguir cobertura, bloqueio e warning.
- **Pré-condições:** Plano válido e QualityEvidence sintética com baseline completo.
- **Dados:** Sem media; sem descriptors; true_peak=0/+0.01/-0.5 dBTP; codec vp9; frozen_ratio=0.20/0.21.
- **Passos:**
  1. Remover métricas/descritores do baseline.
  2. Variar uma métrica por fixture.
  3. Ler coverage, severidade e checks_run.
- **Esperado:** Ausências declaram not_verified; pico positivo e codec incompatível bloqueiam; -0.5 dBTP gera warning; congelamento acima de 20% gera warning, não aprovação semântica.
- **Limitações:** Checks opcionais só rodam quando respectivas métricas existem; não afirmar cobertura multimodal sem provedor.
- **Automação:** camada `unit`; referência `Existentes: tests/test_quality_v2_domain.py e tests/test_quality_semantic_v2.py; matriz proposta.`

### REN-10 — Perda de posse antes de publicar resultado

- **Tipo:** concorrencia/erro
- **Regras:** REN.R07
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Evitar substituir saída por job que perdeu validade.
- **Pré-condições:** Job em execução com MP4 sintético e QA dublê; jobs.alive controlável.
- **Dados:** alive=false após QA; variante complete=false após publish.
- **Passos:**
  1. Encerrar validade antes de checar alive.
  2. Em outra fixture perder comparação na conclusão.
  3. Verificar chamadas publish/complete/prune e arquivo anterior.
- **Esperado:** alive=false bloqueia publish; complete=false impede prune e conclusão vitoriosa; erro é tratado como falha.
- **Limitações:** Janela publish→complete pode deixar arquivo órfão; garantia de zero órfãos não é afirmada. Limpeza transacional seria requisito adicional.
- **Automação:** camada `mock`; referência `Existente: tests/test_render.py; interleavings propostos.`

### REN-11 — Invalidar só dependências e recompor final

- **Tipo:** regressao/volume
- **Regras:** REN.R08, REN.R05
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Evitar TTS e FFmpeg desnecessários sem servir final antigo.
- **Pré-condições:** Plano revision=1 com artefatos íntegros para 20 cenas; índices de cache preenchidos.
- **Dados:** Revision=2 muda apenas asset de S7; variante muda só narração S7; variante sem alterações.
- **Passos:**
  1. Decidir regeneração para cada variante.
  2. Executar com runner espião e comparar nós/chamadas.
  3. Remover entry de nó reutilizável e decidir novamente.
- **Esperado:** Mudança invalida seus dependentes e final; cenas não impactadas reutilizam; entrada ausente aparece missing; sem alteração e com final íntegro pode copiar MP4 final.
- **Limitações:** PlanRegeneration.decide não verifica bytes; integridade precisa ser confirmada pelo executor/resolvedor antes do reúso.
- **Automação:** camada `mock`; referência `Existentes: tests/test_render_regeneration.py e tests/test_render_reuse.py:277-312; lote proposto.`

### REN-12 — Regeneração individual de voz e colisões

- **Tipo:** feliz/concorrencia/erro
- **Regras:** REN.R09
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Caracterizar chave financeira e disputa de temporário por cena.
- **Pré-condições:** Cena editável; TTS dublê; store temporário; guard com estado controlado.
- **Dados:** Mesmo video/scene; texto A muda para B; duas chamadas simultâneas usam .tmp.wav da cena.
- **Passos:**
  1. Regenerar uma vez e conferir duração/SHA/voz.
  2. Repetir com operação paga já CONFIRMED.
  3. Com provider gratuito bloquear duas sínteses no mesmo destino e liberar em ordens opostas.
- **Esperado:** Caso isolado troca WAV e salva duração; paga confirmada não reexecuta automaticamente. Critério de segurança proposto: concorrência deve preservar WAV íntegro coerente com texto/voz e não perder temporário; caracterizar resultado atual sem pressupor lock.
- **Limitações:** Colisão é risco estático, não reprodução realizada. Chave atual não inclui conteúdo/voz; FREE permite replay, pago confirmado exige tratamento distinto.
- **Automação:** camada `mock`; referência `Existente: tests/test_scene_narration.py; concorrência e troca de conteúdo propostas.`

## Resumo do capítulo

12 cenários A_PROJETAR. Plano documental direto, sem workflow e sem executar testes, TTS ou FFmpeg. Referências existentes não são PASS. Futuras medições usam mídia sintética e diretório descartável.
