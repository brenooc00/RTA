import os
import base64
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from psycopg2 import connect, Binary, sql
import psycopg2.extras

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.getenv('SECRET_KEY', 'chave_super_secreta')

DATABASE_URL = os.getenv('DATABASE_URL')
def get_db_connection():
    return connect(DATABASE_URL, sslmode='require')

# Rotas de login / cadastro / dashboard permanecem iguais,
# exceto que a captura não usa mais /capturar, mas /upload:

@app.route('/dashboard')
def dashboard():
    nome = session.get('nome')
    paciente_id = session.get('paciente_id')
    if not nome or not paciente_id:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT imagem FROM imagens WHERE paciente_id = %s", (paciente_id,))
    imagens = [ base64.b64encode(r['imagem']).decode('utf-8') for r in cur.fetchall() ]
    conn.close()

    return render_template('dashboard.html', nome=nome, imagens=imagens)

@app.route('/upload', methods=['POST'])
def upload():
    data = request.get_json()
    img_b64 = data.get('image')
    if not img_b64:
        return jsonify({"error":"Nenhuma imagem"}), 400

    # remover header "data:image/png;base64,"
    header, encoded = img_b64.split(',', 1)
    img_bytes = base64.b64decode(encoded)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO imagens (paciente_id, data, imagem)
        VALUES (%s, %s, %s)
    """, ( session['paciente_id'], datetime.now(), Binary(img_bytes) ))
    conn.commit()
    conn.close()

    return jsonify({"status":"ok"})

if __name__ == '__main__':
    app.run(debug=True)
