from flask import Flask, render_template, request, redirect, session, url_for
from psycopg2 import connect, sql
import psycopg2.extras
import base64
from datetime import datetime
import cv2
import numpy as np
import time
from cvzone.HandTrackingModule import HandDetector

app = Flask(__name__)
app.secret_key = 'chave_super_secreta'  # Necessário para usar sessão


# Configuração do banco de dados
DATABASE_URL = "postgresql://pacientes_web_user:uKk2h90mdG3FVesUsIBf2AuZqCbmfwnZ@dpg-cvu4v9h5pdvs73e4qec0-a.oregon-postgres.render.com/pacientes_web"

# Função para conectar ao banco de dados
def get_db_connection():
    conn = connect(DATABASE_URL, sslmode='require')
    return conn

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

# Codigo novo

@app.route('/capturar', methods=['POST'])
def capturar():

    paciente_id = session.get('paciente_id')
    if not paciente_id:
        return redirect(url_for('login'))

    imagem_bytes = imagem_coluna()  # captura com OpenCV

    conn = get_db_connection()
    cursor = conn.cursor()

    # Inserção no banco com imagem BYTEA
    cursor.execute("""
        INSERT INTO imagens (paciente_id, data, imagem)
        VALUES (%s, %s, %s)
    """, (paciente_id, datetime.now(), psycopg2.Binary(imagem_bytes)))
    
    conn.commit()
    conn.close()

    return redirect(url_for('dashboard'))

def imagem_coluna():
    # Inicializar detector do cvzone
    detector = HandDetector(detectionCon=0.8, maxHands=1)

    # Captura de vídeo
    cap = cv2.VideoCapture(0)
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Criar a janela antes de mostrar
    cv2.namedWindow("Desenho com os dedos", cv2.WINDOW_NORMAL)
    cv2.moveWindow("Desenho com os dedos", 100, 100)  # Posição na tela
    cv2.setWindowProperty("Desenho com os dedos", cv2.WND_PROP_TOPMOST, 1)  # Fica em primeiro plano

    # Tela preta para desenhar
    canvas = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)

    # Variáveis de controle
    prev_x, prev_y = None, None
    initial_x = None

    # Estados
    countdown_started = False
    capture_started = False
    start_time = None
    countdown_time = None
    countdown_duration = 5
    capture_duration = 7
    first_hand_detected = False
    frame_final = None  # Para salvar ao final

    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break

        frame = cv2.flip(frame, 1)

        # Aumentar contraste da imagem para facilitar a detecção
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        enhanced = cv2.equalizeHist(gray)
        frame = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

        # Detectar a mão
        hands, frame = detector.findHands(frame, flipType=False, draw=True)

        if hands and not first_hand_detected:
            first_hand_detected = True
            countdown_started = True
            countdown_time = time.time()

        if not first_hand_detected:
            cv2.putText(frame, "Aguardando mao...", (10, frame.shape[0] - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255,140,0), 2)

        if countdown_started and not capture_started:
            elapsed_countdown = time.time() - countdown_time
            if elapsed_countdown >= countdown_duration:
                capture_started = True
                start_time = time.time()
            else:
                remaining = countdown_duration - elapsed_countdown
                cv2.putText(frame, f"Iniciando em: {int(remaining) + 1}s", (10, frame.shape[0] - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (124,252,0), 2)

        if capture_started:
            elapsed_time = time.time() - start_time
            if elapsed_time >= capture_duration:
                break

            if hands:
                lmList = hands[0]['lmList']
                x, y = lmList[4][0], lmList[4][1]  # Ponto 4 = dedão (THUMB_TIP)

                if initial_x is None:
                    initial_x = x

                if prev_x is not None and prev_y is not None:
                    dx = abs(x - prev_x)
                    dy = abs(y - prev_y)
                    if dx > 3 or dy > 3:
                        cv2.line(canvas, (prev_x, prev_y), (x, y), (255, 255, 255), 3)
                        prev_x, prev_y = x, y
                else:
                    prev_x, prev_y = x, y

                # --- Conversão de pixels para cm ---
                # Base do dedão e base do mindinho
                x1, y1 = lmList[0][0], lmList[0][1]
                x2, y2 = lmList[17][0], lmList[17][1]
                ref_distance_px = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                ref_distance_cm = 8.0  # valor estimado
                px_to_cm = ref_distance_cm / ref_distance_px if ref_distance_px != 0 else 0

            if initial_x is not None:
                cv2.line(frame, (initial_x, 0), (initial_x, frame.shape[0]), (255,0,255), 2)

            if prev_x is not None and initial_x is not None:
                distance_x = abs(prev_x - initial_x)
                distance_cm = distance_x * px_to_cm
                cv2.putText(frame, f"Distancia X: {distance_cm:.2f} cm", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

            # Suavizar desenho
            smooth_canvas = cv2.GaussianBlur(canvas, (9, 9), 0)
            frame = cv2.addWeighted(frame, 0.5, smooth_canvas, 0.5, 0)

        cv2.imshow("Desenho com os dedos", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or cv2.getWindowProperty("Desenho com os dedos", cv2.WND_PROP_VISIBLE) < 1:
            break

    cap.release()
    cv2.destroyAllWindows()

     # Salvar automaticamente
    time_stamp = time.strftime("%Y%m%d-%H%M%S")

    final_image = cv2.addWeighted(frame, 0.5, smooth_canvas, 0.5, 0)

    # Codificar a imagem em PNG para bytes
    _, buffer = cv2.imencode('.png', final_image)
    imagem_bytes = buffer.tobytes()

    return imagem_bytes


if __name__ == '__main__':
    app.run(debug=True)
