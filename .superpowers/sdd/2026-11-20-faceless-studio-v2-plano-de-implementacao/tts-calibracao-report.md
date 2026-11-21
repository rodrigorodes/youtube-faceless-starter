# Calibração real de TTS (F4-03) — Piper pt_BR-faber-medium

Worktree: `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/tts-calibracao`
Branch: `feat/tts-calibracao` · base `db8eebb`

## Resultado em uma linha

O Piper **rodou de verdade** com a **voz exata do produto** (`piper:pt_BR-faber-medium`,
piper-tts 1.8.0, sha256 `75e913eb…b8ffc`, o mesmo do `renderer/Dockerfile`): **26
sínteses × 3 execuções** (mais uma quarta no teste). O ritmo efetivo medido é **172
palavras/minuto**, não as 150 da hipótese anterior; a 150 o roteiro de ~480 s era estimado
em **477,2 s** quando a voz leva **412,7 s** (+15,6%). Aplicado como padrão calibrado
(`DEFAULT_WORDS_PER_MINUTE = 172`) e como modelo medido com pausas
(`estimate_voice_durations`), com teste que compara estimativa × WAV real.

## A voz e o ambiente (verificados, não supostos)

| item | valor |
|---|---|
| voz | `piper:pt_BR-faber-medium` (a de `renderer/app/studio/application/config.py`) |
| modelo | `pt_BR-faber-medium.onnx` sha256 `75e913eb463db0b6ac7ddf68d3e4c9ac19ace36dc3b710a81039b448352b8ffc` |
| config | `pt_BR-faber-medium.onnx.json` sha256 `6b6801319e5a70aa4d75c63343515f55d1cd671ecd1ac511586bc16216812261` |
| hashes | os dois conferem com o `sha256sum -c` do `renderer/Dockerfile` |
| piper-tts | 1.8.0 (a de `renderer/requirements.txt`), Python 3.12.16 |
| imagem | `faceless-v2-hygiene-test-local:latest` — já traz Piper e a voz em `/opt/voices` |
| síntese | `PiperVoice.load(...).synthesize_wav(texto, wav)` — o mesmo caminho do `PiperVoice.speak` |
| medição | quadros / taxa do WAV (`wave`), uma síntese por texto, como o renderer faz por cena |

A execução 1 usou a imagem `yfs-test` com a voz extraída da imagem do renderer (hash
conferido). As execuções 2 e 3 usaram a imagem canônica de testes, sem montagem:
`/opt/voices` e `PIPER_VOICE` já estão na imagem. Nenhuma execução usou rede. O script
recusa rodar se o sha256 da voz não for o do produto.

## Corpus (`scripts/tts_calibration_samples.json`)

Cada item é sintetizado texto a texto (não um bloco gigante), porque o produto sintetiza
**por cena** (`PiperVoice.speak` por `Scene.narration`, limite de 400 caracteres).

| amostra | o que cobre | textos | palavras* | marcas de pausa |
|---|---|---|---|---|
| `curto_uma_frase` | fala mínima | 1 | 8 | 1 |
| `curto_pontuado` | pergunta + exclamação + vírgula em pouco texto | 1 | 7 | 4 |
| `frases_curtas` | 10 frases curtas, muito ponto/interrogação | 1 | 26 | 10 |
| `prosa_pontuada` | parágrafo natural | 1 | 58 | 10 |
| `prosa_sem_pontuacao` | **as mesmas palavras**, sem pontuação: isola a pausa | 1 | 58 | 0 |
| `numeros_siglas` | `2026`, `5,7 milhões`, `R$ 1.200.000,00`, `2,3%`, `1º`, `IBGE`, `ONU`, `FMI`, `CEO`, `IA` | 1 | 53 | 13 |
| `longo_480s` | roteiro documental em **20 cenas** (todas ≤ 400 caracteres) | 20 | 1.193 | 176 |

\* contagem da própria função do domínio (`_WORD`), não `split()`.

Total: **26 utterances, 1.403 palavras**.

## Números medidos (três execuções independentes)

Duração real do WAV, em segundos (execução 1 / 2 / 3), maior variação entre execuções, e
as três estimativas. Colunas de erro na ordem das três execuções:

| amostra | real (exec 1/2/3) | spread | estim. @150 | erro @150 | estim. @172 | erro @172 | modelo medido | erro modelo |
|---|---|---|---|---|---|---|---|---|
| curto_uma_frase | 2,740 / 2,844 / 2,786 | 3,8% | 3,20 | +16,8 / +12,5 / +14,8% | 2,79 | +1,9 / −1,9 / +0,2% | 3,26 | +19,0 / +14,6 / +17,0% |
| curto_pontuado | 3,634 / 3,715 / 3,738 | 2,9% | 2,80 | −22,9 / −24,6 / −25,1% | 2,44 | −32,8 / −34,3 / −34,7% | 4,18 | +15,2 / +12,6 / +11,9% |
| frases_curtas | 12,608 / 12,562 / 12,678 | 0,9% | 10,40 | −17,5 / −17,2 / −18,0% | 9,07 | −28,1 / −27,8 / −28,5% | 11,84 | −6,1 / −5,8 / −6,6% |
| prosa_pontuada | 20,294 / 20,341 / 20,434 | 0,7% | 23,20 | +14,3 / +14,1 / +13,5% | 20,23 | −0,3 / −0,5 / −1,0% | 20,68 | +1,9 / +1,7 / +1,2% |
| prosa_sem_pontuacao | 17,160 / 16,985 / 17,160 | 1,0% | 23,20 | +35,2 / +36,6 / +35,2% | 20,23 | +17,9 / +19,1 / +17,9% | 16,68 | −2,8 / −1,8 / −2,8% |
| numeros_siglas | 20,317 / 20,155 / 20,225 | 0,8% | 21,20 | +4,3 / +5,2 / +4,8% | 18,49 | −9,0 / −8,3 / −8,6% | 20,50 | +0,9 / +1,7 / +1,4% |
| **longo_480s** | **412,688 / 412,735 / 412,851** | **0,04%** | **477,20** | **+15,6 / +15,6 / +15,6%** | **416,16** | **+0,8 / +0,8 / +0,8%** | **413,11** | **+0,1 / +0,1 / +0,1%** |

Estimativa @150 e @172 são a fórmula pura do domínio; "modelo medido" é
`estimate_voice_durations` (constantes finais). Agregados:

| grandeza | exec 1 | exec 2 | exec 3 | usado no código |
|---|---|---|---|---|
| palavras/minuto efetivas (com pausas) | 172,0 | 172,0 | 171,8 | **172,0** |
| ritmo de fala (regressão, sem pausas) | 216,7 | 217,2 | 217,4 | **217,1** |
| segundos por marca de pausa (regressão) | 0,402 | 0,394 | 0,395 | **0,40** |
| silêncio de borda por síntese | 0,577 | 0,672 | 0,693 | **0,65** |
| pausa por marca, par com/sem pontuação | 0,313 | 0,336 | 0,327 | referência: 0,31–0,34 |
| relógio de parede das 26 sínteses | 32,1 s | 57,6 s | 54,5 s | máquina carregada |

Regressão por utterance: `segundos = 0,65 + palavras × 60/217,1 + pausas × 0,40`.
As constantes são a **média** das três execuções; cada número cru está na evidência.

Erro por cena do roteiro longo, com a hipótese calibrada (172 wpm): **−6,1% a +11,0%** por
cena, **+0,8%** no total. Com o modelo com pausas: **+0,1%** no total.

### O que os números dizem

1. **O padrão de 150 palavras/minuto estava errado para esta voz.** A fala real é ~217
   palavras/minuto; com pausas, ~172. Trocar o padrão para 172 leva o total do roteiro de
   480 s de +15,6% de erro para +0,8%.
2. **Pausa custa tempo de verdade.** Mesmas 58 palavras: 20,29 s com pontuação × 17,16 s
   sem = **+3,13 s para 10 marcas (0,31 s cada)**. Texto curto e pontuado é o pior caso:
   7 palavras em 3,63 s (0,52 s por palavra) contra 8 palavras em 2,74 s no texto corrido.
   Uma taxa única não cobre isso; por isso o modelo com pausas.
3. **Números e siglas não são "uma palavra cada" para o Piper.** `5,7 milhões`,
   `R$ 1.200.000,00` e siglas soletradas fazem o texto ter mais fala do que a contagem
   sugere: −8% a −9% de erro na hipótese pura; o modelo com pausas fecha em +1%.
4. **O Piper varia a duração entre execuções** (predição de duração estocástica):
   até 3,8% no texto de 8 palavras, ≤1% nas amostras ≥ 26 palavras e 0,04% no roteiro de
   20 cenas. A tolerância declarada leva isso em conta.

## O que foi aplicado

`renderer/app/studio/domain/narration_duration.py` (API existente **intacta**):

- constantes documentadas com a proveniência e os três números medidos:
  `MEASURED_VOICE`, `MEASURED_PIPER_VERSION`, `MEASURED_SPEECH_WORDS_PER_MINUTE = 217.1`,
  `MEASURED_PAUSE_SECONDS = 0.40`, `MEASURED_UTTERANCE_OVERHEAD_SECONDS = 0.65`,
  `MEASURED_EFFECTIVE_WORDS_PER_MINUTE = 172.0`;
- `estimate_voice_durations(texts)`: modelo medido do WAV (overhead por síntese + fala +
  pausas). Não substitui a API configurável; é a medição explícita;
- `estimate_text_durations`/`estimate_narration_durations`: inalteradas na assinatura e na
  matemática; docstrings passam a apontar a medição. Nenhum teste de duração da F4 mudou.

`renderer/app/studio/application/longform.py`:

- `DEFAULT_WORDS_PER_MINUTE` passou de `150.0` para `MEASURED_EFFECTIVE_WORDS_PER_MINUTE`
  (`172.0`). Continua configurável por chamada; só o padrão reflete a voz real.

Não foi alterado `domain/render_plan.py`, `domain/ticks.py`, `contracts/`,
`scripts/export_contracts.py`, o painel (`api/panel.py`) nem arquivos de outras trilhas.
**Nenhuma migração** — nada toca o banco.

## Reprodução

```sh
# medir e gravar uma execução de evidência (imagem canônica; já tem Piper + voz)
docker run --rm --network none -v "$PWD:/workspace" -w /workspace \
  -e PYTHONPATH=/workspace/renderer --entrypoint python \
  faceless-v2-hygiene-test-local:latest scripts/tts_calibration.py \
  --out .superpowers/sdd/2026-11-20-faceless-studio-v2-plano-de-implementacao/tts-calibracao-evidence-run1.json

# teste que compara estimativa x WAV real (sem Piper/voz, pula com motivo)
docker run --rm --network none -v "$PWD:/workspace:ro" -w /workspace \
  -e PYTHONPATH=/workspace/renderer --entrypoint python \
  faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider \
  tests/test_tts_calibration.py
```

Evidência bruta (JSON com cada utterance, palavras, pausas, segundos e a regressão):

- `.superpowers/sdd/2026-11-20-faceless-studio-v2-plano-de-implementacao/tts-calibracao-evidence-run1.json`
- `.superpowers/sdd/2026-11-20-faceless-studio-v2-plano-de-implementacao/tts-calibracao-evidence-run2.json`
- `.superpowers/sdd/2026-11-20-faceless-studio-v2-plano-de-implementacao/tts-calibracao-evidence-run3.json`

## Testes

`tests/test_tts_calibration.py` (novo, 6 testes):

- model × WAV real: **≤ 25%** por amostra e **≤ 10%** para textos ≥ 20 palavras (a faixa
  folgada cobre a variação própria da síntese em texto de 7–8 palavras);
- hipótese calibrada (172) no roteiro de 480 s: **≤ 10%** no total e **≤ 15%** por cena,
  e também em prosa natural e números/siglas;
- pausa: Δ com/sem pontuação > 2,0 s e ≈ 10 × 0,40 s (±1,0 s);
- números/siglas: modelo **≤ 10%**;
- constantes × as três evidências gravadas (ritmo, pausa, overhead, voz/hash/versão);
- três execuções concordam em **≤ 5%** por amostra.

Sem Piper, sem a voz do produto, com versão ou **sha256** diferente, os 4 testes de
síntese são **pulados com motivo** explícito — nunca inventam número. O teste confere a
voz antes de importar `piper` (o import carrega onnxruntime e é caro).

O corpus é sintetizado de verdade: a execução do teste levou **48,9 s** e passou **6/6**
(uma execução anterior, com 5 testes, levou 61,9 s).

Não-DB, foco na fatia (imagem de testes, `-p no:cacheprovider`):

- `test_narration_duration + test_longform_domain + test_longform_editorial +
  test_longform_480s + test_architecture + test_contracts + test_contracts_snapshot +
  constants/run-to-run` → **65 passed**; com os testes novos do modelo, **21 passed** no
  subconjunto rápido.
- Suíte inteira **sem DSN** e **sem** `test_tts_calibration`: **1488 passed, 467
  skipped, 9 failed**. As 9 falhas são `test_render_adapters`, todas com
  `subprocess.CalledProcessError: ffmpeg … died with SIGKILL` — o OOM killer da máquina
  matou o `ffmpeg` (havia ~60 MB livres e 19 contêineres de outras fatias). Isolado, o
  arquivo ainda falhou 4 testes pelo mesmo SIGKILL: é ambiente, não código desta fatia
  (não toquei em render). A suíte com DSN fica para a validação do coordenador.

## Pendências e limites (explícitos)

- **Prosódia continua fora**: a duração do WAV é medida; entonação, ênfase e pausas
  sintáticas reais não são modeladas. A estimativa é a fala esperada, não a duração exata
  daquela síntese.
- **Uma voz, um ritmo**: só `pt_BR-faber-medium` em `length_scale` padrão. Outra voz ou
  outro ritmo invalidam as constantes (o teste recusa por hash/versão).
- **LEAD/TAIL do renderer não entram**: `rich.py` soma 0,30 + 0,50 s por cena e arredonda
  para quadros de 25 fps. Em 20 cenas isso é ~+9,6 s (+2,3%) sobre a fala; a estimativa do
  domínio é de fala, como `wav_duration`.
- **Sem calibração do DarkPlanner**: o adaptador não está implementado/habilitado; não
  havia voz para medir.
- **`F4-03`**: o item "validada contra velocidade real do TTS" passa a ter medição real
  desta voz, constante aplicada e teste com tolerância declarada. A duração por cena exata
  só existe depois do TTS — isso permanece, como o próprio produto já avisa. A linha de
  status em `docs/.../STATUS-EXECUCAO.md` não foi editada nesta worktree para não colidir
  com as outras fatias; o coordenador decide a marcação.