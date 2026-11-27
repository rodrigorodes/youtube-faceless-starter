# PC-03.01 Execution Evidence

**Task ID:** `PC-03.01`  
**Description:** Canonical Voice Catalog, Channel Vocal Identity & Frozen Run Configuration  
**Executed by:** `Gemini 3.8 Flash Vertex`  
**Date:** 2026-11-27  
**Branch:** `develop`  
**Status:** `VERIFIED`

---

## 1. Implementação Técnica

1. **Migração de Banco de Dados:**
   - Arquivo: `renderer/app/studio/adapters/postgres/migrations/0057_voice_identity.sql`
   - Adicionada coluna `voice_settings JSONB NOT NULL DEFAULT '{}'::jsonb` em:
     - `studio.channel_profiles`
     - `studio.videos`
     - `studio.scenes`
   - Rollback seguro documentado no header da migration.
   - Atualizado `tests/test_db.py`.

2. **Domínio e Imutabilidade Profunda:**
   - `renderer/app/studio/domain/channel.py`:
     - `ChannelProfile.voice_settings` implementado como `Mapping[str, object]` encapsulado em `MappingProxyType`.
     - `validate_voice_settings` valida que todos os valores são escalares primitivos (`int`, `float`, `str`, `bool`) e restringe o tamanho das chaves.
     - `ChannelProfile.__hash__` calcula hash determinístico baseado nos itens ordenados de `voice_settings`, garantindo hashability estável em `set` e `dict`.
   - `renderer/app/studio/domain/visual_style.py`:
     - `_clean_voice` estendido para suportar parâmetros adicionais de voz (`pacing`, `pitch`, `emotion`, `volume`).

3. **Herança Audiovisual e Congelamento de Run:**
   - `renderer/app/studio/domain/effective_config.py`:
     - `_merge_audiovisual` suporta `channel_defaults` com precedência: `ENGINE < CHANNEL (defaults) < STYLE < CHANNEL (patch) < VIDEO (patch)`.
     - `resolve_effective_config` materializa `voice` e `voice_settings` com proveniência de canal.
     - Prova de isolamento: alteração no perfil do canal pós-criação do run não contamina o snapshot gravado em `studio.production_runs`.

4. **Desacoplamento Arquitetural e API:**
   - `renderer/app/studio/application/use_cases.py`:
     - `UseCases` estendido com `preview_voice`, `list_voices` e `find_voice`.
     - `SynthesizeVoicePreview` encapsula a síntese em áudio sem expor adaptadores à API.
   - `renderer/app/studio/composition/wiring.py`:
     - Injeta `list_voice_catalog` e `find_voice_profile` em `UseCases.from_repo`.
   - `renderer/app/studio/api/routes.py`:
     - `GET /studio/voices` e `POST /studio/voices/preview` utilizam `_need(uc, ...)` e eliminam qualquer import de `composition` ou `adapters`.
     - `FileResponse` em `/studio/voices/preview` utiliza `BackgroundTask(wav_path.unlink, missing_ok=True)` para limpeza garantida de temporários.
     - `ChannelProfileIn` e `ChannelUpdateIn` com suporte explícito a `voice_settings`, e preservação da concorrência otimista (HTTP 409 para `ChannelVersionConflict`).

5. **Criação Transacional de Canal:**
   - `renderer/app/studio/application/channel_creation.py`:
     - `_snapshot` atualizado para converter instâncias de `Mapping` para `dict`.
     - `_CHANNEL_PROFILE_COLS` e a query `INSERT` em `studio.channel_profiles` propagam `voice_settings` atomicamente.

---

## 2. Evidências de Teste

- **Testes Unitários e Integrados em Container:**
  - `tests/test_pc03_voice_identity.py` + `tests/test_db.py`: `21 passed` em 7.25s.
  - `tests/test_channel_api.py` + `tests/test_channel_creation_use_case.py` + `tests/test_channel_preferences_api.py`: `44 passed` em 16.13s.
  - Suíte consolidada de canais e vozes: `65 passed` em 23.38s.
  - Suíte completa de container (tags, banco, canais, produção, voz): `154 passed` em 68.68s.
- **Testes Locais de Domínio e Arquitetura:**
  - `tests/test_architecture.py`, `tests/test_contracts_snapshot.py`, `tests/test_effective_config.py`, `tests/test_visual_style_domain.py`, `tests/test_channel_domain.py`: `120 passed` em 1.12s.
- **Fail-Closed & Custo Zero:**
  - ElevenLabs e Kokoro retornam `available=False` e falham com HTTP 422 sem chamadas de rede.
  - Custo externo: `$0.00 USD`.
