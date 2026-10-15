"""Read-only check that the assistant can talk to your MetaTrader 5 terminal. Use a DEMO account.

Usage (terminal open and logged in):
    set MT5_SYMBOL_SUFFIX=m        (Exness standard account; "c" for cent; empty for none)
    python scripts/mt5_smoke.py [--account]

Prints bid/ask and the last candle for each supported symbol. Account balance is printed only with --account.
Nothing here can place or modify an order.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app import data

feed = data.MT5Feed()
for sym in data.DEMO_BASE:
    try:
        print(sym, feed.price(sym), feed.candles(sym, "M5", 1)[-1])
    except Exception as e:  # noqa: BLE001
        print(sym, "ERROR:", e)
if "--account" in sys.argv:
    print(feed.account())
