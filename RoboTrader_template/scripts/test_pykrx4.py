# -*- coding: utf-8 -*-
"""pykrx decorator 우회 - __wrapped__ 접근"""
import logging
logging.basicConfig(level=logging.INFO)

from pykrx.stock import krx
import inspect

# __wrapped__ 로 원본 함수 소스 접근
fn = krx.get_market_net_purchases_of_equities_by_ticker
print("has __wrapped__:", hasattr(fn, '__wrapped__'))
if hasattr(fn, '__wrapped__'):
    print(inspect.getsource(fn.__wrapped__))
else:
    # 모듈 파일 직접 검색
    mod_file = inspect.getfile(krx)
    print("krx module file:", mod_file)
    with open(mod_file, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    # net_purchases 함수 주변 찾기
    for i, line in enumerate(lines):
        if 'net_purchases' in line and 'def ' in line:
            print(f"Line {i}: {line.rstrip()}")
            for j in range(i, min(i+50, len(lines))):
                print(f"  {i+j-i}: {lines[j].rstrip()}")
            print()
