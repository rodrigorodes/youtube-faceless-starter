# Baseline de evidências

## Situação em 21/11/2026 (baseline do pacote — histórico)

- ZIP `youtube-faceless-starter(3).zip`: HEAD simbólico `refs/heads/main`; hash lido `c0cd97ce530255d3ea7d5649e2bed350410ab140`.
- Inspeção direta: `renderer/app/studio/api/panel_new_video.py`, payload `JSON.stringify` contém projeto/tema/formato, não style_id.
- Documento fornecido: `Faceless Studio V3.1 — UX & Settings Redesign.md`, revisão baseada em bf2c6b1, §22 G01–G14.
- Demais evidências e testes são anteriores, não reexecutados durante a geração deste pacote. F00 deve confirmar no checkout ativo.
- Não foram modificados arquivos do repositório nem executados efeitos externos.

## Revalidação da F00 (21/11/2026)

Executada no checkout ativo `/Users/rodrigomendes/youtube-faceless-starter`.

| Item | Baseline do pacote | Checkout ativo | Delta |
|---|---|---|---|
| HEAD | `c0cd97c` | `e254b61` | árvore idêntica (`git diff c0cd97c HEAD` vazio) |
| Ancestralidade | `c0cd97c` no `main` | `c0cd97c` **sem ancestral comum** com o HEAD | histórias não relacionadas; o hash do ZIP não serve como referência Git |
| Delta desde `bf2c6b1` | 21 commits / 24 arquivos (+4030/−877) | 24 arquivos (+4030/−877) | conteúdo confere; a contagem de commits é 448 na cadeia completa |
| Branch | `main` | `main`, árvore limpa (só `docs/backlogs/` não rastreado) | — |

- `git cat-file -t bf2c6b1` → `commit`; `bf2c6b1` é ancestral do HEAD.
- `python3 -V` → 3.11.9; `pytest` 8.2.0; `pydantic` 2.5.0 (pin do projeto: 2.11.4).
- Docker disponível; `STUDIO_TEST_DSN` ausente no shell.
- Todos os símbolos de `01-current-state.md` confirmados (ver [inventory](inventory.md)).

Conclusão: o baseline é **confirmado por conteúdo**, não por hash. Qualquer evidência nova
deve citar `e254b61`, não `c0cd97c`.

## Regra

Evidência de código (símbolo localizado) não prova execução externa. Publicação, cobrança,
chamada paga, workflow real e deploy permanecem não executados e não autorizados nesta fase.