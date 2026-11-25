# Editorial e roteiro

**Prefixo dos cenários:** `EDT`

> Arquivo gerado por `gerar.py` a partir de `dados/`. Não editar à mão; altere os dados e gere de novo.

## Como funciona

ContentBrief valida entradas, sem pesquisar nem verificar referências. Fontes alimentam claims; o gerador curto cria cenas e o longform usa outline e cenas. Fact-check é lexical/determinístico. Edições idempotentes criam versões; restore exige plano longo e snapshot. Aprovação longa prende versão e hash.

## Regras desta funcionalidade

| Regra | O que exige | Fontes | Cenários |
|---|---|---|---|
| `EDT.R01` | Brief imutável, campos extras proibidos, versão 1 e duração inteira positiva; referências não são fontes verificadas. | `renderer/app/studio/domain/content_brief.py:1-34` | [EDT-01](#edt-01) |
| `EDT.R02` | URL buscada exige allowlist; texto colado só exige URL HTTP válida e texto não vazio dentro do limite. | `renderer/app/studio/application/editorial.py:191-267` | [EDT-02](#edt-02) |
| `EDT.R03` | Gerar exige IDEA/SCRIPTED e claims; parser valida cenas, recusa ids desconhecidos, mas preenche citação isolada ausente com primeiro id válido. | `renderer/app/studio/application/editorial.py:330-386`, `renderer/app/studio/application/editorial.py:369-428` | [EDT-03](#edt-03), [EDT-04](#edt-04) |
| `EDT.R04` | Fact-check cobre narração/caption/label e nomes do prompt, exige versão estável e preserva problemas no override motivado. | `renderer/app/studio/application/editorial.py:470-494` | [EDT-04](#edt-04), [EDT-05](#edt-05) |
| `EDT.R05` | Diretor valida JSON e limita orçamento declarado; guard é opcional e valida resposta antes de confirmar custo. | `renderer/app/studio/application/creative_director.py:55-95` | [EDT-06](#edt-06) |
| `EDT.R06` | Edição usa versão esperada e hash de payload; replay não cria versão; ordem deve ser permutação; roteiro curto mantém ao menos uma cena. | `renderer/app/studio/application/longform.py:426-532`, `renderer/app/studio/application/longform.py:561-661` | [EDT-07](#edt-07) |
| `EDT.R07` | Restore cria nova versão de snapshot longo; aprovação depende da última versão, hash e fact-check correspondente. | `renderer/app/studio/application/longform.py:740-777`, `renderer/app/studio/application/longform.py:801-832` | [EDT-05](#edt-05), [EDT-08](#edt-08) |
| `EDT.R08` | Longform faz duas chamadas e revisão estrutural/factual/duração; alvo explícito vence configuração e default é 480 s. Caminho pago acessa usage no retorno já transformado pelo guard: inconsistência estática a caracterizar. | `renderer/app/studio/application/longform.py:294-374`, `renderer/app/studio/application/budget.py:427-469` | [EDT-09](#edt-09), [EDT-10](#edt-10) |

## Resumo dos cenários

Total: 10 cenário(s), todos documentais nesta elaboração.

| ID | Cenário | Tipo | Regras | Status |
|---|---|---|---|---|
| [EDT-01](#edt-01) | Brief manual válido e limites do contrato | feliz/borda/erro | EDT.R01 | `A_PROJETAR` |
| [EDT-02](#edt-02) | Fonte buscada versus texto colado | feliz/erro/borda | EDT.R02 | `A_PROJETAR` |
| [EDT-03](#edt-03) | Gerar roteiro curto e rejeitar saída inválida | feliz/erro | EDT.R03 | `A_PROJETAR` |
| [EDT-04](#edt-04) | Citação ausente recuperada pelo parser | regressao/erro | EDT.R03, EDT.R04 | `A_PROJETAR` |
| [EDT-05](#edt-05) | Checagem, override e corrida de versão | feliz/erro/concorrencia | EDT.R04, EDT.R07 | `A_PROJETAR` |
| [EDT-06](#edt-06) | Diretor criativo limita orçamento declarado | feliz/erro | EDT.R05 | `A_PROJETAR` |
| [EDT-07](#edt-07) | Editar, adicionar, remover e reordenar com CAS | feliz/concorrencia/regressao | EDT.R06 | `A_PROJETAR` |
| [EDT-08](#edt-08) | Restaurar revisão longa sem apagar histórico | feliz/erro/regressao | EDT.R07 | `A_PROJETAR` |
| [EDT-09](#edt-09) | Longform de 480 segundos e pressão de fontes | feliz/volume/borda | EDT.R08 | `A_PROJETAR` |
| [EDT-10](#edt-10) | Retorno transformado do guard no longform | erro/regressao | EDT.R08 | `A_PROJETAR` |

## Cenários

### EDT-01 — Brief manual válido e limites do contrato

- **Tipo:** feliz/borda/erro
- **Regras:** EDT.R01
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Separar intenção editorial de fonte verificada.
- **Pré-condições:** Instanciar contrato isolado.
- **Dados:** topic=Oceanos, audience=adultos, objective=explicar, interest_hypothesis=curiosidade, duração=480, referência=https://exemplo.org.
- **Passos:**
  1. Serializar e reler brief válido.
  2. Variar duração para 0, 1.5 e true; tópico para espaços; versão para 2; acrescentar campo estranho.
- **Esperado:** Válido preserva campos normalizados; variantes inválidas são recusadas; referência não cria snapshot nem claim.
- **Limitações:** Contrato não demonstra persistência ou pesquisa.
- **Automação:** camada `unit`; referência `Existente: tests/test_content_brief.py:18-66; ampliar matriz proposta.`

### EDT-02 — Fonte buscada versus texto colado

- **Tipo:** feliz/erro/borda
- **Regras:** EDT.R02
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Exercitar políticas distintas de ingestão sem rede.
- **Pré-condições:** Vídeo sintético existente; fetcher espião; allowlist exemplo.org.
- **Dados:** https://exemplo.org/a; https://exemplo.org.evil.test/a; texto 'O evento reuniu 3600 artistas.'
- **Passos:**
  1. Buscar URL permitida e simular redirect fora da lista.
  2. Colar o texto com referência https://outra.test/a.
  3. Repetir com texto vazio e 200001 caracteres.
- **Esperado:** Busca fora da lista ou redirect indevido recusa; texto colado aceita referência HTTP fora da lista, sem fetch; vazio/excesso recusa.
- **Limitações:** Proteções DNS/SSRF do fetcher exigem bateria própria; não interpretar texto colado como autenticado.
- **Automação:** camada `mock`; referência `Existentes: tests/test_editorial.py e tests/test_fetcher.py; matriz combinada proposta.`

### EDT-03 — Gerar roteiro curto e rejeitar saída inválida

- **Tipo:** feliz/erro
- **Regras:** EDT.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Persistir somente cenas aceitas.
- **Pré-condições:** Vídeo IDEA; snapshot com claim c1; modelo dublê; repositório espião.
- **Dados:** Duas cenas, narração de 30 caracteres, prompt de 30 caracteres, claim_ids=[c1].
- **Passos:**
  1. Gerar roteiro válido com scene_count=2.
  2. Em fixtures novas devolver JSON inválido, claim c999 e narração de 4 caracteres.
  3. Tentar gerar sem fonte e em FACT_CHECKED.
- **Esperado:** Caso válido salva SCRIPTED; saídas inválidas não salvam roteiro; ausência de claims e estado indevido bloqueiam chamada conforme ordem das validações.
- **Limitações:** Não avaliar qualidade literária por validade JSON; custos dependem de guard legado ou pago.
- **Automação:** camada `mock`; referência `Existente: tests/test_editorial.py; ampliar matriz proposta.`

### EDT-04 — Citação ausente recuperada pelo parser

- **Tipo:** regressao/erro
- **Regras:** EDT.R03, EDT.R04
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Documentar tolerância real sem confundi-la com lastro factual.
- **Pré-condições:** Ids válidos c1 e c2; c1 contém 3600; c2 contém 4200.
- **Dados:** Cena 0 fala 4200 e não cita; cena 1 cita c2.
- **Passos:**
  1. Analisar as duas cenas e verificar claim atribuída à cena 0.
  2. Rodar fact-check com as cenas resultantes.
  3. Repetir parser com todas as citações vazias.
- **Esperado:** Cena isolada recebe c1 por ordenação, podendo reprovar o número no fact-check; todas sem citação são recusadas.
- **Limitações:** Exigir citação explícita em toda cena seria endurecimento proposto, não comportamento atual; docs/12-editorial.md:38 diverge desta tolerância.
- **Automação:** camada `unit`; referência `Proposto: estender tests/test_editorial.py para fallback de claim isolada.`

### EDT-05 — Checagem, override e corrida de versão

- **Tipo:** feliz/erro/concorrencia
- **Regras:** EDT.R04, EDT.R07
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Evitar aprovação de texto diferente do lido.
- **Pré-condições:** Roteiro v1 SCRIPTED com fonte 3600; persistência controlável por barreira.
- **Dados:** Narração 4600; override vazio ou 'conferido em documento sintético'.
- **Passos:**
  1. Checar sem override e depois com os dois motivos.
  2. Em nova fixture bloquear antes de save, criar v2 e liberar checagem de v1.
  3. Solicitar aprovação longa com hash ou fact-check de v1 para v2.
- **Esperado:** Sem motivo válido permanece reprovação; override motivado mantém itens sem fonte; corrida retorna conflito; aprovação longa recusa versão/hash/fact-check incompatíveis.
- **Limitações:** Correspondência lexical não prova relação semântica entre número e substantivo.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_editorial_repo.py, tests/test_facts.py e tests/test_longform_editorial.py; corrida ampliada proposta.`

### EDT-06 — Diretor criativo limita orçamento declarado

- **Tipo:** feliz/erro
- **Regras:** EDT.R05
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Validar briefing e rastrear a passagem pelo guard.
- **Pré-condições:** Modelo dublê com CreativeBrief completo; guard espião.
- **Dados:** Tema Oceanos; contexto idioma pt-BR; budget_cap=2; resposta max_budget_usd=5.
- **Passos:**
  1. Executar com resposta válida.
  2. Repetir com JSON inválido, tópico vazio e teto negativo.
  3. Inspecionar ordem reserva, chamada, validação e confirmação.
- **Esperado:** Brief válido retorna teto 2; entradas inválidas recusam; JSON inválido não produz brief aceito; guard não confirma saída recusada.
- **Limitações:** Limitar max_budget_usd no brief não substitui reserva financeira; sem guard o caso de uso chama modelo diretamente.
- **Automação:** camada `mock`; referência `Existente: tests/test_creative_director_use_case.py; inspeção de ordem proposta.`

### EDT-07 — Editar, adicionar, remover e reordenar com CAS

- **Tipo:** feliz/concorrencia/regressao
- **Regras:** EDT.R06
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Preservar identidade e impedir sobrescrita concorrente.
- **Pré-condições:** Roteiro curto v1 com 3 cenas e fontes; banco descartável em futura execução.
- **Dados:** Duas edições expected_version=1; keys edit-a/edit-b; ordem [2,0,1].
- **Passos:**
  1. Disparar edições por barreira e repetir a vencedora com mesma chave/payload.
  2. Reusar chave com payload diferente.
  3. Em versões atuais adicionar cena, ordenar, remover; tentar ordem [0,0] e remover última cena.
- **Esperado:** Uma edição vence, outra fica stale; replay não incrementa versão; payload divergente conflita; ordem inválida/remoção final recusam; mutações válidas versionam.
- **Limitações:** Validação de conteúdo de cena alterada não equivale a nova aprovação de roteiro completo.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_longform_editorial.py e tests/test_longform_repo.py; disputa coordenada proposta.`

### EDT-08 — Restaurar revisão longa sem apagar histórico

- **Tipo:** feliz/erro/regressao
- **Regras:** EDT.R07
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Recuperar snapshot escolhido como versão nova.
- **Pré-condições:** Longform v1 e v2 com 12 cenas; snapshot v1 disponível.
- **Dados:** Restaurar v1 com expected_version=2 e key restore-1; um asset de v1 ausente.
- **Passos:**
  1. Executar restore e repetir mesma requisição.
  2. Comparar texto, ordem e ids com snapshot v1.
  3. Em fixtures separadas remover snapshot ou usar roteiro curto sem plano.
- **Esperado:** Cria v3 e preserva v1/v2; replay mantém v3; mídia ausente sinaliza revisão; aprovação velha não vale para v3; sem snapshot/plano recusa.
- **Limitações:** Listagem restorable baseada em snapshot não elimina a exigência de plano no caso de uso.
- **Automação:** camada `local-integrado`; referência `Existente: tests/test_script_revision_restore.py:109-201.`

### EDT-09 — Longform de 480 segundos e pressão de fontes

- **Tipo:** feliz/volume/borda
- **Regras:** EDT.R08
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Cobrir duas passagens e alvo longo sem confundir estimativa com WAV.
- **Pré-condições:** Modelo determinístico; guard legado; fontes sintéticas com claims suficientes.
- **Dados:** Alvo 480 s; WPM calibrado da fixture; perfil com duração default 60 s; 1000 claims sintéticas.
- **Passos:**
  1. Gerar outline e cenas dentro dos limites do domínio.
  2. Repetir com alvo explícito 600 s e perfil 480 s.
  3. Devolver capítulos sem cobertura e cenas redundantes em variantes.
  4. Inspecionar claims que cabem nos prompts.
- **Esperado:** Default curto do perfil não encolhe longform; chamada explícita vence; revisão inválida não persiste; resultado expõe duração estimada e contagem de palavras.
- **Limitações:** 480 s é alvo estimado; áudio real só é medido no render; volume não define SLA sem medição futura.
- **Automação:** camada `mock`; referência `Existente: tests/test_longform_480s.py:112 e tests/test_longform_editorial.py; volume proposto.`

### EDT-10 — Retorno transformado do guard no longform

- **Tipo:** erro/regressao
- **Regras:** EDT.R08
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Caracterizar inconsistência estática no caminho pago.
- **Pré-condições:** PaidOperationGuard com repositório dublê e settlement confirmado; parser retorna ScriptPlan/lista de drafts.
- **Dados:** Resposta válida de outline com UsageEntry no TextResult original.
- **Passos:**
  1. Executar _call com guard real e validate=parse_outline.
  2. Inspecionar tipo retornado por guard.run e acesso seguinte a result.usage.
  3. Comparar com caminho sem paid.
- **Esperado:** Caracterização atual: guard retorna objeto validado; acesso a usage nesse objeto gera erro em vez do par resultado/custo. Critério de correção proposto: preservar custo do TextResult original e concluir as duas passagens.
- **Limitações:** Achado estático, não reproduzido nesta tarefa; não pressupor incidência em toda composição ou em chamadas sem paid.
- **Automação:** camada `mock`; referência `Proposto: regressão em tests/test_longform_editorial.py com PaidOperationGuard real e provider dublê.`

## Resumo do capítulo

10 cenários documentais. Execução direta, sem runtime de workflow. Todos A_PROJETAR; testes citados são referências existentes, não comprovação de aprovação. Usar somente fixtures sintéticas e dublês; integração futura em banco descartável.
