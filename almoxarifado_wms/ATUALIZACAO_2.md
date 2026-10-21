# WMS — Busca, conservação de itens e patrimônio

## O que mudou

- **Estoque:** a antiga situação **Normal** correspondia a *saldo acima do estoque mínimo*, e não à conservação. Passou a chamar **Em dia**; **Repor** continua quando o saldo está no mínimo ou abaixo dele.
- **Condição física dos itens:** **Novo / Usado / Descarte**, escolhida ao cadastrar e editável depois. Para material de estoque, a classificação é do SKU cadastrado, não de cada unidade física (para distinguir lotes de condições diferentes, cadastre SKUs distintos).
- **Equipamentos:** cada patrimônio tem sua própria condição (**Novo / Usado / Descarte**) independente do status de movimentação (**Disponível / Reservado / Emprestado / Manutenção / Descartado**). Marcar Descarte deixa o patrimônio indisponível para empréstimo, mas não apaga dados nem histórico. Descarte de patrimônio reservado/emprestado é bloqueado.
- **Pesquisas:** campos de busca e filtros nas telas de **Itens**, **Estoque** e **Equipamentos**. Pesquise por SKU, nome, categoria, série, patrimônio, filial ou depósito conforme a tela. **Limpar** remove os filtros.
- **Exportação:** botão **↓ CSV** exporta somente os resultados da consulta filtrada, com `;` como separador e acentuação em UTF-8 para Excel.
- **Devolução:** pode informar "Bom estado" ou "Danificado"; a devolução em bom estado classifica um equipamento emprestado como Usado; danos bloqueiam disponibilidade para manutenção. Na ficha do patrimônio, após reparo e conferência, há botão **Liberar após manutenção**.

## Compatibilidade dos dados existentes

O pacote **não contém seu `wms.db`**. A versão nova adiciona **somente a coluna `items.condition`** para registrar condição dos itens; a estrutura existente do equipamento já tinha `assets.condition`.

- **SQLite:** o sistema detecta e adiciona a coluna automaticamente na primeira inicialização, sem excluir os registros. A execução é idempotente. Cadastros antigos ficam **A classificar**, pois não é correto adivinhar se são novos ou usados. Para classificar, use a coluna de atualização em *Itens* ou a ficha do patrimônio em *Equipamentos*.
- **SQL Server:** antes de iniciar, execute `sql/02_add_item_condition.sql` no banco, fazendo o backup conforme o procedimento da sua empresa.
- A conservação de um item no catálogo não altera automaticamente a condição dos patrimônios associados, pois cada equipamento físico pode estar em um estado diferente.
- Uma classificação *Descarte* em material de estoque **não baixa quantidade automaticamente**: para dar baixa, registre a saída correspondente.

## Atualizar seu Windows com segurança

1. **Feche o servidor** no terminal com `Ctrl+C`.
2. **Faça backup** de `almoxarifado_wms/instance/wms.db` e de `instance/uploads/`, além da pasta do projeto. Se usar SQL Server, faça backup do banco SQL Server.
3. Extraia o ZIP **somente dos arquivos alterados** sobre o projeto instalado, respeitando as pastas (`templates/`, `static/`, `sql/`). **Não substitua `.env`, `.venv`, `wms.db` ou uploads.**
4. Inicie normalmente pelo `start.bat` ou `python run_server.py` (com o ambiente virtual ativo).
5. Atualize o navegador com `Ctrl+F5`. Experimente pesquisar patrimônio/série, classificar equipamento, procurar saldo, exportar CSV e devolver um equipamento de teste.

## Arquivos atualizados

- `app.py`, `models.py`, `loan_pdf.py`
- `templates/items.html`, `templates/stock.html`, `templates/assets.html`, `templates/asset_detail.html`, `templates/loans.html`
- `static/style.css`
- `sql/02_add_item_condition.sql`

Não execute `flask init-db` para tentar atualizar seu cadastro: isso não é uma migração.
