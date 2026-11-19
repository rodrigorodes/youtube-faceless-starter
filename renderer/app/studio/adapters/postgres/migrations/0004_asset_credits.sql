-- P03: atribuição e origem do asset; licença não pode ser só espaços.
ALTER TABLE studio.assets
    ADD COLUMN attribution text NOT NULL DEFAULT '',
    ADD COLUMN source_url text NOT NULL DEFAULT '',
    ADD CONSTRAINT assets_license_nonblank CHECK (btrim(license) <> '');
