import ccxt
import requests
import time
import schedule
import threading

# API 키 설정
BINANCE_API_KEY = 'your_binance_api_key'
BINANCE_API_SECRET = 'your_binance_api_secret'

UPBIT_ACCESS_KEY = 'your_upbit_access_key'
UPBIT_SECRET_KEY = 'your_upbit_secret_key'

# 디스코드 웹훅 URL 설정
DISCORD_WEBHOOK_URL = 'your_discord_webhook_url'

# ExchangeRate-API URL 설정
EXCHANGE_RATE_API_KEY = 'your_exchange_rate_api_key'
EXCHANGE_RATE_API_URL = f'https://v6.exchangerate-api.com/v6/{EXCHANGE_RATE_API_KEY}/latest/USD'

# 바이낸스 API 연결
binance = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_API_SECRET,
    'options': {
        'defaultType': 'future',
    },
})

# 업비트 API 연결
upbit = ccxt.upbit({
    'apiKey': UPBIT_ACCESS_KEY,
    'secret': UPBIT_SECRET_KEY,
    'options': {
        'createMarketBuyOrderRequiresPrice': False
    }
})

# 거래 횟수 추적 변수
trade_count = 0
max_trades = 1

# 전역 환율 변수
usd_krw_exchange_rate = None

def get_binance_price(symbol):
    try:
        ticker = binance.fetch_ticker(symbol)
        return ticker['last']
    except Exception as e:
        send_discord_notification(f"바이낸스 가격 가져오기 오류: {e}")
        raise

def get_upbit_price(symbol):
    try:
        ticker = upbit.fetch_ticker(symbol)
        return ticker['last']
    except Exception as e:
        send_discord_notification(f"업비트 가격 가져오기 오류: {e}")
        raise

def fetch_usd_krw_exchange_rate():
    try:
        response = requests.get(EXCHANGE_RATE_API_URL)
        data = response.json()
        if response.status_code == 200:
            return data['conversion_rates']['KRW']
        else:
            send_discord_notification(f"환율 가져오기 오류: {data['error-type']}")
            return None
    except Exception as e:
        send_discord_notification(f"환율 가져오기 오류: {e}")
        raise

def update_exchange_rate():
    global usd_krw_exchange_rate
    usd_krw_exchange_rate = fetch_usd_krw_exchange_rate()
    if usd_krw_exchange_rate:
        send_discord_notification(f"환율이 갱신되었습니다: {usd_krw_exchange_rate} KRW/USD")

def get_usd_krw_exchange_rate():
    global usd_krw_exchange_rate
    return usd_krw_exchange_rate

def calculate_kimchi_premium(binance_price_usdt, upbit_price_krw, usd_krw):
    binance_price_krw = binance_price_usdt * usd_krw
    return (upbit_price_krw - binance_price_krw) / binance_price_krw * 100

def send_discord_notification(message):
    data = {"content": message}
    response = requests.post(DISCORD_WEBHOOK_URL, json=data)
    if response.status_code == 204:
        print("알림이 성공적으로 전송되었습니다.")
    else:
        print("알림 전송에 실패했습니다.")

def open_positions(btc_amount, binance_symbol, upbit_symbol, upbit_price_krw):
    global trade_count
    try:
        if trade_count >= max_trades:
            send_discord_notification("최대 거래 횟수에 도달했습니다. 더 이상 거래하지 않습니다.")
            return

        # 업비트에서 매수
        total_cost = btc_amount * upbit_price_krw
        upbit.create_market_buy_order(upbit_symbol, total_cost)
        send_discord_notification(f"업비트: {btc_amount} BTC 매수 완료")

        # 바이낸스에서 숏 포지션 오픈
        binance.create_market_sell_order(binance_symbol, btc_amount)
        send_discord_notification(f"바이낸스: {btc_amount} BTC 숏 포지션 오픈 완료")

        trade_count += 1
    except Exception as e:
        send_discord_notification(f"포지션 오픈 중 오류 발생: {e}")
        raise

def close_positions(btc_amount, binance_symbol, upbit_symbol):
    global trade_count
    try:
        # 업비트에서 매도
        upbit.create_market_sell_order(upbit_symbol, btc_amount)
        send_discord_notification(f"업비트: {btc_amount} BTC 매도 완료")

        # 바이낸스에서 숏 포지션 종료
        binance.create_market_buy_order(binance_symbol, btc_amount)
        send_discord_notification(f"바이낸스: {btc_amount} BTC 숏 포지션 종료 완료")

        trade_count -= 1
    except Exception as e:
        send_discord_notification(f"포지션 종료 중 오류 발생: {e}")
        raise

def trade():
    global trade_count
    binance_symbol = 'BTC/USDT'
    upbit_symbol = 'BTC/KRW'
    usdt_amount = 120  # 거래량 설정 (120 USDT)

    try:
        binance_price = get_binance_price(binance_symbol)
        upbit_price_krw = get_upbit_price(upbit_symbol)
        usd_krw = get_usd_krw_exchange_rate()

        if usd_krw is None:
            return

        send_discord_notification(f"바이낸스 가격: {binance_price} USDT\n업비트 가격: {upbit_price_krw} KRW\nUSD-KRW 환율: {usd_krw} KRW/USD")

        kimchi_premium = calculate_kimchi_premium(binance_price, upbit_price_krw, usd_krw)
        send_discord_notification(f"김프: {kimchi_premium:.2f}%")

        if trade_count >= max_trades:
            send_discord_notification(f"김프: {kimchi_premium:.2f}% (거래 중지: 최대 거래 횟수 도달)")
            return

        # 거래량 계산 (120 USDT에 해당하는 BTC 양)
        btc_amount = usdt_amount / binance_price

        if btc_amount * binance_price < 100:
            send_discord_notification("거래 금액이 최소 주문 금액보다 작습니다. 거래를 건너뜁니다.")
            return

        if kimchi_premium <= 0:
            send_discord_notification(f"조건 충족: 김프({kimchi_premium:.2f}) <= 0. 포지션 오픈 중.")
            open_positions(btc_amount, binance_symbol, upbit_symbol, upbit_price_krw)
            message = f"포지션 오픈:\n업비트 매수 가격: {upbit_price_krw / usd_krw} USDT\n바이낸스 숏 가격: {binance_price} USDT\n김프: {kimchi_premium:.2f}%\nBTC 양: {btc_amount} BTC"
            send_discord_notification(message)

        elif kimchi_premium >= 3:
            send_discord_notification(f"조건 충족: 김프({kimchi_premium:.2f}) >= 3. 포지션 종료 중.")
            close_positions(btc_amount, binance_symbol, upbit_symbol)
            message = f"포지션 종료:\n업비트 매도 가격: {upbit_price_krw / usd_krw} USDT\n바이낸스 커버 가격: {binance_price} USDT\n김프: {kimchi_premium:.2f}%\nBTC 양: {btc_amount} BTC"
            send_discord_notification(message)

    except Exception as e:
        print(f"오류 발생: {e}")
        send_discord_notification(f"오류 발생: {e}")

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

# 봇 시작 알림
send_discord_notification("김프 매매 봇이 시작되었습니다.")

# 환율 초기화 및 일정 예약
update_exchange_rate()
schedule.every().day.at("00:00").do(update_exchange_rate)  # 매일 자정에 환율 갱신

# 스케줄러를 별도의 스레드에서 실행
threading.Thread(target=run_schedule).start()

# 무한 루프에서 트레이딩 실행
while True:
    trade()
    time.sleep(60)  # 1분마다 실행


## ExchangeRate-API 홈페이지
## https://www.exchangerate-api.com/