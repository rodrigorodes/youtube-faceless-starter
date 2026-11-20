# Projeto executável — DarkPlanner Voice Provider

## Meta e escopo
Aprimorar o módulo de narração por uma integração **plugin/adapters**, reaproveitando a porta `Voice` atual. Entregar síntese por cena, rastreabilidade e controles de custo; preparar evolução para SRT, catálogo de vozes, multi-voz e SaaS sem empurrar responsabilidades ao domínio.

## Baseline → alvo
| Elemento | Hoje (starter) | Alvo |
|---|---|---|
| Voz | `Voice.speak(text, Path)->float` | Compatibilidade mantida; metadados extras opcionais em um contrato de aplicação novo |
| Seleção | `register('voice','piper',PiperVoice)` e `voice='piper:...'` | `darkplanner:<id>` resolvido apenas na composition root |
| Render | `RunRender` usa WAV por cena | Continua sem importar DarkPlanner; converter arquivo remoto para WAV validado |
| Custos | Guardas gerais | Reserva/registro de gasto por geração, sem duplicar chamadas em retries |
| Subtitles | Cues locais de texto/duração | Não assumir SRT externo; conciliar caso suportado |
| Persistência | Jobs/asset registram etapas da renderização | Persistir external job reference, estado e idempotência quando API assíncrona |
| Configuração | `ProjectConfig.voice` string | Canal escolhe voz e provider; secrets resolvidos fora do config |

## Iterações / marcos (estimativas relativas)
- **M0: Descoberta, segurança e decisão go/no-go (DPA-01/02)** — verificar API oficial, licenças, custos, quotas, payloads, formatos. Sem esta confirmação, usar fake adapter; não iniciar client HTTP real.
- **M1: Contract-first / plugabilidade (DPA-03/04)** — padronizar retorno WAV, erros, capabilities; manter compatibilidade com Piper.
- **M2: Integração funcional (DPA-05/06)** — client e adapter testados, áudio por cena, conversão normalizada, medição de duração e teste de silêncio.
- **M3: Confiabilidade (DPA-07/08)** — tratamento de jobs assíncronos caso API necessite, persistência, controle de custos e retries seguros.
- **M4: Experiência/configuração (DPA-09/10)** — provider em configuração do canal e UI para testar voz, recurso dependendo da F10/F6.
- **M5: Qualidade, SaaS e release (DPA-11/12)** — contrato test suite, isolamento org secrets, rollout progressivo e documentação.

## Integração com roadmap F0–F11
| Fase | Alterações |
|---|---|
| F0 | Inspecionar secrets, API discovery, termos e plano de rollback |
| F1 | Retry/lease/worker e orquestração de áudio de longa duração; não bloquear request HTTP |
| F5 | Adapter DarkPlanner, WAV por cena, sincronização e QA |
| F6 | Teste de voz, preview e regeração granular |
| F10 | Configuração de provider/canal; catálogo/capabilities |
| F11 | BYOK, cofre por organização, quotas e rate limits segregados |

## Gates
- **Go/no-go externo:** contrato de API legítimo, permissão comercial para uso em SaaS, método seguro de auth, quotas e download viáveis.
- **Compatibilidade:** o pipeline com Piper passa sem regressões.
- **Segurança:** zero segredos em core, configuração de projeto, logs ou artefatos exportados.
- **Custo:** chamadas de retry não podem lançar cobrança adicional por repetição sem reconhecimento explícito; orçamento reservado antes de provider pago.
- **E2E:** render de vídeo com cenas narradas via adapter real em sandbox, QA aprovado e nenhuma mudança no código do domínio.

## Definition of Done global
PR com contrato, fake + adapter, testes de unidade/integração, migrations aditivas (se necessário), docs, feature flag desligada por padrão, dashboards, instruções de rollback e evidência de validação externa. Nenhuma afirmação de funcionalidade do DarkPlanner sem evidência da API.
