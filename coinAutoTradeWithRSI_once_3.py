import asyncio
import requests
import pandas as pd
import pyupbit
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict

# Upbit API key 설정
access = "your-access-key"
secret = "your-secret-key"
upbit = pyupbit.Upbit(access, secret)

# Discord Webhook URL
discord_webhook_url = "your-discord-webhook-url"

# 심볼별로 상태를 저장할 딕셔너리
trade_status = defaultdict(lambda: {"buying": False, "selling": False, "owned": False, "latest_rsi": None, "latest_price": None})

# 현재 거래 중인 심볼 개수를 추적하는 변수
max_active_trades = 2
active_trades = set()

def send_discord_message(message):
    data = {"content": message}
    response = requests.post(discord_webhook_url, json=data)
    if response.status_code == 204:
        print("디스코드로 메시지를 성공적으로 보냈습니다")
    else:
        print(f"디스코드로 메시지 전송 실패: {response.status_code}")

def rsi(ohlc: pd.DataFrame, period: int = 14):
    delta = ohlc["close"].diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    _gain = up.ewm(com=(period - 1), min_periods=period).mean()
    _loss = down.abs().ewm(com=(period - 1), min_periods=period).mean()
    RS = _gain / _loss
    return pd.Series(100 - (100 / (1 + RS)), name="RSI")

def fetch_ohlcv(symbol):
    try:
        url = "https://api.upbit.com/v1/candles/minutes/10"
        querystring = {"market": symbol, "count": "500"}
        response = requests.request("GET", url, params=querystring)
        data = response.json()
        if not data or isinstance(data, dict):
            send_discord_message(f"No OHLCV data fetched for {symbol} or invalid response format")
            return None
        df = pd.DataFrame(data)
        if df.empty:
            send_discord_message(f"No OHLCV data fetched for {symbol}")
            return None
        df = df.iloc[::-1].reset_index(drop=True)
        df['close'] = df["trade_price"]
        return df
    except Exception as e:
        send_discord_message(f"Error fetching OHLCV data for {symbol}: {e}")
        return None

async def search_onetime(settingRSI, executor):
    tickers = pyupbit.get_tickers(fiat="KRW")
    send_discord_message("과매도 현상을 찾기 위한 검색을 시작합니다.")
    
    loop = asyncio.get_event_loop()
    futures = [loop.run_in_executor(executor, fetch_ohlcv, symbol) for symbol in tickers]

    for symbol, future in zip(tickers, asyncio.as_completed(futures)):
        try:
            df = await future
            if df is not None:
                rsi_value = rsi(df, 14).iloc[-1]
                trade_status[symbol]["latest_rsi"] = rsi_value
                if rsi_value < settingRSI and not trade_status[symbol]["owned"] and symbol not in active_trades:
                    message = f"!!과매도 현상 발견!! {symbol}"
                    send_discord_message(message)
                    return symbol
            await asyncio.sleep(0.1)
        except Exception as e:
            send_discord_message(f"Error in search_onetime ({symbol}): {e}")

    send_discord_message("과매도 현상이 발견되지 않았습니다.")
    return None

async def buyRSI(symbol, rsi_threshold, amount):
    global trade_status
    if trade_status[symbol]["buying"] or trade_status[symbol]["owned"]:
        send_discord_message(f"{symbol} 매수 시도 중 또는 이미 보유 중입니다. 다시 시도하지 않습니다.")
        return None, None
    
    trade_status[symbol]["buying"] = True
    try:
        send_discord_message(f"{symbol} 매수를 시도합니다.")
        df = pyupbit.get_ohlcv(symbol, interval="minute10")
        if df is None or df.empty:
            send_discord_message(f"No OHLCV data for {symbol} during buy attempt")
            trade_status[symbol]["buying"] = False
            return None, None
        current_rsi = rsi(df, 14).iloc[-1]
        trade_status[symbol]["latest_rsi"] = current_rsi
        if current_rsi < rsi_threshold:
            krw_balance = upbit.get_balance("KRW")
            if amount > krw_balance:
                amount = krw_balance * 0.9995
            order = upbit.buy_market_order(symbol, amount)
            if order is None:
                send_discord_message(f"Error: 매수 주문 실패 - {symbol}")
                trade_status[symbol]["buying"] = False
                return None, None
            message = f"구매 완료: {symbol} - 금액: {amount} KRW"
            send_discord_message(message)
            await asyncio.sleep(1)  # 주문 처리를 위해 잠시 대기
            volume = upbit.get_balance(symbol)  # 매수한 수량
            avg_price = float(amount) / float(volume)
            send_discord_message(f"{symbol} 매수 평균가: {avg_price}, 수량: {volume}")
            trade_status[symbol]["owned"] = True
            active_trades.add(symbol)
            trade_status[symbol]["buying"] = False
            return avg_price, volume
        await asyncio.sleep(1)
    except Exception as e:
        send_discord_message(f"Error in buyRSI: {e}")
        trade_status[symbol]["buying"] = False
    return None, None

async def sellRSI(symbol, rsi_threshold, avg_price, volume, stop_loss_pct):
    global trade_status
    if trade_status[symbol]["selling"]:
        return

    trade_status[symbol]["selling"] = True
    send_discord_message(f"{symbol} 매도를 시도합니다.")
    try:
        while trade_status[symbol]["selling"]:
            df = pyupbit.get_ohlcv(symbol, interval="minute10")
            if df is None or df.empty:
                send_discord_message(f"No OHLCV data for {symbol} during sell attempt")
                trade_status[symbol]["selling"] = False
                return
            current_rsi = rsi(df, 14).iloc[-1]
            current_price = pyupbit.get_current_price(symbol)
            trade_status[symbol]["latest_rsi"] = current_rsi
            trade_status[symbol]["latest_price"] = current_price
            if current_rsi > rsi_threshold or current_price <= avg_price * (1 - stop_loss_pct):
                balance = upbit.get_balance(symbol)
                if volume > balance:
                    volume = balance
                sell_order = upbit.sell_market_order(symbol, volume)
                if sell_order is None:
                    send_discord_message(f"Error: 매도 주문 실패 - {symbol}")
                    trade_status[symbol]["selling"] = False
                    return
                await asyncio.sleep(1)  # 주문 처리를 위해 잠시 대기
                sell_price = current_price
                profit_loss = (sell_price - avg_price) * volume
                message = f"판매 완료: {symbol} - 수량: {volume}\n손익: {profit_loss} KRW"
                send_discord_message(message)
                trade_status[symbol]["owned"] = False
                active_trades.remove(symbol)
                trade_status[symbol]["selling"] = False
                return
            await asyncio.sleep(1)
    except Exception as e:
        send_discord_message(f"Error in sellRSI: {e}")
        trade_status[symbol]["selling"] = False

    trade_status[symbol]["selling"] = False

async def trade_symbol(symbol_to_trade, buy_rsi, sell_rsi, trade_amount, stop_loss_pct):
    avg_price, volume = await buyRSI(symbol_to_trade, buy_rsi, trade_amount)
    if avg_price is not None and volume is not None:
        await sellRSI(symbol_to_trade, sell_rsi, avg_price, volume, stop_loss_pct)

async def main():
    send_discord_message("봇이 시작되었습니다.")
    with ThreadPoolExecutor(max_workers=10) as executor:
        while True:
            try:
                tasks = []
                # 필요한 심볼 개수만큼 병렬 검색
                search_tasks = [search_onetime(25, executor) for _ in range(max_active_trades - len(active_trades))]
                results = await asyncio.gather(*search_tasks)

                for symbol_to_trade in results:
                    if symbol_to_trade:
                        tasks.append(trade_symbol(symbol_to_trade, 30, 70, 100000, 0.10))  # 100000은 거래할 금액 (KRW)입니다.
                
                if tasks:
                    await asyncio.gather(*tasks)
                if not tasks and len(active_trades) < max_active_trades:
                    send_discord_message("거래 가능한 심볼을 찾지 못했습니다. 다시 시도합니다.")
                    await asyncio.sleep(60)  # 60초 대기 후 다시 시도
            except Exception as e:
                send_discord_message(f"Error in main loop: {e}")
                await asyncio.sleep(1)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
