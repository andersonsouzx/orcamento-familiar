# Orçamento Familiar — Calculadora de Despesas Mensais

Aplicação web desenvolvida em **Python** e **Flask** com persistência em **SQLite** para controle de orçamento doméstico, acompanhamento de metas por categoria e cálculo automático de saldo restante.

## Funcionalidades

- **Indicadores em Tempo Real:** Exibição da renda familiar mensal (editável), total de despesas, percentual comprometido e saldo restante.
- **Limites por Categoria:** Barras de progresso dinâmicas que mudam de cor conforme o consumo do teto mensal de cada categoria (`Moradia`, `Alimentação`, `Contas Fixas`, `Transporte` e `Lazer`).
- **Gestão de Lançamentos:** Cadastro e exclusão de despesas com atualização imediata do banco de dados.
- **Interface Responsiva:** Desenvolvida com Bootstrap 5 em modo escuro (*Dark Mode*).

## Tecnologias Utilizadas

- **Backend:** Python 3.12, Flask
- **Banco de Dados:** SQLite3
- **Frontend:** HTML5, Jinja2, Bootstrap 5.3, Bootstrap Icons

## Como Executar Localmente

```bash
# Clonar o repositório
git clone [https://github.com/andersonsouzx/orcamento-familiar.git](https://github.com/andersonsouzx/orcamento-familiar.git)
cd orcamento-familiar

# Criar e ativar o ambiente virtual
python -m venv venv
source venv/Scripts/activate  # No Windows (Git Bash)

# Instalar dependências e iniciar
pip install flask
python app.py