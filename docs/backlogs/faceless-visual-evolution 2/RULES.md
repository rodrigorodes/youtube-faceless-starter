# Regras de implementação · revisão 2

1. Um RenderPlan canônico, um coordenador e um executor FFmpeg; ampliar contratos existentes.
2. Domain e compilador puros. SDK/HTTP/DB/filesystem/FFmpeg em adapters.
3. Shots base/overlay, timebase em ticks, cobertura base contínua e ordenação determinística.
4. Seguir DECISIONS.md para schema, cache, compatibilidade e flags. Não exigir digest antigo idêntico.
5. Compatibilidade funcional de áudio, duração, legendas, resolução e disclosure. Migração conforme dados reais; sem limpeza automática.
6. N providers por portas/capacidades e composition root. Não acoplar UX a SDK ou enum fechado por fornecedor.
7. Configuração efetiva e snapshots existentes; não criar outra fonte de verdade de estilo/voz.
8. Edição versionada, IDs de cena estáveis, idempotência e conflito explícito; sem last-write-wins silencioso.
9. Salvar rascunho não gera mídia. Geração respeita custo estimado, limite, reserva e reconciliação.
10. Fallback não muda voz, identidade, direitos ou limite financeiro silenciosamente.
11. QA com evidência; sem avaliação semântica = not_verified, nunca pass inventado.
12. Aprovação vinculada ao render/checksum; publicar valida revisão, autorização e destino no servidor.
13. Revisão local não altera publicação concluída. Intenção de envio obsoleta é bloqueada.
14. Autorização derivada da sessão e membership; nunca confiar em organization_id enviado pelo cliente.
15. Assets privados, cache, jobs, URLs e credenciais também precisam de escopo de conta.
16. Reusar V3.1 e evitar colisões de Settings, estilos, effective_config e budget.
17. Timeline simples e edição por cena; sem NLE completo, segundo workflow ou nova SPA obrigatória.
18. Testes do produto em container com Postgres; registrar evidências reais. Demo offline não é teste de renderer.
19. Licença/proveniência de mídia obrigatórias; URLs externas tratadas no adapter com validação.
20. Documentar status como implementado/parcial/proposto/desconhecido; não promover protótipo a funcionalidade.
