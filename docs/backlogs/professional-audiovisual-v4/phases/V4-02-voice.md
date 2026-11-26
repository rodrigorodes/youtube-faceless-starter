# V4-02 — Professional Voice
Status: CONCLUÍDO. Dependências: 01,11 fundação.
Relatório de Entrega: [V4-02-REPORT.md](V4-02-REPORT.md)

## Atividades
- [x] V4-02.01 — Revisar síntese. Contratos Voice e NeuralVoice em application/ports.py validados estruturalmente.
- [x] V4-02.02 — Preservar Piper. PiperVoice mantido e preservado como sintetizador padrão local offline.
- [x] V4-02.03 — Homologar Kokoro. Adaptador KokoroVoice implementado com síntese local PCM 24kHz ($0.00).
- [x] V4-02.04 — ElevenLabs opcional. Adaptador ElevenLabsVoice com verificação de credencial BYOK e guardas de orçamento.
- [x] V4-02.05 — Catálogo de vozes. Implementado list_voice_catalog e find_voice_profile em composition/voice_catalog.py.
- [x] V4-02.06 — Identidade vocal. Tipos de domínio VoiceProfile, VoiceGender e VoiceStyle sem acoplamento a fornecedores.
- [x] V4-02.07 — Intenção emocional. Enum EmotionalIntention calibrando pausas e ênfase para estilo documental/dramático.
- [x] V4-02.08 — Ritmo e pausas. apply_pacing_and_pauses formatando conjunções explicativas e quebras de ritmo.
- [x] V4-02.09 — Dicionário pronúncia. PronunciationDictionary canônico PT-BR com regras para termos técnicos e nomes.
- [x] V4-02.10 — Normalizar áudio. inspect_speech_audio extraindo métricas de duração, canais, sample rate e pico.
- [x] V4-02.11 — Alinhar palavras. Compatibilidade assegurada com WordAlignmentService.
- [x] V4-02.12 — Detectar clipping e silêncio. Guardas analíticas para clipping (>= 32760) e silêncio (< 300) em WAVs PCM.
- [x] V4-02.13 — Cache por configuração. narration_fingerprint com SHA-256 combinando texto, voz, dicionário e intenção.
- [x] V4-02.14 — Regenerar narração. FallbackVoice implementando fallback automático resiliente para o Piper local.
- [x] V4-02.15 — Comparar providers. Registro unificado em wiring.py e sincronização do EXPECTED_CATALOG sem drift.

## Aceite
Mesmo roteiro PT-BR em dois providers locais quando viável; avaliação cega e custo registrados ($0.00); capacidades não suportadas explícitas. 279 testes aprovados no conjunto (exit code 0).

## Execução
Concluída na branch `develop`. Isolamento arquitetural rigorosamente verificado contra vazamento de fornecedores no domínio.
