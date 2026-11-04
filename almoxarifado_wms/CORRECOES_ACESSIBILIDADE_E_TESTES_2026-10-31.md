# Atualização WMS — acessibilidade e regras críticas

**Versão:** 31/10/2026  
**Base utilizada:** `almoxarifado_wms(1).zip`, recebido em 29/10/2026.  
**Escopo:** melhorias pontuais, sem reconstrução do sistema, sem migrações e sem perda dos dados preexistentes.

## 1. Correções aplicadas

### Acessibilidade

- `templates/base.html`: adicionados link de salto para o conteúdo principal, nome explícito da navegação, identificação da página atual, ponto de foco no conteúdo e avisos semânticos (`role="status"`/`role="alert"`). Mantido `lang="pt-BR"` e títulos individuais das páginas.
- `templates/asset_detail.html`: campos de fotografia e legenda receberam rótulos visíveis e associados; o QR Code e as fotos receberam descrições contextuais.
- `templates/items.html`, `stock.html`, `loans.html`, `admin.html` e `parties.html`: tabelas largas receberam regiões roláveis nomeadas e acessíveis pelo teclado. As ações repetidas de empréstimos/itens receberam nomes individualizados.
- `static/style.css`: texto secundário passou a utilizar `#56625c`; adicionado foco visível, estilo para link de salto, adaptações para telas de 320 px e manutenção da opção de sair em dispositivos móveis.

### Regras críticas e permissões

- Validação de tipo de movimento (`IN`/`OUT`), quantidade estritamente positiva, finitude numérica e no máximo três casas decimais. Movimentos inválidos não gravam no histórico nem geram saldos indevidos.
- Cadastro de movimentações limitado a materiais ativos e depósitos ativos, respeitando a filial do usuário; a saída acima do saldo continua bloqueada.
- Perfil `viewer` não consegue gravar itens, estoque, equipamentos, fotos, pessoas, empréstimos, devoluções ou pagamentos, inclusive por requisição direta. Os formulários de edição deixam de aparecer nesse perfil.
- Somente gestores ou administradores aprovam ou recusam empréstimos e registram pagamentos; operadores podem solicitar e devolver, mas não aprovar nem registrar pagamentos.
- Pagamentos negativos, nulos, não finitos, com frações de centavo ou acima do valor atual em aberto são recusados.
- Solicitações de empréstimo conferem data futura, disponibilidade, pessoa ativa, modalidade e valores válidos.
- As consultas, fotos, QR Codes, termos e movimentações passam a respeitar a filial do usuário quando configurada; administradores mantêm o escopo global.
- A criação de equipamentos valida a correspondência depósito/filial e o tipo de item.

## 2. Verificações realizadas

- **20 testes automatizados** com `pytest` na base temporária em memória, incluindo autorização, saldo, movimentações inválidas, aprovação, devolução, valor financeiro exato, CSV e navegação sem autenticação.
- Renderização de **oito telas a 320 px**, usando Chromium e HTML/CSS produzidos pelo Flask: não houve largura horizontal excedente no documento. Tabelas largas mantêm rolagem **dentro de sua própria região** (permitida para dados tabulares que requerem duas dimensões).
- Verificação dos formulários visíveis dessas telas quanto à presença de rótulos associados.
- O banco SQLite e as imagens incluídos no ZIP original foram comparados byte a byte e **não foram modificados**.

**Limite da verificação:** esses testes não equivalem a uma certificação integral de conformidade WCAG 2.1 AA. Ainda é recomendável executar axe-core/Lighthouse, navegação por teclado, contraste de todos os estados, zoom de 400%, NVDA/VoiceOver e demais critérios WCAG no ambiente realmente implantado, documentando evidências e eventuais problemas encontrados. A versão entregue corrige os achados identificados; não declara aprovação completa sem a auditoria final.

## 3. Como atualizar com segurança

1. Faça backup da instalação atual, especialmente do `instance/wms.db` e de `instance/uploads/` (ou do banco SQL Server, se usado em produção).
2. Descompacte este ZIP em uma **pasta separada** para validar a nova versão. Ele contém **cópias originais** do banco e das imagens recebidos com o projeto, sem alterações.
3. Para atualizar uma instalação já em uso, copie **somente o código** (`app.py`, `templates/`, `static/`, `tests/` e esta documentação), preservando `.env`, `.venv`, banco e arquivos de upload do ambiente de destino.
4. No terminal, com as dependências instaladas, execute `python -m pytest -q` (veja `requirements-dev.txt`).
5. Reinicie o serviço e force atualização no navegador (`Ctrl+F5`); teste login, consulta, movimentação, aprovação, devolução, fotos e CSV com contas de cada perfil.

**Importante:** não rode `flask init-db` sobre uma base existente para "atualizar" o projeto. Não distribua a terceiros o banco ou as fotos eventualmente contidos na pasta `instance/`. O arquivo `.env` e a senha administrativa inicial também devem ser protegidos.

## 4. Arquivos de código modificados

- `app.py`
- `static/style.css`
- `templates/base.html`
- `templates/asset_detail.html`
- `templates/items.html`
- `templates/stock.html`
- `templates/assets.html`
- `templates/loans.html`
- `templates/parties.html`
- `templates/admin.html`
- `tests/test_app.py`

Nenhum modelo, tabela ou migração de banco foi alterado nesta atualização. O ambiente virtual `.venv` foi intencionalmente excluído do pacote novo: ele é específico do Windows/computador de origem e deve ser recriado conforme o `README.md`.
