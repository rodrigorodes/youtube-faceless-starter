# Estender o Studio: providers e portas

Revisado em 24/11/2026. [Mapa operacional](11-arquitetura-operacional.md) ·
[Configuração](04-variaveis-de-ambiente.md).

## Fronteiras e fontes de verdade

| Camada | Responsabilidade | Fonte |
|---|---|---|
| Domínio | Contratos e políticas, sem imports de infraestrutura | `renderer/app/studio/domain/` |
| Aplicação | Casos de uso com dependências injetadas; não importa adapters/API | `renderer/app/studio/application/` |
| Portas | Interfaces e resultados usados pelos casos de uso | `renderer/app/studio/application/ports.py` |
| Adaptadores | HTTP, arquivos, PostgreSQL, mídia e SDKs | `renderer/app/studio/adapters/` |
| Composição | Registro, catálogo, roteamento e montagem de dependências | `renderer/app/studio/composition/` |

O antigo arquivo `composition.py` foi dividido: `settings.py` lê configuração,
`providers.py` contém catálogo/probes/roteamento e `wiring.py` monta o Studio.
Não adicionar nomes de fornecedores ao domínio para fazer dispatch.

`tests/test_architecture.py` verifica imports de banco/rede, mídia e SDKs, além de
nomes de fornecedores no domínio. É um check disponível; a CI versionada de
higiene não executa automaticamente toda essa suíte. A guarda de imports também
não prova ausência de qualquer I/O via `Path`; preserve as portas existentes e
evite aumentar esse acoplamento.

## Adicionar provider a uma porta existente

1. Leia a interface atual em `application/ports.py` e o adaptador mais próximo.
   Portas centrais: `TextModel`, `ImageModel`, `Voice`, `Renderer`; busca de mídia
   tem capacidade própria. Não copie uma assinatura de documentação antiga.
2. Implemente o adapter em `adapters/<nome>.py`. Identidade `name`/`model`, resultado,
   erro, timeout e estimativa de custo devem refletir a chamada real. SDK só aqui.
3. Registre a factory em `Studio.__init__`, em `composition/wiring.py`, por
   `register(kind, name, factory)`. O modelo é passado à factory; credenciais
   chegam via Settings/portas, nunca do domínio.
4. Declare a implementação em `_provider_implementations`, em
   `composition/providers.py`, com capacidades, validação, custo e motivo de
   indisponibilidade. Registro existente não significa capacidade implementada:
   Veo é o exemplo de stub que deve continuar indisponível.
5. Se precisar de segredo/configuração, acrescente campo e leitura em
   `composition/settings.py`, encaminhamento explícito no Compose, exemplo
   **sem segredo** e documentação. Variável só em `.env` não chega ao container.
6. Adicione probe em `_provider_probes` quando útil. Conectividade não comprova
   autorização para todos os modelos, qualidade, cobrança ou licença.
7. Atualize catálogo esperado/contratos em `tests/test_port_contracts.py` e
   testes de comportamento do adapter. Preserve guard de custo, snapshot de
   seleção por run e semântica de cache.
8. Verifique uma execução com provider fake pela mesma porta; depois, se
   autorizado, faça validação real isolada. Não use token/banco de produção em testes.

Custos: declarar `free`, `estimate` ou `unknown` com evidência; ausência de preço
não vira zero. Em operação paga, reserva e confirmação do gasto devem usar os
contratos existentes. Timeout de uma chamada externa não prova ausência de efeito.

## Adicionar capacidade/porta nova

1. Defina interface e tipos puros na aplicação e injete-a no caso de uso.
2. Implemente adapters e monte-os na composição.
3. Se a capacidade for configurável por projeto, atualize `KINDS`, `_DEFAULTS` e
   `ProjectConfig` em `application/config.py`, catálogo, snapshot e consumidores.
   `search` já é exemplo de capacidade construível que não pertence às quatro
   chaves de configuração de projeto.
4. Atualize testes de fronteira, catálogo, comportamento e fluxo; registre
   finalidade, obrigatoriedade, origem e default na documentação de configuração.

## Exemplo de evolução: voz de nuvem

Um provider `elevenlabs` seria uma implementação **nova, ainda não entregue** de
`Voice`, com adapter, factory e catálogo. Não basta escrever
`STUDIO_VOICE=elevenlabs:<voz>` hoje.

O modelo efetivo precisa identificar a voz realmente sintetizada: entra no
fingerprint/cache e no ledger em `application/render.py` (`_voice_identity`).
Preserve duração real, identidade do áudio e contrato de custo; modelo diferente
não deve reutilizar áudio da voz anterior. Para Piper, trocar o arquivo/modelo
exige rever calibração, conforme o guia de configuração.

## Limite da checagem de contrato

`tests/test_port_contracts.py` verifica registro/catálogo e presença de membros
nas portas marcadas `@runtime_checkable`; não substitui testes de assinatura,
semântica, erro ou efeito. A prova importante é o caso de uso real consumindo o
adapter pela porta, sem depender do fornecedor no núcleo.
