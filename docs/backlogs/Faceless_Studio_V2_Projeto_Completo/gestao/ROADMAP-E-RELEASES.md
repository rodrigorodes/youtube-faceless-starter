# Roadmap e plano de releases

A ordem numérica de F0–F11 representa **classificação funcional**, não necessariamente ordem estrita de implementação. Cada release é uma **fatia vertical utilizável**.

| Marco | Fases | Demo obrigatória | Liberação |
|---|---|---|---|
| M0 Base confiável | F0 | CI + export seguro + inventário | Dev |
| M1 Primeiro vídeo guiado | F1 + F2 (mínimos) | Ideia → run → estados → aprovação; stub de media | Interna |
| M2 Conteúdo 8 min | F3 + F4 | Tendência → fontes → roteiro 480s → revisão | Piloto editorial |
| M3 Vídeo de qualidade | F5 + F6 + F7 | B-roll/beats → editor → QA → thumbnail | Piloto de produção |
| M4 Publicação segura | F8 (iniciar hardening desde M1) | Publicação privada testada com concorrência/recovery | Canal teste → produção após gate |
| M5 Operação inteligente | F9 + F10 | Analytics e gestão de múltiplos canais | Produto operacional |
| M6 SaaS controlado | F11 | 2 tenants isolados + BYOK + medição | Beta fechado |

## Sequência de implementação sugerida

**Trilha do core:** F0 → F1 → F8 hardening → F8 integração.

**Trilha UX/conteúdo:** F1 → F2 → F3 → F4 → F5 → F6 → F7.

**Trilha plataforma:** F0 → F10 (depois de F2 mínimo) → F11; F9 depois de publicação real.

## Gates de avanço

- F0: nenhum segredo nas distribuições e credenciais expostas tratadas.
- F1: deterministic replay, fencing e pausa humana em testes.
- F4: fonte + claim + roteiro + TTS 8 min validado sem inventar referência.
- F8: reconciliação de uploads remotos; não religar publicação automática antes dos testes.
- F11: isolamento entre tenants comprovado em DB, storage, cache, logs, workers e secrets.

## Cadência de execução

Planeje em ciclos de cards pequenos que terminem com demonstração. Evite estimativas rígidas antes de medir velocidade do time. Para cada card registrar responsável, dependências, risco, contrato, teste, critério de aceite, rollback e evidência.
