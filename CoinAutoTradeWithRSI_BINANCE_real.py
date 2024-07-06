import ccxt
import time
import pandas as pd
import numpy as np
from discord_webhook import DiscordWebhook

DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL"
MAX_RISK_PER_TRADE = 0.01  # 거래당 최대 리스크 (계좌 잔고의 1%)
TAKE_PROFIT_PERCENT = 10  # 익절 퍼센트
STOP_LOSS_PERCENT = 5  # 손절 퍼센트
MAX_SYMBOLS_TO_TRADE = 100  # 최대 거래할 심볼 수

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
        'defaultType': 'spot'  # 현물 거래를 위해 'spot'으로 설정
    }
})

def get_account_balance():
    balance = exchange.fetch_balance()
    return balance['total']['USDT']

def get_all_symbols():
    markets = exchange.load_markets()
    symbols = []
    for symbol in markets.keys():
        market = markets[symbol]
        if market['active'] and 'USDT' in symbol and '/' in symbol:
            try:
                # 추가 검증: 심볼이 유효한지 확인
                exchange.fetch_ohlcv(symbol, timeframe='1d', limit=1)
                symbols.append(symbol)
            except:
                continue
    return symbols

def analyze_symbol(symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        last_close = df['close'].iloc[-1]
        last_rsi = calculate_rsi(df['close'])
        last_upper_bb, last_lower_bb = calculate_bollinger_bands(df['close'])
        last_macd, last_signal = calculate_macd(df['close'])
        last_atr = calculate_atr(df)

        # Buy condition based on RSI, Bollinger Bands, and MACD
        buy_condition = (
            (last_rsi < 30 and df['RSI'].shift(1).iloc[-1] >= 30) or
            (last_close < last_lower_bb and df['close'].shift(1).iloc[-1] >= last_lower_bb) or
            (last_macd > last_signal)
        )

        # Sell condition based on RSI, Bollinger Bands, and MACD
        sell_condition = (
            (last_rsi > 70 and df['RSI'].shift(1).iloc[-1] <= 70) or
            (last_close > last_upper_bb and df['close'].shift(1).iloc[-1] <= last_upper_bb) or
            (last_macd < last_signal)
        )

        return {
            'symbol': symbol,
            'buy_condition': buy_condition,
            'sell_condition': sell_condition,
            'price': last_close,
            'atr': last_atr,
            'volatility': last_atr / last_close  # 변동성 계산 추가
        }

    except Exception as e:
        print(f"{symbol} 분석 중 오류 발생: {e}")
        return None

def calculate_rsi(close, window=14):
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def calculate_bollinger_bands(close, window=20):
    sma = close.rolling(window=window).mean()
    stddev = close.rolling(window=window).std()
    upper_bb = sma + (stddev * 2)
    lower_bb = sma - (stddev * 2)
    return upper_bb.iloc[-1], lower_bb.iloc[-1]

def calculate_macd(close, short_window=12, long_window=26, signal_window=9):
    ema12 = close.ewm(span=short_window, adjust=False).mean()
    ema26 = close.ewm(span=long_window, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=signal_window, adjust=False).mean()
    return macd.iloc[-1], signal.iloc[-1]

def calculate_atr(df, window=14):
    tr = np.maximum(df['high'] - df['low'],
                    np.maximum(abs(df['high'] - df['close'].shift(1)),
                               abs(df['low'] - df['close'].shift(1))))
    atr = tr.rolling(window=window).mean().iloc[-1]
    return atr

def calculate_position_size(account_balance, price):
    risk_amount = account_balance * MAX_RISK_PER_TRADE
    position_size = risk_amount / price
    return position_size

def place_order(symbol, side, amount):
    try:
        if side == 'buy':
            order = exchange.create_market_buy_order(symbol, amount)
            message = f"바이낸스 봇 매수 주문 실행: {symbol} {amount}"
        else:
            order = exchange.create_market_sell_order(symbol, amount)
            message = f"바이낸스 봇 매도 주문 실행: {symbol} {amount}"
        print(message)
        send_discord_message(message)
        return order
    except Exception as e:
        print(f"바이낸스 봇 주문 실패: {symbol} {side} {amount} - {e}")
        return None

def check_positions():
    positions = {}
    try:
        balance = exchange.fetch_balance()
        for asset in balance['total']:
            if balance['total'][asset] > 0 and asset != 'USDT':
                positions[asset + '/USDT'] = balance['total'][asset]
    except Exception as e:
        print(f"포지션 확인 중 오류 발생: {e}")
    return positions

def manage_positions(positions):
    for symbol, amount in positions.items():
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            buy_price = positions[symbol]['entryPrice']
            roi = (current_price - buy_price) / buy_price * 100

            if roi >= TAKE_PROFIT_PERCENT:
                place_order(symbol, 'sell', amount)
                send_discord_message(f"익절: {symbol} {roi:.2f}%")
            elif roi <= -STOP_LOSS_PERCENT:
                place_order(symbol, 'sell', amount)
                send_discord_message(f"손절: {symbol} {roi:.2f}%")
        except Exception as e:
            print(f"{symbol} 포지션 관리 중 오류 발생: {e}")

def trading_bot():
    while True:
        try:
            send_discord_message("바이낸스 트레이딩 봇 실행 중...")
            account_balance = get_account_balance()
            symbols = get_all_symbols()

            opportunities = []
            for symbol in symbols:
                result = analyze_symbol(symbol)
                if result:
                    opportunities.append(result)

            opportunities = opportunities[:MAX_SYMBOLS_TO_TRADE]  # 거래할 심볼 수 제한

            send_discord_message(f"발견된 거래 기회 총 개수: {len(opportunities)}")

            positions = check_positions()
            manage_positions(positions)

            for opportunity in opportunities:
                symbol = opportunity['symbol']
                action = 'buy' if opportunity['buy_condition'] else 'sell'
                price = opportunity['price']

                # 계좌 잔고와 최대 리스크를 고려하여 포지션 사이즈 계산
                position_size = calculate_position_size(account_balance, price)

                # 현재 보유 중인 포지션을 고려하여 매수 또는 매도 주문 실행
                if action == 'buy' and symbol not in positions:
                    place_order(symbol, 'buy', position_size)
                elif action == 'sell' and symbol in positions:
                    place_order(symbol, 'sell', positions[symbol])

            send_discord_message("바이낸스 봇 거래 사이클 완료. 1분 대기...")
            time.sleep(60)  # 1분 대기

        except Exception as e:
            error_msg = f"봇 에러 발생: {e}"
            print(error_msg)
            send_discord_message(error_msg)
            time.sleep(60)  # 오류 발생 시 1분 대기

# 트레이딩 봇 실행
trading_bot()
