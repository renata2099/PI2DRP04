# Armazém — WMS e Gestão de Equipamentos

Sistema web para rede interna que reúne controle de almoxarifado, empréstimos e locações. Desenvolvido em Python/Flask, com SQL Server em produção e SQLite disponível apenas para desenvolvimento.

## Funcionalidades entregues

- login com perfis `admin`, `manager`, `operator` e `viewer`;
- filiais e depósitos independentes;
- materiais de consumo com entrada, saída, saldo, estoque mínimo e histórico;
- equipamentos individualizados por patrimônio e número de série;
- fotos e QR Code individual de cada equipamento;
- pessoas classificadas como funcionário, cliente ou fornecedor;
- empréstimo sem cobrança ou locação com valor diário;
- multa diária automática por atraso e registro de pagamentos;
- aprovação ou recusa por gestor/administrador;
- reserva do equipamento durante a aprovação, impedindo duplicidade;
- devolução com condição do bem e bloqueio para manutenção quando danificado;
- termo de responsabilidade/locação gerado em PDF;
- trilha de eventos por usuário e data.

## Arquitetura

```text
Navegador na rede interna
        │ HTTP/HTTPS
        ▼
Waitress + aplicação Flask
        ├── SQLAlchemy ── SQL Server
        ├── uploads ───── fotos dos equipamentos
        └── ReportLab ─── termos em PDF
```

As fotos ficam no servidor da aplicação e o banco guarda o nome do arquivo. Em produção, inclua a pasta `instance/uploads` no backup junto com o banco.

## Instalação no Windows Server

Pré-requisitos:

- Python 3.11 ou superior;
- SQL Server 2019 ou superior;
- Microsoft ODBC Driver 18 for SQL Server;
- acesso TCP entre o servidor da aplicação e o SQL Server.

Abra o PowerShell na pasta do projeto:

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edite `.env`. Exemplo com autenticação do SQL Server:

```ini
SECRET_KEY=gere-uma-chave-longa-e-unica
DATABASE_URL=mssql+pyodbc://wms_app:SENHA@SERVIDOR/AlmoxarifadoWMS?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
UPLOAD_FOLDER=D:/WMS/uploads
COMPANY_NAME=Nome da Empresa
```

Se usuário ou senha tiver caracteres especiais, aplique URL encoding ou use uma string ODBC completa. Nunca versione o arquivo `.env`.

1. Execute `sql/01_create_database.sql` no SQL Server Management Studio.
2. Crie as tabelas e a carga inicial:

```powershell
.venv\Scripts\flask --app app init-db
```

3. Inicie:

```powershell
python run_server.py
```

4. Acesse `http://IP-DO-SERVIDOR:5000` em outro computador da rede.

Login inicial: `admin@empresa.local` / `Admin@123`. Troque essa senha antes de liberar o sistema. A primeira versão permite definir senhas de novos usuários na área Administração; a alteração da senha inicial deve ser feita pelo administrador no banco ou implementada antes do go-live.

## Uso operacional

### Configuração inicial

1. Entre como administrador.
2. Em **Administração**, cadastre filiais, depósitos e usuários.
3. Em **Itens**, cadastre materiais ou modelos de equipamentos.
4. Em **Equipamentos**, crie cada unidade física e adicione suas fotos.
5. Em **Clientes **, cadastre quem receberá os bens.

### Almoxarifado

- Use **Entrada** para compra, devolução ao estoque ou ajuste positivo.
- Use **Saída** para consumo ou ajuste negativo.
- Informe pedido, nota fiscal ou requisição em **Documento/referência**.
- O sistema não aceita saída superior ao saldo disponível.

### Empréstimo ou locação

1. Abra uma solicitação escolhendo equipamento, responsável, modalidade e prazo.
2. O equipamento fica `RESERVED`.
3. Gestor ou administrador aprova; o bem passa para `LOANED`.
4. Imprima o termo em PDF e colha a assinatura.
5. Na devolução, registre a condição. Danificado vai para `MAINTENANCE`.

Para locação, o total é:

```text
(dias de uso × diária) + (dias de atraso × multa diária) − desconto
```

## Perfis

| Perfil | Consulta | Movimenta/cadastra | Aprova/recusa | Configura usuários |
|---|---:|---:|---:|---:|
| viewer | Sim | Não | Não | Não |
| operator | Sim | Sim | Não | Não |
| manager | Sim | Sim | Sim | Não |
| admin | Sim | Sim | Sim | Sim |

Usuários ligados a uma filial veem os equipamentos daquela filial. Administradores sem filial podem operar todas.

## Backup e segurança

- backup diário do banco com retenção definida pela TI;
- backup diário da pasta de uploads;
- HTTPS por proxy reverso (IIS ou Nginx), mesmo na rede interna;
- usuário de banco exclusivo e com menor privilégio possível;
- `SECRET_KEY` exclusiva e fora do repositório;
- firewall liberando a porta somente para a rede corporativa;
- teste trimestral de restauração;
- política de retenção e base legal para CPF, telefone e fotos, conforme LGPD.

## Testes

```powershell
pip install pytest
pytest -q
```

Os testes cobrem autenticação/cadastro, bloqueio de estoque negativo e cálculo de locação/multa.

## Limites conscientes do MVP

- não inclui integração com Protheus, Active Directory, emissão fiscal ou gateway de pagamento;
- o PDF registra o termo, mas a assinatura é manual;
- não há leitura direta pela câmera: o QR é gerado e abre a ficha quando escaneado;
- não há redefinição de senha por e-mail;
- não há exclusão física de históricos, preservando rastreabilidade.

Esses pontos podem ser adicionados sem alterar o modelo central.

