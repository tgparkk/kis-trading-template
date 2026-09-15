"""매수후보 원장 재현기 — ma20 · daytrading.

설계서: `docs/superpowers/specs/2026-09-14-candidate-ledger-replayer-design.md` v0.5

🔴 이 패키지는 «후보 원장»만 만든다. 전방 수익률·PnL·체결·사이징은 만들지 않는다.
🔴 라이브 코드(`strategies/`·`core/`·`bot/`·`config/`)는 **읽기만** 한다(import).
"""
