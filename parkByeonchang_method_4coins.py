import time
import pyupbit
import pandas as pd
from datetime import datetime

# 업비트 API 키
access_key = 'your_access_key'
secret_key = 'your_secret_key'

# 로그인
upbit = pyupbit.Upbit(access_key, secret_key)

def get_moving_averages(df, windows=[5, 20]):
    """
    이동평균선 및 거래량 평균 계산
    """
    for window in windows:
        df[f'ma{window}'] = df['close'].rolling(window=window).mean()
        df[f'vol_ma{window}'] = df['volume'].rolling(window=window).mean()
    return df

def is_long_bullish_candle(candle):
    """
    장대양봉 판별: 몸통이 전체 길이의 70% 이상인 양봉
    """
    body_size = abs(candle['close'] - candle['open'])
    total_size = abs(candle['high'] - candle['low'])
    return candle['close'] > candle['open'] and body_size / total_size >= 0.7

def is_long_bearish_candle(candle):
    """
    장대음봉 판별: 몸통이 전체 길이의 70% 이상인 음봉
    """
    body_size = abs(candle['close'] - candle['open'])
    total_size = abs(candle['high'] - candle['low'])
    return candle['close'] < candle['open'] and body_size / total_size >= 0.7

def is_doji(candle):
    """
    십자형 캔들 판별: 몸통이 전체 길이의 5% 이하인 경우
    """
    body_size = abs(candle['close'] - candle['open'])
    total_size = abs(candle['high'] - candle['low'])
    return body_size / total_size <= 0.05

def is_explosive_volume(latest_volume, prev_volume):
    """
    폭발적인 거래량 증가 판별: 직전 거래량의 1.8배 이상
    """
    return latest_volume >= 1.8 * prev_volume

def check_buy_conditions(df):
    """
    매수 조건 확인 함수
    """
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    # 매수 제 1원칙: 5일 이동평균선 위에 있을 때, 폭발적인 거래량 상승과 함께 장대양봉 발생 시
    if latest['ma5'] and latest['close'] > latest['ma5']:
        if is_explosive_volume(latest['volume'], prev['volume']) and is_long_bullish_candle(latest):
            print("매수 제 1원칙 충족")
            return True

    # 매수 제 2원칙: 5일 이동평균선과 20일 이동평균선 사이에 있을 때, 거래량 폭발 증가와 전일 장대음봉의 50% 넘는 양봉 발생 시
    if latest['ma5'] and latest['ma20'] and latest['ma5'] > latest['close'] > latest['ma20']:
        if latest['volume'] < prev['volume'] and latest['close'] > prev['close'] * 0.5:
            if is_explosive_volume(latest['volume'], prev['volume']) and is_long_bullish_candle(latest):
                print("매수 제 2원칙 충족")
                return True

    # 매수 제 3원칙: 20일 이동평균선 아래, 하락하는 동안 거래량 감소 후 폭발적인 거래량 증가와 함께 장대 양봉 발생 시
    if latest['ma20'] and latest['close'] < latest['ma20']:
        # 하락하는 동안 거래량 감소
        decreasing_volume = True
        for i in range(3, 6):  # 최근 3개 봉을 확인
            if df['volume'].iloc[-i] >= df['volume'].iloc[-i-1]:
                decreasing_volume = False
                break
        if decreasing_volume and is_explosive_volume(latest['volume'], prev['volume']) and is_long_bullish_candle(latest):
            print("매수 제 3원칙 충족")
            return True

    return False

def check_sell_conditions(df):
    """
    매도 조건 확인 함수
    """
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    # 매도 제 1원칙: 5일 이동평균선 위, 거래량 급증과 함께 장대음봉 또는 십자형 캔들 발생 시
    if latest['ma5'] and latest['close'] > latest['ma5']:
        if is_explosive_volume(latest['volume'], prev['volume']):
            if is_long_bearish_candle(latest) or is_doji(latest):
                print("매도 제 1원칙 충족")
                return True

    # 매도 제 2원칙: 5일 이동평균선과 20일 이동평균선 사이, 거래량 급증과 함께 음봉 발생 시
    if latest['ma5'] and latest['ma20'] and latest['ma5'] > latest['close'] > latest['ma20']:
        if is_explosive_volume(latest['volume'], prev['volume']):
            if latest['close'] < prev['close']:
                print("매도 제 2원칙 충족")
                return True

    return False

def auto_trade():
    """
    자동 매매 실행 함수
    """
    # 모니터링할 코인 리스트
    coins = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-DOGE", "KRW-SOL"]
    max_investment_per_coin = 50000  # 코인당 최대 투자 금액
    investment_per_trade = 10000  # 매수당 투자 금액
    max_trades_per_coin = max_investment_per_coin // investment_per_trade  # 코인당 최대 매수 횟수

    # 각 코인별 매수 횟수 초기화
    trade_counts = {coin: 0 for coin in coins}

    while True:
        try:
            now = datetime.now()
            # 5분봉이 끝나는 시점 (4, 9, 14, 19, 24, 29, 34, 39, 44, 49, 54, 59분)에 작업 수행
            if now.minute % 5 == 4 and now.second == 59:
                for coin in coins:
                    # 5분봉 데이터 가져오기
                    df = pyupbit.get_ohlcv(coin, interval="minute5", count=200)
                    df = get_moving_averages(df)

                    # 매수 조건 확인 및 매수
                    if check_buy_conditions(df) and trade_counts[coin] < max_trades_per_coin:
                        balance = upbit.get_balance("KRW")
                        if balance >= investment_per_trade:
                            print(f"Buying 10000 KRW of {coin}")
                            upbit.buy_market_order(coin, 10000)
                            trade_counts[coin] += 1

                    # 매도 조건 확인 및 매도
                    if check_sell_conditions(df):
                        coin_balance = upbit.get_balance(coin.replace("KRW-", ""))
                        if coin_balance > 0.00008:  # 최소 거래 가능 수량 (업비트 기준)
                            print(f"Selling {coin_balance} of {coin}")
                            upbit.sell_market_order(coin, coin_balance)
                            trade_counts[coin] = 0  # 매도 후 매수 횟수 초기화

                # 분봉 끝난 후 1초 대기
                time.sleep(1)
            else:
                # 다음 체크포인트까지 대기
                time.sleep(1)
        except Exception as e:
            print(e)
            time.sleep(60)

# 실행
auto_trade()
