from binance.client import Client
from binance.enums import *
import pandas as pd
import numpy as np

API_KEY = 'your_api_key_here'
API_SECRET = 'your_api_secret_here'
client = Client(API_KEY, API_SECRET)
futures_client = Client(API_KEY, API_SECRET) 

def set_leverage(symbol, leverage=2):
    response = futures_client.futures_change_leverage(symbol=symbol, leverage=leverage)
    print("Leverage set to:", response)
    return response

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

def calculate_order_quantity(symbol, fixed_balance, leverage, last_price, step_size):
    quantity = (fixed_balance * leverage) / last_price
    precision = len(step_size.rstrip('0')) - 2
    quantity = round(quantity, precision)
    return quantity

def execute_futures_trade(signal, symbol, quantity):
    if quantity <= 0:
        print("Invalid quantity, cannot place order.")
        return
    if signal == 'buy':
        order = futures_client.futures_create_order(symbol=symbol, side=SIDE_BUY, type=ORDER_TYPE_MARKET, quantity=quantity)
    elif signal == 'sell':
        order = futures_client.futures_create_order(symbol=symbol, side=SIDE_SELL, type=ORDER_TYPE_MARKET, quantity=quantity)
    print("Order executed:", order)
    return order

symbol = 'ETHUSDT'
interval = Client.KLINE_INTERVAL_2HOUR
start_str = '2024-04-09'
end_str = '2050-09-16'
step_size = '0.01'  # This should be dynamically obtained for accuracy

set_leverage(symbol, leverage=2)
fixed_balance = 100  # Fixed amount of USDT to use for trading
last_price = float(futures_client.futures_symbol_ticker(symbol=symbol)['price'])

df = get_historical_data(symbol, interval, start_str, end_str)
calculate_bollinger_bands(df)

df['Momentum'] = df['Close'].diff()
df['Long_Entry'] = (df['Momentum'] > 0) & (df['Close'] > df['Upper'])
df['Short_Entry'] = (df['Momentum'] < 0) & (df['Close'] < df['Lower'])
df['Exit'] = (df['Momentum'] < 0) & (df['Long_Entry']) | (df['Momentum'] > 0) & (df['Short_Entry'])

position_opened = None

for index, row in df.iterrows():
    quantity = calculate_order_quantity(symbol, fixed_balance, 2, last_price, step_size)
    print(f"Calculated quantity for {symbol}: {quantity}")

    if row['Long_Entry'] and position_opened != 'long':
        if position_opened == 'short':
            print(f"Closing Short Position at {index}, Price: {row['Close']}")
            execute_futures_trade('sell', symbol, quantity)
        print(f"Opening Long Position at {index}, Price: {row['Close']}")
        execute_futures_trade('buy', symbol, quantity)
        position_opened = 'long'
        
    elif row['Short_Entry'] and position_opened != 'short':
        if position_opened == 'long':
            print(f"Closing Long Position at {index}, Price: {row['Close']}")
            execute_futures_trade('buy', symbol, quantity)
        print(f"Opening Short Position at {index}, Price: {row['Close']}")
        execute_futures_trade('sell', symbol, quantity)
        position_opened = 'short'
    
    elif row['Exit']:
        if position_opened == 'long':
            print(f"Closing Long Position at {index}, Price: {row['Close']}")
            execute_futures_trade('sell', symbol, quantity)
            position_opened = None
        elif position_opened == 'short':
            print(f"Closing Short Position at {index}, Price: {row['Close']}")
            execute_futures_trade('buy', symbol, quantity)
            position_opened = None
