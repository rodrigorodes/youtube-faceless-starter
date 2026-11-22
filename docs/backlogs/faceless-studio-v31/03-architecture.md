# Arquitetura alvo

Ver [diagrama de arquitetura](diagrams/01-architecture.md). A UI usa view models existentes. A aplicação resolve configuração de produção a partir dos agregados atuais; o ProductionRun registra entradas criativas congeladas ou referências imutáveis verificadas. Render Plan representa instruções audiovisuais, não toda a autorização operacional. Não criar um banco paralelo de Settings.

## Contrato conceitual (validar no código antes de definir schema)

```yaml
schema_version: 1
project_id: <id>
video_id: <id>
channel_profile: {id: <id>, version: <revision>}
style: {id: <id>, version: <revision>}
editorial: {language: <value>, audience: <value>, pillars: [], narrative: <value>, duration_s: <value>, cta: <value>}
audiovisual: {voice: {}, captions: {}, motion: {}, music: {}, palette: {}}
provider_policy: {profile: <enum>, version: <revision>, preferences: {}}
provenance: {}
```

Contrato ilustrativo, não payload existente. Não incluir tokens, API keys, saldo ou autorização congelada. Evitar guardar apenas hash de revisão mutável; registrar valores necessários ou referências a revisões comprovadamente imutáveis. Canonicalização determinística e versão do schema devem ser documentadas.

| Congelado por run | Dinâmico por operação |
|---|---|
| Editorial, base de estilo, versão, patches resolvidos, voz, parâmetros de render, política de providers | Autorização, grant vigente, limites e saldo, disponibilidade, preço/estimativa, destino validado |
| Referência ao destino pretendido quando aplicável | Verificar se identidade atual corresponde ao destino; mudança exige decisão explícita |

Registrar provider/modelo efetivo por tentativa e artefatos/versões necessários para rastreabilidade. Não prometer determinismo bit a bit de IA generativa.

## Precedência

Selecionar estilo inteiro: `video.style_id > channel.style_id > default`. Depois resolver patches permitidos: `video override > channel override > selected style > engine default`. A aplicabilidade de patch de canal quando o vídeo troca de base deve ser decidida em ADR-004; sugestão: herdar apenas campos semanticamente compatíveis, exigir validação e informar origem. Correção G15 não depende de criar patches.

## Lifecycle

Start resolve e congela antes de efeitos; retry/resume reutilizam; regeneração de cena mantém run salvo revisão explícita; nova produção resolve novamente; publish revalida. Runs legados exigem política explícita, sem fabricar snapshots históricos. Mudança de estilo arquivado não deve mudar execução iniciada.

## Fronteiras

n8n chama casos de uso protegidos; não seleciona identidade de upload de forma independente. Finder consome contexto editorial por contrato, sem acoplamento a FFmpeg. O motor permanece independente de tecnologias da UI. Projeto A não ativa tenancy ou BYOK operacional.
