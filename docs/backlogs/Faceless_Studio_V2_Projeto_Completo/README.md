# Faceless Studio V2 — Projeto de implementação

> **North Star:** transformar uma ideia em um vídeo publicado, com qualidade, controle de custo e segurança.

Este é um **pacote de planejamento para execução**, não um projeto de código já modificado. Baseado na revisão do `youtube-faceless-starter(1).zip` e no plano consolidado anterior. Não contém credenciais nem arquivos locais do starter.

## Comece aqui

1. Leia [`PLANO_MESTRE.md`](PLANO_MESTRE.md) para visão, baseline e arquitetura.
2. Siga [`gestao/ROADMAP-E-RELEASES.md`](gestao/ROADMAP-E-RELEASES.md) para a ordem de entregas.
3. Abra cards de [`gestao/BACKLOG-MESTRE.md`](gestao/BACKLOG-MESTRE.md) no gerenciador de tarefas.
4. Detalhes técnicos e aceite em [`fases/`](fases/), um arquivo por fase.
5. Alinhe contratos e decisões em [`arquitetura/CONTRATOS-E-DECISOES.md`](arquitetura/CONTRATOS-E-DECISOES.md).
6. Valide a UX-alvo em [`produto/JORNADA-E-TELAS.md`](produto/JORNADA-E-TELAS.md).
7. Use [`qualidade/MATRIZ-DE-ACEITE.md`](qualidade/MATRIZ-DE-ACEITE.md) como checklist de release.

## Escopo

**F0–F11:** segurança; orquestração resiliente; UX end-to-end; tendências e pesquisa; long-form; audiovisual; editor e QA; thumbnails/SEO; publicação; analytics; canais e provedores; SaaS/BYOK.

**MVP de maior valor:** F0 → F1 → F2 → F3 → F4 + F8 (com gates de QA e packaging mínimo); depois F5–F7, F9–F11. O hardening de F8 começa antecipadamente e só é habilitado após aprovação/QA.

## Sem confusão de status

- **Existente no starter:** componentes técnicos listados no baseline do plano.
- **Proposto:** novos endpoints, models, UX e tarefas deste pacote.
- **Não validado:** e2e com providers/YouTube, multiusuário e produção de escala; exige testes no ambiente de deploy.

## Princípios de engenharia

Contrato antes de adapter; Postgres como fonte da verdade; operações longas fora do HTTP; aprovação humana persistida; execução retomável; side effects controlados; configuração sensível em secrets manager; rollback por flag; observabilidade e custo por estágio.
