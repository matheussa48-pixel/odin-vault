from flask import Flask, jsonify, request, render_template, session, redirect, url_for
import sqlite3
import base64
from functools import wraps

app = Flask(__name__)
app.secret_key = 'odin_vault_super_secret_key_2026'

def get_db():
    conn = sqlite3.connect('vault.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Tabela de Utilizadores com Foto de Perfil
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            foto_perfil TEXT DEFAULT 'https://img.icons8.com/ios-filled/100/ccff00/user-male-circle.png',
            role TEXT DEFAULT 'user',
            status TEXT DEFAULT 'ativo'
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS botoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            icone TEXT DEFAULT 'folder'
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conteudos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            botao_id INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            descricao TEXT NOT NULL,
            link_ferramenta TEXT,
            FOREIGN KEY (botao_id) REFERENCES botoes (id)
        )
    ''')

    # Sistema de Amizades (Com status: 'pendente' ou 'aceito')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS amizades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            de_user_id INTEGER NOT NULL,
            para_user_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pendente',
            FOREIGN KEY (de_user_id) REFERENCES usuarios (id),
            FOREIGN KEY (para_user_id) REFERENCES usuarios (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            conteudo TEXT NOT NULL,
            link_anexo TEXT,
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )
    ''')

    # Mensagens Criptografadas no Chat Privado com suporte a Ficheiros
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mensagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            de_user_id INTEGER NOT NULL,
            para_user_id INTEGER NOT NULL,
            mensagem TEXT NOT NULL,
            link_arquivo TEXT DEFAULT '',
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (de_user_id) REFERENCES usuarios (id),
            FOREIGN KEY (para_user_id) REFERENCES usuarios (id)
        )
    ''')

    cursor.execute("SELECT * FROM usuarios WHERE usuario = 'admin'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO usuarios (usuario, senha, role) VALUES ('admin', 'admin123', 'admin')")

    conn.commit()
    conn.close()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session or session.get('role') != 'admin':
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# Função simples de encriptação/desencriptação Obfuscated Base64 (pode ser expandida para AES)
def enc_msg(texto):
    if not texto: return ""
    return "ENC_" + base64.b64encode(texto.encode('utf-8')).decode('utf-8')

def dec_msg(texto_enc):
    if not texto_enc or not texto_enc.startswith("ENC_"): return texto_enc
    try:
        raw = texto_enc.replace("ENC_", "")
        return base64.b64decode(raw.encode('utf-8')).decode('utf-8')
    except:
        return texto_enc

# --- ROTAS WEB ---

@app.route('/')
@admin_required
def admin_panel():
    return render_template('painel.html', usuario=session['usuario'])

@app.route('/app')
def app_client():
    return render_template('app.html')

@app.route('/login')
def login_page():
    return redirect(url_for('app_client'))

# --- APIS DE AUTENTICAÇÃO E PERFIL ---

@app.route('/api/login', methods=['POST'])
def api_login():
    dados = request.form if request.form else request.json
    usuario = dados.get('usuario')
    senha = dados.get('senha')
    
    conn = get_db()
    user = conn.execute("SELECT * FROM usuarios WHERE usuario = ? AND senha = ?", (usuario, senha)).fetchone()
    conn.close()

    if user:
        session['usuario'] = user['usuario']
        session['role'] = user['role']
        session['user_id'] = user['id']
        return jsonify({
            "status": "sucesso", 
            "usuario": user['usuario'], 
            "role": user['role'], 
            "id": user['id'],
            "foto_perfil": user['foto_perfil']
        })
    return jsonify({"status": "erro", "mensagem": "Credenciais inválidas"}), 401

@app.route('/api/registrar', methods=['POST'])
def api_registrar():
    dados = request.json
    usuario = dados.get('usuario')
    senha = dados.get('senha')
    foto = dados.get('foto_perfil', 'https://img.icons8.com/ios-filled/100/ccff00/user-male-circle.png')
    
    if not usuario or not senha:
        return jsonify({"status": "erro", "mensagem": "Preencha todos os campos"}), 400

    conn = get_db()
    try:
        conn.execute("INSERT INTO usuarios (usuario, senha, foto_perfil, role) VALUES (?, ?, ?, 'user')", (usuario, senha, foto))
        conn.commit()
        conn.close()
        return jsonify({"status": "sucesso", "mensagem": "Conta criada com sucesso!"}), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"status": "erro", "mensagem": "Nome de utilizador já existe!"}), 400

@app.route('/api/perfil/atualizar', methods=['POST'])
def atualizar_perfil():
    dados = request.json
    user_id = dados.get('user_id')
    foto = dados.get('foto_perfil')
    
    conn = get_db()
    conn.execute("UPDATE usuarios SET foto_perfil = ? WHERE id = ?", (foto, user_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "sucesso", "mensagem": "Foto atualizada!"})

# --- APIS DE AMIZADES ---

@app.route('/api/amigos/pedir', methods=['POST'])
def pedir_amizade():
    dados = request.json
    de_id = dados.get('de_id')
    target_username = dados.get('target_username')

    conn = get_db()
    target = conn.execute("SELECT id FROM usuarios WHERE usuario = ?", (target_username,)).fetchone()
    
    if not target:
        conn.close()
        return jsonify({"status": "erro", "mensagem": "Utilizador não encontrado!"}), 404
    
    para_id = target['id']
    if de_id == para_id:
        conn.close()
        return jsonify({"status": "erro", "mensagem": "Não pode adicionar a si mesmo!"}), 400

    # Verifica se já existe pedido
    existe = conn.execute("""
        SELECT * FROM amizades 
        WHERE (de_user_id = ? AND para_user_id = ?) OR (de_user_id = ? AND para_user_id = ?)
    """, (de_id, para_id, para_id, de_id)).fetchone()

    if existe:
        conn.close()
        return jsonify({"status": "erro", "mensagem": "Pedido de amizade já existente ou pendente!"}), 400

    conn.execute("INSERT INTO amizades (de_user_id, para_user_id, status) VALUES (?, ?, 'pendente')", (de_id, para_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "sucesso", "mensagem": "Pedido de amizade enviado!"})

@app.route('/api/amigos/responder', methods=['POST'])
def responder_amizade():
    dados = request.json
    amizade_id = dados.get('amizade_id')
    acao = dados.get('acao') # 'aceitar' ou 'recusar'

    conn = get_db()
    if acao == 'aceitar':
        conn.execute("UPDATE amizades SET status = 'aceito' WHERE id = ?", (amizade_id,))
    else:
        conn.execute("DELETE FROM amizades WHERE id = ?", (amizade_id,))
    
    conn.commit()
    conn.close()
    return jsonify({"status": "sucesso"})

@app.route('/api/amigos/lista', methods=['GET'])
def listar_amigos_confirmados():
    user_id = request.args.get('user_id')
    conn = get_db()
    
    # Amigos confirmados (status = 'aceito')
    query = """
        SELECT u.id, u.usuario, u.foto_perfil FROM usuarios u
        JOIN amizades a ON (a.de_user_id = u.id OR a.para_user_id = u.id)
        WHERE (a.de_user_id = ? OR a.para_user_id = ?) 
        AND a.status = 'aceito' AND u.id != ?
    """
    amigos = conn.execute(query, (user_id, user_id, user_id)).fetchall()

    # Pedidos Pendentes recebidos
    query_pendentes = """
        SELECT a.id as amizade_id, u.usuario, u.foto_perfil FROM amizades a
        JOIN usuarios u ON a.de_user_id = u.id
        WHERE a.para_user_id = ? AND a.status = 'pendente'
    """
    pendentes = conn.execute(query_pendentes, (user_id,)).fetchall()

    conn.close()
    return jsonify({
        "amigos": [dict(a) for a in amigos],
        "pendentes": [dict(p) for p in pendentes]
    })

# --- APIS GESTÃO CONTEÚDOS & CHAT ENCRIPTADO ---

@app.route('/api/botoes', methods=['GET', 'POST'])
def gerenciar_botoes():
    conn = get_db()
    if request.method == 'POST':
        dados = request.json
        conn.execute("INSERT INTO botoes (nome, icone) VALUES (?, ?)", (dados['nome'], dados.get('icone', 'folder')))
        conn.commit()
        conn.close()
        return jsonify({"status": "Botão criado!"}), 201
    
    botoes = conn.execute("SELECT * FROM botoes").fetchall()
    conn.close()
    return jsonify([dict(b) for b in botoes])

@app.route('/api/conteudos', methods=['GET', 'POST'])
def gerenciar_conteudos():
    conn = get_db()
    if request.method == 'POST':
        dados = request.json
        conn.execute(
            "INSERT INTO conteudos (botao_id, titulo, descricao, link_ferramenta) VALUES (?, ?, ?, ?)",
            (dados['botao_id'], dados['titulo'], dados['descricao'], dados.get('link_ferramenta', ''))
        )
        conn.commit()
        conn.close()
        return jsonify({"status": "Conteúdo adicionado!"}), 201

    botao_id = request.args.get('botao_id')
    if botao_id:
        conteudos = conn.execute("SELECT c.*, b.nome as categoria FROM conteudos c JOIN botoes b ON c.botao_id = b.id WHERE c.botao_id = ?", (botao_id,)).fetchall()
    else:
        conteudos = conn.execute("SELECT c.*, b.nome as categoria FROM conteudos c JOIN botoes b ON c.botao_id = b.id").fetchall()
    
    conn.close()
    return jsonify([dict(c) for c in conteudos])

@app.route('/api/feed', methods=['GET', 'POST'])
def gerenciar_feed():
    conn = get_db()
    if request.method == 'POST':
        dados = request.json
        conn.execute("INSERT INTO posts (usuario_id, conteudo, link_anexo) VALUES (?, ?, ?)", 
                     (dados['usuario_id'], dados['conteudo'], dados.get('link_anexo', '')))
        conn.commit()
        conn.close()
        return jsonify({"status": "Publicado com sucesso!"}), 201

    posts = conn.execute("SELECT p.*, u.usuario, u.foto_perfil FROM posts p JOIN usuarios u ON p.usuario_id = u.id ORDER BY p.id DESC").fetchall()
    conn.close()
    return jsonify([dict(p) for p in posts])

@app.route('/api/chat', methods=['GET', 'POST'])
def gerenciar_chat_encriptado():
    conn = get_db()
    if request.method == 'POST':
        dados = request.json
        mensagem_encriptada = enc_msg(dados['mensagem'])
        conn.execute(
            "INSERT INTO mensagens (de_user_id, para_user_id, mensagem, link_arquivo) VALUES (?, ?, ?, ?)", 
            (dados['de_user_id'], dados['para_user_id'], mensagem_encriptada, dados.get('link_arquivo', ''))
        )
        conn.commit()
        conn.close()
        return jsonify({"status": "Mensagem encriptada e enviada!"}), 201

    de_id = request.args.get('de_id')
    para_id = request.args.get('para_id')
    
    raw_msgs = conn.execute("""
        SELECT m.*, u.usuario as remetente, u.foto_perfil FROM mensagens m 
        JOIN usuarios u ON m.de_user_id = u.id
        WHERE (m.de_user_id = ? AND m.para_user_id = ?) OR (m.de_user_id = ? AND m.para_user_id = ?)
        ORDER BY m.id ASC
    """, (de_id, para_id, para_id, de_id)).fetchall()
    
    conn.close()

    # Desencripta as mensagens ao enviar para os utilizadores autorizados
    resultado = []
    for m in raw_msgs:
        d = dict(m)
        d['mensagem'] = dec_msg(d['mensagem'])
        resultado.append(d)

    return jsonify(resultado)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
