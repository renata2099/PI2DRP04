/* Execute no SQL Server como administrador. Ajuste os caminhos/tamanhos conforme a infraestrutura. */
IF DB_ID(N'AlmoxarifadoWMS') IS NULL
BEGIN
    CREATE DATABASE AlmoxarifadoWMS;
END;
GO
ALTER DATABASE AlmoxarifadoWMS SET READ_COMMITTED_SNAPSHOT ON;
GO
USE AlmoxarifadoWMS;
GO
/* Opção recomendada: crie um login exclusivo e informe a senha fora do código.
   CREATE LOGIN wms_app WITH PASSWORD = 'SENHA_FORTE_AQUI';
   CREATE USER wms_app FOR LOGIN wms_app;
   ALTER ROLE db_datareader ADD MEMBER wms_app;
   ALTER ROLE db_datawriter ADD MEMBER wms_app;
   ALTER ROLE db_ddladmin ADD MEMBER wms_app; -- retirar após o primeiro init-db
*/

