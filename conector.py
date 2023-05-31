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
FEE = 0.00075
SYMBOL = 'DOGEUSDT'         # Substitua pelo símbolo que vocé deseja operar
QTD = 0.45                  # Defina a porcentagem do saldo em USDT que você deseja usar para a negociação por bot
LEVERAGE = 3                # Quantidade de leverage que vocé quer usar
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
        duration TEXT,
        saldo_init REAL,
        saldo_final REAL,
        profit REAL,
        profit_percentage REAL,
        fee REAL
    )
''')
conn.commit()
conn.close()

@app.route('/order', methods=['POST'])
def order(side=None):
    global open_order_id
    symbol = SYMBOL
    entry_time = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
    balance = get_balance()
    response = requests.get(f'{BYBIT_API_URL}/v2/public/tickers?symbol={symbol}')
    try:
        data = response.json()
    except json.decoder.JSONDecodeError:
        print("Erro ao abrir a ordem")
        send_message_to_telegram(f"Erro ao abrir a ordem: \n{symbol}, \n{direction}\nLeverage: {get_leverage(symbol)}")
        return 'Erro ao abrir a ordem', 400

    if data['ret_code'] != 0:
        print(f"Erro ao abrir a ordem: {data['ret_msg']}")
        send_message_to_telegram(f"Erro ao fechar a ordem: \n{data['ret_msg']} \n{symbol}, \n{direction}\nLeverage: {get_leverage(symbol)}")

        return 'Erro ao fechar a ordem', 400
    current_price = float(data['result'][0]['last_price'])

    if get_leverage(symbol) !=  LEVERAGE:
        set_leverage(symbol, LEVERAGE)
        print(f"Leverage after setting: {get_leverage(symbol)}")

    if side == None:
        side = request.form.get('side')

    if side == 'Buy':
        stop_loss = round(current_price * STOP_LOSS_LONG, 8)
        take_profit = round(current_price * TAKE_PROFIT_LONG, 8)
    else:  # side == 'Sell'
        stop_loss = round(current_price * STOP_LOSS_SHORT, 8)
        take_profit = round(current_price * TAKE_PROFIT_SHORT, 8)

    # Obtenha o saldo atual da sua conta em USDT
    
    percentage = QTD  
    usdt_amount = balance * percentage

    # Obtenha o preço atual de DOGEUSDT
    response = requests.get(f'{BYBIT_API_URL}/v2/public/tickers?symbol={symbol}')
    data = response.json()
    current_price = float(data['result'][0]['last_price'])

    # Calcule a quantidade de DOGE correspondente à quantidade de USDT que você deseja usar
    qty = (usdt_amount / current_price) * LEVERAGE
    print(round(qty, 0))

    order_type = ORDER
    leverage = LEVERAGE
    timestamp = int(time.time() * 1000)

    params = {
        'api_key': API_KEY,
        'symbol': symbol,
        'side': side,
        'order_type': order_type,
        'qty': round(qty, 0),
        'time_in_force': 'GoodTillCancel',
        'buyLeverage': leverage,
        'sellLeverage': leverage,
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
    saldo_init = balance
    fee = usdt_amount * FEE
    conn = sqlite3.connect('trading.db')
    c = conn.cursor()
    c.execute('''
    INSERT INTO trades (symbol, side, order_type, qty, leverage, take_profit, stop_loss, entry_price, entry_time, saldo_init, fee)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (symbol, side, order_type, qty, leverage, take_profit, stop_loss, entry_price, entry_time, saldo_init, fee))
    conn.commit()

    conn.close()
    print('enviando mensagem para o telegram')
    if side == 'Buy':
        direction = 'Entrada Long'
    if side == 'Sell':
        direction = 'Entrada Short'
    send_message_to_telegram(f"Trade aberto \n {symbol}, {direction}  \n Leverage: {get_leverage(symbol)} \n Saldo Total inicial: U$ {balance:,.2f} \n Saldo usado: U$ {usdt_amount:,.2f} \n Valor com leverage usado: U$ {(usdt_amount*3):,.2f} \n Saldo Restante: U$ {get_balance():,.2f} \n Fee abertura: U$ {fee:,.2f}")
    print('mensagem enviada para o telegram')
    return 'OK', 200

@app.route('/close', methods=['POST'])
def close(side=None):
    global open_order_id
    symbol = SYMBOL

    if get_leverage(symbol) !=  LEVERAGE:
        set_leverage(symbol, LEVERAGE)
        print(f"Leverage after setting: {get_leverage(symbol)}")

    exit_time = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
    response = requests.get(f'{BYBIT_API_URL}/v2/public/tickers?symbol={symbol}')

    if side == None:
        side = request.form.get('side')
    
    order_type = ORDER
    qty = get_position_qty(symbol, side)
    leverage = LEVERAGE
    timestamp = int(time.time() * 1000)
    params = {
        'api_key': API_KEY,
        'symbol': symbol,
        'side': side,
        'order_type': order_type,
        'qty': qty,
        'time_in_force': 'GoodTillCancel',
        'buyLeverage': leverage,
        'sellLeverage': leverage,
        'reduce_only': True,
        'close_on_trigger': False,
        'timestamp': timestamp
    }

    params['sign'] = generate_signature(params)

    response = requests.post(f'{BYBIT_API_URL}/private/linear/order/create', params=params)
    data = response.json()

    if side == 'Sell':
        direction = 'Saída Long'
    if side == 'Buy':
        direction = 'Saída Short'

    if data['ret_code'] != 0:
        print(f"Erro ao fechar a ordem: {data['ret_msg']}")
        send_message_to_telegram(f"Erro ao fechar a ordem: \n{data['ret_msg']} \n{symbol}, \n{direction}\nLeverage: {get_leverage(symbol)}")

        return 'Erro ao fechar a ordem', 400

    exit_price = data['result']['price']

    conn = sqlite3.connect('trading.db')
    c = conn.cursor()
    c.execute('SELECT entry_time, entry_price FROM trades WHERE id = (SELECT MAX(id) FROM trades)')
    entry_time, entry_price = c.fetchone()
    duration = str(datetime.strptime(exit_time, '%Y-%m-%d %H:%M:%S') - datetime.strptime(entry_time, '%Y-%m-%d %H:%M:%S'))
    # profit_loss = exit_price - entry_price if side == 'Sell' else entry_price - exit_price
    balance = get_balance()
    percentage = QTD  
    usdt_amount = balance * percentage
    # Calcular o lucro ou perda
    profit_loss = LEVERAGE * (exit_price - entry_price) * usdt_amount if side == 'Sell' else LEVERAGE * (entry_price - exit_price) * usdt_amount
    c.execute('SELECT fee FROM trades WHERE id = (SELECT MAX(id) FROM trades)')
    fee = (FEE * usdt_amount) + c.fetchone()[0]
    profit_loss -= fee
    c.execute('SELECT saldo_init FROM trades WHERE id = (SELECT MAX(id) FROM trades)')
    saldo_init = c.fetchone()[0]
    saldo_final = get_balance()
    profit = saldo_final - saldo_init
    profit_percentage = (profit / saldo_init) * 100
    # Atualizar o banco de dados
    c.execute('''
        UPDATE trades
        SET exit_price = ?, profit_loss = ?, exit_time = ?, duration = ?, saldo_final = ?, profit = ?, profit_percentage = ?
        WHERE id = (SELECT MAX(id) FROM trades)
    ''', (exit_price, profit_loss, exit_time, duration, saldo_final, profit, profit_percentage))
    conn.commit()
    conn.close()

    open_order_id = None
    print('enviando mensagem de fechamento via telegran')
    send_message_to_telegram(f"Trade Encerrado: \n{symbol}, {direction} \nQuant. DOGE {(qty):,.2f} \nLeverage: {get_leverage(symbol)} \nDuração: {duration}, \nGanho: U$ {profit_loss:,.2f} \nPreço de Entrada: {entry_price:,.4f} \nPreço de Saída: {exit_price:,.4f} \nFee Bybit: U$ {fee:,.2f} \nSaldo inicial:{saldo_init:,.2f} \nSaldo final: U$ {get_balance():,.2f} \nLucro: U$ {profit:,.2f} \nLucro: {profit_percentage:,.2f}% \n")

    print("mensagem enviada")
    return 'OK', 200


@app.route('/webhook', methods=['POST'])
def webhook():
    print('Webhook received')
    try:
        data = request.get_json()
        print('Received data:', data)
    except json.JSONDecodeError:
        print('Received invalid JSON')
        return 'Invalid JSON', 400

    sides = data['strategy']['order']['action'].capitalize()
    send_message_to_telegram(f"Sinal Webhook recebido: \n BOT 01\noperação {sides}")
    if sides == 'Longbuy':
        print(f'open trade {sides}')
        order('Buy')

    elif sides == 'Longexit':
        print(f'close trade {sides}')
        close('Sell')

    elif sides == 'Shortsell':
        print(f'open trade {sides}')
        order('Sell')
    
    elif sides == 'Shortexit':
        print(f'close trade {sides}')
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
    trades = [dict(zip(['id', 'symbol', 'side', 'order_type', 'qty', 'leverage', 'take_profit', 'stop_loss', 'entry_price', 'exit_price', 'profit_loss', 'entry_time', 'exit_time', 'duration', 'saldo_init', 'saldo_final', 'profit', 'profit_percentage'], trade)) for trade in trades]

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

def set_leverage(symbol, leverage):
    timestamp = int(time.time() * 1000)

    params = {
        'api_key': API_KEY,
        'symbol': symbol,
        'buy_leverage': int(leverage),  # para posições long
        'sell_leverage': int(leverage),  # para posições short
        'timestamp': timestamp
    }

    params['sign'] = generate_signature(params)

    response = requests.post(f'{BYBIT_API_URL}/private/linear/position/set-leverage', params=params)
    data = response.json()
    if data['ret_code'] != 0:
        print(f"Erro ao definir a alavancagem: {data['ret_msg']}")
        return False
        
    return True
    
def get_leverage(symbol):
    timestamp = int(time.time() * 1000)

    params = {
        'api_key': API_KEY,
        'symbol': symbol,
        'timestamp': timestamp
    }

    params['sign'] = generate_signature(params)

    response = requests.get(f'{BYBIT_API_URL}/private/linear/position/list', params=params)
    data = response.json()

    if data['ret_code'] != 0:
        print(f"Erro ao obter a posição: {data['ret_msg']}")
        return None

    return data['result'][0]['leverage']


def get_balance():
    timestamp = int(time.time() * 1000)

    params = {
        'api_key': API_KEY,
        'timestamp': timestamp
    }

    params['sign'] = generate_signature(params)

    response = requests.get(f'{BYBIT_API_URL}/v2/private/wallet/balance', params=params)
    data = response.json()

    if data['ret_code'] != 0:
        print(f"Erro ao recuperar o saldo: {data['ret_msg']}")
        return None

    return data['result']['USDT']['available_balance']

def get_position_qty(symbol, side):
    timestamp = int(time.time() * 1000)
    opposite_side = 'Sell' if side == 'Buy' else 'Buy'
    params = {
        'api_key': API_KEY,
        'symbol': symbol,
        'timestamp': timestamp
    }

    params['sign'] = generate_signature(params)

    response = requests.get(f'{BYBIT_API_URL}/private/linear/position/list', params=params)
    data = response.json()

    if data['ret_code'] != 0:
        print(f"Erro ao obter a posição: {data['ret_msg']}")
        return None

    for position in data['result']:
        if position['symbol'] == symbol and position['side'] == opposite_side:
            return float(position['size'])
    return 0.0


if __name__ == '__main__':
    app.run(port=5000, debug=True)
