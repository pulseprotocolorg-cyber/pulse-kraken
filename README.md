# PULSE-Kraken

**Kraken adapter for PULSE Protocol — trade Kraken with semantic messages.**

Write your trading bot once, run it on any exchange. Same code works with Binance, Bybit, OKX — just change one line.

## Quick Start

```bash
pip install pulse-kraken
```

```python
from pulse import PulseMessage
from pulse_kraken import KrakenAdapter

# Connect
adapter = KrakenAdapter(api_key="your-key", api_secret="your-base64-secret")
adapter.connect()

# Get BTC price
msg = PulseMessage(action="ACT.QUERY.DATA", parameters={"symbol": "XBTUSD"})
response = adapter.send(msg)
print(response.content["parameters"]["result"])
```

## Switch Exchanges in One Line

```python
# from pulse_binance import BinanceAdapter as Adapter
from pulse_kraken import KrakenAdapter as Adapter

adapter = Adapter(api_key="...", api_secret="...")
```

Your bot code stays exactly the same. Only the import changes.

## Supported Actions

| PULSE Action | What It Does | Kraken Endpoint |
|---|---|---|
| `ACT.QUERY.DATA` | Price, OHLC, order book | `/0/public/Ticker`, `/0/public/OHLC`, `/0/public/Depth` |
| `ACT.TRANSACT.REQUEST` | Place market/limit order | `/0/private/AddOrder` |
| `ACT.CANCEL` | Cancel an order | `/0/private/CancelOrder` |
| `ACT.QUERY.STATUS` | Check order status | `/0/private/QueryOrders` |
| `ACT.QUERY.LIST` | List open orders | `/0/private/OpenOrders` |
| `ACT.QUERY.BALANCE` | Account balance | `/0/private/Balance` |

## Features

- **SHA256 + HMAC-SHA512 authentication** — Kraken's unique signing, fully handled
- **Base64 secret decoding** — automatic
- **Kraken pair format** — use `XBTUSD`, `ETHUSD`, etc.
- **Tiny footprint** — one file, ~10 KB

## Kraken-Specific Notes

- Kraken uses pair names like `XBTUSD` (not `BTCUSDT`)
- Order sides are lowercase: `buy`/`sell` (adapter handles conversion)
- All private endpoints use POST (even queries)
- API secret is base64-encoded (just pass it as-is, adapter decodes it)

## Testing

```bash
pytest tests/ -q  # 31 tests, all mocked
```

## PULSE Ecosystem

| Package | Provider | Install |
|---|---|---|
| [pulse-protocol](https://pypi.org/project/pulse-protocol/) | Core | `pip install pulse-protocol` |
| [pulse-binance](https://pypi.org/project/pulse-binance/) | Binance | `pip install pulse-binance` |
| [pulse-bybit](https://pypi.org/project/pulse-bybit/) | Bybit | `pip install pulse-bybit` |
| **pulse-kraken** | **Kraken** | `pip install pulse-kraken` |
| [pulse-okx](https://pypi.org/project/pulse-okx/) | OKX | `pip install pulse-okx` |
| [pulse-openai](https://pypi.org/project/pulse-openai/) | OpenAI | `pip install pulse-openai` |
| [pulse-anthropic](https://pypi.org/project/pulse-anthropic/) | Anthropic | `pip install pulse-anthropic` |
| [pulse-gateway](https://pypi.org/project/pulse-gateway/) | Gateway | `pip install pulse-gateway` |

## License

Apache 2.0 — open source, free forever.
