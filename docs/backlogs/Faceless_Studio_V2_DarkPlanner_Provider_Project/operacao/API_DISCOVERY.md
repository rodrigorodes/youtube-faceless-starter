# DPA-01 — Descoberta e viabilidade da API

> Não existe aqui documento oficial validado de API externa. Esta checklist é requisito de integração, não alegação sobre funcionalidades atuais.

| Pergunta ao fornecedor | Evidência requerida | Gate |
|---|---|---|
| API pública/privada para gerar TTS? | OpenAPI, SDK ou exemplos oficiais de request/response | Bloqueante |
| Como autentica? | Headers, renovação, scopes, política de revogação | Bloqueante |
| TTS síncrono, job assíncrono ou ambos? | Status, polling, webhook, idempotência | Bloqueante |
| Como receber áudio? | Content-type, URL, limites, expiração, codec | Bloqueante |
| PT-BR e seleção de voz? | Catálogo e IDs documentados | Bloqueante |
| Limites de caracteres e rate? | Quotas por chamada/dia/mês, retry-after | Bloqueante |
| Cobrança API / regeneração / falha? | Tabela de preços e política de cobrança | Bloqueante |
| Permite uso em SaaS e BYOK? | Termos de uso, redistribuição, multitenancy | Bloqueante F11 |
| Política de privacidade do roteiro? | Retenção, treinamento, localização, exclusão | Bloqueante F11 |
| SRT, timing por palavra, multi-voz? | Contrato e exemplos testáveis | Opcional F5/F6 |
| Suporte a idempotency keys? | Semântica real e janela de deduplicação | Bloqueante p/ retries automáticos |
| Ambiente de testes? | Chave/sandbox, limites e exemplos | Recomendado |

## Decisão
- **GO:** documentação suficiente para testar autenticação + TTS + download + cobrança + termos adequados.
- **GO CONDICIONAL:** TTS confirmado mas sem idempotência; usar trava local e reconciliação manual, sem retry cego de submit.
- **NO-GO:** sem API automatizável legítima ou termos incompatíveis com o uso pretendido. Manter Piper e arquitetura pronta; não automatizar interface web nem usar endpoints privados não autorizados.

## Artefatos de saída
`darkplanner-api-contract.md` (sem segredos), exemplo sanitizado, matriz de capabilities, custo esperado por 1.000 caracteres e decisão GO/NO-GO datada.
