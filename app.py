from flask import Flask, render_template, request, redirect, session, url_for
from psycopg2 import connect, sql
import psycopg2.extras
import base64
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'chave_super_secreta'
DATABASE_URL = "postgresql://pacientes_web_user:uKk2h90mdG3FVesUsIBf2AuZqCbmfwnZ@dpg-cvu4v9h5pdvs73e4qec0-a.oregon-postgres.render.com/pacientes_web"

def get_db_connection():
    return connect(DATABASE_URL, sslmode='require')

#Pagina de Login
# Redireciona inicio para ser login.html
@app.route('/')
def index():
    return render_template('login.html')

# Rota para realizar o login e ser redirecionado ao dashboard 
@app.route('/login', methods=['POST'])
def login():
    cpf = request.form['cpf']
    senha = request.form['senha']   

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute(sql.SQL("SELECT * FROM pacientes WHERE cpf = %s AND senha = %s"), (cpf, senha))
    user = cursor.fetchone()

    conn.close()
 
    if user:
        session['nome'] = user['nome']
        session['paciente_id'] = user['id']  # Armazena para a próxima rota
        return redirect(url_for('dashboard'))
   
    else:
        return "CPF ou senha inválidos"

# Redireciona de login para a pagina cadastro
@app.route('/redireciona_Login_Cadastro')
def redirecionar_LoginCadastro():
    return render_template('cadastro.html')

# Redireciona de cadastro para a pagina login
@app.route('/redireciona_Cadastro_Login')
def redirecionar_CadastroLogin():
    return render_template('login.html')

# Cadastro de paciente e redirecionamento ao login 
@app.route('/cadastro', methods=['POST'])
def cadastro():
    nome = request.form['nome']
    data_nascimento = request.form['data_nascimento']
    cpf = request.form['cpf']
    senha = request.form['senha']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Verifica se o CPF já está cadastrado
    query = sql.SQL("SELECT * FROM pacientes WHERE cpf = %s")
    cursor.execute(query, (cpf,))
    existing_user = cursor.fetchone()

    if existing_user:
        conn.close()
        return "Este CPF já está cadastrado.", 400

    # Cadastrar novo usuário
    insert_query = sql.SQL("""
        INSERT INTO pacientes (nome, data_nascimento, cpf, senha)
        VALUES (%s, %s, %s, %s)
    """)
    cursor.execute(insert_query, (nome, data_nascimento, cpf, senha))
    conn.commit()
    conn.close()

    return redirect(url_for('index'))  # Redireciona para a página de login após cadastro

#Pagina de Dashboard
# Codigo do dashboard onde mostra as imagens do paciente 
@app.route('/dashboard')
def dashboard():
    nome = session.get('nome')
    paciente_id = session.get('paciente_id')

    if not nome or not paciente_id:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Busca todas as imagens relacionadas ao paciente
    cursor.execute("SELECT imagem FROM imagens WHERE paciente_id = %s", (paciente_id,))
    imagens_raw = cursor.fetchall()
    conn.close()

    # Converte as imagens bytea para base64
    imagens_base64 = [
        base64.b64encode(img['imagem']).decode('utf-8') for img in imagens_raw
    ]

    return render_template('dashboard.html', nome=nome, imagens=imagens_base64)

# Rota para exibir a página de captura pelo navegador
@app.route('/camera')
def camera():
    if 'paciente_id' not in session:
        return redirect(url_for('login'))
    return render_template('camera.html')

# Rota para receber imagem capturada no cliente
@app.route('/capturar', methods=['POST'])
def capturar():
    paciente_id = session.get('paciente_id')
    if not paciente_id:
        return redirect(url_for('login'))

    data = request.get_json()
    img_data = data.get('image')  # data:image/png;base64,...
    if not img_data:
        return "Nenhuma imagem recebida", 400

    header, encoded = img_data.split(',', 1)
    imagem_bytes = base64.b64decode(encoded)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO imagens (paciente_id, data, imagem)
        VALUES (%s, %s, %s)
        """,
        (paciente_id, datetime.now(), psycopg2.Binary(imagem_bytes))
    )
    conn.commit()
    conn.close()

    return ('', 204)

if __name__ == '__main__':
    app.run(debug=True)
