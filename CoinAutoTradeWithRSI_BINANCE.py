import ccxt
import time
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from discord_webhook import DiscordWebhook

DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL"
MAX_RISK_PER_TRADE = 0.01  # 거래당 최대 리스크 (계좌 잔고의 1%)

def send_discord_message(message):
    webhook = DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=message)
    response = webhook.execute()
    if response.status_code != 200:
        print(f"디스코드 메시지 전송 실패: {response.status_code}, {response.text}")

exchange = ccxt.binance({
    'apiKey': 'YOUR_API_KEY',
    'secret': 'YOUR_SECRET_KEY',
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future'
    }
})

def get_account_balance():
    balance = exchange.fetch_balance()
    return balance['USDT']['free']

def get_all_symbols():
    markets = exchange.load_markets()
    symbols = []
    for symbol in markets.keys():
        market = markets[symbol]
        if market['active'] and 'USDT' in symbol and '/' in symbol:
            try:
                # 추가 검증: 심볼이 유효한지 확인
                exchange.fetch_ohlcv(symbol, timeframe='1m', limit=1)
                symbols.append(symbol)
            except:
                continue
    return symbols

def get_ohlcv(symbol, timeframe='1m', limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"{symbol}의 OHLCV 데이터를 가져오는 중 오류 발생: {e}")
        return None

def calculate_indicators(df):
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    df['SMA20'] = df['close'].rolling(window=20).mean()
    df['stddev'] = df['close'].rolling(window=20).std()
    df['upper_bb'] = df['SMA20'] + (df['stddev'] * 2)
    df['lower_bb'] = df['SMA20'] - (df['stddev'] * 2)

    # MACD
    df['EMA12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['EMA26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

    return df

def analyze_symbol(symbol):
    df = get_ohlcv(symbol)
    if df is None or len(df) < 100:
        return None

    df = calculate_indicators(df)

    last_close = df['close'].iloc[-1]
    last_rsi = df['RSI'].iloc[-1]
    last_upper_bb = df['upper_bb'].iloc[-1]
    last_lower_bb = df['lower_bb'].iloc[-1]
    last_macd = df['MACD'].iloc[-1]
    last_signal = df['Signal'].iloc[-1]
    volume_increase = df['volume'].iloc[-1] > df['volume'].mean() * 1.2  # 볼륨 증가 기준을 1.5에서 1.2로 낮춤

    # 변동성 계산 (ATR 사용)
    df['TR'] = np.maximum(df['high'] - df['low'],
                          np.maximum(abs(df['high'] - df['close'].shift(1)),
                                     abs(df['low'] - df['close'].shift(1))))
    df['ATR'] = df['TR'].rolling(window=14).mean()
    volatility = df['ATR'].iloc[-1] / last_close

    # 매수 조건
    buy_condition = (
        (last_rsi < 40 or last_close < last_lower_bb) and  # RSI 기준을 30에서 40으로 완화
        (last_macd > last_signal or volume_increase)  # MACD 조건과 볼륨 조건을 OR로 변경
    )

    # 매도 조건
    sell_condition = (
        (last_rsi > 60 or last_close > last_upper_bb) and  # RSI 기준을 70에서 60으로 완화
        (last_macd < last_signal or volume_increase)  # MACD 조건과 볼륨 조건을 OR로 변경
    )

    if buy_condition:
        return {'symbol': symbol, 'action': 'buy', 'price': last_close, 'volatility': volatility}
    elif sell_condition:
        return {'symbol': symbol, 'action': 'sell', 'price': last_close, 'volatility': volatility}

    return None

def calculate_position_size(account_balance, price, volatility):
    risk_amount = account_balance * MAX_RISK_PER_TRADE
    position_size = risk_amount / (price * volatility)
    return min(position_size, account_balance * 0.1 / price)  # 최대 계좌의 10%까지만 투자

def place_order(symbol, side, amount):
    try:
        order = exchange.create_market_order(symbol, side, amount)
        message = f"바이낸스 봇 주문 실행: {symbol} {side} {amount}"
        print(message)
        send_discord_message(message)
        return order
    except Exception as e:
        error_msg = f"바이낸스 봇 주문 실패: {symbol} {side} {amount} - {e}"
        print(error_msg)
        return None

def trading_bot():
    while True:
        try:
            send_discord_message("바이낸스 트레이딩 봇 실행 중...")
            account_balance = get_account_balance()
            symbols = get_all_symbols()

            with ThreadPoolExecutor(max_workers=10) as executor:
                results = list(executor.map(analyze_symbol, symbols))

            opportunities = [r for r in results if r is not None]
            send_discord_message(f"발견된 거래 기회 총 개수: {len(opportunities)}")

            for opportunity in opportunities:
                symbol = opportunity['symbol']
                action = opportunity['action']
                price = opportunity['price']
                volatility = opportunity['volatility']

                position_size = calculate_position_size(account_balance, price, volatility)

                order = place_order(symbol, action, position_size)

                if order:
                    send_discord_message(f"주문 성공: {symbol} {action} {position_size}")

            send_discord_message("바이낸스 봇 거래 사이클 완료. 1분 대기...")
            time.sleep(60)  # 1분 대기
        except Exception as e:
            error_msg = f"봇 에러 발생: {e}"
            print(error_msg)
            send_discord_message(error_msg)
            time.sleep(60)  # 오류 발생 시 1분 대기

# 트레이딩 봇 실행
trading_bot()