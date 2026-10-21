-- Somente para instalações SQL Server existentes; SQLite atualiza automaticamente.
-- Execute uma vez antes de iniciar a versão nova em um SQL Server.
IF COL_LENGTH('dbo.items', 'condition') IS NULL
BEGIN
    ALTER TABLE dbo.items
    ADD condition VARCHAR(20) NOT NULL
        CONSTRAINT DF_items_condition DEFAULT ('UNSPECIFIED');
END;
