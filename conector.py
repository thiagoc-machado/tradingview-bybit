from flask import Flask, request, render_template
import requests
import hmac
import time
import sqlite3
from dotenv import load_dotenv
import os
import hashlib

load_dotenv()

app = Flask(__name__)

# Substitua pelas suas credenciais da Bybit
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')

BYBIT_API_URL = 'https://api-testnet.bybit.com'  # URL da API da Bybit Testnet
open_order_id = None

SYMBOL = 'DOGEUSDT'  # Substitua pelo símbolo que você deseja operar
ORDER_TIPE = 'Market'  # Tipo de ordem
QTD = 1  # Quantidade de ordem
LEVERAGE = 5  # Alavancagem
TAKE_PROFIT = 1.02  # Take profit
STOP_LOSS = 0.8  # Stop loss
REDUCE_ONLY =  False,  # Adiciona o parâmetro reduce_only
CLOSE_ON_TRIGGER = False,  # Adiciona o parâmetro close_on_trigger

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
        profit_loss REAL
    )
''')
conn.commit()
conn.close()

@app.route('/order', methods=['POST'])
def order():
    global open_order_id
    side = request.form.get('side')
    print(f'Abrindo ordem {side} - {QTD} - {SYMBOL}')
    
    # Recupera o preço atual do mercado
    response = requests.get(f'{BYBIT_API_URL}/v2/public/tickers?symbol={SYMBOL}')
    data = response.json()
    current_price = float(data['result'][0]['last_price'])

    # Calcula o stop loss e o take profit com base no preço atual do mercado
    stop_loss = current_price * STOP_LOSS  # 20% abaixo do preço atual do mercado
    take_profit = current_price * TAKE_PROFIT  # 2% acima do preço atual do mercado
    timestamp = int(time.time() * 1000)

    params = {
        'api_key': API_KEY,
        'symbol': SYMBOL,
        'side': side,
        'order_type': ORDER_TIPE,
        'qty': QTD,
        'time_in_force': 'GoodTillCancel',
        'leverage': LEVERAGE,
        'take_profit': take_profit,
        'stop_loss': stop_loss,
        'reduce_only': REDUCE_ONLY,  # Adiciona o parâmetro reduce_only
        'close_on_trigger': CLOSE_ON_TRIGGER,  # Adiciona o parâmetro close_on_trigger
        'timestamp': timestamp
    }

    params['sign'] = generate_signature(params)

    response = requests.post(f'{BYBIT_API_URL}/private/linear/order/create', params=params)
    data = response.json()
    print('Response:', data)
    # Armazena o order_id da ordem aberta
    # open_order_id = data['result']['order_id']
    # Armazena as informações da operação no banco de dados SQLite
    conn = sqlite3.connect('trading.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO trades (symbol, side, order_type, qty, leverage, take_profit, stop_loss)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (SYMBOL, side, ORDER_TIPE, QTD, LEVERAGE, take_profit, stop_loss))
    conn.commit()
    conn.close()

    return 'OK', 200

@app.route('/close', methods=['POST'])

def close():
    global open_order_id
    if open_order_id is None:
        return 'No open order', 400

    side = request.form.get('side')
    print(f'Fechando ordem {side} - {QTD} - {SYMBOL}')

    # Recupera o preço atual do mercado
    response = requests.get(f'{BYBIT_API_URL}/v2/public/tickers?symbol={SYMBOL}')
    data = response.json()
    current_price = float(data['result'][0]['last_price'])

    # Calcula o stop loss e o take profit com base no preço atual do mercado
    stop_loss = current_price * STOP_LOSS # 20% abaixo do preço atual do mercado
    take_profit = current_price * TAKE_PROFIT  # 2% acima do preço atual do mercado
    timestamp = int(time.time() * 1000)

    params = {
        'api_key': API_KEY,
        'symbol': SYMBOL,
        'side': side,
        # 'order_type': ORDER_TIPE,
        # 'qty': QTD,
        # 'time_in_force': 'GoodTillCancel',
        # 'leverage': LEVERAGE,
        # 'take_profit': take_profit,
        # 'stop_loss': stop_loss,
        'reduce_only': True,  # Adiciona o parâmetro reduce_only
        # 'close_on_trigger': CLOSE_ON_TRIGGER,  # Adiciona o parâmetro close_on_trigger
        # 'order_id': open_order_id,
        'timestamp': timestamp
    }

    params['sign'] = generate_signature(params)

    response = requests.post(f'{BYBIT_API_URL}/private/linear/order/create', params=params)
    print('Response:', response.json())

    # Armazena as informações da operação no banco de dados SQLite
    conn = sqlite3.connect('trading.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO trades (symbol, side, order_type, qty, leverage, take_profit, stop_loss)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (SYMBOL, side, ORDER_TIPE, QTD, LEVERAGE, take_profit, stop_loss))
    conn.commit()
    conn.close()
    # Limpa o order_id da ordem aberta
    open_order_id = None
    return 'OK', 200

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    print('Received data:', data)

    side = 'Buy'  # Substitua pelo lado da ordem (Buy ou Sell)
    take_profit = 2  # Take profit
    stop_loss = ''  # Stop loss

    create_order(SYMBOL, side, ORDER_TIPE, QTD, LEVERAGE, take_profit, stop_loss)

    return 'OK', 200

def create_order(symbol, side, order_type, qty, leverage, take_profit, stop_loss):
    # Recupera o preço atual do mercado
    response = requests.get(f'{BYBIT_API_URL}/v2/public/tickers?symbol={symbol}')
    data = response.json()
    current_price = float(data['result'][0]['last_price'])

    # Calcula o stop loss e o take profit com base no preço atual do mercado
    stop_loss = current_price * STOP_LOSS  # 20% abaixo do preço atual do mercado
    take_profit = current_price * TAKE_PROFIT  # 2% acima do preço atual do mercado
    timestamp = int(time.time() * 1000)

    params = {
        'api_key': API_KEY,
        'side': side,
        'symbol': symbol,
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
    print('Response:', response.json())


    # Armazena as informações da operação no banco de dados SQLite
    conn = sqlite3.connect('trading.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO trades (symbol, side, order_type, qty, leverage, take_profit, stop_loss)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (symbol, side, order_type, qty, leverage, take_profit, stop_loss))
    conn.commit()
    conn.close()

def generate_signature(params):
    sorted_params = sorted(params.items())
    signature_payload = '&'.join(f'{k}={v}' for k, v in sorted_params)
    return hmac.new(bytes(API_SECRET, 'latin-1'), msg=bytes(signature_payload, 'latin-1'), digestmod=hashlib.sha256).hexdigest()


@app.route('/trades', methods=['GET'])
def trades():
    conn = sqlite3.connect('trading.db')
    c = conn.cursor()
    c.execute('SELECT * FROM trades')
    trades = c.fetchall()
    conn.close()

    return render_template('trades.html', trades=trades)

if __name__ == '__main__':
    app.run(port=5000)
