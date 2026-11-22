# Provedores: estado da configurabilidade (auditoria da F02)

Pergunta do operador: a plataforma deve configurar **N provedores diferentes**, sem acoplamento
ao core (Clean Architecture). O que o código mostra hoje, HEAD `e254b61` + F02:

## O que já é porta + adaptador (desacoplado)

| Peça | Onde | Fato |
|---|---|---|
| Contrato da porta | `application/ports.py`, `domain/provider.py` | `TextModel`, `ImageModel`, `Voice`, `Renderer`, `ProviderImplementation`, `ProviderCard`, `RoutingDecision` — domínio puro, sem SDK nem HTTP |
| Registro por nome | `application/config.py::register/build` | `register(kind, name, factory)`; `build(kind, "provider:modelo")` recusa nome desconhecido cedo |
| Catálogo por tarefa | `application/providers.py::ProviderService` | `candidates(kind)` devolve **N** implementações da mesma porta; cada uma vira `ProviderCard` com disponibilidade/custo/qualidade |
| Seleção por canal | `ProjectConfig` (text/image/voice/renderer) | quatro slots por canal, spec `"<provedor>[:<modelo>]"`; ambiente dá o padrão, o canal sobrescreve |
| Fiação | `composition.py` | único lugar que conhece implementações concretas; `provider_for(kind, project_id)` monta sob demanda |
| Fronteira | `tests/test_architecture.py` (6 testes, verdes) | domínio não importa camadas externas/I-O; aplicação só importa domínio; API não toca adaptadores/banco |

Consequência prática: adicionar um provedor novo é escrever um adaptador da porta e registrar
um nome na composição. Nada no domínio, nos casos de uso ou nas telas precisa mudar.

## O que ainda **não** é configurável de verdade

1. **Cadeia de fallback**: `route_provider` calcula primário + fallback, mas a execução usa
   `provider_for` direto do `ProjectConfig` — o roteamento por perfil econômico é consultivo
   (G09, fase F06).
2. **BYOK**: chaves existem no modelo SaaS (`studio.byok_keys` com máscara/fingerprint) e na tela
   de Equipe, mas **nenhum provider as consome** (G10, Projeto C).
3. **Um por tarefa por canal**: não há, hoje, "provedor A para vídeo curto e B para longo" — a
   escolha é por tarefa (texto/imagem/voz/render), não por formato (F06.T01 decide se haverá).
4. **Custo desconhecido**: `CostEstimate.UNKNOWN` existe e é honesto no painel; a política de
   reserva para custo desconhecido é decisão de F01/F06.

## Onde isso encosta no que foi entregue na F02

- A tela **Avançado** mostra o catálogo real (N providers da instalação) e a configuração
  efetiva do canal, sem expor chave — é o lugar onde o operador confere o que está ligado.
- A tela **Canais** continua sendo onde se troca o provedor de cada tarefa do canal
  (`painel-providers`), com teste de conexão por provider.
- Nenhuma dessas telas importa adaptador: recebem cartões/projeções da aplicação.

## Para o próximo bloco (F06), sem inventar

- `ProviderService.route` já devolve decisão com ranking/custo/qualidade: F06.T02 liga essa
  decisão ao `provider_for` e registra o efetivo por tentativa.
- O registro aceita N por tarefa: a decisão de "qual" é política, não estrutura.
- Testes existentes que protegem o contrato: `test_provider_catalog.py`,
  `test_provider_service.py`, `test_port_contracts.py` (este tem 2 falhas sensíveis à ordem —
  ver `pre-existing-failures.md`).