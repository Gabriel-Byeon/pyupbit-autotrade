import ccxt
import pandas as pd
import time
import requests

# Binance Futures API key 설정
api_key = "your-api-key"
secret_key = "your-secret-key"
exchange = ccxt.binance({
    'apiKey': api_key,
    'secret': secret_key,
    'options': {
        'defaultType': 'future',  # 선물 계정을 사용하도록 설정
    }
})

# Discord Webhook URL
discord_webhook_url = "your-discord-webhook-url"

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

def set_leverage(symbol, leverage):
    try:
        exchange.fapiPrivate_post_leverage({
            'symbol': symbol.replace('/', ''),
            'leverage': leverage
        })
        send_discord_message(f"레버리지 설정: {symbol} - {leverage}배")
    except Exception as e:
        send_discord_message(f"Error setting leverage for {symbol}: {e}")

def search_onetime(settingRSI):
    markets = exchange.load_markets()
    usdt_symbols = [symbol for symbol in markets if '/USDT' in symbol and markets[symbol]['active']]

    for symbol in usdt_symbols:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=500)  # 15분 간격으로 변경
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            rsi_value = rsi(df, 14).iloc[-1]
            if rsi_value < settingRSI:
                message = f"!!과매도 현상 발견!! {symbol}"
                send_discord_message(message)
                return symbol
        except ccxt.BaseError as e:
            if 'does not have market symbol' in str(e):
                continue  # 심볼을 지원하지 않으면 다음 심볼로 넘어감
            send_discord_message(f"Error fetching data for {symbol}: {e}")
        except Exception as e:
            send_discord_message(f"Unexpected error for {symbol}: {e}")
        time.sleep(1)

def buyRSI(symbol, rsi_threshold, leverage):
    set_leverage(symbol, leverage)
    while True:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=500)  # 15분 간격으로 변경
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            current_rsi = rsi(df, 14).iloc[-1]
            if current_rsi < rsi_threshold:
                usdt_balance = exchange.fetch_balance()['total']['USDT']
                amount = usdt_balance * leverage * 0.9995  # 사용 가능한 전체 잔액에 레버리지 적용
                order = exchange.create_market_buy_order(symbol, amount)
                if order is None:
                    send_discord_message(f"Error: 매수 주문 실패 - {symbol}")
                    return None, None
                message = f"구매 완료: {symbol} - 금액: {amount} USDT (레버리지 {leverage}배)"
                send_discord_message(message)
                time.sleep(1)  # 주문 처리를 위해 잠시 대기
                volume = order['filled']  # 매수한 수량
                avg_price = order['price']
                return avg_price, volume
            time.sleep(1)
        except ccxt.BaseError as e:
            send_discord_message(f"Error in buyRSI: {e}")
            time.sleep(1)
        except Exception as e:
            send_discord_message(f"Unexpected error in buyRSI: {e}")
            time.sleep(1)

def sellRSI(symbol, rsi_threshold, avg_price, volume, stop_loss_pct):
    while True:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=500)  # 15분 간격으로 변경
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            current_rsi = rsi(df, 14).iloc[-1]
            current_price = exchange.fetch_ticker(symbol)['close']
            if current_rsi > rsi_threshold or current_price <= avg_price * (1 - stop_loss_pct):
                balance = exchange.fetch_balance()[symbol.split('/')[0]]['total']
                if volume > balance:
                    volume = balance
                sell_order = exchange.create_market_sell_order(symbol, volume)
                if sell_order is None:
                    send_discord_message(f"Error: 매도 주문 실패 - {symbol}")
                    return
                time.sleep(1)  # 주문 처리를 위해 잠시 대기
                sell_price = current_price
                profit_loss = (sell_price - avg_price) * volume
                message = f"판매 완료: {symbol} - 수량: {volume}\n손익: {profit_loss} USDT"
                send_discord_message(message)
                break
            time.sleep(1)
        except ccxt.BaseError as e:
            send_discord_message(f"Error in sellRSI: {e}")
            time.sleep(1)
        except Exception as e:
            send_discord_message(f"Unexpected error in sellRSI: {e}")
            time.sleep(1)
    usdt_balance = exchange.fetch_balance()['total']['USDT']
    send_discord_message(f"현재 현금 잔액: {usdt_balance} USDT")

while True:
    try:
        symbol_to_trade = search_onetime(25)
        if symbol_to_trade:
            avg_price, volume = buyRSI(symbol_to_trade, 30, 10)  # 여기서 10은 레버리지 배수입니다.
            if avg_price is not None and volume is not None:
                sellRSI(symbol_to_trade, 70, avg_price, volume, 0.10)  # 손절 기준은 10% 손실로 설정
    except ccxt.BaseError as e:
        send_discord_message(f"Error in main loop: {e}")
        time.sleep(1)
    except Exception as e:
        send_discord_message(f"Unexpected error in main loop: {e}")
        time.sleep(1)
