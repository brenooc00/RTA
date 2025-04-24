from flask import Flask, render_template, request, redirect, session, url_for, flash,  get_flashed_messages
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

# Página de login - Redireciona inicio para ser login.html
@app.route('/')
def index():
    mensagens = get_flashed_messages()
    erro = mensagens[0] if mensagens else None
    return render_template('login.html', erro=erro)

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
        flash("CPF ou senha incorretos.")
        return redirect(url_for('index'))  # Redireciona para GET

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

# Página de dashboard onde mostra as imagens do paciente 
@app.route('/dashboard')
def dashboard():
    nome = session.get('nome')
    paciente_id = session.get('paciente_id')

    if not nome or not paciente_id:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Busca o CPF e data de nascimento do paciente
    cursor.execute("""
        SELECT cpf, data_nascimento 
        FROM pacientes 
        WHERE id = %s
    """, (paciente_id,))
    paciente_info = cursor.fetchone()

    if paciente_info:
        cpf = paciente_info['cpf']
        data_nascimento = paciente_info['data_nascimento']  # Formata a data
    else:
        cpf = 'Não encontrado'
        data_nascimento = 'Não encontrado'

    # Busca todas as imagens relacionadas ao paciente
    cursor.execute("SELECT imagem, desenho, data FROM imagens WHERE paciente_id = %s", (paciente_id,))
    imagens_raw = cursor.fetchall()
    conn.close()

    # Converte as imagens bytea para base64
    imagens = []
    for row in imagens_raw:
        timestamp = row['data'].strftime("%d/%m/%Y %H:%M:%S")
        imagens.append({
            'real': base64.b64encode(row['imagem']).decode('utf-8'),
            'desenho': base64.b64encode(row['desenho']).decode('utf-8'),
            'timestamp': timestamp
        })

    return render_template(
        'dashboard.html',
        nome=nome,
        imagens=imagens,
        cpf=cpf,
        data_nascimento=data_nascimento
    )


@app.route('/capturar', methods=['POST'])
def capturar():

    paciente_id = session.get('paciente_id')
    if not paciente_id:
        return redirect(url_for('login'))

    resultado = imagem_coluna()  # Chama a função de captura de imagem

    if resultado is None:
        flash("Captura cancelada pelo usuário.")
        return redirect(url_for('dashboard'))

    imagem_bytes, desenho_bytes = resultado  #Se tiver ocorrido com sucesso, pega os bytes da imagem e do desenho

    conn = get_db_connection()
    cursor = conn.cursor()

    # Inserção no banco com imagem BYTEA
    cursor.execute("""
        INSERT INTO imagens (paciente_id, data, imagem, desenho)
        VALUES (%s, %s, %s, %s)
    """, (paciente_id, datetime.now(), psycopg2.Binary(imagem_bytes), psycopg2.Binary(desenho_bytes)))
    
    conn.commit()
    conn.close()

    return redirect(url_for('dashboard'))

def imagem_coluna():
    # Inicializar detector do cvzone
    detector = HandDetector(detectionCon=0.7, maxHands=1)

    # Captura de vídeo
    cap = cv2.VideoCapture(0)
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Criar a janela antes de mostrar
    cv2.namedWindow("Desenho com os dedos", cv2.WINDOW_NORMAL)
    cv2.moveWindow("Desenho com os dedos", 450, 200)  # Posição na tela
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
    captura_finalizada = False  # Para verificar se a captura foi finalizada com sucesso

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

            #Antigo e simples
            #if not first_hand_detected:
                #cv2.putText(frame, "Aguardando mao...", (10, frame.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 1, (55,240,5), 2)
                        
            #Definindo as configurações para o texto
            font = cv2.FONT_HERSHEY_DUPLEX
            font_scale = 1
            thickness = 2
            text_color = (75, 230, 210)
            bg_color = (70, 70, 70)  # cinza escuro

            #Texto a ser exibido
            message = "Aguardando mao..."

            # Calcular tamanho do texto
            (text_width, text_height), _ = cv2.getTextSize(message, font, font_scale, thickness)

            # Coordenadas para centralizar
            x = (frame.shape[1] - text_width) // 2
            y = (frame.shape[0] -20)

            # Desenhar fundo (retângulo)
            cv2.rectangle(frame, (x - 10, y - text_height - 10), (x + text_width + 10, y + 10), bg_color, -1)
            # Escrever texto por cima
            cv2.putText(frame, message, (x, y), font, font_scale, text_color, thickness)

        if countdown_started and not capture_started:
            elapsed_countdown = time.time() - countdown_time
            if elapsed_countdown >= countdown_duration:
                capture_started = True
                start_time = time.time()
            else:
                remaining = countdown_duration - elapsed_countdown
                #cv2.putText(frame, f"Iniciando em: {int(remaining) + 1}s", (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_DUPLEX, 1, (124,252,0), 2) #Antigo e simples
                message = f"Iniciando em: {int(remaining) + 1}s"
                text_color = (0, 255, 0)

                (text_width, text_height), _ = cv2.getTextSize(message, font, font_scale, thickness)  # Calcular tamanho do texto

                # Coordenadas para centralizar na parte inferior
                x = (frame.shape[1] - text_width) // 2
                y = frame.shape[0] - 20

                # Desenhar fundo (retângulo)
                cv2.rectangle(frame, (x - 10, y - text_height - 10), (x + text_width + 10, y + 10), bg_color, -1)

                # Escrever texto
                cv2.putText(frame, message, (x, y), font, font_scale, text_color, thickness)

        if capture_started:
            elapsed_time = time.time() - start_time
            if elapsed_time >= capture_duration:
                captura_finalizada = True  # finalizou com sucesso
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
                #Linha vertical de referência
                cv2.line(frame, (initial_x, 0), (initial_x, frame.shape[0]), (255,200,0), 2)

            if prev_x is not None and initial_x is not None:
                distance_x = abs(prev_x - initial_x)
                distance_cm = distance_x * px_to_cm
                
                text = f"Distancia: {distance_cm:.1f} cm"
                text_color = (255, 200, 0) 

                # Calcular tamanho do texto
                (text_width, text_height), _ = cv2.getTextSize(text, font, font_scale, thickness)

                # Coordenadas para canto superior esquerdo
                x, y = 10, 30

                # Desenhar fundo com padding
                cv2.rectangle(frame, (x - 5, y - text_height - 5), (x + text_width + 5, y + 5), bg_color, -1)

                # Escrever texto
                cv2.putText(frame, text, (x, y),
                            font, font_scale, text_color, thickness)
                
            # Suavizar desenho
            smooth_canvas = cv2.GaussianBlur(canvas, (9, 9), 0)
            frame = cv2.addWeighted(frame, 0.5, smooth_canvas, 0.5, 0)

        cv2.imshow("Desenho com os dedos", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or cv2.getWindowProperty("Desenho com os dedos", cv2.WND_PROP_VISIBLE) < 1:
            break

    cap.release()
    cv2.destroyAllWindows()

    if not captura_finalizada:
        return None  # Retorno se o usuário fechou antes do fim

    # Salvar automaticamente
    time_stamp = time.strftime("%Y%m%d-%H%M%S")

    final_image = cv2.addWeighted(frame, 0.5, smooth_canvas, 0.5, 0)

    # Codificar a imagem em PNG para bytes
    _, buffer = cv2.imencode('.png', final_image)
    imagem_bytes = buffer.tobytes()

    desenho = smooth_canvas if smooth_canvas is not None else canvas
    _, buf_des = cv2.imencode('.png', desenho)
    desenho_bytes = buf_des.tobytes()

    return imagem_bytes, desenho_bytes

@app.route('/realtime', methods=['POST'])
def realtime():
    realtime_coluna()
    return redirect(url_for('dashboard'))

def realtime_coluna():
    detector = HandDetector(detectionCon=0.7, maxHands=1)
    cap = cv2.VideoCapture(0)

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Configura janela
    win_name = "Distancia em Tempo Real"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_name, frame_width, frame_height)
    cv2.moveWindow(win_name, 450, 200)
    cv2.setWindowProperty(win_name, cv2.WND_PROP_TOPMOST, 1)

    # Estados
    first_hand_detected = False
    countdown_started = False
    countdown_time = None
    countdown_duration = 5.0
    measuring = False
    initial_x = None
    px_to_cm = 0.0

    while True:
        success, frame = cap.read()
        if not success:
            break
        frame = cv2.flip(frame, 1)

        # Realça contraste
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        enhanced = cv2.equalizeHist(gray)
        frame = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

        hands, frame = detector.findHands(frame, flipType=False, draw=True)
        now = time.time()

        # 1) Ao detectar a mão pela primeira vez, inicia contagem
        if hands and not first_hand_detected:
            first_hand_detected = True
            countdown_started = True
            countdown_time = now

        # 2) Se estiver na contagem regressiva (e ainda não medindo)
        if countdown_started and not measuring:
            elapsed = now - countdown_time
            if elapsed >= countdown_duration:
                measuring = True
                # fixa a linha vertical de referência no X do polegar
                initial_x = hands[0]['lmList'][4][0]
            else:
                # exibe o contador na parte inferior, centralizado
                remaining = int(countdown_duration - elapsed) + 1
                message = f"Iniciando em: {remaining}s"
                font, fs, th = cv2.FONT_HERSHEY_DUPLEX, 1, 2
                (tw, tht), _ = cv2.getTextSize(message, font, fs, th)
                x = (frame.shape[1] - tw) // 2
                y = frame.shape[0] - 20
                cv2.rectangle(frame,
                              (x - 10, y - tht - 10),
                              (x + tw + 10, y + 10),
                              (70, 70, 70), -1)
                cv2.putText(frame, message, (x, y), font, fs, (0, 255, 0), th)

        # 3) Se estiver em modo de medição e detectar a mão
        if measuring and hands:
            lmList = hands[0]['lmList']
            thumb_x = lmList[4][0]

            # recalcula escala px→cm a cada quadro
            x1, y1 = lmList[0][0], lmList[0][1]
            x2, y2 = lmList[17][0], lmList[17][1]
            ref_px = ((x2 - x1)**2 + (y2 - y1)**2)**0.5
            px_to_cm = 8.0 / ref_px if ref_px != 0 else 0

            # distância do polegar à linha de referência
            dist_px = abs(thumb_x - initial_x)
            dist_cm = dist_px * px_to_cm

            # desenha linha vertical de referência
            cv2.line(frame, (initial_x, 0),
                     (initial_x, frame.shape[0]),
                     (255, 0, 255), 2)

            # exibe a distância no canto superior esquerdo
            text = f"Distancia: {dist_cm:.1f} cm"
            font, fs, th = cv2.FONT_HERSHEY_DUPLEX, 1, 2
            (tw, tht), _ = cv2.getTextSize(text, font, fs, th)
            x, y = 10, 30
            cv2.rectangle(frame,
                          (x - 5, y - tht - 5),
                          (x + tw + 5, y + 5),
                          (70, 70, 70), -1)
            cv2.putText(frame, text, (x, y),
                        font, fs, (255, 200, 0) , th)

        # 4) Se não detectar mão em nenhum modo, mostra “Aguardando mão...”
        if not hands and not (countdown_started and not measuring):
            message = "Aguardando mao..."
            font, fs, th = cv2.FONT_HERSHEY_DUPLEX, 1, 2
            (tw, tht), _ = cv2.getTextSize(message, font, fs, th)
            x = (frame.shape[1] - tw) // 2
            y = frame.shape[0] - 20
            cv2.rectangle(frame,
                          (x - 10, y - tht - 10),
                          (x + tw + 10, y + 10),
                          (70, 70, 70), -1)
            cv2.putText(frame, message, (x, y),
                        font, fs, (75, 230, 210), th)

        cv2.imshow(win_name, frame)

        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('q') or cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) < 1:
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    app.run(debug=True)