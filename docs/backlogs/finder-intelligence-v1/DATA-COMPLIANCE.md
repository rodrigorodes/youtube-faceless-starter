# FI-00 — Data Compliance Gate (P0)
Antes de coletar, calcular ou armazenar dados reais, responsável técnico deve validar documentação vigente e aprovação aplicável; nenhum acesso comercial presumido. Referências oficiais a conferir e registrar data/versão:
- https://developers.google.com/youtube/terms/developer-policies
- https://developers.google.com/youtube/terms/api-services-terms-of-service
- https://developers.google.com/youtube/v3/docs/search/list
- https://developers.google.com/youtube/v3/docs/captions/download
- https://support.google.com/youtube/answer/1311392
## Matriz
| Capacidade | Regra |
|---|---|
| Dados públicos | API autorizada; cotas, cache, refresh/retenção e remoção conforme termos |
| VPH, outlier, scores, histórico | checar permissões para dados derivados e históricos, termos adicionais e aprovação quando aplicável; desabilitar até GO |
| Monetização de terceiro | desconhecida por padrão; não inferir YPP por ads ou sinais de página; conta própria somente dados autorizados |
| Receita de terceiro | não afirmar real; não oferecer projeção sem base/autorização |
| Transcrição | somente conteúdo próprio/autorizado e mecanismo permitido; API captions.download exige autorização adequada |
| Thumbnail/filmagem | referência não é licença; export/import somente com direitos e mecanismo autorizado |
| Providers terceiros | autorização contratual, origem, licença, retenção, custo, segurança e quotas; não contornar limites com projetos/chaves |
| Extensão | menor privilégio, sem scraping não autorizado, sem credenciais em DOM/log, consentimento e exclusão de dados |
Entregar matriz capability → fonte → permissão → retenção → evidência → owner → decisão, com revisão dos scores existentes. Bloquear em runtime por capability/policy (default deny quando desconhecido); fixtures sintéticas para POC offline; nenhum bypass para produção. Dados insuficientes = unknown, não zero. Não coletar privados nem publicar sem autorização.
