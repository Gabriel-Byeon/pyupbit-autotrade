import time
import pyupbit
import datetime
import pandas as pd

access = "OWSEtnPWwdBNVnvMzHWwvkDhRZZN6m8pzGn49azb"
secret = "TsXy0mZ2tgbsieVmLx5n01LPxhw0IHQxoDaW01rP"

def get_bollinger_band(ticker, k=20, n=2):
    """볼린저 밴드 계산"""
    df = pyupbit.get_ohlcv(ticker, interval="minute5", count=k)
    df['MA20'] = df['close'].rolling(window=k).mean()
    df['stddev'] = df['close'].rolling(window=k).std()
    df['upper'] = df['MA20'] + (df['stddev'] * n)
    df['lower'] = df['MA20'] - (df['stddev'] * n)
    return df.iloc[-1]['upper'], df.iloc[-1]['lower']

def get_start_time(ticker):
    """시작 시간 조회"""
    df = pyupbit.get_ohlcv(ticker, interval="day", count=1)
    start_time = df.index[0]
    return start_time

def get_balance(ticker):
    """잔고 조회"""
    balances = upbit.get_balances()
    print(balances)  # 디버깅을 위한 출력
    for b in balances:
        if b['currency'] == ticker:
            if 'balance' in b and b['balance'] is not None:
                return float(b['balance'])
            else:
                return 0
    return 0

def get_current_price(ticker):
    """현재가 조회"""
    return pyupbit.get_orderbook(ticker=ticker)["orderbook_units"][0]["ask_price"]

# 로그인
upbit = pyupbit.Upbit(access, secret)
print("autotrade start")

# 자동매매 시작
while True:
    try:
        now = datetime.datetime.now()
        start_time = get_start_time("KRW-BTC")
        end_time = start_time + datetime.timedelta(days=1)

        if start_time < now < end_time - datetime.timedelta(seconds=10):
            upper_band, lower_band = get_bollinger_band("KRW-BTC")
            current_price = get_current_price("KRW-BTC")
            if current_price > upper_band:
                krw = get_balance("KRW")
                if krw > 5000:
                    upbit.buy_market_order("KRW-BTC", krw*0.9995)
            elif current_price < lower_band:
                btc = get_balance("BTC")
                if btc > 0.00008:
                    upbit.sell_market_order("KRW-BTC", btc*0.9995)
        else:
            btc = get_balance("BTC")
            if btc > 0.00008:
                upbit.sell_market_order("KRW-BTC", btc*0.9995)
        time.sleep(1)
    except Exception as e:
        print(e)
        time.sleep(1)
