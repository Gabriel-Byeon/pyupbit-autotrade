import requests
import pandas as pd
import time
import pyupbit

# Upbit API key 설정
access = "your-access-key"
secret = "your-secret-key"
upbit = pyupbit.Upbit(access, secret)

# Discord Webhook URL
discord_webhook_url = "your-discord-webhook-url"

# 수수료 비율 (0.05%)
fee_rate = 0.0005

def send_discord_message(message):
    data = {"content": message}
    response = requests.post(discord_webhook_url, json=data)
    if response.status_code == 204:
        print("Message sent to Discord successfully")
    else:
        print(f"Failed to send message to Discord: {response.status_code}")

def rsi(ohlc: pd.DataFrame, period: int = 14):
    delta = ohlc["close"].diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    _gain = up.ewm(com=(period - 1), min_periods=period).mean()
    _loss = down.abs().ewm(com=(period - 1), min_periods=period).mean()
    RS = _gain / _loss
    return pd.Series(100 - (100 / (1 + RS)), name="RSI")

def search_onetime(settingRSI):
    tickers = pyupbit.get_tickers(fiat="KRW")
    for symbol in tickers:
        url = "https://api.upbit.com/v1/candles/minutes/10"
        querystring = {"market": symbol, "count": "500"}
        response = requests.request("GET", url, params=querystring)
        data = response.json()
        df = pd.DataFrame(data).iloc[::-1].reset_index()
        df['close'] = df["trade_price"]
        rsi_value = rsi(df, 14).iloc[-1]
        if rsi_value < settingRSI:
            message = f"!!과매도 현상 발견!! {symbol}"
            send_discord_message(message)
            return symbol
        time.sleep(1)

def buyRSI(symbol, rsi_threshold, amount):
    while True:
        try:
            current_rsi = rsi(pyupbit.get_ohlcv(symbol, interval="minute10"), 14).iloc[-1]
            if current_rsi < rsi_threshold:
                krw_balance = upbit.get_balance("KRW")
                if amount > krw_balance:
                    amount = krw_balance * 0.9995
                order = upbit.buy_market_order(symbol, amount)
                if order is None:
                    send_discord_message(f"Error: 매수 주문 실패 - {symbol}")
                    return None, None
                message = f"구매 완료: {symbol} - 금액: {amount} KRW"
                send_discord_message(message)
                time.sleep(1)  # 주문 처리를 위해 잠시 대기
                # 매수한 수량 계산
                avg_price = amount / upbit.get_avg_buy_price(symbol)
                volume = amount / avg_price
                return avg_price, volume
            time.sleep(1)
        except Exception as e:
            send_discord_message(f"Error in buyRSI: {e}")
            time.sleep(1)

def sellRSI(symbol, rsi_threshold, avg_price, volume, stop_loss_pct):
    while True:
        try:
            current_rsi = rsi(pyupbit.get_ohlcv(symbol, interval="minute10"), 14).iloc[-1]
            current_price = pyupbit.get_current_price(symbol)
            if current_rsi > rsi_threshold or current_price <= avg_price * (1 - stop_loss_pct):
                balance = upbit.get_balance(symbol)
                if volume > balance:
                    volume = balance
                sell_order = upbit.sell_market_order(symbol, volume)
                if sell_order is None:
                    send_discord_message(f"Error: 매도 주문 실패 - {symbol}")
                    return
                time.sleep(1)  # 주문 처리를 위해 잠시 대기
                sell_price = current_price
                buy_fee = avg_price * volume * fee_rate
                sell_fee = sell_price * volume * fee_rate
                profit_loss = (sell_price * volume - sell_fee) - (avg_price * volume + buy_fee)
                message = f"판매 완료: {symbol} - 수량: {volume}\n손익: {profit_loss} KRW"
                send_discord_message(message)
                break
            time.sleep(1)
        except Exception as e:
            send_discord_message(f"Error in sellRSI: {e}")
            time.sleep(1)
    krw_balance = upbit.get_balance("KRW")
    send_discord_message(f"현재 현금 잔액: {krw_balance} KRW")

while True:
    try:
        symbol_to_trade = search_onetime(25)
        if symbol_to_trade:
            avg_price, volume = buyRSI(symbol_to_trade, 30, 100000)  # 여기서 100000은 거래할 금액 (KRW)입니다.
            if avg_price is not None and volume is not None:
                sellRSI(symbol_to_trade, 70, avg_price, volume, 0.10)  # 손절 기준은 10% 손실로 설정
    except Exception as e:
        send_discord_message(f"Error in main loop: {e}")
        time.sleep(1)
