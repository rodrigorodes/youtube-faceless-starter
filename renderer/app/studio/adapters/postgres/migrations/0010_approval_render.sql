-- NULL identifica decisões legadas sem render comprovado; elas não podem ser publicadas.
ALTER TABLE studio.approvals
    ADD COLUMN output_asset_id text REFERENCES studio.assets(id) ON DELETE RESTRICT;
