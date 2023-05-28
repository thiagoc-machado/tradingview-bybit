import json
from flask import Flask, Response, request, render_template, send_file, redirect, url_for, send_from_directory, copy_current_request_context
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import requests
import hmac
import time
import sqlite3
from dotenv import load_dotenv
import os
from datetime import datetime
import pandas as pd
from telegram import Bot
from telegram.error import TelegramError

load_dotenv()

app = Flask(__name__)  

bot_token = os.getenv('TELEGRAN_TOKEN')
bot_chat_id = os.getenv('TELEGRAN_ID')

USERNAME = os.getenv('USERNAME')
PASSWORD = os.getenv('PASSWORD')
KEY = os.getenv('KEY')
NAME= os.getenv('NAME')
# Substitua pelas suas credenciais da Bybit
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')

BYBIT_API_URL = 'https://api-testnet.bybit.com'  # URL da API da Bybit Testnet

SYMBOL = 'DOGEUSDT'         # Substitua pelo símbolo que vocé deseja operar
QTD = 1000                   # Valor a operar
LEVERAGE = 5                # Quantidade de leverage que vocé quer usar
TAKE_PROFIT_LONG = 1.005    # 0.5% acima do preço atual do mercado
STOP_LOSS_LONG = 0.8        # 20% abaixo do preço atual do mercado
TAKE_PROFIT_SHORT = 0.995   # 0.5% abaixo do preço atual do mercado
STOP_LOSS_SHORT = 1.2       # 20% acima do preço atual do mercado
ORDER = 'Market'

open_order_id = None
app.secret_key = KEY 

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
class User(UserMixin):
    pass

@login_manager.user_loader
def user_loader(username):
    if username != NAME:
        return

    user = User()
    user.id = username
    return user


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET': 
        return render_template('login.html')
 
    username = request.form['username'] 
    password = request.form['password']
    if username == NAME and password == PASSWORD:
        user = User()
        user.id = username
        login_user(user)
        print(f'Logged in as {username}')
        return redirect(url_for('trades'))  # Redireciona para a rota protegida

    return 'Invalid username or password'


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return 'Logged out'

@app.route('/protected')
@login_required
def protected():
    return 'Logged in as: ' + current_user.id


# Cria o banco de dados SQLite e a tabela de operações
conn = sqlite3.connect('trading.db')
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY,
        symbol TEXT,
        side TEXT,
        order_type TEXT,
        qty REAL,
        leverage INTEGER,
        take_profit REAL,
        stop_loss REAL,
        entry_price REAL,
        exit_price REAL,
        profit_loss REAL,
        entry_time TEXT,
        exit_time TEXT,
        duration TEXT
    )
''')
conn.commit()
conn.close()

@app.route('/order', methods=['POST'])
def order(side=None):
    global open_order_id
    symbol = SYMBOL
    entry_time = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
    print('def order')
    response = requests.get(f'{BYBIT_API_URL}/v2/public/tickers?symbol={symbol}')
    print(response.text)
    print(response.status_code)
    data = response.json()
    current_price = float(data['result'][0]['last_price'])

    print(f"side antes do if {side}")
    if side == None:
        side = request.form.get('side')
    print(f"side depois do if {side}")

    if side == 'Buy':
        stop_loss = round(current_price * STOP_LOSS_LONG, 8)
        take_profit = round(current_price * TAKE_PROFIT_LONG, 8)
    else:  # side == 'Sell'
        stop_loss = round(current_price * STOP_LOSS_SHORT, 8)
        take_profit = round(current_price * TAKE_PROFIT_SHORT, 8)

    order_type = ORDER
    qty = QTD
    leverage = LEVERAGE
    timestamp = int(time.time() * 1000)

    params = {
        'api_key': API_KEY,
        'symbol': symbol,
        'side': side,
        'order_type': order_type,
        'qty': qty,
        'time_in_force': 'GoodTillCancel',
        'leverage': leverage,
        'take_profit': take_profit,
        'stop_loss': stop_loss,
        'reduce_only': False,
        'close_on_trigger': False,
        'timestamp': timestamp
    }

    params['sign'] = generate_signature(params)

    response = requests.post(f'{BYBIT_API_URL}/private/linear/order/create', params=params)
    data = response.json()
    open_order_id = data['result']['order_id']
    entry_price = data['result']['price']

    conn = sqlite3.connect('trading.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO trades (symbol, side, order_type, qty, leverage, take_profit, stop_loss, entry_price, entry_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (symbol, side, order_type, qty, leverage, take_profit, stop_loss, entry_price, entry_time))
    conn.commit()
    conn.close()
    print('enviando mensagem para o telegram')
    if side == 'Buy':
        direction = 'Entrada Long'
    if side == 'Sell':
        direction = 'Entrada Short'
    send_message_to_telegram(f"Trade aberto \n {symbol}, {direction} \n U$ {qty},00, Leverage: {leverage}")
    print('mensagem enviada para o telegram')
    return 'OK', 200

@app.route('/close', methods=['POST'])
def close(side=None):
    global open_order_id
    symbol = SYMBOL
    exit_time = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
    response = requests.get(f'{BYBIT_API_URL}/v2/public/tickers?symbol={symbol}')
    data = response.json()
    current_price = float(data['result'][0]['last_price'])

    print(f"side antes do if {side}")
    if side == None:
        side = request.form.get('side')
    
    order_type = ORDER
    qty = QTD
    leverage = LEVERAGE
    timestamp = int(time.time() * 1000)
    if side == 'Buy':
        params = {
            'api_key': API_KEY,
            'symbol': symbol,
            'side': side,
            'order_type': order_type,
            'qty': qty,
            'time_in_force': 'GoodTillCancel',
            'buyLeverage': leverage,
            'reduce_only': True,
            'close_on_trigger': False,
            'timestamp': timestamp
        }
    if side == 'Sell':
        params = {
            'api_key': API_KEY,
            'symbol': symbol,
            'side': side,
            'order_type': order_type,
            'qty': qty,
            'time_in_force': 'GoodTillCancel',
            'sellLeverage': leverage,
            'reduce_only': True,
            'close_on_trigger': False,
            'timestamp': timestamp
        }

    params['sign'] = generate_signature(params)

    response = requests.post(f'{BYBIT_API_URL}/private/linear/order/create', params=params)
    exit_price = response.json()['result']['price']

    conn = sqlite3.connect('trading.db')
    c = conn.cursor()
    c.execute('SELECT entry_time, entry_price FROM trades WHERE id = (SELECT MAX(id) FROM trades)')
    entry_time, entry_price = c.fetchone()
    duration = str(datetime.strptime(exit_time, '%Y-%m-%d %H:%M:%S') - datetime.strptime(entry_time, '%Y-%m-%d %H:%M:%S'))
    profit_loss = exit_price - entry_price if side == 'Sell' else entry_price - exit_price

    c.execute('''
        UPDATE trades
        SET exit_price = ?, profit_loss = ?, exit_time = ?, duration = ?
        WHERE id = (SELECT MAX(id) FROM trades)
    ''', (exit_price, profit_loss, exit_time, duration))
    conn.commit()
    conn.close()

    if side == 'Sell':
        direction = 'Saída Long'
    if side == 'Buy':
        direction = 'Saída Short'

    open_order_id = None
    print('enviando mensagem de fechamento via telegran')
    send_message_to_telegram(f"Trade Encerrado: \n{symbol}, {direction} \n U$ {qty:.2f}, Leverage: {leverage} \n Duração: {duration}, Ganho: U$ {profit_loss:.2f}")

    print("mensagem enviada")
    return 'OK', 200



@app.route('/webhook', methods=['POST'])
def webhook():
    print('*'*50)
    print('Webhook received')
    try:
        data = request.get_json()
        print('Received data:', data)
    except json.JSONDecodeError:
        print('Received invalid JSON')
        return 'Invalid JSON', 400

    side = data['strategy']['order']['action'].capitalize()

    # if side in ['Buy', 'Sell']:
    #     print(f'open trade {side}')
    #     order(side)

    # elif side == 'Exit':
    #     print(f'close trade {side}')
    #     close(side)
    print(side)

    if side == 'Longbuy':
        print(f'open trade {side}')
        order('Buy')

    elif side == 'Longexit':
        print(f'close trade {side}')
        close('Sell')

    elif side == 'Shortsell':
        print(f'open trade {side}')
        order('Sell')
    
    elif side == 'Shortexit':
        print(f'close trade {side}')
        close('Buy')

    return 'OK', 200


def generate_signature(params):
    sorted_params = sorted(params.items())
    signature_payload = '&'.join(f'{k}={v}' for k, v in sorted_params)
    return hmac.new(API_SECRET.encode(), signature_payload.encode(), 'sha256').hexdigest()


@app.route('/trades', methods=['GET'])
@login_required
def trades():
    conn = sqlite3.connect('trading.db')
    c = conn.cursor()
    c.execute('SELECT * FROM trades')
    trades = c.fetchall()
    conn.close()

    # Convert each trade to a dictionary
    trades = [dict(zip(['id', 'symbol', 'side', 'order_type', 'qty', 'leverage', 'take_profit', 'stop_loss', 'entry_price', 'exit_price', 'profit_loss', 'entry_time', 'exit_time', 'duration'], trade)) for trade in trades]

    return render_template('trades.html', trades=trades)


@app.route('/export', methods=['GET'])
@login_required
def export():
    print('exportando em excel')
    conn = sqlite3.connect('trading.db')
    df = pd.read_sql_query("SELECT * from trades", conn)
    filename = 'trades.xlsx'
    df.to_excel(filename, index=False)
    conn.close()
    with open(filename, 'rb') as f:
        content = f.read()
    return Response(
        content,
        mimetype="application/vnd.ms-excel",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )



@app.route('/backup', methods=['GET'])
@login_required
def backup():
    print('Fazendo backup do banco de dados')
    directory = os.getcwd()
    filename = 'trading.db'
    with open(filename, 'rb') as f:
        content = f.read()
    return Response(
        content,
        mimetype="application/octet-stream",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )


def send_message_to_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        params = {
            "chat_id": bot_chat_id,
            "text": text
        }
        response = requests.get(url, params=params)
        if response.status_code != 200:
            print(f"Erro ao enviar mensagem para o Telegram: {response.text}")
    except Exception as e:
        print(f"Erro ao enviar mensagem para o Telegram: {e}")



if __name__ == '__main__':
    app.run(port=5000, debug=True)
