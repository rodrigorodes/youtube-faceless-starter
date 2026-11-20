# Faceless Studio V2 — Render Plan Foundation

**Projeto:** F5-RP — Audiovisual Render Plan  
**Versão:** 1.0  
**Status:** Planejado  
**Prioridade:** P0 — Fundação audiovisual  
**Integração:** Faceless Studio V2, fases F1, F5, F6 e F10

---

## 1. Objetivo

Implementar um contrato audiovisual canônico, versionado e independente de fornecedores, chamado `RenderPlan`.

O contrato deverá representar integralmente a composição de um vídeo, incluindo:

- Timeline global e cenas.
- Múltiplos shots por cena.
- Imagens, vídeos, gráficos, textos e outros assets.
- Narração, música e efeitos sonoros.
- Legendas e sincronização.
- Transições e efeitos de composição.
- Identidade visual do canal.
- Metadados, versões e referências dos assets.
- Informações para reprodução e regeneração seletiva.

**Resultado esperado:** o renderer deve executar um plano validado sem precisar conhecer o roteiro editorial, o provider que criou um asset ou as regras do canal.

## 2. Princípios arquiteturais

1. **Core independente:** nenhuma dependência direta de FFmpeg, DarkPlanner, Veo ou SDK externo no domínio.
2. **Contrato versionado:** qualquer alteração incompatível exige nova versão de schema.
3. **Timeline determinística:** todos os tempos representados em unidades inteiras, com timebase explícita.
4. **Assets imutáveis:** referências a versões específicas e hashes de conteúdo.
5. **Regeneração seletiva:** invalidar somente os artefatos impactados.
6. **Providers plugáveis:** resolvidos por portas e adapters.
7. **Observabilidade:** métricas de duração, custo, erros e qualidade por cena.
8. **Compatibilidade:** a produção existente deve continuar funcionando durante a migração.

## 3. Estrutura lógica proposta

Adaptar aos módulos já existentes, evitando reorganizações desnecessárias.

```text
renderer/
├── domain/
│   └── audiovisual/
│       ├── render_plan.py
│       ├── timeline.py
│       ├── scene.py
│       ├── shot.py
│       ├── asset_reference.py
│       └── validation.py
│
├── application/
│   └── audiovisual/
│       ├── build_render_plan.py
│       ├── validate_render_plan.py
│       ├── resolve_assets.py
│       ├── execute_render_plan.py
│       └── regenerate_scene.py
│
├── ports/
│   ├── asset_resolver.py
│   ├── render_engine.py
│   ├── visual_style.py
│   └── quality_evaluator.py
│
├── adapters/
│   └── rendering/
│       └── ffmpeg/
│           ├── adapter.py
│           ├── compiler.py
│           └── executor.py
│
└── contracts/
    └── render_plan/
        └── v1/
            ├── schema.json
            └── examples/
```

## 4. Modelo de dados

### RenderPlan

Raiz do documento audiovisual.

Campos obrigatórios:

- `schema_version`
- `plan_id`
- `revision`
- `project_id`
- `video_id`
- `output`
- `timeline`
- `asset_manifest`
- `style_snapshot`
- `provenance`

### Scene

Agrupa segmentos audiovisuais de uma unidade narrativa.

- `scene_id`
- `start_tick`
- `duration_ticks`
- `shots`
- `narration_refs`
- `subtitle_refs`

### Shot

Representa um elemento visual em uma faixa temporal.

- `shot_id`
- `track_id`
- `start_tick`
- `duration_ticks`
- `asset_ref`
- `composition`
- `effects`
- `transition`

### AssetReference

Referencia conteúdo previamente gerado ou obtido.

- `asset_id`
- `asset_version`
- `uri`
- `content_sha256`
- `media_type`
- `metadata`

Os detalhes específicos do fornecedor permanecem em registros de proveniência fora do contrato obrigatório de renderização.

## 5. Contrato JSON ilustrativo

```json
{
  "schema_version": "1.0.0",
  "plan_id": "rp-001",
  "revision": 1,
  "project_id": "channel-001",
  "video_id": "video-001",
  "output": {
    "width": 1920,
    "height": 1080,
    "fps_num": 30,
    "fps_den": 1,
    "duration_ticks": 14400
  },
  "timeline": {
    "ticks_per_second": 30,
    "scenes": [
      {
        "scene_id": "scene-01",
        "start_tick": 0,
        "duration_ticks": 540,
        "shots": [
          {
            "shot_id": "shot-01",
            "track_id": "visual-main",
            "start_tick": 0,
            "duration_ticks": 150,
            "asset_ref": "asset-video-01"
          },
          {
            "shot_id": "shot-02",
            "track_id": "visual-main",
            "start_tick": 150,
            "duration_ticks": 210,
            "asset_ref": "asset-image-01"
          },
          {
            "shot_id": "shot-03",
            "track_id": "visual-main",
            "start_tick": 360,
            "duration_ticks": 180,
            "asset_ref": "asset-chart-01"
          }
        ]
      }
    ]
  },
  "asset_manifest": [],
  "style_snapshot": {
    "style_id": "cinematic-documentary",
    "version": "1.0.0"
  },
  "provenance": {
    "builder_version": "1.0.0"
  }
}
```

Este exemplo mostra apenas uma cena de 18 segundos dentro de um vídeo de 480 segundos. O schema final precisará representar faixas de áudio, legendas, efeitos, transições, o catálogo completo de assets e todos os intervalos da timeline.

## 6. Backlog de implementação

### RP-00 — Baseline e compatibilidade

- **RP-001:** mapear o fluxo atual `Storyboard → Assets → Render`.
- **RP-002:** identificar contratos e DTOs existentes que podem ser reutilizados.
- **RP-003:** criar vídeos de referência e registrar hashes, duração e qualidade.
- **RP-004:** criar testes de regressão para o renderer atual.

**Aceite:** baseline executável e documentado, sem alterações de comportamento.

### RP-01 — Contrato canônico

- **RP-005:** escrever ADR do Render Plan.
- **RP-006:** implementar modelos tipados em Python.
- **RP-007:** publicar JSON Schema v1.
- **RP-008:** definir política de versionamento e compatibilidade.
- **RP-009:** criar testes de serialização, validação e round-trip.

**Aceite:** contratos testáveis sem FFmpeg ou chamadas externas.

### RP-02 — Timeline e sincronização

- **RP-010:** implementar timebase racional e ticks inteiros.
- **RP-011:** definir cenas, shots e tracks.
- **RP-012:** implementar regras de sobreposição e intervalos.
- **RP-013:** associar narração e legendas à timeline.
- **RP-014:** criar validações de duração, lacunas e alinhamento.

**Aceite:** a duração e os intervalos são reproduzíveis, sem acúmulo de erros de arredondamento.

### RP-03 — Render Plan Builder

- **RP-015:** converter storyboard existente em plano.
- **RP-016:** consumir snapshot versionado do Channel Identity.
- **RP-017:** implementar a porta `VisualStyle`.
- **RP-018:** criar o primeiro preset `cinematic-documentary`.

**Aceite:** gerar um Render Plan válido sem conhecer o renderer específico.

### RP-04 — Asset Resolver e multi-asset

- **RP-019:** criar contrato `AssetResolver`.
- **RP-020:** implementar manifest com URI, versão, hash e licença.
- **RP-021:** suportar imagem, vídeo, gráfico e texto.
- **RP-022:** validar disponibilidade, duração, codec e resolução dos assets.

**Aceite:** cada cena suporta múltiplos shots com mídias distintas.

### RP-05 — FFmpeg Adapter

- **RP-023:** implementar compilador Render Plan → comandos/graph FFmpeg.
- **RP-024:** implementar composição visual e transições.
- **RP-025:** integrar áudio, narração, música e legendas.
- **RP-026:** implementar renderização com diretórios temporários isolados e publicação atômica do artefato final.

**Aceite:** renderização de um vídeo de 8 minutos a partir exclusivamente do Render Plan e do Asset Resolver.

### RP-06 — Regeneração seletiva

- **RP-027:** versionar Render Plan e assets.
- **RP-028:** implementar grafo de dependências e invalidação seletiva.
- **RP-029:** reutilizar trechos não impactados, com política de cache e render parcial quando tecnicamente viável.

**Aceite:** alterar uma cena não exige regenerar narrações, imagens ou vídeos de outras cenas. A composição final pode continuar necessária para produzir o MP4 definitivo.

### RP-07 — QA e rollout

- **RP-030:** adicionar QA técnico e integração com `VisualQualityEvaluator`.
- **RP-031:** criar testes E2E e benchmark audiovisual.
- **RP-032:** implantar feature flag, compatibilidade e rollback.

**Aceite:** execução estável e comparação documentada com o pipeline anterior.

## 7. Contratos entre componentes

| Porta | Entrada | Saída |
|---|---|---|
| `VisualStyle` | Storyboard + identidade | Preset/plano visual |
| `RenderPlanBuilder` | Storyboard + estilo + assets | RenderPlan |
| `PlanValidator` | RenderPlan | ValidationReport |
| `AssetResolver` | AssetReference | AssetDescriptor |
| `QualityEvaluator` | Plano + assets/evidências | QualityReport |
| `RenderEngine` | RenderPlan + assets resolvidos | RenderArtifact |
| `ArtifactRepository` | Artefatos e metadados | Referências persistentes |

O Production Coordinator deve depender dessas portas, nunca das classes concretas dos adapters.

## 8. Persistência

Usar PostgreSQL para armazenar:

- Identificadores e revisões dos planos.
- Estado de execução e checkpoints.
- Relações entre planos, cenas e assets.
- Resultados de validação e QA.
- Referências dos artefatos renderizados.

Os arquivos de mídia permanecem no storage, com referências persistidas no banco.

Separar rigorosamente:

**Identidade lógica:** plano, cena e shot.

**Identidade física:** hash do arquivo, codec, localização no storage e versão.

Isso permite trocar a localização física dos arquivos sem alterar a identidade editorial da cena.

## 9. Testes obrigatórios

**Contrato e domínio**
- Schema inválido deve ser rejeitado.
- IDs de cenas e shots devem ser únicos no escopo correto.
- Nenhum shot pode referenciar asset inexistente.
- Tracks não podem violar as regras de sobreposição.
- A duração deve respeitar o formato de saída.

**Renderização**
- Imagens e vídeos misturados.
- Áudio e vídeo sincronizados.
- Legendas preservadas.
- Aspect ratios diferentes.
- Transições sem frames pretos inesperados.
- Ausência de silêncio não intencional.

**Recuperação**
- Falha no download de um asset.
- Interrupção durante o render.
- Retomada sem duplicação de trabalhos concluídos.
- Regeneração de uma única cena.
- Falha de provider externo.
- Limpeza de artefatos temporários.

**Arquitetura**
- Core não importa FFmpeg ou SDKs de IA.
- Troca de renderer via configuração.
- Teste de conformidade de cada adapter.
- Compatibilidade com vídeos do pipeline anterior.

## 10. Métricas de sucesso

Metas propostas para o MVP, sujeitas a benchmark:

- 100% dos planos aceitos devem passar pelo schema e pelas validações determinísticas.
- Zero lacunas não intencionais na timeline de vídeo.
- Sincronização de narração e legendas dentro da tolerância definida por tipo de mídia.
- 100% dos assets utilizados devem ter referência, versão e origem rastreáveis.
- Regeneração de uma cena sem refazer assets independentes.
- Renderização de vídeo de 8 minutos em 1080p.
- Ausência de regressão funcional nos vídeos produzidos pelo fluxo anterior.

Registrar também custo por minuto de vídeo, tempo de renderização, taxa de falhas, cache hit e quantidade de correções humanas.

## 11. Estratégia de migração

1. Preservar o renderer atual.
2. Implementar RenderPlan e validações isoladamente.
3. Adicionar adaptador do storyboard atual para RenderPlan.
4. Implementar novo FFmpeg Adapter.
5. Executar os dois caminhos em ambiente de teste.
6. Comparar saída, custos e estabilidade.
7. Habilitar o novo caminho por feature flag.
8. Manter rollback até a estabilização.

Não realizar migração destrutiva de dados ou remoção do caminho legado na primeira entrega.

## 12. Definição de pronto

O projeto estará concluído quando:

- RenderPlan v1 estiver publicado, validado e versionado.
- Houver pelo menos um estilo de edição operacional.
- O mesmo plano puder ser executado repetidamente com os mesmos assets e parâmetros.
- A composição suportar vários shots por cena.
- A sincronização audiovisual estiver validada.
- Uma cena puder ser alterada sem recriar assets independentes.
- Os testes de contratos, integração e E2E estiverem aprovados.
- A produção pelo painel estiver integrada ao Production Coordinator.
- Os recursos tiverem logs, métricas, controle de custo e rollback.

## 13. Evolução posterior

Depois dessa fundação:

- **Visual Style Engine V2:** biblioteca de estilos e templates avançados.
- **Visual Quality Evaluator:** avaliação multimodal com regeneração seletiva.
- **Channel Identity:** presets persistentes e versionados por canal.
- **Editor visual:** timeline interativa, cortes e alterações por shot.
- **AI Video Providers:** Veo, outros modelos e bibliotecas de B-roll.
- **SaaS:** storage por organização, quotas e renderização distribuída.

Essas funcionalidades devem consumir o contrato RenderPlan, não alterar suas responsabilidades centrais.

---

**Decisão final:** construir o Render Plan como a linguagem comum do sistema audiovisual. A inteligência editorial produz o plano; os adapters geram ou resolvem a mídia; o renderer executa; o QA avalia; e o usuário controla o resultado.