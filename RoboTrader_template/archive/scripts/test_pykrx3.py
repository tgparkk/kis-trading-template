# -*- coding: utf-8 -*-
"""pykrx 디버그 - 실제 오류 추적"""
import logging
logging.basicConfig(level=logging.DEBUG)

from pykrx.stock import krx
import inspect, requests

# krx 모듈 내부 클래스로 직접 호출
print("=== get_market_net_purchases_of_equities_by_ticker 내부 클래스 탐색 ===")
src = inspect.getsource(krx.get_market_net_purchases_of_equities_by_ticker)
print(src)
