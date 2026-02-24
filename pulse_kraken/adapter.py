"""Kraken adapter for PULSE Protocol.

Translates PULSE semantic messages to Kraken REST API.
Same interface as BinanceAdapter — swap exchanges in one line.

Example:
    >>> adapter = KrakenAdapter(api_key="...", api_secret="...")
    >>> msg = PulseMessage(
    ...     action="ACT.QUERY.DATA",
    ...     parameters={"symbol": "XBTUSD"}
    ... )
    >>> response = adapter.send(msg)
"""

import base64
import hashlib
import hmac
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

from pulse.message import PulseMessage
from pulse.adapter import PulseAdapter, AdapterError, AdapterConnectionError


# Kraken REST API endpoints
ENDPOINTS = {
    "ticker": "/0/public/Ticker",
    "ohlc": "/0/public/OHLC",
    "depth": "/0/public/Depth",
    "server_time": "/0/public/Time",
    "balance": "/0/private/Balance",
    "add_order": "/0/private/AddOrder",
    "cancel_order": "/0/private/CancelOrder",
    "open_orders": "/0/private/OpenOrders",
    "query_orders": "/0/private/QueryOrders",
}

# Map PULSE actions to Kraken operations
ACTION_MAP = {
    "ACT.QUERY.DATA": "query",
    "ACT.QUERY.STATUS": "order_status",
    "ACT.TRANSACT.REQUEST": "place_order",
    "ACT.CANCEL": "cancel_order",
    "ACT.QUERY.LIST": "open_orders",
    "ACT.QUERY.BALANCE": "balance",
}


class KrakenAdapter(PulseAdapter):
    """PULSE adapter for Kraken exchange.

    Translates PULSE semantic actions to Kraken REST API.
    Same interface as BinanceAdapter — switch exchanges in one line.

    Supported PULSE actions:
        - ACT.QUERY.DATA — get ticker price, OHLC, order book
        - ACT.QUERY.STATUS — check order status
        - ACT.QUERY.LIST — list open orders
        - ACT.QUERY.BALANCE — get account balance
        - ACT.TRANSACT.REQUEST — place an order (BUY/SELL)
        - ACT.CANCEL — cancel an order

    Example:
        >>> adapter = KrakenAdapter(api_key="...", api_secret="...")
        >>> msg = PulseMessage(
        ...     action="ACT.QUERY.DATA",
        ...     parameters={"symbol": "XBTUSD"}
        ... )
        >>> response = adapter.send(msg)
    """

    BASE_URL = "https://api.kraken.com"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            name="kraken",
            base_url=self.BASE_URL,
            config=config or {},
        )
        self._api_key = api_key
        self._api_secret = api_secret
        self._session: Optional[requests.Session] = None

    def connect(self) -> None:
        """Initialize HTTP session and verify connectivity."""
        self._session = requests.Session()

        try:
            resp = self._session.get(
                f"{self.base_url}{ENDPOINTS['server_time']}", timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("error"):
                raise AdapterConnectionError(f"Kraken API error: {data['error']}")
            self.connected = True
        except requests.ConnectionError as e:
            raise AdapterConnectionError(f"Cannot reach Kraken API: {e}") from e
        except requests.HTTPError as e:
            raise AdapterConnectionError(f"Kraken API error: {e}") from e

    def disconnect(self) -> None:
        """Close HTTP session."""
        if self._session:
            self._session.close()
        self._session = None
        self.connected = False

    def to_native(self, message: PulseMessage) -> Dict[str, Any]:
        """Convert PULSE message to Kraken API request."""
        action = message.content["action"]
        params = message.content.get("parameters", {})
        operation = ACTION_MAP.get(action)

        if not operation:
            raise AdapterError(
                f"Unsupported action '{action}'. Supported: {list(ACTION_MAP.keys())}"
            )

        if operation == "query":
            return self._build_query_request(params)
        elif operation == "place_order":
            return self._build_order_request(params)
        elif operation == "cancel_order":
            return self._build_cancel_request(params)
        elif operation == "order_status":
            return self._build_status_request(params)
        elif operation == "open_orders":
            return self._build_open_orders_request(params)
        elif operation == "balance":
            return self._build_balance_request()

        raise AdapterError(f"Unknown operation: {operation}")

    def call_api(self, native_request: Dict[str, Any]) -> Dict[str, Any]:
        """Execute Kraken API call."""
        if not self._session:
            self._ensure_session()

        method = native_request["method"]
        endpoint = native_request["endpoint"]
        url = f"{self.base_url}{endpoint}"
        params = native_request.get("params", {})
        signed = native_request.get("signed", False)

        try:
            if method == "GET":
                resp = self._session.get(url, params=params, timeout=10)
            elif method == "POST":
                if signed:
                    if not self._api_key or not self._api_secret:
                        raise AdapterError(
                            "API key and secret required for signed requests."
                        )
                    nonce = str(int(time.time() * 1000))
                    params["nonce"] = nonce
                    headers = self._sign_request(endpoint, nonce, params)
                    resp = self._session.post(
                        url, data=params, headers=headers, timeout=10
                    )
                else:
                    resp = self._session.post(url, data=params, timeout=10)
            else:
                raise AdapterError(f"Unknown HTTP method: {method}")

            data = resp.json()

            # Kraken uses error array
            errors = data.get("error", [])
            if errors:
                raise AdapterError(f"Kraken error: {'; '.join(errors)}")

            return data.get("result", data)

        except (requests.ConnectionError, ConnectionError) as e:
            raise AdapterConnectionError(f"Cannot reach Kraken: {e}") from e
        except (requests.Timeout, TimeoutError) as e:
            raise AdapterConnectionError(f"Kraken request timed out: {e}") from e
        except AdapterError:
            raise
        except Exception as e:
            raise AdapterError(f"Kraken request failed: {e}") from e

    def from_native(self, native_response: Any) -> PulseMessage:
        """Convert Kraken response to PULSE message."""
        return PulseMessage(
            action="ACT.RESPOND",
            parameters={"result": native_response},
            validate=False,
        )

    @property
    def supported_actions(self) -> List[str]:
        return list(ACTION_MAP.keys())

    # --- Request Builders ---

    def _build_query_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Build market data query."""
        symbol = params.get("symbol")
        query_type = params.get("type", "price")

        if query_type in ("price", "24h"):
            req_params = {}
            if symbol:
                req_params["pair"] = symbol.upper()
            return {
                "method": "GET",
                "endpoint": ENDPOINTS["ticker"],
                "params": req_params,
                "signed": False,
            }

        elif query_type == "klines":
            if not symbol:
                raise AdapterError("Symbol required for klines query.")
            return {
                "method": "GET",
                "endpoint": ENDPOINTS["ohlc"],
                "params": {
                    "pair": symbol.upper(),
                    "interval": params.get("interval", 60),
                },
                "signed": False,
            }

        elif query_type == "depth":
            if not symbol:
                raise AdapterError("Symbol required for depth query.")
            return {
                "method": "GET",
                "endpoint": ENDPOINTS["depth"],
                "params": {
                    "pair": symbol.upper(),
                    "count": params.get("limit", 20),
                },
                "signed": False,
            }

        raise AdapterError(
            f"Unknown query type '{query_type}'. Use: price, 24h, klines, depth."
        )

    def _build_order_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Build order placement request."""
        required = ["symbol", "side", "quantity"]
        for field in required:
            if field not in params:
                raise AdapterError(
                    f"Missing required field '{field}' for order placement."
                )

        order_params = {
            "pair": params["symbol"].upper(),
            "type": params["side"].lower(),
            "ordertype": params.get("order_type", "market").lower(),
            "volume": str(params["quantity"]),
        }

        if order_params["ordertype"] == "limit":
            if "price" not in params:
                raise AdapterError("Price required for LIMIT orders.")
            order_params["price"] = str(params["price"])

        return {
            "method": "POST",
            "endpoint": ENDPOINTS["add_order"],
            "params": order_params,
            "signed": True,
        }

    def _build_cancel_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Build order cancellation request."""
        if "order_id" not in params:
            raise AdapterError("Order ID required for cancellation.")

        return {
            "method": "POST",
            "endpoint": ENDPOINTS["cancel_order"],
            "params": {"txid": str(params["order_id"])},
            "signed": True,
        }

    def _build_status_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Build order status query."""
        if "order_id" not in params:
            raise AdapterError("Order ID required for status query.")

        return {
            "method": "POST",
            "endpoint": ENDPOINTS["query_orders"],
            "params": {"txid": str(params["order_id"])},
            "signed": True,
        }

    def _build_open_orders_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Build open orders query."""
        return {
            "method": "POST",
            "endpoint": ENDPOINTS["open_orders"],
            "params": {},
            "signed": True,
        }

    def _build_balance_request(self) -> Dict[str, Any]:
        """Build balance query."""
        return {
            "method": "POST",
            "endpoint": ENDPOINTS["balance"],
            "params": {},
            "signed": True,
        }

    # --- Signing ---

    def _sign_request(
        self, urlpath: str, nonce: str, data: Dict[str, Any]
    ) -> Dict[str, str]:
        """Generate Kraken API signature.

        Algorithm:
        1. SHA256(nonce + urlencode(data))
        2. HMAC-SHA512(urlpath + sha256_digest, base64_decode(secret))
        3. Base64 encode result
        """
        encoded_data = urlencode(data)
        sha256_hash = hashlib.sha256(
            (nonce + encoded_data).encode("utf-8")
        ).digest()

        message = urlpath.encode("utf-8") + sha256_hash

        signature = hmac.new(
            base64.b64decode(self._api_secret),
            message,
            hashlib.sha512,
        ).digest()

        return {
            "API-Key": self._api_key,
            "API-Sign": base64.b64encode(signature).decode("utf-8"),
        }

    def _ensure_session(self) -> None:
        if not self._session:
            self._session = requests.Session()

    def __repr__(self) -> str:
        return f"KrakenAdapter(connected={self.connected})"
