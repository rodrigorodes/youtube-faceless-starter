-- Retrofit do limite de pilares do perfil de canal.
--
-- A 0016 antiga (já aplicada em alguns bancos e registrada em schema_migrations) não tem o CHECK
-- de cardinalidade; editar o arquivo daquela migração não alcança esses bancos, porque o migrador
-- pula versões registradas. Esta migração aditiva garante o limite de 20 pilares e recusa elemento
-- NULL em instalações novas e em bancos que já aplicaram a 0016 antiga.
--
-- Idempotente: a 0016 nova já cria `channel_profiles_pillars_check` inline; o guard `IF NOT EXISTS`
-- por nome e tabela evita constraint duplicada. A cláusula `ADD CONSTRAINT` (sem NOT VALID) valida
-- as linhas existentes dentro da transação da migração; a tabela é pequena, mas isso toma um lock
-- ACCESS EXCLUSIVE em `studio.channel_profiles` durante a validação. Se houver linha legada com
-- mais de 20 pilares ou elemento NULL, a migração falha alto (em vez de truncar silenciosamente).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'channel_profiles_pillars_check'
          AND conrelid = 'studio.channel_profiles'::regclass
    ) THEN
        ALTER TABLE studio.channel_profiles
            ADD CONSTRAINT channel_profiles_pillars_check CHECK (cardinality(pillars) <= 20);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'channel_profiles_pillars_not_null_check'
          AND conrelid = 'studio.channel_profiles'::regclass
    ) THEN
        ALTER TABLE studio.channel_profiles
            ADD CONSTRAINT channel_profiles_pillars_not_null_check
            CHECK (array_position(pillars, NULL) IS NULL);
    END IF;
END
$$;