# VE-08 — Relatório de fidelidade (Vídeos, Storyboard, Composição, Progresso)

Referência: protótipo v4-v3 renderizado em `file://`. App: HTML real do workspace. O app real não tem vídeo com
roteiro; por isso Cenas/Composição/estados de progresso são capturados com o HTML real sobre o backend simulado
(`tests/ve08/harness.py`), com as mesmas 3 cenas do vídeo `v2` do protótipo (`scripts/ve08_evidence.py`).
Vídeos usa o app real (`scripts/fidelity_gate.py --only videos`, em `videos-gate/`).

| Tela | VP | Texto | Campos | Estilos diferentes | Pixels | Altura ref/app | Overflow ref/app |
|------|----|-------|--------|--------------------|--------|----------------|------------------|
| Cenas | 1440 | 58,8% | 26,3% | 0 | 10,2% | 1000/1487 | 0/0 |
| Cenas | 768 | 60,5% | 26,3% | 0 | 15,4% | 1589/2866 | 0/0 |
| Cenas | 390 | 60,5% | 26,3% | 0 | 20,2% | 1912/3071 | 0/0 |
| Composição | 1440 | 57,5% | 10,3% | 3 | 7,9% | 1212/1369 | 0/0 |
| Composição | 768 | 59,1% | 10,3% | 3 | 6,9% | 2409/2721 | 0/0 |
| Composição | 390 | 59,1% | 10,3% | 3 | 15,1% | 2511/2721 | 76/0 |
| Vídeos (app real) | 1440/768/390 | 12,9% | 0,0% | 0 | 5,2/10,9/13,1% | dado real | 0/0 |

Leitura: a similaridade de texto/campos é baixa porque a casca do protótipo traz dados ilustrativos (canal, orçamento,
"Mockup", "Roteiro da demo", nav em `button` × `a`), e porque o app tem cards completos de cena (D1), textos de áudio
real (D2) e controles reais extras (D14/D15). As 3 diferenças de estilo da Composição são o mesmo `Transição`/`Movimento`/
`Abaixar a música…` (label × span dentro de `details` fechado) — ver D14/D15. Nenhuma tela é declarada idêntica ao protótipo;
o diff de pixels é maior que zero em todas. Detalhe por texto/campo/estilo em `*-report-*.txt`.

Arquivos: `scenes-{reference,app,diff}-{1440,768,390}.png`, `composition-…`, `progress-state-{before,running,stage-done,failed,done}-*.png`,
`progress-{app,reference}-*.png` (página de execução), `videos-gate/`.

## Funcional (Playwright, `tests/ve08`, 1440×1000; composição também 768 e 390)
20 testes passando, sem custo de mídia:
- todos os cards na ordem do roteiro, sem seletor; edição independente + persistência após reload;
- Desfazer/Refazer (texto, mídia religada, nova edição invalida refazer), B-roll por cena + descrição + reload;
- nova cena sem navegação (marcador de página preservado) + contagem do dock + persistência; excluir/reordenar com desfazer;
- modal de mídia altera só a cena alvo; falha do servidor → rollback com mensagem;
- Gerar/Renderizar: diálogo de impacto, 1 POST, progresso por etapas reais, retomada após reload sem novo POST;
- Composição: 5 trilhas, parâmetros, prévia viva, salvar via `style-patch`, estado vazio, sem overflow em 768/390.
Suíte Python: 2564 passed, 4 falhas pré-existentes (`test_contracts_snapshot`, `test_schema_docs`, `test_secrets_hygiene`,
`test_publishing::test_preview_page_renders_sidebar_navigation`); testes de Postgres pulados (sem `STUDIO_TEST_DSN`).
