from flask import Flask, request, render_template
import requests
import hmac
import time
import sqlite3
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

# Substitua pelas suas credenciais da Bybit
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')

BYBIT_API_URL = 'https://api-testnet.bybit.com'  # URL da API da Bybit Testnet

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

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    print('Received data:', data)

    # Aqui você pode extrair os detalhes do sinal do TradingView do objeto de dados
    # e usar essas informações para criar uma ordem na Bybit

    symbol = 'USDTDOGE'  # Substitua pelo símbolo que você deseja operar
    side = 'Buy'  # Substitua pelo lado da ordem (Buy ou Sell)
    order_type = 'Market'  # Tipo de ordem
    qty = 1  # Quantidade de ordem
    leverage = 5  # Alavancagem
    take_profit = 2  # Take profit
    stop_loss = 20  # Stop loss

    create_order(symbol, side, order_type, qty, leverage, take_profit, stop_loss)

    return 'OK', 200

def create_order(symbol, side, order_type, qty, leverage, take_profit, stop_loss):
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
        'timestamp': timestamp
    }

    params['sign'] = generate_signature(params)

    response = requests.post(f'{BYBIT_API_URL}/v2/private/order/create', params=params)
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
    return hmac.new(API_SECRET.encode(), signature_payload.encode(), 'sha256').hexdigest()

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
