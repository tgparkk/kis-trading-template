
import os

target = os.path.join(r"d:\GIT\kis-trading-template\RoboTrader_template	ests", "test_market_dashboard.py")

# Read the template from base64 encoded data
import base64, zlib
data = open(os.path.join(r"d:\GIT\kis-trading-template\RoboTrader_template	ests", "_test_data.bin"), "rb").read()
content = zlib.decompress(base64.b64decode(data)).decode("utf-8")
with open(target, "w", encoding="utf-8") as f:
    f.write(content)
print(f"Written {len(content)} chars")
