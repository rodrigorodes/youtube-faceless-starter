-- P03 (revisão): licença só com tab/quebra de linha também é branco (btrim só aparava espaços).
ALTER TABLE studio.assets DROP CONSTRAINT assets_license_nonblank;
ALTER TABLE studio.assets ADD CONSTRAINT assets_license_nonblank CHECK (license !~ '^\s*$');
