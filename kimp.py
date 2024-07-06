# 현재 동작중
import ccxt
import requests
import time

# API 키 설정
BINANCE_API_KEY = ''
BINANCE_API_SECRET = ''

UPBIT_ACCESS_KEY = ''
UPBIT_SECRET_KEY = ''

# 디스코드 웹훅 URL 설정
DISCORD_WEBHOOK_URL = ''

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

def get_usdt_krw_price():
    try:
        ticker = upbit.fetch_ticker("USDT/KRW")
        return ticker['last']
    except Exception as e:
        send_discord_notification(f"USDT-KRW 환율 가져오기 오류: {e}")
        raise

def calculate_kimchi_premium(binance_price, upbit_price_krw, usdt_krw):
    upbit_price_usd = upbit_price_krw / usdt_krw
    return (upbit_price_usd - binance_price) / binance_price * 100

def send_discord_notification(message):
    data = {
        "content": message
    }
    response = requests.post(DISCORD_WEBHOOK_URL, json=data)
    if response.status_code == 204:
        print("알림이 성공적으로 전송되었습니다.")
    else:
        print("알림 전송에 실패했습니다.")

def open_positions(btc_amount, binance_symbol, upbit_symbol, upbit_price_krw):
    try:
        # 업비트에서 매수
        total_cost = btc_amount * upbit_price_krw
        upbit.create_market_buy_order(upbit_symbol, total_cost)
        send_discord_notification(f"업비트: {btc_amount} BTC 매수 완료")

        # 바이낸스에서 숏 포지션 오픈
        binance.create_market_sell_order(binance_symbol, btc_amount)
        send_discord_notification(f"바이낸스: {btc_amount} BTC 숏 포지션 오픈 완료")
    except Exception as e:
        send_discord_notification(f"포지션 오픈 중 오류 발생: {e}")
        raise

def close_positions(btc_amount, binance_symbol, upbit_symbol):
    try:
        # 업비트에서 매도
        upbit.create_market_sell_order(upbit_symbol, btc_amount)
        send_discord_notification(f"업비트: {btc_amount} BTC 매도 완료")

        # 바이낸스에서 숏 포지션 종료
        binance.create_market_buy_order(binance_symbol, btc_amount)
        send_discord_notification(f"바이낸스: {btc_amount} BTC 숏 포지션 종료 완료")
    except Exception as e:
        send_discord_notification(f"포지션 종료 중 오류 발생: {e}")
        raise

def trade():
    binance_symbol = 'BTC/USDT'
    upbit_symbol = 'BTC/KRW'
    usdt_amount = 120  # 거래량 설정 (120 USDT)
    slippage_tolerance = 0.5  # 슬리피지 허용 범위 (%)

    try:
        binance_price = get_binance_price(binance_symbol)
        upbit_price_krw = get_upbit_price(upbit_symbol)
        usdt_krw = get_usdt_krw_price()

        send_discord_notification(f"바이낸스 가격: {binance_price} USDT\n업비트 가격: {upbit_price_krw} KRW\nUSDT-KRW 환율: {usdt_krw} KRW/USD")

        kimchi_premium = calculate_kimchi_premium(binance_price, upbit_price_krw, usdt_krw)

        send_discord_notification(f"김프: {kimchi_premium:.2f}%")

        # 슬리피지를 고려한 가격 계산
        adjusted_binance_price = binance_price * (1 + slippage_tolerance / 100)
        adjusted_upbit_price_usd = (upbit_price_krw / usdt_krw) * (1 - slippage_tolerance / 100)

        # 거래량 계산 (120 USDT에 해당하는 BTC 양)
        btc_amount = usdt_amount / adjusted_binance_price

        if btc_amount * binance_price < 100:
            send_discord_notification("거래 금액이 최소 주문 금액보다 작습니다. 거래를 건너뜁니다.")
            return

        if kimchi_premium <= 0:  # 김프가 0 이하일 때
            send_discord_notification("조건 충족: 김프 <= 0. 포지션 오픈 중.")
            open_positions(btc_amount, binance_symbol, upbit_symbol, upbit_price_krw)
            message = f"포지션 오픈:\n업비트 매수 가격: {adjusted_upbit_price_usd} USDT\n바이낸스 숏 가격: {adjusted_binance_price} USDT\n김프: {kimchi_premium:.2f}%\nBTC 양: {btc_amount} BTC"
            send_discord_notification(message)

        elif kimchi_premium >= 3:  # 김프가 3 이상일 때
            send_discord_notification("조건 충족: 김프 >= 3. 포지션 종료 중.")
            close_positions(btc_amount, binance_symbol, upbit_symbol)
            message = f"포지션 종료:\n업비트 매도 가격: {adjusted_upbit_price_usd} USDT\n바이낸스 커버 가격: {adjusted_binance_price} USDT\n김프: {kimchi_premium:.2f}%\nBTC 양: {btc_amount} BTC"
            send_discord_notification(message)

    except Exception as e:
        print(f"오류 발생: {e}")
        send_discord_notification(f"오류 발생: {e}")

# 봇 시작 알림
send_discord_notification("김프 매매 봇이 시작되었습니다.")

while True:
    trade()
    time.sleep(60)  # 1분마다 실행


###################################################3 나중에 동작시킬 예정
# import ccxt
# import requests
# import time

# # API 키 설정
# BINANCE_API_KEY = ''
# BINANCE_API_SECRET = ''

# UPBIT_ACCESS_KEY = ''
# UPBIT_SECRET_KEY = ''

# # 디스코드 웹훅 URL 설정
# DISCORD_WEBHOOK_URL = ''

# # 바이낸스 API 연결
# binance = ccxt.binance({
#     'apiKey': BINANCE_API_KEY,
#     'secret': BINANCE_API_SECRET,
#     'options': {
#         'defaultType': 'future',
#     },
# })

# # 업비트 API 연결
# upbit = ccxt.upbit({
#     'apiKey': UPBIT_ACCESS_KEY,
#     'secret': UPBIT_SECRET_KEY,
#     'options': {
#         'createMarketBuyOrderRequiresPrice': False
#     }
# })

# # 거래 횟수 추적 변수
# trade_count = 0
# max_trades = 5

# def get_binance_price(symbol):
#     try:
#         ticker = binance.fetch_ticker(symbol)
#         return ticker['last']
#     except Exception as e:
#         send_discord_notification(f"바이낸스 가격 가져오기 오류: {e}")
#         raise

# def get_upbit_price(symbol):
#     try:
#         ticker = upbit.fetch_ticker(symbol)
#         return ticker['last']
#     except Exception as e:
#         send_discord_notification(f"업비트 가격 가져오기 오류: {e}")
#         raise

# def get_usdt_krw_price():
#     try:
#         ticker = upbit.fetch_ticker("USDT/KRW")
#         return ticker['last']
#     except Exception as e:
#         send_discord_notification(f"USDT-KRW 환율 가져오기 오류: {e}")
#         raise

# def calculate_kimchi_premium(binance_price, upbit_price_krw, usdt_krw):
#     upbit_price_usd = upbit_price_krw / usdt_krw
#     return (upbit_price_usd - binance_price) / binance_price * 100

# def send_discord_notification(message):
#     data = {
#         "content": message
#     }
#     response = requests.post(DISCORD_WEBHOOK_URL, json=data)
#     if response.status_code == 204:
#         print("알림이 성공적으로 전송되었습니다.")
#     else:
#         print("알림 전송에 실패했습니다.")

# def open_positions(btc_amount, binance_symbol, upbit_symbol, upbit_price_krw):
#     global trade_count
#     try:
#         if trade_count >= max_trades:
#             send_discord_notification("최대 거래 횟수에 도달했습니다. 더 이상 거래하지 않습니다.")
#             return

#         # 업비트에서 매수
#         total_cost = btc_amount * upbit_price_krw
#         upbit.create_market_buy_order(upbit_symbol, total_cost)
#         send_discord_notification(f"업비트: {btc_amount} BTC 매수 완료")
        
#         # 바이낸스에서 숏 포지션 오픈
#         binance.create_market_sell_order(binance_symbol, btc_amount)
#         send_discord_notification(f"바이낸스: {btc_amount} BTC 숏 포지션 오픈 완료")

#         trade_count += 1
#     except Exception as e:
#         send_discord_notification(f"포지션 오픈 중 오류 발생: {e}")
#         raise

# def close_positions(btc_amount, binance_symbol, upbit_symbol):
#     global trade_count
#     try:
#         # 업비트에서 매도
#         upbit.create_market_sell_order(upbit_symbol, btc_amount)
#         send_discord_notification(f"업비트: {btc_amount} BTC 매도 완료")
        
#         # 바이낸스에서 숏 포지션 종료
#         binance.create_market_buy_order(binance_symbol, btc_amount)
#         send_discord_notification(f"바이낸스: {btc_amount} BTC 숏 포지션 종료 완료")

#         trade_count -= 1
#     except Exception as e:
#         send_discord_notification(f"포지션 종료 중 오류 발생: {e}")
#         raise

# def trade():
#     global trade_count
#     binance_symbol = 'BTC/USDT'
#     upbit_symbol = 'BTC/KRW'
#     usdt_amount = 120  # 거래량 설정 (120 USDT)
#     slippage_tolerance = 0.5  # 슬리피지 허용 범위 (%)

#     try:
#         binance_price = get_binance_price(binance_symbol)
#         upbit_price_krw = get_upbit_price(upbit_symbol)
#         usdt_krw = get_usdt_krw_price()

#         send_discord_notification(f"바이낸스 가격: {binance_price} USDT\n업비트 가격: {upbit_price_krw} KRW\nUSDT-KRW 환율: {usdt_krw} KRW/USD")

#         kimchi_premium = calculate_kimchi_premium(binance_price, upbit_price_krw, usdt_krw)

#         send_discord_notification(f"김프: {kimchi_premium:.2f}%")

#         if trade_count >= max_trades:
#             send_discord_notification(f"김프: {kimchi_premium:.2f}% (거래 중지: 최대 거래 횟수 도달)")
#             return

#         # 슬리피지를 고려한 가격 계산
#         adjusted_binance_price = binance_price * (1 + slippage_tolerance / 100)
#         adjusted_upbit_price_usd = (upbit_price_krw / usdt_krw) * (1 - slippage_tolerance / 100)

#         # 거래량 계산 (120 USDT에 해당하는 BTC 양)
#         btc_amount = usdt_amount / adjusted_binance_price

#         if btc_amount * binance_price < 100:
#             send_discord_notification("거래 금액이 최소 주문 금액보다 작습니다. 거래를 건너뜁니다.")
#             return

#         if kimchi_premium <= 0:  # 김프가 0 이하일 때
#             send_discord_notification("조건 충족: 김프 <= 0. 포지션 오픈 중.")
#             open_positions(btc_amount, binance_symbol, upbit_symbol, upbit_price_krw)
#             message = f"포지션 오픈:\n업비트 매수 가격: {adjusted_upbit_price_usd} USDT\n바이낸스 숏 가격: {adjusted_binance_price} USDT\n김프: {kimchi_premium:.2f}%\nBTC 양: {btc_amount} BTC"
#             send_discord_notification(message)

#         elif kimchi_premium >= 3:  # 김프가 3 이상일 때
#             send_discord_notification("조건 충족: 김프 >= 3. 포지션 종료 중.")
#             close_positions(btc_amount, binance_symbol, upbit_symbol)
#             message = f"포지션 종료:\n업비트 매도 가격: {adjusted_upbit_price_usd} USDT\n바이낸스 커버 가격: {adjusted_binance_price} USDT\n김프: {kimchi_premium:.2f}%\nBTC 양: {btc_amount} BTC"
#             send_discord_notification(message)

#     except Exception as e:
#         print(f"오류 발생: {e}")
#         send_discord_notification(f"오류 발생: {e}")

# # 봇 시작 알림
# send_discord_notification("김프 매매 봇이 시작되었습니다.")

# while True:
#     trade()
#     time.sleep(60)  # 1분마다 실행
