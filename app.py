import os
import sqlite3
from datetime import date, datetime
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "orcamento.db")


# Filtros personalizados para formatar moeda e data no HTML
@app.template_filter("moeda")
def formatar_moeda(valor):
    if valor is None:
        valor = 0.0
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@app.template_filter("data_br")
def formatar_data_br(data_iso):
    try:
        return datetime.strptime(data_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return data_iso


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes (
            id INTEGER PRIMARY KEY,
            renda_mensal REAL NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            limite_mensal REAL NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lancamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            data TEXT NOT NULL,
            categoria_id INTEGER NOT NULL,
            FOREIGN KEY (categoria_id) REFERENCES categorias (id)
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM categorias")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO configuracoes (id, renda_mensal) VALUES (1, 4500.00)")

        categorias_iniciais = [
            ("Moradia", 1600.00),
            ("Alimentação", 1000.00),
            ("Contas Fixas", 500.00),
            ("Transporte", 450.00),
            ("Lazer", 400.00),
        ]
        cursor.executemany(
            "INSERT INTO categorias (nome, limite_mensal) VALUES (?, ?)",
            categorias_iniciais,
        )

        hoje = date.today().isoformat()
        lancamentos_iniciais = [
            ("Aluguel Apartamento", 1350.00, hoje, 1),
            ("Compra do Mês (Mercado)", 620.50, hoje, 2),
            ("Feira e Açougue", 185.00, hoje, 2),
            ("Conta de Luz (Enel)", 145.80, hoje, 3),
            ("Internet Fibra", 119.90, hoje, 3),
            ("Recarga Bilhete Único", 220.00, hoje, 4),
            ("Cinema e Lanche", 130.00, hoje, 5),
        ]
        cursor.executemany(
            "INSERT INTO lancamentos (descricao, valor, data, categoria_id) VALUES (?, ?, ?, ?)",
            lancamentos_iniciais,
        )

    conn.commit()
    conn.close()


@app.route("/")
def index():
    conn = get_db_connection()

    config = conn.execute("SELECT renda_mensal FROM configuracoes WHERE id = 1").fetchone()
    renda_mensal = config["renda_mensal"] if config else 0.0

    categorias_db = conn.execute("""
        SELECT 
            c.id, 
            c.nome, 
            c.limite_mensal,
            COALESCE(SUM(l.valor), 0) AS total_gasto
        FROM categorias c
        LEFT JOIN lancamentos l ON c.id = l.categoria_id
        GROUP BY c.id
    """).fetchall()

    # Calcula percentual e cor da barra de progresso para cada categoria
    categorias = []
    for cat in categorias_db:
        limite = cat["limite_mensal"]
        gasto = cat["total_gasto"]
        percentual = (gasto / limite * 100) if limite > 0 else 0
        if percentual >= 100:
            cor_barra = "bg-danger"
        elif percentual >= 80:
            cor_barra = "bg-warning"
        else:
            cor_barra = "bg-success"

        categorias.append({
            "id": cat["id"],
            "nome": cat["nome"],
            "limite_mensal": limite,
            "total_gasto": gasto,
            "percentual": round(percentual, 1),
            "largura_barra": min(percentual, 100),
            "cor_barra": cor_barra,
        })

    lancamentos = conn.execute("""
        SELECT 
            l.id, l.descricao, l.valor, l.data, c.nome AS categoria_nome
        FROM lancamentos l
        JOIN categorias c ON l.categoria_id = c.id
        ORDER BY l.data DESC, l.id DESC
    """).fetchall()

    conn.close()

    total_despesas = sum(cat["total_gasto"] for cat in categorias)
    saldo_restante = renda_mensal - total_despesas
    percentual_renda = (total_despesas / renda_mensal * 100) if renda_mensal > 0 else 0

    return render_template(
        "index.html",
        renda_mensal=renda_mensal,
        total_despesas=total_despesas,
        saldo_restante=saldo_restante,
        percentual_renda=round(percentual_renda, 1),
        categorias=categorias,
        lancamentos=lancamentos,
        hoje=date.today().isoformat(),
    )


@app.route("/adicionar", methods=["POST"])
def adicionar():
    descricao = request.form.get("descricao")
    valor = float(request.form.get("valor"))
    data_lancamento = request.form.get("data")
    categoria_id = int(request.form.get("categoria_id"))

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO lancamentos (descricao, valor, data, categoria_id) VALUES (?, ?, ?, ?)",
        (descricao, valor, data_lancamento, categoria_id),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


@app.route("/atualizar-renda", methods=["POST"])
def atualizar_renda():
    nova_renda = float(request.form.get("renda_mensal"))
    conn = get_db_connection()
    conn.execute("UPDATE configuracoes SET renda_mensal = ? WHERE id = 1", (nova_renda,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


@app.route("/excluir/<int:id>", methods=["POST"])
def excluir(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM lancamentos WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


@app.route("/resetar", methods=["GET", "POST"])
def resetar():
    conn = get_db_connection()
    conn.execute("DROP TABLE IF EXISTS lancamentos")
    conn.execute("DROP TABLE IF EXISTS categorias")
    conn.execute("DROP TABLE IF EXISTS configuracoes")
    conn.commit()
    conn.close()
    init_db()
    return redirect(url_for("index"))

init_db()

if __name__ == "__main__":
    app.run(debug=True)