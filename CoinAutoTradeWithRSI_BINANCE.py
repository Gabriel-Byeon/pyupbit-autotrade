import ccxt
import time
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from discord_webhook import DiscordWebhook

DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL"
MAX_RISK_PER_TRADE = 0.01  # 거래당 최대 리스크 (계좌 잔고의 1%)
LEVERAGE = 20  # 설정할 레버리지 비율

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

def set_leverage(symbol, leverage, margin_type='ISOLATED'):
    try:
        # 레버리지 설정
        exchange.fapiPrivate_post_leverage({
            'symbol': symbol.replace('/', ''),
            'leverage': leverage
        })
        # 마진 타입 설정
        exchange.fapiPrivate_post_margintype({
            'symbol': symbol.replace('/', ''),
            'marginType': margin_type
        })
        print(f"{symbol} 레버리지 설정: {leverage}x, 마진 타입: {margin_type}")
    except Exception as e:
        print(f"{symbol} 레버리지 설정 실패: {e}")

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
                exchange.fetch_ohlcv(symbol, timeframe='5m', limit=1)
                symbols.append(symbol)
            except:
                continue
    return symbols

def get_ohlcv(symbol, timeframe='5m', limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"{symbol}의 OHLCV 데이터를 가져오는 중 오류 발생: {e}")
        return None

def calculate_indicators(df):
    try:
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

        # ATR
        df['TR'] = np.maximum(df['high'] - df['low'],
                              np.maximum(abs(df['high'] - df['close'].shift(1)),
                                         abs(df['low'] - df['close'].shift(1))))
        df['ATR'] = df['TR'].rolling(window=14).mean()

        return df

    except Exception as e:
        print(f"기술적 지표 계산 중 오류 발생: {e}")
        return None

def analyze_symbol(symbol):
    try:
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
        last_atr = df['ATR'].iloc[-1]
        volume_increase = df['volume'].iloc[-1] > df['volume'].mean() * 1.2  # 볼륨 증가 기준을 1.5에서 1.2로 낮춤

        # RSI 기반 매수 조건
        buy_condition = (
            (last_rsi < 30 and df['RSI'].shift(1).iloc[-1] >= 30) or  # RSI가 30 이하에서 30보다 상승할 때
            (last_close < last_lower_bb and df['close'].shift(1).iloc[-1] >= last_lower_bb) or  # 볼린저 밴드 하단에서 상승할 때
            (last_macd > last_signal or volume_increase)  # MACD 조건과 볼륨 조건을 OR로 변경
        )

        # RSI 기반 매도 조건
        sell_condition = (
            (last_rsi > 70 and df['RSI'].shift(1).iloc[-1] <= 70) or  # RSI가 70 이상에서 70 이하로 떨어질 때
            (last_close > last_upper_bb and df['close'].shift(1).iloc[-1] <= last_upper_bb) or  # 볼린저 밴드 상단에서 하락할 때
            (last_macd < last_signal or volume_increase)  # MACD 조건과 볼륨 조건을 OR로 변경
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

def calculate_position_size(account_balance, price, volatility):
    risk_amount = account_balance * MAX_RISK_PER_TRADE
    position_size = risk_amount / (price * volatility)
    return min(position_size, account_balance * 0.1 / price)  # 최대 계좌의 10%까지만 투자

def place_order(symbol, side, amount):
    try:
        order = exchange.create_order(symbol, 'market', side, amount)
        if side == 'buy':
            message = f"바이낸스 봇 Long 포지션 시작: {symbol} {amount}"
        else:
            message = f"바이낸스 봇 Short 포지션 시작: {symbol} {amount}"
        print(message)
        send_discord_message(message)
        return order
    except Exception as e:
        print(f"바이낸스 봇 주문 실패: {symbol} {side} {amount} - {e}")
        return None

def check_open_positions():
    try:
        positions = exchange.fapiPrivateV2_get_positionrisk()
        open_positions = []
        for pos in positions:
            if float(pos['positionAmt']) != 0:
                open_positions.append(pos)
        return open_positions
    except Exception as e:
        print(f"포지션 확인 오류: {e}")
        return []

def close_position(symbol, side, amount, reason):
    try:
        if side == 'buy':
            order = exchange.create_order(symbol, 'market', 'sell', amount)
            message = f"바이낸스 봇 Long 포지션 종료: {symbol} {amount} - {reason}"
        else:
            order = exchange.create_order(symbol, 'market', 'buy', amount)
            message = f"바이낸스 봇 Short 포지션 종료: {symbol} {amount} - {reason}"
        print(message)
        send_discord_message(message)
        return order
    except Exception as e:
        print(f"바이낸스 봇 포지션 종료 실패: {symbol} {amount} - {e}")
        return None

def get_entry_price(symbol):
    try:
        position_info = exchange.fapiPrivateV2_get_positionrisk()
        for pos in position_info:
            if pos['symbol'] == symbol.replace('/', ''):
                return float(pos['entryPrice'])
    except Exception as e:
        print(f"진입 가격 조회 오류: {e}")
        return None

def close_position_if_needed(symbol, position_amt, entry_price, current_price):
    try:
        if position_amt > 0:  # Long 포지션
            roi = (current_price - entry_price) / entry_price * 100 * LEVERAGE
            if roi <= -5:
                close_position(symbol, 'sell', position_amt, '손절')
            elif roi >= 10:
                close_position(symbol, 'sell', position_amt, '익절')
        elif position_amt < 0:  # Short 포지션
            roi = (entry_price - current_price) / entry_price * 100 * LEVERAGE
            if roi <= -5:
                close_position(symbol, 'buy', abs(position_amt), '손절')
            elif roi >= 10:
                close_position(symbol, 'buy', abs(position_amt), '익절')
    except Exception as e:
        print(f"{symbol} 포지션 청산 중 에러 발생: {e}")

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

            open_positions = check_open_positions()

            for position in open_positions:
                symbol = position['symbol']
                position_amt = float(position['positionAmt'])
                entry_price = float(position['entryPrice'])
                current_price = float(position['markPrice'])

                close_position_if_needed(symbol, position_amt, entry_price, current_price)

            for opportunity in opportunities:
                symbol = opportunity['symbol']
                action = 'buy' if opportunity['buy_condition'] else 'sell'
                price = opportunity['price']
                atr = opportunity['atr']

                # 레버리지 설정
                set_leverage(symbol, LEVERAGE, margin_type='ISOLATED')

                position_size = calculate_position_size(account_balance, price, atr)

                if action == 'buy' and not any(pos['symbol'] == symbol and float(pos['positionAmt']) > 0 for pos in open_positions):
                    place_order(symbol, 'buy', position_size)
                elif action == 'sell' and not any(pos['symbol'] == symbol and float(pos['positionAmt']) < 0 for pos in open_positions):
                    place_order(symbol, 'sell', position_size)

            send_discord_message("바이낸스 봇 거래 사이클 완료. 1분 대기...")
            time.sleep(60)  # 1분 대기
        except Exception as e:
            error_msg = f"봇 에러 발생: {e}"
            print(error_msg)
            send_discord_message(error_msg)
            time.sleep(60)  # 오류 발생 시 1분 대기

# 트레이딩 봇 실행
trading_bot()
