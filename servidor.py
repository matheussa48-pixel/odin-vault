import os
import time
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from supabase import create_client, Client

app = Flask(__name__, static_folder="static", static_url_path="/static")

# Variáveis de ambiente configuradas no Render
DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "vault-files")

supabase: Client | None = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_db():
    if not DATABASE_URL:
        raise RuntimeError("A variável de ambiente DATABASE_URL não está configurada.")
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    return conn


def init_db():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS categorias (
                    id SERIAL PRIMARY KEY,
                    nome TEXT NOT NULL,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conteudos (
                    id SERIAL PRIMARY KEY,
                    titulo TEXT NOT NULL,
                    descricao TEXT DEFAULT '',
                    link TEXT DEFAULT '',
                    categoria_id INTEGER REFERENCES categorias(id) ON DELETE SET NULL,
                    arquivo_path TEXT DEFAULT '',
                    arquivo_nome TEXT DEFAULT '',
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # Garante que a coluna arquivo_path existe caso a tabela já existisse
            cur.execute("""
                ALTER TABLE conteudos
                ADD COLUMN IF NOT EXISTS arquivo_path TEXT DEFAULT '';
            """)
            cur.execute("""
                ALTER TABLE conteudos
                ADD COLUMN IF NOT EXISTS arquivo_nome TEXT DEFAULT '';
            """)
        conn.commit()
    finally:
        conn.close()


def upload_arquivo_supabase(file_storage) -> tuple[str, str]:
    """Envia o ficheiro (.apk, .zip, imagem, etc.) para o Supabase Storage e retorna (url_publica, nome_limpo)."""
    if not supabase:
        raise RuntimeError("Supabase Storage não configurado. Verifique SUPABASE_URL e SUPABASE_KEY.")

    nome_original = secure_filename(file_storage.filename or "arquivo.bin")
    if not nome_original:
        nome_original = f"arquivo_{int(time.time())}.bin"

    # Evita sobrescrever ficheiros com o mesmo nome (ex.: app.apk ou backup.zip)
    nome_unico = f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{nome_original}"
    conteudo_bytes = file_storage.read()
    content_type = file_storage.mimetype or "application/octet-stream"

    supabase.storage.from_(SUPABASE_BUCKET).upload(
        path=nome_unico,
        file=conteudo_bytes,
        file_options={"content-type": content_type, "upsert": "false"},
    )

    public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(nome_unico)
    return public_url, nome_original


# Inicializa as tabelas ao arrancar o servidor
try:
    init_db()
except Exception as e:
    print(f"[AVISO init_db]: {e}")


@app.route("/")
def index():
    if os.path.exists("app.html"):
        return send_from_directory(".", "app.html")
    return jsonify({"status": "ok", "servico": "Odin Vault API"})


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "db_configurado": bool(DATABASE_URL),
        "storage_configurado": bool(supabase),
        "bucket": SUPABASE_BUCKET,
    })


@app.route("/api/categorias", methods=["GET", "POST"])
def categorias():
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if request.method == "POST":
                data = request.get_json(silent=True) or {}
                nome = (data.get("nome") or "").strip()
                if not nome:
                    return jsonify({"erro": "Nome da categoria é obrigatório."}), 400

                cur.execute(
                    "INSERT INTO categorias (nome) VALUES (%s) RETURNING *;",
                    (nome,),
                )
                nova = cur.fetchone()
                conn.commit()
                return jsonify(nova), 201

            cur.execute("SELECT * FROM categorias ORDER BY id DESC;")
            rows = cur.fetchall()
            return jsonify(rows)
    finally:
        conn.close()


@app.route("/api/conteudos", methods=["GET", "POST"])
def conteudos():
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if request.method == "POST":
                # Aceita tanto multipart/form-data (com ficheiro) quanto JSON
                if request.content_type and "multipart/form-data" in request.content_type:
                    form = request.form
                    titulo = (form.get("titulo") or "").strip()
                    descricao = (form.get("descricao") or "").strip()
                    link = (form.get("link") or "").strip()
                    categoria_id = form.get("categoria_id")
                    arquivo = request.files.get("arquivo") or request.files.get("file")
                else:
                    data = request.get_json(silent=True) or {}
                    titulo = (data.get("titulo") or "").strip()
                    descricao = (data.get("descricao") or "").strip()
                    link = (data.get("link") or "").strip()
                    categoria_id = data.get("categoria_id")
                    arquivo = None

                if not titulo:
                    return jsonify({"erro": "Título é obrigatório."}), 400

                cat_id_int = int(categoria_id) if str(categoria_id or "").isdigit() else None
                arquivo_url = ""
                arquivo_nome = ""

                if arquivo and arquivo.filename:
                    arquivo_url, arquivo_nome = upload_arquivo_supabase(arquivo)

                cur.execute(
                    """
                    INSERT INTO conteudos (titulo, descricao, link, categoria_id, arquivo_path, arquivo_nome)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING *;
                    """,
                    (titulo, descricao, link, cat_id_int, arquivo_url, arquivo_nome),
                )
                criado = cur.fetchone()
                conn.commit()
                return jsonify(criado), 201

            cur.execute("""
                SELECT c.*, cat.nome AS categoria_nome
                FROM conteudos c
                LEFT JOIN categorias cat ON c.categoria_id = cat.id
                ORDER BY c.id DESC;
            """)
            rows = cur.fetchall()
            return jsonify(rows)
    except Exception as e:
        conn.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/conteudos/<int:conteudo_id>", methods=["DELETE"])
def deletar_conteudo(conteudo_id):
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("DELETE FROM conteudos WHERE id = %s RETURNING id;", (conteudo_id,))
            removido = cur.fetchone()
            conn.commit()
            if not removido:
                return jsonify({"erro": "Conteúdo não encontrado."}), 404
            return jsonify({"removido": True, "id": removido["id"]})
    finally:
        conn.close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
