# PROMPT-MASTER — Integração e Estabilização V4 (INT-01 a INT-07)

**Referência Base:** `develop` (`0257c045dbff8ef3f78b4f8ffba76b20db226433`)  
**Autorização:** Operador autorizou execução sequencial contínua via `/goal`  
**Governança:** Clean Architecture estrita, Custo $0.00 em testes, Publicação Externa bloqueada via Kill Switch, Sem simulação de aprovação humana.

---

## Ondas de Execução

- [x] **INT-01 — Auditoria Arquitetural e Matriz de Achados (A01–A13):**
  - Auditoria completa de todos os componentes isolados, falsos positivos e stubs.
  - Relatório entregue em `INT-01-AUDIT-REPORT.md`.

- [x] **INT-02 — Providers Reais e Saneamento de Síntese:**
  - Desabilitar Kokoro como voz neural padrão validada (`validated=False`) enquanto gerar senoide.
  - Piper estabelecido como provedor local offline padrão e validado (`pt_BR-faber-medium`).
  - ElevenLabs mantido estritamente opt-in e inativo sem credencial.
  - Garantia de zero chamadas externas pagas ($0.00).

- [x] **INT-03 — Composição Audiovisual e Compilador de Múltiplas Camadas:**
  - Elevar `MAX_OVERLAYS_PER_SCENE` em `render_compiler.py` para suportar múltiplas camadas simultâneas.
  - Implementar suporte real no FFmpeg para posicionamento x/y, escala, opacidade e transições.
  - Integrar multitrack com medição real de True Peak EBU R128 (`ebur128` FFmpeg).

- [x] **INT-04 — Pipeline, Coordenador Real e Resiliência:**
  - Conectar resiliência e idempotência ao `ProductionCoordinator` e `PostgresProductionRunRepository` existentes.
  - Provar invalidação seletiva de cache de cena e reconciliação pré-retry de operações assíncronas.

- [ ] **INT-05 — Studio, Acervo Persistente e Mídia Externa (GAI-01/02):**
  - Suportar importação segura de PNG e MP4 externos com magic bytes, sem path traversal.
  - Conectar storyboard ao `AssetRepository` persistente.

- [ ] **INT-06 — Piloto Audiovisual Real:**
  - Gerar arquivo MP4 físico via Studio real medido pelo FFmpeg e QA real.
  - Rotular claramente métricas reais observadas vs contratos sintéticos.
  - Kill switch de publicação verificado como `BLOCKED`.

- [ ] **INT-07 — Regressão Canônica Completa e Homologação:**
  - Execução de 100% dos testes no container canônico.
  - Auditoria de arquitetura limpa (`test_architecture.py`).
  - Emissão do relatório final e parada para Avaliação Humana formal do operador.
