import requests
import pandas as pd
import time
import pyupbit

# Upbit API key 설정 - 봇 1
access_bot1 = "your-access-key-for-bot1"
secret_bot1 = "your-secret-key-for-bot1"
upbit_bot1 = pyupbit.Upbit(access_bot1, secret_bot1)

# Discord Webhook URL - 봇 1
discord_webhook_url_bot1 = "your-discord-webhook-url-for-bot1"

# 현재 거래 중인 코인 기록
current_trading_symbol_bot1 = None

def send_discord_message_bot1(message):
    data = {"content": message}
    response = requests.post(discord_webhook_url_bot1, json=data)
    if response.status_code == 204:
        print("봇 1 - 디스코드로 메시지를 성공적으로 보냈습니다")
    else:
        print(f"봇 1 - 디스코드로 메시지 전송 실패: {response.status_code}")

def rsi_bot1(ohlc: pd.DataFrame, period: int = 14):
    delta = ohlc["close"].diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    _gain = up.ewm(com=(period - 1), min_periods=period).mean()
    _loss = down.abs().ewm(com=(period - 1), min_periods=period).mean()
    RS = _gain / _loss
    return pd.Series(100 - (100 / (1 + RS)), name="RSI")

def search_onetime_bot1(settingRSI):
    send_discord_message_bot1("봇 1 - 과매도 현상을 찾기 위한 검색을 시작합니다.")

    tickers = pyupbit.get_tickers(fiat="KRW")
    global current_trading_symbol_bot1
    for symbol in tickers:
        # 이미 보유한 자산인지 확인
        if float(upbit_bot1.get_balance(symbol)) > 0 or symbol == current_trading_symbol_bot1:
            continue
        
        url = "https://api.upbit.com/v1/candles/minutes/10"
        querystring = {"market": symbol, "count": "500"}
        response = requests.request("GET", url, params=querystring)
        data = response.json()
        df = pd.DataFrame(data).iloc[::-1].reset_index()
        df['close'] = df["trade_price"]
        rsi_value = rsi_bot1(df, 14).iloc[-1]
        if rsi_value < settingRSI:
            message = f"봇 1 - !!과매도 현상 발견!! {symbol}"
            send_discord_message_bot1(message)
            return symbol
        time.sleep(1)
    return None

def buyRSI_bot1(symbol, rsi_threshold, amount):
    send_discord_message_bot1(f"봇 1 - {symbol} 매수를 시도합니다.")
    
    while True:
        try:
            current_rsi = rsi_bot1(pyupbit.get_ohlcv(symbol, interval="minute10"), 14).iloc[-1]
            if current_rsi < rsi_threshold:
                krw_balance = upbit_bot1.get_balance("KRW")
                if amount > krw_balance:
                    amount = krw_balance * 0.9995
                order = upbit_bot1.buy_market_order(symbol, amount)
                if order is None:
                    send_discord_message_bot1(f"봇 1 - Error: 매수 주문 실패 - {symbol}")
                    return None, None
                message = f"봇 1 - 구매 완료: {symbol} - 금액: {amount} KRW"
                send_discord_message_bot1(message)
                time.sleep(1)  # 주문 처리를 위해 잠시 대기
                volume = upbit_bot1.get_balance(symbol)  # 매수한 수량
                avg_price = float(amount) / float(volume)
                return avg_price, volume
            time.sleep(1)
        except Exception as e:
            send_discord_message_bot1(f"봇 1 - Error in buyRSI: {e}")
            time.sleep(1)

def sellRSI_bot1(symbol, rsi_threshold, avg_price, volume, stop_loss_pct):
    send_discord_message_bot1(f"봇 1 - {symbol} 매도를 시도합니다.")

    while True:
        try:
            current_rsi = rsi_bot1(pyupbit.get_ohlcv(symbol, interval="minute10"), 14).iloc[-1]
            current_price = pyupbit.get_current_price(symbol)
            if current_rsi > rsi_threshold or current_price <= avg_price * (1 - stop_loss_pct):
                balance = upbit_bot1.get_balance(symbol)
                if volume > balance:
                    volume = balance
                sell_order = upbit_bot1.sell_market_order(symbol, volume)
                if sell_order is None:
                    send_discord_message_bot1(f"봇 1 - Error: 매도 주문 실패 - {symbol}")
                    return
                time.sleep(1)  # 주문 처리를 위해 잠시 대기
                sell_price = current_price
                profit_loss = (sell_price - avg_price) * volume
                message = f"봇 1 - 판매 완료: {symbol} - 수량: {volume}\n봇 1 - 손익: {profit_loss} KRW"
                send_discord_message_bot1(message)
                break
            time.sleep(1)
        except Exception as e:
            send_discord_message_bot1(f"봇 1 - Error in sellRSI: {e}")
            time.sleep(1)
    krw_balance = upbit_bot1.get_balance("KRW")
    send_discord_message_bot1(f"봇 1 - 현재 현금 잔액: {krw_balance} KRW")

send_discord_message_bot1("봇 1 - 봇이 시작되었습니다.")

while True:
    try:
        symbol_to_trade = search_onetime_bot1(25)
        if symbol_to_trade:
            avg_price, volume = buyRSI_bot1(symbol_to_trade, 30, 100000)  # 여기서 100000은 거래할 금액 (KRW)입니다.
            if avg_price is not None and volume is not None:
                sellRSI_bot1(symbol_to_trade, 70, avg_price, volume, 0.10)  # 손절 기준은 10% 손실로 설정
        else:
            send_discord_message_bot1("봇 1 - 거래 가능한 심볼을 찾지 못했습니다. 다시 시도합니다.")
            time.sleep(60)  # 60초 대기 후 다시 시도
    except Exception as e:
        send_discord_message_bot1(f"봇 1 - Error in main loop: {e}")
        time.sleep(1)
