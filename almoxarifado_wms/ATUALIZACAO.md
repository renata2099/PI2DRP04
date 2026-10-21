# Atualização do WMS — categorias, responsáveis e termos

Este pacote atualiza o projeto original **sem alterar o esquema do banco**.

## Antes de atualizar no Windows

1. Encerre o servidor com `Ctrl + C`.
2. Faça uma cópia de segurança **da pasta inteira do projeto**, especialmente `instance/wms.db` e `instance/uploads/` (se estiver utilizando SQLite). Para SQL Server, faça o backup normal do banco no servidor.
3. Atualize **somente o código**. Não apague nem substitua seu banco `wms.db`, seus uploads, sua `.venv` ou seu `.env`.
4. Arquivos alterados: `app.py`, `templates/items.html`, `templates/loans.html`, `templates/assets.html`, `templates/asset_detail.html`, `static/style.css`.
5. Arquivo novo e obrigatório: `loan_pdf.py` (coloque ao lado de `app.py`).
6. Execute normalmente o `start.bat` ou `python run_server.py` (no ambiente virtual existente).

**Importante:** o ZIP enviado para análise **não continha `wms.db`**, portanto esta atualização não inclui dados de usuários, itens, empréstimos ou o banco existente. O código utiliza as mesmas tabelas já criadas. Não execute `init-db` para tentar recuperar dados.

## Novidades

### Itens

- Lista de categorias extraída automaticamente dos itens cadastrados.
- Ao selecionar `+ Cadastrar nova categoria`, surge um campo para digitar o nome.
- A nova categoria passa a ser opção **depois de cadastrar o item**.
- Reutilização da grafia existente, ignorando diferenças de caixa no cadastro.
- Não foi criada uma tabela `categories`: isso evita migração do banco para esta atualização.

### Equipamentos e empréstimos

- O responsável aparece de forma destacada na listagem de empréstimos, nos cartões de equipamentos e na ficha do equipamento.
- Estados de reserva, posse atual e devolução ficam distintos na tela.
- Datas de solicitação, retirada, prazo e devolução mostradas conforme disponíveis.
- Campo de registro de pagamento deixa de ficar comprimido como no print anterior.

### Termo PDF

- Identificação de empresa, pessoa, documento, contato e colaboradores envolvidos.
- Modelo, patrimônio, série, filial, depósito, condição, datas e modalidade.
- Valores da operação, pagamentos, observações e regras de responsabilidade.
- Espaços para data de entrega, assinaturas e conferência da devolução.
- Paginação automática, adequada para termos com observações longas.

## Observações

- Não substitui assinatura eletrônica nem aprovação jurídica das condições do termo.
- Se o valor de diárias não aparecer correto, confira a modalidade e os valores registrados no aluguel.
- Para exibir o nome da empresa no PDF, defina `COMPANY_NAME` no `.env` utilizado pelo sistema.
- Testes: `pytest -q` (com dependências de `requirements-dev.txt`).
