# Regras
- Um único Composition Core e registry; SDKs somente em adapters.
- RenderPlan neutro e versionado; sem comandos específicos de renderer no domínio.
- Compatibilidade de leitura v1/v2; migração reversível e fixtures.
- Fallback explícito, orçamento e capability preflight; não simular sucesso.
- Licença desconhecida não é CC0; bloquear publicação.
- Cache por conteúdo e configuração, idempotência e invalidação transitiva.
- Identidade por canal congelada no run; preservar UX e edição humana.
- Testes e render real por incremento; sem microserviços prematuros.
- Não publicar, gastar ou avançar gate crítico sem aprovação.
