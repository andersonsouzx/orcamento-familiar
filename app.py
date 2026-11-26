import os
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "finlar-chave-sessao-2026")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "orcamento.db")

PERCENTUAIS_CATEGORIAS = {
    "Moradia": 0.35,
    "Alimentação": 0.22,
    "Contas Fixas": 0.13,
    "Transporte": 0.10,
    "Lazer": 0.10,
}


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


def aplicar_limites_automaticos(conn, session_id, renda):
    categorias = conn.execute(
        "SELECT id, nome FROM categorias WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    for cat in categorias:
        percentual = PERCENTUAIS_CATEGORIAS.get(cat["nome"], 0.10)
        novo_limite = round(renda * percentual, 2)
        conn.execute(
            "UPDATE categorias SET limite_mensal = ? WHERE id = ? AND session_id = ?",
            (novo_limite, cat["id"], session_id),
        )


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Atualiza tabelas antigas caso ainda não possuam suporte a sessões individuais
    colunas = [row["name"] for row in cursor.execute("PRAGMA table_info(configuracoes)").fetchall()]
    if colunas and "session_id" not in colunas:
        cursor.execute("DROP TABLE IF EXISTS lancamentos")
        cursor.execute("DROP TABLE IF EXISTS categorias")
        cursor.execute("DROP TABLE IF EXISTS configuracoes")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes (
            session_id TEXT PRIMARY KEY,
            renda_mensal REAL NOT NULL,
            criada_em TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            nome TEXT NOT NULL,
            limite_mensal REAL NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lancamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            data TEXT NOT NULL,
            categoria_id INTEGER NOT NULL,
            FOREIGN KEY (categoria_id) REFERENCES categorias (id)
        )
    """)

    conn.commit()
    conn.close()


def limpar_sessoes_antigas(conn):
    limite = (datetime.now() - timedelta(hours=24)).isoformat()
    expiradas = conn.execute(
        "SELECT session_id FROM configuracoes WHERE criada_em < ?",
        (limite,),
    ).fetchall()

    for row in expiradas:
        sid = row["session_id"]
        conn.execute("DELETE FROM lancamentos WHERE session_id = ?", (sid,))
        conn.execute("DELETE FROM categorias WHERE session_id = ?", (sid,))
        conn.execute("DELETE FROM configuracoes WHERE session_id = ?", (sid,))


def seed_session(conn, session_id):
    limpar_sessoes_antigas(conn)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO configuracoes (session_id, renda_mensal, criada_em) VALUES (?, ?, ?)",
        (session_id, 4500.00, datetime.now().isoformat()),
    )

    categorias_iniciais = [
        ("Moradia", 1600.00),
        ("Alimentação", 1000.00),
        ("Contas Fixas", 500.00),
        ("Transporte", 450.00),
        ("Lazer", 400.00),
    ]

    ids_categorias = {}
    for nome, limite in categorias_iniciais:
        cursor.execute(
            "INSERT INTO categorias (session_id, nome, limite_mensal) VALUES (?, ?, ?)",
            (session_id, nome, limite),
        )
        ids_categorias[nome] = cursor.lastrowid

    lancamentos_iniciais = [
        ("Aluguel apartamento", 1350.00, "2026-11-05", ids_categorias["Moradia"]),
        ("Compra do mês (mercado)", 620.50, "2026-11-08", ids_categorias["Alimentação"]),
        ("Internet fibra", 119.90, "2026-11-10", ids_categorias["Contas Fixas"]),
        ("Conta de luz (Enel)", 145.80, "2026-11-14", ids_categorias["Contas Fixas"]),
        ("Feira e açougue", 185.00, "2026-11-18", ids_categorias["Alimentação"]),
        ("Recarga bilhete único", 220.00, "2026-11-21", ids_categorias["Transporte"]),
        ("Cinema e lanche", 130.00, "2026-11-24", ids_categorias["Lazer"]),
    ]

    cursor.executemany(
        "INSERT INTO lancamentos (session_id, descricao, valor, data, categoria_id) VALUES (?, ?, ?, ?, ?)",
        [(session_id, desc, val, dt, cat_id) for desc, val, dt, cat_id in lancamentos_iniciais],
    )


def garantir_sessao(conn):
    sid = session.get("session_id")
    if not sid:
        sid = str(uuid.uuid4())
        session["session_id"] = sid

    existe = conn.execute(
        "SELECT 1 FROM configuracoes WHERE session_id = ?",
        (sid,),
    ).fetchone()

    if not existe:
        seed_session(conn, sid)
        conn.commit()

    return sid


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/dashboard")
def dashboard():
    conn = get_db_connection()
    sid = garantir_sessao(conn)

    config = conn.execute(
        "SELECT renda_mensal FROM configuracoes WHERE session_id = ?",
        (sid,),
    ).fetchone()
    renda_mensal = config["renda_mensal"] if config else 0.0

    categorias_db = conn.execute("""
        SELECT 
            c.id, 
            c.nome, 
            c.limite_mensal,
            COALESCE(SUM(l.valor), 0) AS total_gasto
        FROM categorias c
        LEFT JOIN lancamentos l ON c.id = l.categoria_id AND l.session_id = ?
        WHERE c.session_id = ?
        GROUP BY c.id
    """, (sid, sid)).fetchall()

    categorias = []
    for cat in categorias_db:
        limite = cat["limite_mensal"]
        gasto = cat["total_gasto"]

        if limite > 0:
            percentual = gasto / limite * 100
        elif gasto > 0:
            percentual = 100.0
        else:
            percentual = 0.0

        if percentual >= 100 or (limite == 0 and gasto > 0):
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
        WHERE l.session_id = ?
        ORDER BY l.data DESC, l.id DESC
    """, (sid,)).fetchall()

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
        percentuais_categorias=PERCENTUAIS_CATEGORIAS,
        hoje=date.today().isoformat(),
    )


@app.route("/adicionar", methods=["POST"])
def adicionar():
    descricao = (request.form.get("descricao") or "").strip()
    data_lancamento = request.form.get("data") or date.today().isoformat()

    try:
        valor = float(request.form.get("valor", 0))
        categoria_id = int(request.form.get("categoria_id", 0))
    except (ValueError, TypeError):
        return redirect(url_for("dashboard"))

    if not descricao or valor <= 0 or categoria_id <= 0:
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    sid = garantir_sessao(conn)

    cat_valida = conn.execute(
        "SELECT 1 FROM categorias WHERE id = ? AND session_id = ?",
        (categoria_id, sid),
    ).fetchone()

    if cat_valida:
        conn.execute(
            "INSERT INTO lancamentos (session_id, descricao, valor, data, categoria_id) VALUES (?, ?, ?, ?, ?)",
            (sid, descricao, round(valor, 2), data_lancamento, categoria_id),
        )
        conn.commit()

    conn.close()
    return redirect(url_for("dashboard"))


@app.route("/atualizar-renda", methods=["POST"])
def atualizar_renda():
    try:
        nova_renda = max(0.0, float(request.form.get("renda_mensal", 0)))
    except (ValueError, TypeError):
        return redirect(url_for("dashboard"))

    recalcular = request.form.get("recalcular_limites") == "on"

    conn = get_db_connection()
    sid = garantir_sessao(conn)

    conn.execute(
        "UPDATE configuracoes SET renda_mensal = ? WHERE session_id = ?",
        (round(nova_renda, 2), sid),
    )
    if recalcular:
        aplicar_limites_automaticos(conn, sid, nova_renda)

    conn.commit()
    conn.close()
    return redirect(url_for("dashboard"))


@app.route("/atualizar-limites", methods=["POST"])
def atualizar_limites():
    conn = get_db_connection()
    sid = garantir_sessao(conn)

    categorias = conn.execute(
        "SELECT id FROM categorias WHERE session_id = ?",
        (sid,),
    ).fetchall()

    for cat in categorias:
        campo = request.form.get(f"limite_{cat['id']}")
        if campo is not None and campo.strip() != "":
            try:
                novo_limite = max(0.0, float(campo))
                conn.execute(
                    "UPDATE categorias SET limite_mensal = ? WHERE id = ? AND session_id = ?",
                    (round(novo_limite, 2), cat["id"], sid),
                )
            except (ValueError, TypeError):
                continue

    conn.commit()
    conn.close()
    return redirect(url_for("dashboard"))


@app.route("/excluir/<int:id>", methods=["POST"])
def excluir(id):
    conn = get_db_connection()
    sid = garantir_sessao(conn)
    conn.execute(
        "DELETE FROM lancamentos WHERE id = ? AND session_id = ?",
        (id, sid),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("dashboard"))


@app.route("/resetar", methods=["GET", "POST"])
def resetar():
    conn = get_db_connection()
    sid = garantir_sessao(conn)
    conn.execute("DELETE FROM lancamentos WHERE session_id = ?", (sid,))
    conn.execute("DELETE FROM categorias WHERE session_id = ?", (sid,))
    conn.execute("DELETE FROM configuracoes WHERE session_id = ?", (sid,))
    seed_session(conn, sid)
    conn.commit()
    conn.close()
    return redirect(url_for("dashboard"))


@app.route("/resetar-tudo", methods=["POST"])
def resetar_tudo():
    conn = get_db_connection()
    sid = garantir_sessao(conn)
    conn.execute("DELETE FROM lancamentos WHERE session_id = ?", (sid,))
    conn.execute("UPDATE configuracoes SET renda_mensal = 0.0 WHERE session_id = ?", (sid,))
    conn.execute("UPDATE categorias SET limite_mensal = 0.0 WHERE session_id = ?", (sid,))
    conn.commit()
    conn.close()
    return redirect(url_for("dashboard"))


init_db()

if __name__ == "__main__":
    app.run(debug=True)