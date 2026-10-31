from flask import Flask, jsonify, request, render_template, session, redirect, url_for
import sqlite3
import base64
import os
from werkzeug.utils import secure_filename
from functools import wraps

app = Flask(__name__)
app.secret_key = 'odin_vault_super_secret_key_2026'

# Configuração da pasta de Uploads
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db():
    conn = sqlite3.connect('vault.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
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
            arquivo_path TEXT,
            FOREIGN KEY (botao_id) REFERENCES botoes (id)
        )
    ''')

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

@app.route('/')
def admin_panel():
    return render_template('app.html')

@app.route('/app')
def app_client():
    return render_template('app.html')

@app.route('/login')
def login_page():
    return redirect(url_for('app_client'))

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
        if request.form:
            titulo = request.form.get('titulo')
            descricao = request.form.get('descricao')
            link_ferramenta = request.form.get('link_ferramenta', '')
            botao_id = request.form.get('botao_id')
        else:
            dados = request.json or {}
            titulo = dados.get('titulo')
            descricao = dados.get('descricao')
            link_ferramenta = dados.get('link_ferramenta', '')
            botao_id = dados.get('botao_id')
        
        arquivo_path = None
        if 'arquivo' in request.files:
            arquivo = request.files['arquivo']
            if arquivo and arquivo.filename != '':
                filename = secure_filename(arquivo.filename)
                file_full_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                arquivo.save(file_full_path)
                arquivo_path = f"/static/uploads/{filename}"

        if not botao_id or not titulo:
            conn.close()
            return jsonify({"status": "erro", "mensagem": "Campos obrigatórios em falta"}), 400

        conn.execute(
            "INSERT INTO conteudos (botao_id, titulo, descricao, link_ferramenta, arquivo_path) VALUES (?, ?, ?, ?, ?)",
            (botao_id, titulo, descricao, link_ferramenta, arquivo_path)
        )
        conn.commit()
        conn.close()
        return jsonify({"status": "sucesso", "mensagem": "Conteúdo adicionado com sucesso!"}), 201

    botao_id = request.args.get('botao_id')
    if botao_id:
        conteudos = conn.execute("SELECT c.*, b.nome as categoria FROM conteudos c JOIN botoes b ON c.botao_id = b.id WHERE c.botao_id = ?", (botao_id,)).fetchall()
    else:
        conteudos = conn.execute("SELECT c.*, b.nome as categoria FROM conteudos c JOIN botoes b ON c.botao_id = b.id").fetchall()
    
    conn.close()
    return jsonify([dict(c) for c in conteudos])

@app.route('/api/conteudos/deletar/<int:conteudo_id>', methods=['DELETE'])
def deletar_conteudo(conteudo_id):
    if 'usuario' not in session:
        return jsonify({"status": "erro", "mensagem": "Não autorizado"}), 401
    
    conn = get_db()
    conteudo = conn.execute("SELECT * FROM conteudos WHERE id = ?", (conteudo_id,)).fetchone()
    
    if not conteudo:
        conn.close()
        return jsonify({"status": "erro", "mensagem": "Conteúdo não encontrado"}), 404
    
    if session.get('role') != 'admin':
        conn.close()
        return jsonify({"status": "erro", "mensagem": "Apenas administradores podem apagar conteúdos."}), 403

    if conteudo['arquivo_path']:
        file_path = os.path.join(app.root_path, conteudo['arquivo_path'].lstrip('/'))
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass

    conn.execute("DELETE FROM conteudos WHERE id = ?", (conteudo_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "sucesso", "mensagem": "Conteúdo apagado com sucesso!"})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
