from flask_cors import CORS
import random
from flask import make_response
import smtplib
import pymysql
import string
from email.mime.text import MIMEText
from flask import Flask, render_template, request, redirect, session, jsonify
from datetime import datetime, timedelta
import requests
import uuid
import json
from functools import wraps
from flask import url_for, flash
from dateutil.relativedelta import relativedelta
import time

def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get('admin_id'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return wrapped


app = Flask(__name__)
app.secret_key = '15274402'
CORS(app)

@app.after_request
def add_cache_headers(response):
    # Список расширений изображений
    image_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg')
    # Проверка пути на наличие нужного расширения
    if request.path.startswith('/static/') and request.path.lower().endswith(image_extensions):
        response.headers['Cache-Control'] = 'public, max-age=604800'  # 7 дней
    return response
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response


#quests_data = {
#    'daily_case_1': {'title': 'Открой 1 кейс', 'description': 'Открой один кейс за день', 'reward': 0.5, 'type': 'daily'},
#    'daily_case_3': {'title': 'Открой 3 кейса', 'description': 'Открой три кейса за день', 'reward': 1, 'type': 'daily'},
#    'weekly_case_10': {'title': 'Открой 10 кейсов', 'description': 'Открой 10 кейсов за неделю', 'reward': 2, 'type': 'weekly'},
#    'weekly_case_30': {'title': 'Открой 30 кейсов', 'description': 'Открой 30 кейсов за неделю', 'reward': 5, 'type': 'weekly'},
#    'social_telegram_channel': {'title': 'Подписка на Telegram канал', 'description': 'https://t.me/luckyverse_news', 'reward': 0.5, 'type': 'social', 'link': 'https://t.me/luckyverse_news'},
#    'social_telegram_chat': {'title': 'Вход в Telegram чат', 'description': 'https://t.me/luckyverse_chat', 'reward': 0.5, 'type': 'social', 'link': 'https://t.me/luckyverse_chat'},
#    'social_tiktok': {'title': 'Подписка на TikTok', 'description': 'Скоро добавим ссылку', 'reward': 0.5, 'type': 'social', 'link': '#'},
#    'social_youtube': {'title': 'Подписка на YouTube', 'description': 'Скоро добавим ссылку', 'reward': 0.5, 'type': 'social', 'link': '#'}
#}



DOMAIN = 'https://oleg121212.pythonanywhere.com'

DB_HOST = "oleg121212.mysql.pythonanywhere-services.com"
DB_USER = "oleg121212"
DB_PASSWORD = "rootroot"
DB_NAME = "oleg121212$default"

@app.route('/verify_email', methods=['GET'])
def verify_email_page():
    if 'email' not in session:
        return redirect('/register_page')
    return render_template('verify_email.html', email=session['email'])


@app.route('/verify_email_code', methods=['POST'])
def verify_email_code():
    data = request.json
    code = data.get('code')

    if 'email_code' not in session or 'login' not in session:
        return jsonify({'success': False, 'message': 'Сессия истекла'}), 400

    if code == session['email_code']:
        # Подтвердить почту
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE users SET email_confirmed = 1 WHERE login = %s", (session['login'],))
                conn.commit()
        finally:
            conn.close()

        session.pop('email_code', None)
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'message': 'Неверный код'})


def generate_referral_code(length=8):
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choices(characters, k=length))


def get_connection():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )


def load_tokens():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM tokens LIMIT 1")
            row = cursor.fetchone()
            if row:
                return {
                    'PLISIO_API_KEY': row['plisio_api'],
                    'TELEGRAM_BOT_TOKEN': row['tgbot_token'],
                    'CHAT_ID': row['admin_tg_chat_id'],
                    'SUBJECT': row['name_letter'],
                    'TEXT': row['text_letter'],
                    'FROM_EMAIL': row['from_letter'],
                    'SMTP': row['smtp'],
                    'LOGIN_EMAIL': row['login_email'],
                    'LOGIN_PASS': row['login_pass']
                }
    finally:
        conn.close()

tokens = load_tokens()

def get_quests_from_db():
    conn = get_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM quests WHERE active = TRUE")
        quests = cursor.fetchall()

    quests_data = {}
    for q in quests:
        quests_data[q['quest_id']] = {
            'title': q['title_ru'],
            'description': q['description_ru'],
            'reward': float(q['reward']),
            'type': q['quest_type']
        }
        if q['quest_type'] == 'social':
            quests_data[q['quest_id']]['link'] = q['url']

    return quests_data

quests_data = get_quests_from_db()



PLISIO_API_KEY = tokens['PLISIO_API_KEY']
TELEGRAM_BOT_TOKEN = tokens['TELEGRAM_BOT_TOKEN']
CHAT_ID = int(tokens['CHAT_ID'])
subject = tokens['SUBJECT']
text = tokens['TEXT']
fromm = tokens['FROM_EMAIL']
smtp = tokens['SMTP']
login_email = tokens['LOGIN_EMAIL']
login_pass = tokens['LOGIN_PASS']



@app.route('/')
def welcome():
    if 'login' in session:
        return redirect('/menu')

    token = request.cookies.get('remember_token')
    if token:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT users.id, users.login, users.is_admin FROM auth_tokens
                    JOIN users ON users.id = auth_tokens.user_id
                    WHERE auth_tokens.token = %s
                """, (token,))

                user = cursor.fetchone()
                if user:
                    session['login'] = user['login']
                    session['user_id'] = user['id']
                    session['is_admin'] = user.get('is_admin', 0)
                    cursor.execute("SELECT 1 FROM user_stats WHERE user_id = %s", (user['id'],))
                    if not cursor.fetchone():
                        cursor.execute("INSERT INTO user_stats (user_id) VALUES (%s)", (user['id'],))
                        conn.commit()
                    return redirect('/menu')
        finally:
            conn.close()

    return render_template('welcome2.html')



@app.route('/welcome')
def welcome2():
    return render_template('welcome.html')

@app.route('/menu')
def menu():
    if 'login' not in session:
        return redirect('/')

    conn = get_connection()
    balance = 0

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance, email_confirmed FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            if user:
                balance = user.get('balance', 0)
                email_confirmed = user.get('email_confirmed')
                if email_confirmed == 0:
                    # Удаляем аккаунт
                    cursor.execute("DELETE FROM users WHERE login = %s", (session['login'],))
                    conn.commit()
                    session.pop('login', None)
                    return redirect('/')

    finally:
        conn.close()

    return render_template('menu.html', balance=balance)


@app.route('/logout')
def logout():
    token = request.cookies.get('remember_token')
    if token:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM auth_tokens WHERE token = %s", (token,))
                conn.commit()
        finally:
            conn.close()

    session.clear()
    response = make_response(redirect('/'))
    response.set_cookie('remember_token', '', expires=0)
    return response


@app.route('/register', methods=['POST'])
def register():
    def generate_verification_code():
        return ''.join(random.choices(string.digits, k=6))

    def send_verification_email(to_email, code):
        body = f"{text} {code}"
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = fromm
        msg['To'] = to_email

        try:
            with smtplib.SMTP(smtp, 587) as server:
                server.starttls()
                server.login(login_email, login_pass)
                server.send_message(msg)
        except Exception as e:
            print("Ошибка при отправке email:", e)

    data = request.json
    login = data.get('login')
    password = data.get('password')
    referred_code = data.get('referral_code')
    country = data.get('country')
    nickname = data.get('nickname')
    language = data.get('language')

    if not login or not password or not nickname or not country or not language:
        return jsonify({'success': False, 'message': 'Заполните все поля'}), 400

    referral_code = generate_referral_code()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE login = %s", (login,))
            if cursor.fetchone():
                return jsonify({'success': False, 'message': 'Пользователь уже существует'}), 400

            if referred_code:
                cursor.execute("SELECT id FROM users WHERE referral_code = %s", (referred_code,))
                inviter = cursor.fetchone()
                if inviter:
                    cursor.execute("UPDATE users SET referral_count = referral_count + 1, balance = balance + 0.5 WHERE id = %s", (inviter['id'],))
                else:
                    referred_code = None

            cursor.execute(
                "INSERT INTO users (login, password, balance, referred_by, referral_count, country, nickname, language, referral_code) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (login, password, 0, referred_code, 0, country, nickname, language, referral_code)
            )
            conn.commit()

            # Повторный запрос для получения ID
            cursor.execute("SELECT id FROM users WHERE login = %s", (login,))
            user = cursor.fetchone()
            if not user:
                return jsonify({'success': False, 'message': 'Ошибка при создании аккаунта'}), 500

            # Сохраняем сессию
            session['login'] = login
            session['user_id'] = user['id']

            # Добавляем user_stats
            cursor.execute("INSERT INTO user_stats (user_id) VALUES (%s)", (user['id'],))
            conn.commit()

        # Отправляем письмо и код
        code = generate_verification_code()
        session['email_code'] = code
        session['email'] = login
        send_verification_email(login, code)

        return jsonify({'success': True, 'redirect': '/verify_email', 'user_id': user['id']})
    finally:
        conn.close()



@app.route('/cancel_registration', methods=['POST'])
def cancel_registration():
    user_id = session.get('user_id')
    if user_id:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
                conn.commit()
        finally:
            conn.close()
        session.clear()
    return '', 204


@app.route('/check_referral', methods=['POST'])
def check_referral():
    data = request.json
    code = data.get('code')
    if not code:
        return jsonify({'exists': False})

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE referral_code = %s", (code,))
            result = cursor.fetchone()
            return jsonify({'exists': bool(result)})
    finally:
        conn.close()


@app.route('/login', methods=['POST'])
def login():
    data = request.json
    login_input = data.get('login')
    password = data.get('password')

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # Получить попытки входа
            cursor.execute("SELECT * FROM login_attempts WHERE login = %s", (login_input,))
            attempt = cursor.fetchone()

            if attempt and attempt['lock_until'] and datetime.now() < attempt['lock_until']:
                remaining = (attempt['lock_until'] - datetime.now()).seconds // 60 + 1
                return jsonify({'success': False, 'message': f'Аккаунт временно заблокирован. Подождите {remaining} мин.'}), 403

            # Ищем пользователя
            cursor.execute("SELECT * FROM users WHERE login = %s AND password = %s", (login_input, password))
            user = cursor.fetchone()

            if user:
                # Успех — сбрасываем счётчик и блокировку
                cursor.execute("DELETE FROM login_attempts WHERE login = %s", (login_input,))

                # Сохраняем сессию
                session['login'] = login_input
                session['user_id'] = user['id']

                # Токен
                token = str(uuid.uuid4())
                cursor.execute("INSERT INTO auth_tokens (token, user_id) VALUES (%s, %s)", (token, user['id']))
                conn.commit()

                response = make_response(jsonify({'success': True}))
                response.set_cookie('remember_token', token, max_age=30*24*3600, httponly=True, secure=True, samesite='Lax')
                return response
            else:
                # Неудача — увеличиваем попытки
                if attempt:
                    failed_attempts = attempt['failed_attempts'] + 1
                    lock_until = datetime.now() + timedelta(minutes=30) if failed_attempts >= 10 else None
                    cursor.execute("""
                        UPDATE login_attempts
                        SET failed_attempts = %s, lock_until = %s
                        WHERE login = %s
                    """, (failed_attempts, lock_until, login_input))
                else:
                    cursor.execute("""
                        INSERT INTO login_attempts (login, failed_attempts, lock_until)
                        VALUES (%s, %s, %s)
                    """, (login_input, 1, None))
                conn.commit()

                message = (
                    'Превышено число попыток. Аккаунт заблокирован на 30 минут.'
                    if attempt and attempt['failed_attempts'] + 1 >= 10
                    else f'Неверный логин или пароль. Осталось попыток: {10 - (attempt["failed_attempts"] + 1 if attempt else 1)}'
                )
                return jsonify({'success': False, 'message': message}), 401
    finally:
        conn.close()

@app.route('/collect_user_data', methods=['POST'])
def collect_user_data():
    data = request.get_json()
    user_id = data.get('user_id')

    if not user_id:
        return jsonify({'status': 'error', 'message': 'No user_id'}), 400

    ip_address = request.remote_addr

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO user_metadata
                (user_id, ip_address, user_agent, language, timezone, screen_resolution, platform, fingerprint, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """, (
                user_id,
                ip_address,
                data.get('user_agent'),
                data.get('language'),
                data.get('timezone'),
                data.get('screen_resolution'),
                data.get('platform'),
                data.get('fingerprint')
            ))
            conn.commit()
    finally:
        conn.close()

    return jsonify({'status': 'success'})

@app.route('/casino')
def casino():
    if 'login' not in session:
        return redirect('/')
    if not is_game_enabled('slots'):
        return render_template('disabled.html', game_name='Слоты №1')
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            balance = user['balance'] if user else 0

            cursor.execute("SELECT match_min, match_max, multiplier FROM slot_config ORDER BY id")
            rules = cursor.fetchall()
    finally:
        conn.close()
    return render_template('index.html', balance=balance, rules=rules)


@app.route('/casino2')
def casino2():
    if 'login' not in session:
        return redirect('/')
    if not is_game_enabled('slots'):
        return render_template('disabled.html', game_name='Слоты №2')
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            balance = user['balance'] if user else 0

            cursor.execute("SELECT match_min, match_max, multiplier FROM slot_config ORDER BY id")
            rules = cursor.fetchall()
    finally:
        conn.close()
    return render_template('index2.html', balance=balance, rules=rules)

@app.route('/cs2')
def cs2():
    if 'login' not in session:
        return redirect('/')

    conn = get_connection()
    balance = 0
    language = 'Русский'  # Язык по умолчанию

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance, language FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            if user:
                balance = user.get('balance', 0)
                language = user.get('language', 'Русский')
    finally:
        conn.close()
    return render_template('cs2.html', balance=balance, language=language)

@app.route('/drygie')
def drygie():
    if 'login' not in session:
        return redirect('/')

    conn = get_connection()
    balance = 0

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            if user:
                balance = user.get('balance', 0)
    finally:
        conn.close()
    return render_template('drygie.html', balance=balance)

@app.route('/coin')
def coin():
    if 'login' not in session:
        return redirect('/')
    if not is_game_enabled('coin'):
        return render_template('disabled.html', game_name='Орёл и Решка')

    conn = get_connection()
    balance = 0

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()

            cursor.execute("SELECT multiplier FROM coin_config WHERE id = 1")
            rule = cursor.fetchone()
            multiplier = rule['multiplier'] if rule else 2  # или дефолт 2
            if user:
                balance = user.get('balance', 0)
    finally:
        conn.close()
    return render_template('coin.html', balance=balance, multiplier=multiplier)

@app.route('/crush')
def crush():
    if 'login' not in session:
        return redirect('/')
    if not is_game_enabled('crush'):
        return render_template('disabled.html', game_name='Краш')

    conn = get_connection()
    balance = 0

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            if user:
                balance = user.get('balance', 0)
    finally:
        conn.close()
    return render_template('crush.html', balance=balance)



@app.route('/api/sound-volume')
def get_sound_volume():
    if 'login' not in session:
        return {'volume': 0.5}  # значение по умолчанию

    conn = get_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT volume FROM users WHERE login = %s", (session['login'],))
        row = cursor.fetchone()

        if not row or row['volume'] is None:
            return {'volume': 0.5}  # если пользователь не найден или volume не задан

        volume_map = {
            0: 0.0,
            10: 0.1,
            20: 0.2,
            30: 0.3,
            40: 0.4,
            50: 0.5,
            60: 0.6,
            70: 0.7,
            80: 0.8,
            90: 0.9,
            100: 1.0
        }

        volume_value = volume_map.get(row['volume'], 0.5)  # если значение не найдено, вернуть 0.5

    return {'volume': volume_value}



@app.route('/ryletki')
def ryletki():
    if 'login' not in session:
        return redirect('/')

    conn = get_connection()
    balance = 0
    language = 'Русский'  # Язык по умолчанию

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance, language FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            if user:
                balance = user.get('balance', 0)
                language = user.get('language', 'Русский')
    finally:
        conn.close()
    return render_template('ryletki.html', balance=balance, language=language)


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    conn = get_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT balance, nickname FROM users WHERE id=%s", (user_id,))
        user = cursor.fetchone()
        balance = user['balance'] if user else 0
        login = user['nickname'] if user else 'None'

        cursor.execute("SELECT * FROM user_stats WHERE user_id=%s", (user_id,))
        stats = cursor.fetchone() or {
            'slots_played': 0,
            'roulette_played': 0,
            'cases_opened': 0,
            'minesweeper_played': 0
        }

    return render_template('profile.html', balance=balance, login=login, stats=stats)


def increment_stat(user_id, stat_column):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            query = f"""
                INSERT INTO user_stats (user_id, {stat_column})
                VALUES (%s, 1)
                ON DUPLICATE KEY UPDATE {stat_column} = {stat_column} + 1
            """
            cursor.execute(query, (user_id,))
        conn.commit()
    finally:
        conn.close()





@app.route('/deposit')
def deposit():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']

    conn = get_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT balance, nickname FROM users WHERE id=%s", (user_id,))
        user = cursor.fetchone()
        balance = user['balance'] if user else 0
        login = user['nickname'] if user else 'None'

    return render_template('deposit.html', balance=balance, login=login)

@app.route('/vuvod')
def vuvod():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']

    conn = get_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT balance FROM users WHERE id=%s", (user_id,))
        user = cursor.fetchone()
        balance = user['balance'] if user else 0

    return render_template('vuvod.html', balance=balance)




@app.route('/crypto')
def crypto():
    if 'login' not in session:
        return redirect('/')
    if not is_game_enabled('case_crypto'):
        return render_template('disabled.html', game_name='Крипто-кейс')
    conn = get_connection()
    items = []
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            balance = user['balance'] if user else 0

            # 👇 Добавим выборку предметов из базы
            cursor.execute("SELECT name, price, chance FROM case_crypto")
            items = cursor.fetchall()
    finally:
        conn.close()
    return render_template('crypto.html', balance=balance, db_items=items)

@app.route('/onas')
def onas():
    if 'login' not in session:
        return redirect('/')
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            balance = user['balance'] if user else 0
    finally:
        conn.close()
    return render_template('onas.html', balance=balance)

@app.route('/inform')
def inform():
    if 'login' not in session:
        return redirect('/')
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            balance = user['balance'] if user else 0
    finally:
        conn.close()
    return render_template('inform.html', balance=balance)




@app.route('/labubu')
def labubu():
    if 'login' not in session:
        return redirect('/')
    if not is_game_enabled('case_labubu'):
        return render_template('disabled.html', game_name='Лабубу кейс')
    conn = get_connection()
    items = []
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            balance = user['balance'] if user else 0

            # 👇 Добавим выборку предметов из базы
            cursor.execute("SELECT name, price, chance FROM case_labubu")
            items = cursor.fetchall()
    finally:
        conn.close()
    return render_template('labubu.html', balance=balance, db_items=items)


@app.route('/referral')
def referral():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT balance, referral_code, referral_count FROM users WHERE id=%s", (user_id,))
            user = cursor.fetchone()

            if user:
                balance = float(user['balance'])
                referral_code = user['referral_code']
                referral_count = user['referral_count']

                # Подсчёт, сколько людей использовали этот код
                cursor.execute("SELECT COUNT(*) AS used FROM users WHERE referred_by = %s", (referral_code,))
                used_count = cursor.fetchone()['used']

                return render_template('referral.html',
                                       balance=balance,
                                       referral_code=referral_code,
                                       referral_count=referral_count,
                                       used_count=used_count)
            else:
                return "User not found", 404
    finally:
        connection.close()


@app.route('/saper')
def saper():
    if 'login' not in session:
        return redirect('/')
    if not is_game_enabled('saper'):
        return render_template('disabled.html', game_name='Сапёр')

    conn = get_connection()
    balance = 0

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            cursor.execute("SELECT id, multiplier, bombs FROM saper_config ORDER BY id")
            configs = cursor.fetchall()
            if user:
                balance = user.get('balance', 0)
    finally:
        conn.close()
    return render_template('saper.html', balance=balance, saper_configs=configs)

@app.route('/saper_start', methods=['POST'])
def saper_start():
    if 'user_id' not in session:
        return jsonify(success=False, error='Неавторизованный доступ')
    data = request.json
    stake = data.get('stake')
    multiplier = data.get('multiplier')

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT multiplier FROM saper_config WHERE id = 1")
            multiplier1 = cursor.fetchone()['multiplier']
            cursor.execute("SELECT multiplier FROM saper_config WHERE id = 2")
            multiplier2 = cursor.fetchone()['multiplier']
            cursor.execute("SELECT multiplier FROM saper_config WHERE id = 3")
            multiplier3 = cursor.fetchone()['multiplier']

            cursor.execute("SELECT bombs FROM saper_config WHERE id = 1")
            bombs1 = cursor.fetchone()['bombs']
            cursor.execute("SELECT bombs FROM saper_config WHERE id = 2")
            bombs2 = cursor.fetchone()['bombs']
            cursor.execute("SELECT bombs FROM saper_config WHERE id = 3")
            bombs3 = cursor.fetchone()['bombs']

    finally:
        conn.close()

    if not isinstance(stake, (int, float)) or stake <= 0:
        return jsonify(success=False, error='Неверная ставка')

    user_id = session['user_id']
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                return jsonify(success=False, error='Пользователь не найден')
            balance = user['balance']

            if stake > balance:
                return jsonify(success=False, error='Недостаточно средств')

            # Снимаем ставку
            new_balance = balance - stake
            cursor.execute("UPDATE users SET balance = %s WHERE id = %s", (new_balance, user_id))
            increment_stat(session['user_id'], 'minesweeper_played')

            conn.commit()

            # Количество бомб в зависимости от множителя
            #bombs_count = {1.2: 6, 1.5: 12, 1.7: 18}.get(multiplier, 6)
            bombs_count = {multiplier1: bombs1, multiplier2: bombs2, multiplier3: bombs3}.get(multiplier, 6)
            bombs = random.sample(range(25), bombs_count)

            # Сохраняем игру в сессии (можно)
            session['saper_game'] = {
                'bombs': bombs,
                'stake': stake,
                'multiplier': multiplier,
                'opened': []
            }

            return jsonify(success=True, bombs=bombs, new_balance=new_balance)
    finally:
        conn.close()

@app.route('/saper_win', methods=['POST'])
def saper_win():
    if 'user_id' not in session:
        return jsonify(success=False, error='Неавторизованный доступ')
    data = request.json
    stake = data.get('stake')
    multiplier = data.get('multiplier')

    game = session.get('saper_game')
    if not game:
        return jsonify(success=False, error='Игра не найдена')

    user_id = session['user_id']
    win_amount = stake * multiplier

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                return jsonify(success=False, error='Пользователь не найден')
            balance = user['balance']

            new_balance = balance + win_amount
            cursor.execute("UPDATE users SET balance = %s WHERE id = %s", (new_balance, user_id))
            conn.commit()

            # Удаляем игру из сессии
            session.pop('saper_game', None)

            return jsonify(success=True, win_amount=win_amount, new_balance=new_balance)
    finally:
        conn.close()

def is_game_enabled(game_name):
    conn = get_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT is_enabled FROM games_status WHERE game_name = %s", (game_name,))
        result = cursor.fetchone()
        return result and result['is_enabled']


@app.route('/cs2ob')
def cs2ob():
    if 'login' not in session:
        return redirect('/')
    if not is_game_enabled('case_default'):
        return render_template('disabled.html', game_name='Обычный кейс')

    conn = get_connection()
    balance = 0
    items = []

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            if user:
                balance = user['balance']

            # 👇 Добавим выборку предметов из базы
            cursor.execute("SELECT name, price, chance FROM case_default")
            items = cursor.fetchall()
    finally:
        conn.close()

    return render_template('cs2ob.html', balance=balance, db_items=items)



@app.route('/cs2ep')
def cs2ep():
    if 'login' not in session:
        return redirect('/')
    if not is_game_enabled('case_epic'):
        return render_template('disabled.html', game_name='Эпический кейс')

    conn = get_connection()
    balance = 0
    items = []

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            if user:
                balance = user.get('balance', 0)

            # 👇 Добавим выборку предметов из базы
            cursor.execute("SELECT name, price, chance FROM case_epic")
            items = cursor.fetchall()

    finally:
        conn.close()
    return render_template('cs2ep.html', balance=balance, db_items=items)


@app.route('/cs2leg')
def cs2leg():
    if 'login' not in session:
        return redirect('/')
    if not is_game_enabled('case_legendary'):
        return render_template('disabled.html', game_name='Легендарный кейс')

    conn = get_connection()
    balance = 0
    items = []

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            if user:
                balance = user.get('balance', 0)

            # 👇 Добавим выборку предметов из базы
            cursor.execute("SELECT name, price, chance FROM case_legendary")
            items = cursor.fetchall()
    finally:
        conn.close()
    return render_template('cs2leg.html', balance=balance, db_items=items)

@app.route('/cs2simple')
def cs2simple():
    if 'login' not in session:
        return redirect('/')
    if not is_game_enabled('case_simple'):
        return render_template('disabled.html', game_name='Кейс Симпла')

    conn = get_connection()
    balance = 0
    items = []

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            if user:
                balance = user.get('balance', 0)

            # 👇 Добавим выборку предметов из базы
            cursor.execute("SELECT name, price, chance FROM case_simple")
            items = cursor.fetchall()
    finally:
        conn.close()
    return render_template('cs2simple.html', balance=balance, db_items=items)



@app.route('/cs2monesy')
def cs2monesy():
    if 'login' not in session:
        return redirect('/')
    if not is_game_enabled('case_monesy'):
        return render_template('disabled.html', game_name='Кейс Монеси')

    conn = get_connection()
    balance = 0
    items = []

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            if user:
                balance = user.get('balance', 0)

            # 👇 Добавим выборку предметов из базы
            cursor.execute("SELECT name, price, chance FROM case_monesy")
            items = cursor.fetchall()
    finally:
        conn.close()
    return render_template('cs2monesy.html', balance=balance, db_items=items)



@app.route('/cs2donk')
def cs2donk():
    if 'login' not in session:
        return redirect('/')
    if not is_game_enabled('case_donka'):
        return render_template('disabled.html', game_name='Кейс Донка')

    conn = get_connection()
    balance = 0
    items = []

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            if user:
                balance = user.get('balance', 0)

            # 👇 Добавим выборку предметов из базы
            cursor.execute("SELECT name, price, chance FROM case_donka")
            items = cursor.fetchall()
    finally:
        conn.close()
    return render_template('cs2donk.html', balance=balance, db_items=items)




@app.route('/tgpod')
def tgpod():
    if 'login' not in session:
        return redirect('/')
    if not is_game_enabled('case_tgpod'):
        return render_template('disabled.html', game_name='ТГ-подарки кейс')
    conn = get_connection()
    items = []
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            balance = user['balance'] if user else 0

            # 👇 Добавим выборку предметов из базы
            cursor.execute("SELECT name, price, chance FROM case_tgpod")
            items = cursor.fetchall()
    finally:
        conn.close()
    return render_template('tgpod.html', balance=balance, db_items=items)


@app.route('/settings')
def settings():
    if 'login' not in session:
        return redirect('/')

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance, nickname, language, volume FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()

            if user:
                balance = user['balance']
                nickname = user['nickname']
                language = user['language']  # Уже читаемый язык
                volume = user.get('volume', 100)
            else:
                balance = 0
                nickname = ""
                language = "Русский"
                volume = 100
    finally:
        conn.close()

    return render_template('settings.html', balance=balance, nickname=nickname, language=language, volume=volume)


@app.route('/leaders')
def leaders():
    import random

    base_data = [
        ("BigBoss", ">100 000", 100000),
        ("CryptoKing", ">90 000", 90000),
        ("LuckyFox", ">80 000", 80000),
        ("CS2Pro", ">70 000", 70000),
        ("TGDropper", ">60 000", 60000),
        ("JackpotX", ">50 000", 50000),
        ("LoLmaster", ">40 000", 40000),
        ("LabubuFan", ">30 000", 30000),
        ("SkinTrader", ">20 000", 20000),
        ("NewRich", ">10 000", 10000),
    ]

    leaders = []
    for username, range_label, base_value in base_data:
        cases_opened = random.randint(base_value // 1500, base_value // 800)
        roulette_spins = random.randint(base_value // 2000, base_value // 1000)
        leaders.append({
            "username": username,
            "range": range_label,
            "cases": cases_opened,
            "roulette": roulette_spins
        })

    return render_template("leaders.html", leaders=leaders)






@app.route('/open_case', methods=['POST'])
def open_case():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Неавторизованный доступ'}), 403

    data = request.get_json()

    name = data.get('name')
    color = data.get('color')
    price = data.get('price')
    image = data.get('image')
    category = data.get('category') or 'Скины КС2'  # Категория по умолчанию
    case_price = data.get('case_price') or 1

    if not all([name, color, price, image, category]):
        return jsonify({'success': False, 'message': 'Некорректные данные предмета'}), 400

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE id = %s", (session['user_id'],))
            user = cursor.fetchone()
            if not user:
                return jsonify({'success': False, 'message': 'Пользователь не найден'}), 404

            if user['balance'] < case_price:
                return jsonify({'success': False, 'message': 'Недостаточно средств'}), 400

            new_balance = user['balance'] - case_price
            cursor.execute("UPDATE users SET balance = %s WHERE id = %s", (new_balance, session['user_id']))
            increment_stat(session['user_id'], 'cases_opened')

            cursor.execute("""
                INSERT INTO inventory (user_id, name, color, price, image, category)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (session['user_id'], name, color, price, image, category))

            cursor.execute("""
                INSERT INTO case_opens (user_id, opened_at)
                VALUES (%s, UTC_TIMESTAMP())
            """, (session['user_id'],))

            conn.commit()

            return jsonify({
                'success': True,
                'new_balance': new_balance,
                'won_item': {
                    'name': name,
                    'color': color,
                    'price': price,
                    'image': image,
                    'category': category
                }
            })

    except Exception as e:
        print('Ошибка в open_case:', e)
        return jsonify({'success': False, 'message': 'Внутренняя ошибка сервера'}), 500
    finally:
        conn.close()

@app.route('/inventory')
def inventory():
    if 'login' not in session:
        return redirect('/')

    category = request.args.get('category')

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            if not user:
                return redirect('/')

            user_id = user['id']
            balance = user['balance']

            if category and category != 'Все':
                cursor.execute("SELECT * FROM inventory WHERE user_id = %s AND category = %s", (user_id, category))
            else:
                cursor.execute("SELECT * FROM inventory WHERE user_id = %s", (user_id,))
            items = cursor.fetchall()
    finally:
        conn.close()

    return render_template('inventory.html', balance=balance, items=items, selected_category=category or 'Все')


@app.route('/spin', methods=['POST'])
def spin():
    if 'user_id' not in session:
        return jsonify({'error': 'Неавторизованный доступ'}), 403

    data = request.get_json()
    stake = float(data.get('stake', 1))
    user_id = session['user_id']

    SYMBOLS = ['cherry', 'lemon', 'grape', 'bell', 'star', 'seven']
    ROWS, COLS = 3, 5
    TOTAL_CELLS = ROWS * COLS


    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT multiplier FROM slot_config WHERE id = 1")
            matches1 = cursor.fetchone()['multiplier']
            cursor.execute("SELECT multiplier FROM slot_config WHERE id = 2")
            matches2 = cursor.fetchone()['multiplier']
            cursor.execute("SELECT multiplier FROM slot_config WHERE id = 3")
            matches3 = cursor.fetchone()['multiplier']
            cursor.execute("SELECT multiplier FROM slot_config WHERE id = 4")
            matches4 = cursor.fetchone()['multiplier']
            cursor.execute("SELECT multiplier FROM slot_config WHERE id = 5")
            matches5 = cursor.fetchone()['multiplier']
            cursor.execute("SELECT multiplier FROM slot_config WHERE id = 6")
            matches6 = cursor.fetchone()['multiplier']

            cursor.execute("SELECT probability FROM slot_config WHERE id = 1")
            weights1 = cursor.fetchone()['probability']
            cursor.execute("SELECT probability FROM slot_config WHERE id = 2")
            weights2 = cursor.fetchone()['probability']
            cursor.execute("SELECT probability FROM slot_config WHERE id = 3")
            weights3 = cursor.fetchone()['probability']
            cursor.execute("SELECT probability FROM slot_config WHERE id = 4")
            weights4 = cursor.fetchone()['probability']
            cursor.execute("SELECT probability FROM slot_config WHERE id = 5")
            weights5 = cursor.fetchone()['probability']
            cursor.execute("SELECT probability FROM slot_config WHERE id = 6")
            weights6 = cursor.fetchone()['probability']

    finally:
        conn.close()




    def count_most_common_symbol(reels):
        flat = [reels[col][row] for col in range(COLS) for row in range(ROWS)]
        counter = {}
        for symbol in flat:
            counter[symbol] = counter.get(symbol, 0) + 1
        return max(counter.values())

    def calculate_win(stake, matches):
        if matches < 5:
            return stake * float(matches1)
        elif matches == 5:
            return stake * float(matches2)
        elif matches == 6:
            return stake * float(matches3)
        elif matches == 7:
            return stake * float(matches4)
        elif matches == 8:
            return stake * float(matches5)
        else:
            return stake * float(matches6)

    def generate_reels_with_exact_match(match_count):
        chosen = random.choice(SYMBOLS)
        symbols = [chosen] * match_count
        while len(symbols) < TOTAL_CELLS:
            other = random.choice([s for s in SYMBOLS if s != chosen])
            symbols.append(other)
        random.shuffle(symbols)
        grid = [[None for _ in range(ROWS)] for _ in range(COLS)]
        for col in range(COLS):
            for row in range(ROWS):
                grid[col][row] = symbols.pop()
        return grid

    def generate_loss_reels():
        # Гарантируем, что максимум 4 совпадения
        while True:
            reels = generate_reels_with_exact_match(random.randint(1, 4))
            if count_most_common_symbol(reels) <= 4:
                return reels

    # Определяем сценарий по процентам
    scenario = random.choices(
        ['loss', 'match5', 'match6', 'match7', 'match8', 'match9'],
        weights=[weights1, weights2, weights3, weights4, weights5, weights6],
        k=1
    )[0]

    if scenario == 'loss':
        reels = generate_loss_reels()
    else:
        target = {'match5': 5, 'match6': 6, 'match7': 7, 'match8': 8, 'match9': 9}[scenario]
        reels = generate_reels_with_exact_match(target)

    match_count = count_most_common_symbol(reels)
    win = calculate_win(stake, match_count)

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            balance = user['balance'] if user else 0

            if balance < stake:
                return jsonify({'error': 'Недостаточно средств'}), 400

            balance -= stake
            balance += win

            cursor.execute("UPDATE users SET balance = %s WHERE id = %s", (balance, user_id))
            increment_stat(session['user_id'], 'slots_played')

            conn.commit()

            return jsonify({
                'reels': reels,
                'win': round(win, 2),
                'match_count': match_count,
                'new_balance': round(balance, 2)
            })
    finally:
        conn.close()



@app.route('/change_bet', methods=['POST'])
def change_bet():
    data = request.get_json()
    direction = data.get('direction')
    session.setdefault('bet', 1)

    if direction == 'up':
        session['bet'] += 0.25
    elif direction == 'down' and session['bet'] > 0.25:
        session['bet'] -= 0.25

    return jsonify({'bet': session['bet']})

@app.route('/get_balance')
def get_balance():
    user_id = session.get('user_id')
    telegram_id = request.args.get('telegram_id')

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            if user_id:
                cursor.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
            elif telegram_id:
                cursor.execute("SELECT balance FROM users WHERE telegram_id = %s", (telegram_id,))
            else:
                return jsonify({'balance': 0})

            result = cursor.fetchone()
            return jsonify({'balance': round(float(result['balance']), 2) if result else 0})
    finally:
        conn.close()

def get_balance_by_user_id(user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
            result = cursor.fetchone()
            return float(result['balance']) if result else 0
    finally:
        conn.close()



@app.route('/sell_item', methods=['POST'])
def sell_item():
    if 'login' not in session:
        return redirect('/login')

    item_id = request.form.get('item_id')
    if not item_id:
        return redirect('/inventory')

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # Получаем пользователя
            cursor.execute("SELECT id FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            if not user:
                return redirect('/')

            user_id = user['id']

            # Получаем предмет
            cursor.execute("SELECT price FROM inventory WHERE id = %s AND user_id = %s", (item_id, user_id))
            item = cursor.fetchone()
            if item:
                price = item['price']

                # Удаляем предмет
                cursor.execute("DELETE FROM inventory WHERE id = %s AND user_id = %s", (item_id, user_id))

                # Обновляем баланс
                cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (price, user_id))

                conn.commit()
    finally:
        conn.close()

    return redirect('/inventory')


@app.route('/start_social/<quest_id>', methods=['POST'])
def start_social_quest(quest_id):
    if 'user_id' not in session:
        return jsonify({'status': 'unauthorized'})

    user_id = session['user_id']
    now = datetime.utcnow()

    if quest_id not in quests_data or quests_data[quest_id]['type'] != 'social':
        return jsonify({'status': 'invalid quest'})

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO social_quest_timers (user_id, quest_id, start_time)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE start_time = VALUES(start_time)
            """, (user_id, quest_id, now))
        conn.commit()
    finally:
        conn.close()

    return jsonify({'status': 'started'})



def check_case_quest_completion(cursor, user_id, quest_id):
    cursor.execute("""
        SELECT required, interval_days FROM quests WHERE quest_id = %s
    """, (quest_id,))
    quest = cursor.fetchone()

    if not quest:
        return False  # нет такого квеста

    required = quest['required']
    interval_days = quest['interval_days']

    cursor.execute("""
        SELECT COUNT(*) AS count FROM case_opens
        WHERE user_id = %s AND opened_at >= UTC_TIMESTAMP() - INTERVAL %s DAY
    """, (user_id, interval_days))
    result = cursor.fetchone()
    return result['count'] >= required


@app.route('/check_social_status/<quest_id>')
def check_social_status(quest_id):
    if 'user_id' not in session:
        return jsonify({'can_claim': False})

    user_id = session['user_id']
    now = datetime.utcnow()

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT start_time FROM social_quest_timers WHERE user_id = %s AND quest_id = %s", (user_id, quest_id))
            timer = cursor.fetchone()
            if timer:
                elapsed = (now - timer['start_time']).total_seconds()
                return jsonify({'can_claim': elapsed >= 30})
    finally:
        conn.close()

    return jsonify({'can_claim': False})




@app.route('/claim_quest/<quest_id>', methods=['POST'])
def claim_quest(quest_id):
    if 'user_id' not in session:
        return jsonify({'status': 'unauthorized'})

    user_id = session['user_id']
    now = datetime.utcnow()
    qdata = quests_data.get(quest_id)
    if not qdata:
        return jsonify({'status': 'invalid quest'})

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT login FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                return jsonify({'status': 'user not found'})
            login = user['login']

            cursor.execute("SELECT * FROM quests_progress WHERE user_login = %s AND quest_id = %s", (login, quest_id))
            progress = cursor.fetchone()

            can_claim = False
            if qdata['type'] in ('daily', 'weekly'):
                if check_case_quest_completion(cursor, user_id, quest_id):
                    if not progress:
                        can_claim = True
                    else:
                        last = progress['last_claimed']
                        delta = timedelta(days=1 if qdata['type'] == 'daily' else 7)
                        can_claim = (now - last) >= delta
            elif qdata['type'] == 'social':
                if not progress or not progress['completed']:
                    cursor.execute("SELECT start_time FROM social_quest_timers WHERE user_id = %s AND quest_id = %s", (user_id, quest_id))
                    timer = cursor.fetchone()
                    if timer and (now - timer['start_time']).total_seconds() >= 30:
                        can_claim = True

            if not can_claim:
                return jsonify({'status': 'cooldown or not completed'})

            cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (qdata['reward'], user_id))

            if not progress:
                cursor.execute("""
                    INSERT INTO quests_progress (user_login, quest_id, last_claimed, completed)
                    VALUES (%s, %s, %s, %s)
                """, (login, quest_id, now, qdata['type'] == 'social'))
            else:
                cursor.execute("""
                    UPDATE quests_progress SET last_claimed = %s, completed = %s
                    WHERE user_login = %s AND quest_id = %s
                """, (now, qdata['type'] == 'social', login, quest_id))
            conn.commit()
    finally:
        conn.close()

    return jsonify({'status': 'success'})


@app.route('/quests')
def quests():
    if 'user_id' not in session:
        return redirect('/')

    user_id = session['user_id']
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT login, balance FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                return redirect('/')
            login = user['login']
            balance = user['balance']
            now = datetime.utcnow()

            grouped = {'daily': [], 'weekly': [], 'social': []}
            for qid, q in quests_data.items():
                cursor.execute("SELECT * FROM quests_progress WHERE user_login = %s AND quest_id = %s", (login, qid))
                progress = cursor.fetchone()

                can_claim = False
                completed = False

                if q['type'] in ('daily', 'weekly'):
                    if check_case_quest_completion(cursor, user_id, qid):
                        if not progress:
                            can_claim = True
                        else:
                            last = progress['last_claimed']
                            delta = timedelta(days=1 if q['type'] == 'daily' else 7)
                            can_claim = (now - last) >= delta
                    completed = progress and (now - progress['last_claimed']) < timedelta(days=1 if q['type'] == 'daily' else 7)
                elif q['type'] == 'social':
                    completed = progress and progress['completed']
                    if not completed:
                        cursor.execute("SELECT start_time FROM social_quest_timers WHERE user_id = %s AND quest_id = %s", (user_id, qid))
                        timer = cursor.fetchone()
                        if timer and (now - timer['start_time']).total_seconds() >= 30:
                            can_claim = True

                grouped[q['type']].append({
                    'id': qid,
                    'title': q['title'],
                    'description': q['description'],
                    'completed': completed,
                    'can_claim': can_claim,
                    'type': q['type'],
                    'link': q.get('link', '#')
                })

            # Создать секции с заголовками
            all_quests = []
            if grouped['daily']:
                all_quests.append({'name': 'Ежедневные', 'quests': grouped['daily']})
            if grouped['weekly']:
                all_quests.append({'name': 'Еженедельные', 'quests': grouped['weekly']})
            if grouped['social']:
                all_quests.append({'name': 'Социальные', 'quests': grouped['social']})
    finally:
        conn.close()

    return render_template('quests.html', balance=balance, quests=all_quests)






@app.route('/promocode', methods=['GET', 'POST'])
def promocode():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    message = None

    if request.method == 'POST':
        code = request.form.get('code', '').strip()

        if not code:
            message = "❌ Поле промокода не может быть пустым."
        else:
            conn = get_connection()
            try:
                with conn.cursor() as cursor:
                    # Получаем промокод
                    cursor.execute("SELECT * FROM promo_codes WHERE code=%s", (code,))
                    promo = cursor.fetchone()

                    if not promo:
                        message = "❌ Промокод не найден."
                    else:
                        # Проверка uses_left
                        if promo['uses_left'] is not None and promo['uses_left'] <= 0:
                            message = "❌ Промокод больше не активен."
                        else:
                            # Проверка per_user_once
                            if promo['per_user_once']:
                                cursor.execute(
                                    "SELECT 1 FROM promo_code_uses WHERE promo_code=%s AND user_id=%s",
                                    (code, user_id)
                                )
                                if cursor.fetchone():
                                    message = "❌ Вы уже использовали этот промокод."
                                else:
                                    # Засчитываем промокод
                                    cursor.execute(
                                        "UPDATE users SET balance = balance + %s WHERE id = %s",
                                        (promo['reward'], user_id)
                                    )
                                    if promo['uses_left'] is not None:
                                        cursor.execute(
                                            "UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = %s",
                                            (code,)
                                        )
                                    cursor.execute(
                                        "INSERT INTO promo_code_uses (promo_code, user_id) VALUES (%s, %s)",
                                        (code, user_id)
                                    )
                                    conn.commit()
                                    message = f"✅ Вы получили {promo['reward']}$!"
                            else:
                                # Засчитываем промокод без проверки на использование
                                cursor.execute(
                                    "UPDATE users SET balance = balance + %s WHERE id = %s",
                                    (promo['reward'], user_id)
                                )
                                if promo['uses_left'] is not None:
                                    cursor.execute(
                                        "UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = %s",
                                        (code,)
                                    )
                                cursor.execute(
                                    "INSERT INTO promo_code_uses (promo_code, user_id) VALUES (%s, %s)",
                                    (code, user_id)
                                )
                                conn.commit()
                                message = f"✅ Вы получили {promo['reward']}$!"
            finally:
                conn.close()

    balance = get_balance_by_user_id(user_id)
    return render_template('promocode.html', balance=balance, message=message)


@app.route('/roulette')
def roulette():
    if 'login' not in session:
        return redirect('/')
    if not is_game_enabled('roulette'):
        return render_template('disabled.html', game_name='Рулетка')
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            balance = user['balance'] if user else 0

            cursor.execute("SELECT type, multiplier FROM roulette_config")
            config = {row['type']: row['multiplier'] for row in cursor.fetchall()}
    finally:
        conn.close()
    return render_template('roulette.html', balance=balance, config=config)



@app.route('/spin_roulette', methods=['POST'])
def spin_roulette():
    if 'user_id' not in session:
        return jsonify({'error': 'Неавторизован'}), 403


    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT chance FROM roulette_config WHERE id = 1")
            chance1 = cursor.fetchone()['chance']
            cursor.execute("SELECT chance FROM roulette_config WHERE id = 2")
            chance2 = cursor.fetchone()['chance']
            cursor.execute("SELECT chance FROM roulette_config WHERE id = 3")
            chance3 = cursor.fetchone()['chance']
            cursor.execute("SELECT chance FROM roulette_config WHERE id = 4")
            chance4 = cursor.fetchone()['chance']
            cursor.execute("SELECT chance FROM roulette_config WHERE id = 5")
            chance5 = cursor.fetchone()['chance']
            cursor.execute("SELECT chance FROM roulette_config WHERE id = 6")
            chance6 = cursor.fetchone()['chance']
            cursor.execute("SELECT chance FROM roulette_config WHERE id = 7")
            chance7 = cursor.fetchone()['chance']
            cursor.execute("SELECT chance FROM roulette_config WHERE id = 8")
            chance8 = cursor.fetchone()['chance']

            cursor.execute("SELECT multiplier FROM roulette_config WHERE id = 1")
            multiplier1 = cursor.fetchone()['multiplier']
            cursor.execute("SELECT multiplier FROM roulette_config WHERE id = 2")
            multiplier2 = cursor.fetchone()['multiplier']
            cursor.execute("SELECT multiplier FROM roulette_config WHERE id = 3")
            multiplier3 = cursor.fetchone()['multiplier']
            cursor.execute("SELECT multiplier FROM roulette_config WHERE id = 4")
            multiplier4 = cursor.fetchone()['multiplier']
            cursor.execute("SELECT multiplier FROM roulette_config WHERE id = 5")
            multiplier5 = cursor.fetchone()['multiplier']
            cursor.execute("SELECT multiplier FROM roulette_config WHERE id = 6")
            multiplier6 = cursor.fetchone()['multiplier']
            cursor.execute("SELECT multiplier FROM roulette_config WHERE id = 7")
            multiplier7 = cursor.fetchone()['multiplier']
            cursor.execute("SELECT multiplier FROM roulette_config WHERE id = 8")
            multiplier7 = cursor.fetchone()['multiplier']

    finally:
        conn.close()



    data = request.get_json()
    bet_amount = float(data['bet_amount'])
    bet_type = data['bet_type']
    number_value = data.get('number_value')

    user_id = session['user_id']
    conn = get_connection()


    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            balance = user['balance']

            if bet_amount > balance:
                return jsonify({'error': 'Недостаточно средств'}), 400

            # Списываем ставку
            balance -= bet_amount
            cursor.execute("UPDATE users SET balance = %s WHERE id = %s", (balance, user_id))
            increment_stat(session['user_id'], 'roulette_played')
            conn.commit()

            sector_order = [
                0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30,
                8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7,
                28, 12, 35, 3, 26
            ]

            def random_outcome_with_chance(chance, valid_numbers):
                return random.random() < chance and random.choice(valid_numbers) or random.choice(
                    [n for n in sector_order if n not in valid_numbers])

            red = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
            black = {2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35}

            win = 0
            if bet_type == 'color_red':
                win_chance = chance1
                outcome = random_outcome_with_chance(win_chance, list(red))
                color = 'red' if outcome in red else 'black' if outcome in black else 'green'
                if color == 'red':
                    win = bet_amount * multiplier1

            elif bet_type == 'color_black':
                win_chance = chance2
                outcome = random_outcome_with_chance(win_chance, list(black))
                color = 'black' if outcome in black else 'red' if outcome in red else 'green'
                if color == 'black':
                    win = bet_amount * multiplier2

            elif bet_type == 'color_green':
                win_chance = chance3
                outcome = random_outcome_with_chance(win_chance, [0])
                color = 'green' if outcome == 0 else 'red' if outcome in red else 'black'
                if outcome == 0:
                    win = bet_amount * multiplier3

            elif bet_type == 'even':
                win_chance = chance4
                outcome = random_outcome_with_chance(win_chance, [n for n in sector_order if n != 0 and n % 2 == 0])
                color = 'green' if outcome == 0 else 'red' if outcome in red else 'black'
                if outcome != 0 and outcome % 2 == 0:
                    win = bet_amount * multiplier4

            elif bet_type == 'odd':
                win_chance = chance5
                outcome = random_outcome_with_chance(win_chance, [n for n in sector_order if n % 2 == 1])
                color = 'green' if outcome == 0 else 'red' if outcome in red else 'black'
                if outcome % 2 == 1:
                    win = bet_amount * multiplier5

            elif bet_type == 'low':
                win_chance = chance6
                outcome = random_outcome_with_chance(win_chance, [n for n in sector_order if 1 <= n <= 18])
                color = 'green' if outcome == 0 else 'red' if outcome in red else 'black'
                if 1 <= outcome <= 18:
                    win = bet_amount * multiplier6

            elif bet_type == 'high':
                win_chance = chance7
                outcome = random_outcome_with_chance(win_chance, [n for n in sector_order if 19 <= n <= 36])
                color = 'green' if outcome == 0 else 'red' if outcome in red else 'black'
                if 19 <= outcome <= 36:
                    win = bet_amount * multiplier7

            elif bet_type == 'number':
                win_chance = chance8
                if number_value is None or not (0 <= int(number_value) <= 36):
                    return jsonify({'error': 'Неверное число'})
                target_number = int(number_value)
                outcome = random_outcome_with_chance(win_chance, [target_number])
                color = 'green' if outcome == 0 else 'red' if outcome in red else 'black'
                if outcome == target_number:
                    win = bet_amount * multiplier8

            if win > 0:
                balance += win
                cursor.execute("UPDATE users SET balance = %s WHERE id = %s", (balance, user_id))
                conn.commit()

            index = sector_order.index(outcome)

            return jsonify({
                'outcome': outcome,
                'index': index,
                'color': color,
                'win': round(win, 2),
                'new_balance': round(balance, 2)
            })
    finally:
        conn.close()





# Обновление языка
@app.route('/update_language', methods=['POST'])
def update_language():
    if 'login' not in session:
        return jsonify(success=False, message="Нет сессии")

    data = request.json
    language_code = data.get('language')  # Уже "Русский", "English", "Українська"

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET language=%s WHERE login=%s", (language_code, session['login']))
            conn.commit()
    finally:
        conn.close()
    return jsonify(success=True)


# Обновление ника
@app.route('/update_nickname', methods=['POST'])
def update_nickname():
    if 'login' not in session:
        return jsonify(success=False, message="Нет сессии")

    data = request.json
    nickname = data.get('nickname')

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET nickname=%s WHERE login=%s", (nickname, session['login']))
            conn.commit()
    finally:
        conn.close()
    return jsonify(success=True)

# Обновление громкости
@app.route('/update_volume', methods=['POST'])
def update_volume():
    if 'login' not in session:
        return jsonify(success=False, message="Нет сессии")

    data = request.json
    volume = data.get('volume')

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET volume=%s WHERE login=%s", (volume, session['login']))
            conn.commit()
    finally:
        conn.close()
    return jsonify(success=True)


@app.route('/create-invoice', methods=['POST'])
def create_invoice():
    data = request.get_json()
    amount = data.get('amount')
    user_id = session.get('user_id')

    if not user_id:
        return jsonify({'error': 'Not logged in'}), 401

    if not amount or float(amount) <= 0:
        return jsonify({'error': 'Invalid amount'}), 400

    order_number = str(uuid.uuid4())

    params = {
        'api_key': PLISIO_API_KEY,
        'amount': amount,
        'currency': 'USDT_TRX',
        'order_name': 'Deposit to Casino',
        'order_number': order_number,
        'callback_url': 'https://oleg121212.pythonanywhere.com/payment-status',
        'success_url': 'https://oleg121212.pythonanywhere.com/payment-success'
    }

    try:
        response = requests.get('https://api.plisio.net/api/v1/invoices/new', params=params)
        result = response.json()

        if response.status_code == 200 and result.get('status') == 'success':
            invoice_url = result['data']['invoice_url']

            # Сохраняем в базу ордер и пользователя
            conn = get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO invoices (user_id, amount, order_number, status) VALUES (%s, %s, %s, %s)",
                    (user_id, amount, order_number, 'pending')
                )
                conn.commit()

            return jsonify({'invoice_url': invoice_url})
        else:
            return jsonify({'error': 'Invoice creation failed', 'details': result}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/payment-status', methods=['POST'])
def payment_status():
    try:
        data = request.json or request.form
        print('Полученные данные от Plisio:', data)
        print('Plisio Callback:\n' + json.dumps(data, indent=2, ensure_ascii=False))

        status = data.get('status')
        order_number = data.get('order_number') or data.get('params', {}).get('order_number')
        amount = float(data.get('amount') or data.get('params', {}).get('source_amount') or 0)

        if not order_number:
            return 'Missing order number', 400

        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id, status FROM invoices WHERE order_number = %s", (order_number,))
            invoice = cursor.fetchone()

            if not invoice:
                return 'Invoice not found', 404

            user_id = invoice['user_id']
            old_status = invoice['status']

            if old_status == 'completed':
                return 'Already processed', 200

            print(f"Updating balance for user_id={user_id}, amount={amount}")
            user_id = int(user_id)

            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if cursor.fetchone() is None:
                return 'User does not exist', 404

            user_id = int(user_id)
            cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (amount, user_id))
            if cursor.rowcount == 0:
                return 'User not found or balance not updated', 500

            cursor.execute("UPDATE invoices SET status = 'completed' WHERE order_number = %s", (order_number,))
            conn.commit()

        return 'OK', 200

    except Exception as e:
        print('Ошибка в payment-status:', e)
        return jsonify({'error': str(e)}), 500

@app.route('/check-invoice')
def check_invoice():
    order_number = request.args.get('order_number')
    if not order_number:
        return jsonify({'error': 'Missing order_number'}), 400

    try:
        response = requests.get('https://api.plisio.net/api/v1/operations', params={
            'api_key': PLISIO_API_KEY,
            'search': order_number
        })
        data = response.json()
        print('Plisio /operations result:', json.dumps(data, indent=2, ensure_ascii=False))

        if data.get('status') != 'success' or not data['data'].get('operations'):
            return jsonify({'error': 'Operation not found'}), 404

        tx = data['data']['operations'][0]
        tx_status = tx['status']

        if tx_status != 'completed':
            return jsonify({'status': tx_status, 'message': 'Payment not completed yet'})

        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id, status, amount FROM invoices WHERE order_number = %s", (order_number,))
            invoice = cursor.fetchone()

            if not invoice:
                return jsonify({'error': 'Invoice not found'}), 404

            if invoice['status'] == 'completed':
                return jsonify({'status': 'already_processed'})

            user_id = int(invoice['user_id'])
            tx_amount = float(invoice['amount'] or 0)

            if tx_amount <= 0:
                return jsonify({'error': 'Invalid amount in invoice'}), 400

            cursor.execute("UPDATE users SET balance = COALESCE(balance, 0) + %s WHERE id = %s", (tx_amount, user_id))

            cursor.execute("""
                UPDATE users
                SET total_deposit = COALESCE(total_deposit, 0) + %s,
                    has_deposit = TRUE
                WHERE id = %s
            """, (tx_amount, user_id))

            cursor.execute("UPDATE invoices SET status = 'completed' WHERE order_number = %s", (order_number,))

            conn.commit()

        return jsonify({'status': 'completed', 'amount': tx_amount})

    except Exception as e:
        print('Ошибка в check-invoice:', e)
        return jsonify({'error': str(e)}), 500



@app.route('/payment-success')
def payment_success():
    return redirect('/profile')




@app.route('/send-withdraw-request', methods=['POST'])
def send_withdraw_request():
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401

        user_id = session['user_id']
        data = request.get_json()
        amount = data.get('amount')
        username = data.get('username')

        if not username or not username.startswith('@') or len(username) < 2:
            return jsonify({'success': False, 'error': 'Invalid username'}), 400

        if amount is None or amount < 40:
            return jsonify({'success': False, 'error': 'Invalid amount'}), 400


        conn = get_connection()
        with conn.cursor() as cursor:
            # Получаем данные из users
            cursor.execute("SELECT login, balance FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()

            if not user:
                return jsonify({'success': False, 'error': 'User not found'}), 404

            if amount > user['balance']:
                return jsonify({'success': False, 'error': 'Insufficient funds'}), 400

            # Получаем данные из user_metadata
            cursor.execute("""
                SELECT ip_address, language, timezone, screen_resolution, platform, total_deposit, has_deposit
                FROM user_metadata
                WHERE user_id = %s
            """, (user_id,))
            metadata = cursor.fetchone()

        # Формируем сообщение
        message = f"""💸 Запрос на вывод средств
👤 Логин: {user['login']}
🆔 ID: {user_id}
💰 Баланс: {user['balance']} USDT
🔻 Запрошенная сумма: {amount} USDT
👥 Telegram: {username}

📊 Дополнительные данные:
🌍 IP: {metadata['ip_address']}
🗣️ Язык: {metadata['language']}
⏰ Часовой пояс: {metadata['timezone']}
🖥️ Разрешение экрана: {metadata['screen_resolution']}
📱 Платформа: {metadata['platform']}
💳 Всего пополнено: {metadata['total_deposit']} USDT
🔄 Пополнял ранее: {"Да" if metadata['has_deposit'] else "Нет"}"""

        # Отправка в Telegram
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {'chat_id': CHAT_ID, 'text': message}
        response = requests.post(url, json=payload)
        response.raise_for_status()

        return jsonify({'success': True})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        login = request.form.get('login')
        password = request.form.get('password')

        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, is_admin FROM users WHERE login=%s AND password=%s", (login, password))
            admin = cursor.fetchone()
        conn.close()

        if admin and admin['is_admin']:
            session['admin_id'] = admin['id']
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))

        flash('Неверный логин или пароль')
    return render_template('admin/admin_login.html')



@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    conn = get_connection()
    with conn.cursor() as c:
        # KPI
        c.execute("SELECT COUNT(*) total_users FROM users")
        total_users = c.fetchone()['total_users']

        c.execute("SELECT COUNT(*) total_cases FROM case_opens")
        total_cases = c.fetchone()['total_cases']

        c.execute("SELECT COUNT(*) total_promos FROM promo_codes")
        total_promos = c.fetchone()['total_promos']

        c.execute("SELECT SUM(total_deposit) as total_deposit FROM user_metadata")
        total_deposit = c.fetchone()['total_deposit'] or 0

        c.execute("SELECT SUM(balance) as total_balance FROM users")
        total_balance = c.fetchone()['total_balance'] or 0

        c.execute("SELECT login, balance FROM users ORDER BY balance DESC LIMIT 5")
        top_balances = c.fetchall()

        c.execute("SELECT id, user_id, amount, status, created_at FROM invoices ORDER BY created_at DESC LIMIT 5")
        recent_tx = c.fetchall()

        c.execute("SELECT SUM(slots_played) as slots_played FROM user_stats")
        slots_played = c.fetchone()['slots_played'] or 0
        c.execute("SELECT SUM(minesweeper_played) as minesweeper_played FROM user_stats")
        minesweeper_played = c.fetchone()['minesweeper_played'] or 0
        c.execute("SELECT SUM(cases_opened) as cases_opened FROM user_stats")
        cases_opened = c.fetchone()['cases_opened'] or 0
        c.execute("SELECT SUM(roulette_played) as roulette_played FROM user_stats")
        roulette_played = c.fetchone()['roulette_played'] or 0

        # 🎯 Реальные completed суммы по месяцам
        c.execute("""
            SELECT
                YEAR(created_at) AS y,
                MONTH(created_at) AS m,
                SUM(amount) AS total
            FROM invoices
            WHERE status = 'completed' AND created_at IS NOT NULL
            GROUP BY y, m
            ORDER BY y, m
        """)
        rows = c.fetchall()

    conn.close()

    # Построение словаря с ключами ГГГГ-ММ
    now = datetime.now().replace(day=1)
    months = [(now - relativedelta(months=i)) for i in reversed(range(12))]
    month_keys = [d.strftime('%Y-%m') for d in months]
    income_data = {k: 0 for k in month_keys}

    # Вставка данных
    for row in rows:
        k = f"{row['y']}-{row['m']:02}"
        if k in income_data:
            income_data[k] = float(row['total'])

    # Подготовка для графика
    chart_labels = [datetime.strptime(k, "%Y-%m").strftime("%b %Y") for k in month_keys]
    chart_values = [income_data[k] for k in month_keys]

    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           total_cases=total_cases,
                           total_promos=total_promos,
                           total_deposit=total_deposit,
                           total_balance=total_balance,
                           top_balances=top_balances,
                           recent_tx=recent_tx,
                           slots_played=str(slots_played),
                           minesweeper_played=str(minesweeper_played),
                           cases_opened=str(cases_opened),
                           roulette_played=str(roulette_played),
                           chart_labels=chart_labels,
                           chart_values=chart_values)




@app.route('/admin/users')
@admin_required
def admin_users():
    conn = get_connection()
    with conn.cursor() as c:
        c.execute("SELECT * FROM users")
        users = c.fetchall()
    return render_template('admin/users.html', users=users, menu=admin_menu)


@app.route('/admin/games', methods=['GET'])
@admin_required
def admin_games():
    selected_table = request.args.get('case') or 'case_default'
    tables = ['case_default', 'case_epic', 'case_legendary', 'case_simple', 'case_monesy', 'case_donka', 'case_labubu', 'case_tgpod', 'case_crypto', 'slots', 'roulette', 'saper', 'coin', 'crush']

    conn = get_connection()
    with conn.cursor() as c:
        try:
            if selected_table == 'slots':
                c.execute("SELECT * FROM slot_config ORDER BY match_min")
                items = c.fetchall()
            elif selected_table == 'roulette':
                c.execute("SELECT * FROM roulette_config ORDER BY id")
                items = c.fetchall()
            elif selected_table == 'saper':
                c.execute("SELECT * FROM saper_config ORDER BY id")
                items = c.fetchall()
            elif selected_table == 'coin':
                c.execute("SELECT * FROM coin_config ORDER BY id")
                items = c.fetchall()
            elif selected_table == 'crush':
                c.execute("SELECT * FROM crash_config ORDER BY id")
                items = c.fetchall()
            else:
                c.execute(f"SELECT * FROM `{selected_table}`")
                items = c.fetchall()

            # Получаем статус игры
            c.execute("SELECT is_enabled FROM games_status WHERE game_name = %s", (selected_table,))
            status_row = c.fetchone()
            is_enabled = status_row['is_enabled'] if status_row else False

        except Exception as e:
            print("Ошибка при загрузке данных:", e)
            items = []
            is_enabled = False
    conn.close()

    return render_template('admin/games.html',
                           tables=tables,
                           current=selected_table,
                           items=items, is_enabled=is_enabled)


@app.route('/admin/toggle_game_status', methods=['POST'])
@admin_required
def toggle_game_status():
    game_name = request.form.get('game_name')
    if not game_name:
        flash('Не указано имя игры')
        return redirect(url_for('admin_games'))

    conn = get_connection()
    with conn.cursor() as c:
        c.execute("SELECT is_enabled FROM games_status WHERE game_name = %s", (game_name,))
        result = c.fetchone()
        if result is None:
            # если запись отсутствует — создаём и включаем
            c.execute("INSERT INTO games_status (game_name, is_enabled) VALUES (%s, %s)", (game_name, 1))
        else:
            new_status = 0 if result['is_enabled'] else 1
            c.execute("UPDATE games_status SET is_enabled = %s WHERE game_name = %s", (new_status, game_name))
        conn.commit()

    return redirect(url_for('admin_games', case=game_name))



@app.route('/admin/tokens', methods=['GET', 'POST'])
@admin_required
def admin_tokens():
    conn = get_connection()
    msg = None
    if request.method == 'POST':
        data = {key: request.form[key] for key in request.form}
        with conn.cursor() as c:
            c.execute("DELETE FROM tokens")  # всегда храним только 1 строку
            c.execute("""
                INSERT INTO tokens (
                    plisio_api, tgbot_token, admin_tg_chat_id, name_letter,
                    text_letter, from_letter, smtp, login_email, login_pass
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                data['plisio_api'], data['tgbot_token'], data['admin_tg_chat_id'],
                data['name_letter'], data['text_letter'], data['from_letter'],
                data['smtp'], data['login_email'], data['login_pass']
            ))
            conn.commit()
            msg = "Данные обновлены"
    with conn.cursor() as c:
        c.execute("SELECT * FROM tokens LIMIT 1")
        token = c.fetchone()
    return render_template('admin/tokens.html', token=token or {}, msg=msg, menu=admin_menu)




@app.route('/admin/invoices')
@admin_required
def admin_invoices():
    conn = get_connection()
    with conn.cursor() as c:
        c.execute("SELECT * FROM invoices")
        data = c.fetchall()
    return render_template('admin/invoices.html', items=data, menu=admin_menu)

@app.route('/admin/promo_codes', methods=['GET', 'POST'])
@admin_required
def admin_promo_codes():
    conn = get_connection()
    if request.method == 'POST':
        code = request.form['code']
        reward = request.form['reward']
        uses = request.form['uses_left'] or None
        per_user = 1 if request.form.get('per_user_once') else 0
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO promo_codes (code,reward,uses_left,per_user_once) VALUES (%s,%s,%s,%s)",
                (code, reward, uses, per_user)
            )
            conn.commit()
        flash(f'Промокод "{code}" добавлен')
    with conn.cursor() as c:
        c.execute("SELECT * FROM promo_codes")
        items = c.fetchall()
    return render_template('admin/promo_codes.html', items=items, menu=admin_menu)

@app.route('/admin/case_opens')
@admin_required
def admin_case_opens():
    conn = get_connection()
    with conn.cursor() as c:
        c.execute("""
            SELECT co.id, co.user_id, u.login, co.opened_at
            FROM case_opens co
            JOIN users u ON u.id = co.user_id
            ORDER BY co.opened_at DESC
            LIMIT 200
        """)
        items = c.fetchall()
    return render_template('admin/case_opens.html', items=items, menu=admin_menu)

# Роут на отображение всех квестов
@app.route('/admin/quests')
@admin_required
def admin_quests():
    conn = get_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM quests")
        quests = cursor.fetchall()
    return render_template('admin/quests.html', quests=quests, menu=admin_menu)


# Роут для добавления нового квеста
@app.route('/admin/quests/add', methods=['POST'])
@admin_required
def add_quest():
    data = request.form
    conn = get_connection()
    with conn.cursor() as cursor:
        cursor.execute("""
            INSERT INTO quests (quest_id, title_ru, description_ru, reward, quest_type, url, required, interval_days)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data['quest_id'],
            data['title_ru'],
            data['description_ru'],
            data['reward'],
            data['quest_type'],
            data.get('url', ''),
            data.get('required', 0),         # по умолчанию 0
            data.get('interval_days', 0)     # по умолчанию 0
        ))

    conn.commit()
    return redirect(url_for('admin_quests'))

@app.route('/admin/quests/update', methods=['POST'])
@admin_required
def update_quest():
    try:
        data = request.get_json()
        quest_id = data.get('id')
        field = data.get('field')
        value = data.get('value')

        if not quest_id or not field:
            return jsonify({'error': 'Недостаточно данных'}), 400

        # Разрешенные поля для обновления
        allowed_fields = ['title_ru', 'description_ru', 'reward', 'quest_type', 'required', 'interval_days']
        if field not in allowed_fields:
            return jsonify({'error': 'Запрещено редактировать это поле'}), 400

        # Приведение типов
        if field in ['reward']:
            value = float(value)
        elif field in ['required', 'interval_days']:
            value = int(value)

        conn = get_connection()
        with conn.cursor() as c:
            query = f"UPDATE quests SET {field} = %s WHERE id = %s"
            c.execute(query, (value, quest_id))
            conn.commit()

        return jsonify({'success': True})
    except Exception as e:
        print(f"Ошибка при обновлении квеста: {e}")
        return jsonify({'error': str(e)}), 500




# Роут для удаления квеста
@app.route('/admin/quests/delete/<int:quest_id>')
@admin_required
def delete_quest(quest_id):
    conn = get_connection()
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM quests WHERE id = %s", (quest_id,))
    conn.commit()
    return redirect(url_for('admin_quests'))



@app.route('/admin/user_stats')
@admin_required
def admin_user_stats():
    conn = get_connection()
    with conn.cursor() as c:
        c.execute("SELECT * FROM user_stats")
        data = c.fetchall()
    return render_template('admin/user_stats.html', items=data, menu=admin_menu)
@app.route('/admin/user_metadata')
@admin_required
def admin_metadata():
    conn = get_connection()
    with conn.cursor() as c:
        c.execute("SELECT * FROM user_metadata")
        data = c.fetchall()
    return render_template('admin/user_metadata.html', items=data, menu=admin_menu)


@app.route('/admin/balances', methods=['GET','POST'])
@admin_required
def admin_balances():
    conn = get_connection()
    msg = None
    if request.method=='POST':
        uid = request.form['user_id']
        new = float(request.form['new_balance'])
        with conn.cursor() as c:
            c.execute("UPDATE users SET balance=%s WHERE id=%s", (new, uid))
            conn.commit()
            msg = f'Баланс пользователя {uid} обновлён'
    with conn.cursor() as c:
        c.execute("SELECT id, login, balance FROM users")
        users = c.fetchall()
    return render_template('admin/balances.html', msg=msg, users=users, menu=admin_menu)



admin_menu = [
 ('Пользователи', '/admin/users'),
 ('Пополнения', '/admin/invoices'),
 ('Промокоды', '/admin/promo_codes'),
 ('Кейсы', '/admin/case_opens'),
 ('Квесты', '/admin/quests'),
 ('Статистика', '/admin/user_stats'),
 ('Метаданные', '/admin/user_metadata'),
 ('Управление балансами', '/admin/balances'),
]
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    session.pop('is_admin', None)
    return redirect(url_for('admin_login'))

@app.route('/admin/chart/cases_by_day')
@admin_required
def chart_cases_by_day():
    conn = get_connection()
    with conn.cursor() as c:
        c.execute("""
            SELECT DATE(opened_at) as day, COUNT(*) as total
            FROM case_opens
            GROUP BY day
            ORDER BY day ASC
            LIMIT 30
        """)
        rows = c.fetchall()
    data = {
        'labels': [r['day'].strftime('%Y-%m-%d') for r in rows],
        'counts': [r['total'] for r in rows]
    }
    return jsonify(data)
@app.route('/admin/delete_row', methods=['POST'])
@admin_required
def admin_delete_row():
    data = request.get_json()
    table = data.get('table')
    row_id = data.get('id')
    if not table or not row_id:
        return jsonify({'success': False, 'error': 'Missing parameters'})

    conn = get_connection()
    with conn.cursor() as c:
        c.execute(f"DELETE FROM {table} WHERE id = %s", (row_id,))
        conn.commit()
    return jsonify({'success': True})

@app.route('/admin/update_cell', methods=['POST'])
@admin_required
def admin_update_cell():
    data = request.get_json()
    table = data.get('table')
    row_id = data.get('id')
    field = data.get('field')
    value = data.get('value')
    if not table or not row_id or not field:
        return jsonify({'success': False, 'error': 'Missing parameters'})

    conn = get_connection()
    with conn.cursor() as c:
        c.execute(f"UPDATE {table} SET {field} = %s WHERE id = %s", (value, row_id))
        conn.commit()
    return jsonify({'success': True})


@app.route('/admin/referrals')
@admin_required
def admin_referrals():
    conn = get_connection()
    referral_stats = []

    with conn.cursor() as c:
        # Получаем пользователей с рефералами
        c.execute("""
            SELECT id, login, referral_code, referral_count
            FROM users
            WHERE referral_count > 0
            ORDER BY referral_count DESC
        """)
        users = c.fetchall()

        for user in users:
            user_id = user['id']
            login = user['login']
            referral_code = user['referral_code']

            referral_count_raw = user.get('referral_count', 0)
            try:
                referral_count = int(referral_count_raw)
            except (TypeError, ValueError):
                referral_count = 0

            # Рассчитываем доход
            if referral_count <= 10:
               income = referral_count * 0.5
            elif referral_count <= 100:
               income = (10 * 0.5) + ((referral_count - 10) * 0.1)
            else:
               income = (10 * 0.5) + (90 * 0.1) + ((referral_count - 100) * 0.01)


            referral_stats.append({
                'id': user_id,
                'login': login,
                'referral_code': referral_code,
                'referral_count': referral_count,
                'referral_income': str(income)
            })

    conn.close()

    return render_template('admin/referrals.html', referrals=referral_stats, menu=admin_menu)


@app.route('/admin/inventories')
@admin_required
def admin_inventories():
    return render_template('admin/inventories.html', menu=admin_menu)


@app.route('/admin/inventory/<int:user_id>', methods=["GET"])
@admin_required
def admin_view_inventory(user_id):
    conn = get_connection()
    user = None
    items = []

    with conn.cursor() as c:
        c.execute("SELECT id, login FROM users WHERE id = %s", (user_id,))
        user = c.fetchone()

        if user:
            c.execute("""
                SELECT id, name, price, image, color, category
                FROM inventory
                WHERE user_id = %s
            """, (user_id,))
            items = c.fetchall()

    conn.close()
    return render_template("admin/inventories.html", user=user, items=items, menu=admin_menu)


@app.route('/admin/user-search')
@admin_required
def admin_user_search():
    query = request.args.get('q', '').strip()
    conn = get_connection()
    users = []

    with conn.cursor() as c:
        if query.isdigit():
            c.execute("SELECT id, login FROM users WHERE id LIKE %s LIMIT 10", (f"{query}%",))
        else:
            c.execute("SELECT id, login FROM users WHERE login LIKE %s LIMIT 10", (f"{query}%",))
        users = c.fetchall()

    conn.close()
    return jsonify(users)

@app.route('/admin/case-items')
@admin_required
def admin_case_items():
    table = request.args.get("table")
    allowed = ['case_crypto', 'case_labubu', 'case_tgpod', 'case_default', 'case_epic', 'case_legendary', 'case_simple', 'case_monesy', 'case_donka']

    if table not in allowed:
        return jsonify([])

    conn = get_connection()
    items = []
    with conn.cursor() as c:
        c.execute(f"SELECT id, name, price FROM {table} ORDER BY price DESC LIMIT 100")
        items = c.fetchall()
    conn.close()
    return jsonify(items)

@app.route('/admin/add-item/<int:user_id>', methods=['POST'])
@admin_required
def admin_add_item(user_id):
    case_table = request.form.get('case_table')
    item_id = request.form.get('item_id')

    allowed_tables = ['case_crypto', 'case_labubu', 'case_tgpod', 'case_default', 'case_epic', 'case_legendary', 'case_simple', 'case_monesy', 'case_donka']
    if case_table not in allowed_tables:
        return "Неверная таблица", 400

    conn = get_connection()
    with conn.cursor() as c:
        # Получить предмет из указанной таблицы
        c.execute(f"SELECT name, price, image, color, category FROM {case_table} WHERE id = %s", (item_id,))
        item = c.fetchone()
        if not item:
            return "Предмет не найден", 404

        # Добавить в inventory
        c.execute("""
            INSERT INTO inventory (user_id, name, price, image, color, category)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, item['name'], item['price'], item['image'], item['color'], item['category']))
        conn.commit()

    conn.close()
    return redirect(url_for('admin_view_inventory', user_id=user_id))


@app.route('/admin/delete-item/<int:item_id>', methods=['POST'])
@admin_required
def admin_delete_item(item_id):
    conn = get_connection()
    user_id = None

    with conn.cursor() as c:
        c.execute("SELECT user_id FROM inventory WHERE id = %s", (item_id,))
        row = c.fetchone()
        if row:
            user_id = row['user_id']
            c.execute("DELETE FROM inventory WHERE id = %s", (item_id,))
            conn.commit()

    conn.close()
    if user_id:
        return redirect(url_for('admin_view_inventory', user_id=user_id))
    return "Not Found", 404


@app.route('/play_coinflip', methods=['POST'])
def play_coinflip():
    if 'login' not in session:
        return jsonify({'error': 'not_logged_in'}), 401


    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT multiplier FROM coin_config WHERE id = 1")
            matches1 = cursor.fetchone()['multiplier']

            cursor.execute("SELECT probability FROM coin_config WHERE id = 1")
            weights1 = cursor.fetchone()['probability']

    finally:
        conn.close()


    try:
        data = request.get_json()
        bet = float(data.get('bet', 1.0))
        if bet < 0.25:
            return jsonify({'error': 'min_bet'}), 400
    except:
        return jsonify({'error': 'invalid_bet'}), 400

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # Получаем баланс
            cursor.execute("SELECT balance FROM users WHERE login = %s", (session['login'],))
            user = cursor.fetchone()
            if not user:
                return jsonify({'error': 'user_not_found'}), 404

            balance = float(user['balance'])
            if bet > balance:
                return jsonify({'error': 'not_enough_balance'}), 400

            # Списываем ставку сразу
            new_balance = balance - bet
            cursor.execute("UPDATE users SET balance = %s WHERE login = %s", (new_balance, session['login']))
            conn.commit()

            # Определяем победу или проигрыш (50% шанс)
            win_chance = weights1  # можно потом вынести в конфиг
            win = random.random() < win_chance

            if win:
                winnings = bet * matches1
                new_balance += winnings
                cursor.execute("UPDATE users SET balance = %s WHERE login = %s", (new_balance, session['login']))
                conn.commit()

            return jsonify({
                'result': 'win' if win else 'loss',
                'new_balance': round(new_balance, 2)
            })
    finally:
        conn.close()
##################################################################################################################################################

@app.route('/start_crush', methods=['POST'])
def start_crush():
    if 'user_id' not in session:
        return jsonify({'error': 'Неавторизованный доступ'}), 403

    data = request.get_json()
    stake = float(data.get('stake', 1))
    user_id = session['user_id']
    if stake <= 0:
        return jsonify({'error': 'Некорректная ставка'}), 400

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT probability FROM crash_config WHERE id = 1")
            weights1 = cursor.fetchone()['probability']
            cursor.execute("SELECT probability FROM crash_config WHERE id = 2")
            weights2 = cursor.fetchone()['probability']
            cursor.execute("SELECT probability FROM crash_config WHERE id = 3")
            weights3 = cursor.fetchone()['probability']
            cursor.execute("SELECT probability FROM crash_config WHERE id = 4")
            weights4 = cursor.fetchone()['probability']
            cursor.execute("SELECT probability FROM crash_config WHERE id = 5")
            weights5 = cursor.fetchone()['probability']


    finally:
        conn.close()

    # Вероятности взрыва с новыми множителями
    explosion_ranges = [
        (0.0, 1.0, weights1),   # 50% что взорвется до 1.00x
        (1.0, 2.0, weights2),    # 30% что взорвется до 2.00x
        (2.0, 3.0, weights3),   # 15% что взорвется до 4.00x
        (3.0, 4.0, weights4),    # 5% что взорвется до 6.00x
        (4.0, 5.0, weights5)
    ]

    # Выбираем диапазон для взрыва
    chosen_range = random.choices(
        explosion_ranges,
        weights=[r[2] for r in explosion_ranges],
        k=1
    )[0]

    # Генерируем случайный множитель в выбранном диапазоне
    explosion_at = round(random.uniform(chosen_range[0], chosen_range[1]), 2)

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                return jsonify({'error': 'Пользователь не найден'}), 404

            balance = user['balance']

            if balance < stake:
                return jsonify({'error': 'Недостаточно средств'}), 400

            # Списываем ставку
            new_balance = balance - stake
            cursor.execute("UPDATE users SET balance = %s WHERE id = %s", (new_balance, user_id))
            conn.commit()

            return jsonify({
                'success': True,
                'new_balance': round(new_balance, 2),
                'explosion_at': explosion_at
            })
    except Exception as e:
        conn.rollback()
        return jsonify({'error': 'Ошибка при запуске игры'}), 500
    finally:
        conn.close()

@app.route('/cashout_crush', methods=['POST'])
def cashout_crush():
    if 'user_id' not in session:
        return jsonify({'error': 'Неавторизованный доступ'}), 403

    data = request.get_json()
    stake = float(data.get('stake', 1))
    multiplier = float(data.get('multiplier', 0))
    user_id = session['user_id']

    # Дополнительные проверки
    if multiplier <= 0:
        return jsonify({'error': 'Некорректный множитель'}), 400
    if stake <= 0:
        return jsonify({'error': 'Некорректная ставка'}), 400

    win_amount = stake * multiplier

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # Блокируем запись для безопасного обновления
            cursor.execute("SELECT balance FROM users WHERE id = %s FOR UPDATE", (user_id,))
            user = cursor.fetchone()
            if not user:
                return jsonify({'error': 'Пользователь не найден'}), 404

            balance = user['balance']
            new_balance = balance + win_amount

            # Обновляем баланс
            cursor.execute("UPDATE users SET balance = %s WHERE id = %s",
                         (new_balance, user_id))

            conn.commit()

            return jsonify({
                'success': True,
                'new_balance': round(new_balance, 2),
                'win_amount': round(win_amount, 2)
            })
    except Exception as e:
        conn.rollback()
        return jsonify({'error': 'Ошибка при обработке запроса'}), 500
    finally:
        conn.close()

@app.route('/check_crush', methods=['POST'])
def check_crush():
    if 'user_id' not in session or 'crush_game' not in session:
        return jsonify({'error': 'Игра не начата'}), 400

    game = session['crush_game']

    # Если игра уже завершена
    if game['exploded'] or game['cashed_out']:
        return jsonify({
            'current_multiplier': game['current_multiplier'],
            'explosion_at': game['explosion_at'],
            'exploded': game['exploded'],
            'game_over': True
        })

    # Увеличиваем множитель (0.20x в секунду)
    time_passed = time.time() - game['start_time']
    current_multiplier = round(time_passed * 0.2, 2)

    # Проверяем на взрыв
    exploded = current_multiplier >= game['explosion_at']

    # Обновляем состояние игры
    game['current_multiplier'] = current_multiplier
    game['exploded'] = exploded
    session['crush_game'] = game

    if exploded:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE user_stats SET crush_played = crush_played + 1 WHERE user_id = %s", (game['user_id'],))
                conn.commit()
        finally:
            conn.close()

    return jsonify({
        'current_multiplier': current_multiplier,
        'explosion_at': game['explosion_at'],
        'exploded': exploded,
        'game_over': False
    })


#######################################################################################################
if __name__ == '__main__':
    app.run(debug=True)
