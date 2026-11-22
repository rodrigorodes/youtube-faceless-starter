"""Proveniência da calibração do TTS do produto — fora do domínio.

A calibração de ``domain.narration_duration`` é uma **medição** feita com uma voz concreta
(``piper:pt_BR-faber-medium``, piper-tts 1.8.0). O domínio não pode citar nome de fornecedor
(guarda S7 em ``tests/test_architecture.py``), então a identidade da voz e da versão medidas
moram aqui, na raiz do pacote, e são usadas pelos testes de calibração e pelo relatório.

Nenhum código de produção depende destes valores: a regressão de duração vive no domínio e
recebe só números (palavras/minuto, pausa, overhead).
"""

# Voz e versão do sintetizador usadas nas 26 sínteses reais da calibração.
MEASURED_VOICE = "piper:pt_BR-faber-medium"
MEASURED_PIPER_VERSION = "1.8.0"
