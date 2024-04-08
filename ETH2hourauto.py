from binance.client import Client
from binance.enums import *
import pandas as pd
import numpy as np

API_KEY = 'your_api_key'
API_SECRET = 'your_api_secret'
client = Client(API_KEY, API_SECRET)
futures_client = Client(API_KEY, API_SECRET, testnet=True)  # 테스트넷 사용

def set_leverage(symbol, leverage=2):
    response = futures_client.futures_change_leverage(symbol=symbol, leverage=leverage)
    print("Leverage set to:", response)
    return response

def get_balance(asset='USDT'):
    balance = futures_client.futures_account_balance()
    usdt_balance = next((item for item in balance if item['asset'] == asset), None)
    return float(usdt_balance['balance']) if usdt_balance else 0

def get_historical_data(symbol, interval, start_str, end_str=None):
    columns = ['Open Time', 'Open', 'High', 'Low', 'Close', 'Volume',
               'Close Time', 'Quote Asset Volume', 'Number of Trades',
               'Taker Buy Base Asset Volume', 'Taker Buy Quote Asset Volume', 'Ignore']
    klines = futures_client.futures_klines(symbol=symbol, interval=interval, start_str=start_str, end_str=end_str)
    df = pd.DataFrame(klines, columns=columns)
    df['Open Time'] = pd.to_datetime(df['Open Time'], unit='ms')
    df.set_index('Open Time', inplace=True)
    df = df.astype(float)
    return df

def calculate_bollinger_bands(df, window=20, no_of_std=2):
    df['MA'] = df['Close'].rolling(window).mean()
    df['STD'] = df['Close'].rolling(window).std()
    df['Upper'] = df['MA'] + (df['STD'] * no_of_std)
    df['Lower'] = df['MA'] - (df['STD'] * no_of_std)

def calculate_order_quantity(symbol, balance, leverage):
    last_price = float(futures_client.futures_symbol_ticker(symbol=symbol)['price'])
    quantity = (balance * leverage) / last_price
    return np.floor(quantity * 10000) / 10000  # Adjust quantity to 4 decimal places

def execute_futures_trade(signal, symbol, quantity):
    if signal == 'buy':
        order = futures_client.futures_create_order(symbol=symbol, side=SIDE_BUY, type=ORDER_TYPE_MARKET, quantity=quantity)
    elif signal == 'sell':
        order = futures_client.futures_create_order(symbol=symbol, side=SIDE_SELL, type=ORDER_TYPE_MARKET, quantity=quantity)
    return order

def close_position(signal, symbol, quantity):
    return execute_futures_trade(signal, symbol, quantity)

symbol = 'ETHUSDT'
interval = Client.KLINE_INTERVAL_2HOUR
start_str = '2024-04-09'
end_str = '2050-09-16'

# Set leverage
set_leverage(symbol, leverage=2)

# Get available balance
available_balance = get_balance()

df = get_historical_data(symbol, interval, start_str, end_str)
calculate_bollinger_bands(df)

# Determine entry and exit signals
df['Momentum'] = df['Close'].diff()
df['Long_Entry'] = df['Momentum'] > 0
df['Short_Entry'] = df['Momentum'] < 0

position_opened = None

for index, row in df.iterrows():
    quantity = calculate_order_quantity(symbol, available_balance, leverage=2)
    
    if row['Long_Entry'] and position_opened != 'long':
        if position_opened == 'short':
            print(f"Closing Short Position at {index}, Price: {row['Close']}")
            close_position('buy', symbol, quantity)
        print(f"Opening Long Position at {index}, Price: {row['Close']}")
        execute_futures_trade('buy', symbol, quantity)
        position_opened = 'long'
        
    elif row['Short_Entry'] and position_opened != 'short':
        if position_opened == 'long':
            print(f"Closing Long Position at {index}, Price: {row['Close']}")
            close_position('sell', symbol, quantity)
        print(f"Opening Short Position at {index}, Price: {row['Close']}")
        execute_futures_trade('sell', symbol, quantity)
        position_opened = 'short'

    # Add logic to close positions based on your strategy's exit criteria
