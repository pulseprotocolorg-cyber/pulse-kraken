"""Tests for Kraken adapter. All mocked — no real API calls."""

import pytest
from unittest.mock import MagicMock

from pulse.message import PulseMessage
from pulse.adapter import AdapterError, AdapterConnectionError

from pulse_kraken import KrakenAdapter


# --- Mock Helpers ---


def mock_response(result_data, errors=None):
    """Create a mock Kraken response."""
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {
        "error": errors or [],
        "result": result_data,
    }
    mock.raise_for_status.return_value = None
    return mock


# --- Fixtures ---


@pytest.fixture
def adapter():
    a = KrakenAdapter(api_key="test-key", api_secret="dGVzdC1zZWNyZXQ=")  # base64("test-secret")
    a._session = MagicMock()
    a.connected = True
    return a


@pytest.fixture
def price_message():
    return PulseMessage(
        action="ACT.QUERY.DATA",
        parameters={"symbol": "XBTUSD"},
        sender="test-bot",
    )


@pytest.fixture
def klines_message():
    return PulseMessage(
        action="ACT.QUERY.DATA",
        parameters={"symbol": "XBTUSD", "type": "klines", "interval": 60},
        sender="test-bot",
    )


@pytest.fixture
def buy_message():
    return PulseMessage(
        action="ACT.TRANSACT.REQUEST",
        parameters={"symbol": "XBTUSD", "side": "BUY", "quantity": 0.001},
        sender="test-bot",
        validate=False,
    )


@pytest.fixture
def cancel_message():
    return PulseMessage(
        action="ACT.CANCEL",
        parameters={"order_id": "OABC12-DEFGH-IJKLMN"},
        sender="test-bot",
        validate=False,
    )


@pytest.fixture
def status_message():
    return PulseMessage(
        action="ACT.QUERY.STATUS",
        parameters={"order_id": "OABC12-DEFGH-IJKLMN"},
        sender="test-bot",
        validate=False,
    )


@pytest.fixture
def balance_message():
    return PulseMessage(
        action="ACT.QUERY.BALANCE",
        parameters={},
        sender="test-bot",
        validate=False,
    )


# --- Test Initialization ---


class TestKrakenAdapterInit:

    def test_basic_init(self):
        adapter = KrakenAdapter(api_key="key", api_secret="secret")
        assert adapter.name == "kraken"
        assert adapter.base_url == "https://api.kraken.com"
        assert adapter.connected is False

    def test_repr(self):
        adapter = KrakenAdapter()
        assert "connected=False" in repr(adapter)


# --- Test to_native: Market Data ---


class TestToNativeMarketData:

    def test_price_query(self, adapter, price_message):
        native = adapter.to_native(price_message)
        assert native["method"] == "GET"
        assert native["endpoint"] == "/0/public/Ticker"
        assert native["params"]["pair"] == "XBTUSD"
        assert native["signed"] is False

    def test_klines_query(self, adapter, klines_message):
        native = adapter.to_native(klines_message)
        assert native["endpoint"] == "/0/public/OHLC"
        assert native["params"]["interval"] == 60

    def test_depth_query(self, adapter):
        msg = PulseMessage(
            action="ACT.QUERY.DATA",
            parameters={"symbol": "XBTUSD", "type": "depth"},
        )
        native = adapter.to_native(msg)
        assert native["endpoint"] == "/0/public/Depth"
        assert native["params"]["count"] == 20

    def test_symbol_uppercased(self, adapter):
        msg = PulseMessage(action="ACT.QUERY.DATA", parameters={"symbol": "xbtusd"})
        native = adapter.to_native(msg)
        assert native["params"]["pair"] == "XBTUSD"

    def test_unknown_query_type_raises(self, adapter):
        msg = PulseMessage(action="ACT.QUERY.DATA", parameters={"type": "invalid"})
        with pytest.raises(AdapterError, match="Unknown query type"):
            adapter.to_native(msg)

    def test_klines_no_symbol_raises(self, adapter):
        msg = PulseMessage(action="ACT.QUERY.DATA", parameters={"type": "klines"})
        with pytest.raises(AdapterError, match="Symbol required"):
            adapter.to_native(msg)

    def test_depth_no_symbol_raises(self, adapter):
        msg = PulseMessage(action="ACT.QUERY.DATA", parameters={"type": "depth"})
        with pytest.raises(AdapterError, match="Symbol required"):
            adapter.to_native(msg)


# --- Test to_native: Orders ---


class TestToNativeOrders:

    def test_market_buy(self, adapter, buy_message):
        native = adapter.to_native(buy_message)
        assert native["method"] == "POST"
        assert native["endpoint"] == "/0/private/AddOrder"
        assert native["params"]["pair"] == "XBTUSD"
        assert native["params"]["type"] == "buy"
        assert native["params"]["ordertype"] == "market"
        assert native["params"]["volume"] == "0.001"
        assert native["signed"] is True

    def test_sell_side(self, adapter):
        msg = PulseMessage(
            action="ACT.TRANSACT.REQUEST",
            parameters={"symbol": "XBTUSD", "side": "SELL", "quantity": 0.1},
            validate=False,
        )
        native = adapter.to_native(msg)
        assert native["params"]["type"] == "sell"

    def test_limit_order(self, adapter):
        msg = PulseMessage(
            action="ACT.TRANSACT.REQUEST",
            validate=False,
            parameters={
                "symbol": "ETHUSD", "side": "BUY", "quantity": 1,
                "order_type": "LIMIT", "price": 2000,
            },
        )
        native = adapter.to_native(msg)
        assert native["params"]["ordertype"] == "limit"
        assert native["params"]["price"] == "2000"

    def test_limit_no_price_raises(self, adapter):
        msg = PulseMessage(
            action="ACT.TRANSACT.REQUEST",
            parameters={"symbol": "XBTUSD", "side": "BUY", "quantity": 1, "order_type": "LIMIT"},
            validate=False,
        )
        with pytest.raises(AdapterError, match="Price required"):
            adapter.to_native(msg)

    def test_order_missing_field_raises(self, adapter):
        msg = PulseMessage(
            action="ACT.TRANSACT.REQUEST",
            parameters={"symbol": "XBTUSD", "side": "BUY"},
            validate=False,
        )
        with pytest.raises(AdapterError, match="Missing required field"):
            adapter.to_native(msg)

    def test_cancel_order(self, adapter, cancel_message):
        native = adapter.to_native(cancel_message)
        assert native["method"] == "POST"
        assert native["endpoint"] == "/0/private/CancelOrder"
        assert native["params"]["txid"] == "OABC12-DEFGH-IJKLMN"
        assert native["signed"] is True

    def test_cancel_no_order_id_raises(self, adapter):
        msg = PulseMessage(action="ACT.CANCEL", parameters={}, validate=False)
        with pytest.raises(AdapterError, match="Order ID required"):
            adapter.to_native(msg)


# --- Test to_native: Account ---


class TestToNativeAccount:

    def test_order_status(self, adapter, status_message):
        native = adapter.to_native(status_message)
        assert native["endpoint"] == "/0/private/QueryOrders"
        assert native["params"]["txid"] == "OABC12-DEFGH-IJKLMN"
        assert native["signed"] is True

    def test_open_orders(self, adapter):
        msg = PulseMessage(action="ACT.QUERY.LIST", parameters={}, validate=False)
        native = adapter.to_native(msg)
        assert native["endpoint"] == "/0/private/OpenOrders"
        assert native["signed"] is True

    def test_wallet_balance(self, adapter, balance_message):
        native = adapter.to_native(balance_message)
        assert native["endpoint"] == "/0/private/Balance"
        assert native["signed"] is True

    def test_unsupported_action_raises(self, adapter):
        msg = PulseMessage(action="ACT.CREATE.TEXT", parameters={}, validate=False)
        with pytest.raises(AdapterError, match="Unsupported action"):
            adapter.to_native(msg)


# --- Test call_api ---


class TestCallAPI:

    def test_get_request(self, adapter):
        adapter._session.get.return_value = mock_response(
            {"XXBTZUSD": {"c": ["65000.00", "0.001"]}}
        )
        result = adapter.call_api({
            "method": "GET",
            "endpoint": "/0/public/Ticker",
            "params": {"pair": "XBTUSD"},
            "signed": False,
        })
        assert "XXBTZUSD" in result

    def test_post_request(self, adapter):
        adapter._session.post.return_value = mock_response(
            {"descr": {"order": "buy 0.001 XBTUSD"}, "txid": ["OABC12-DEFGH-IJKLMN"]}
        )
        result = adapter.call_api({
            "method": "POST",
            "endpoint": "/0/private/AddOrder",
            "params": {"pair": "XBTUSD", "type": "buy", "volume": "0.001"},
            "signed": True,
        })
        assert result["txid"][0] == "OABC12-DEFGH-IJKLMN"

    def test_api_error_response(self, adapter):
        adapter._session.get.return_value = mock_response(
            {}, errors=["EGeneral:Invalid arguments"]
        )
        with pytest.raises(AdapterError, match="Invalid arguments"):
            adapter.call_api({
                "method": "GET",
                "endpoint": "/0/public/Ticker",
                "params": {"pair": "INVALID"},
                "signed": False,
            })

    def test_connection_error(self, adapter):
        adapter._session.get.side_effect = ConnectionError("Network down")
        with pytest.raises(AdapterConnectionError, match="Cannot reach"):
            adapter.call_api({
                "method": "GET",
                "endpoint": "/0/public/Ticker",
                "signed": False,
            })

    def test_sign_without_key_raises(self, adapter):
        adapter._api_key = None
        with pytest.raises(AdapterError, match="API key and secret required"):
            adapter.call_api({
                "method": "POST",
                "endpoint": "/0/private/Balance",
                "params": {},
                "signed": True,
            })


# --- Test Full Pipeline ---


class TestFullPipeline:

    def test_price_query(self, adapter, price_message):
        adapter._session.get.return_value = mock_response(
            {"XXBTZUSD": {"c": ["65000.50", "0.001"]}}
        )
        response = adapter.send(price_message)
        assert response.type == "RESPONSE"
        assert response.envelope["sender"] == "adapter:kraken"

    def test_order_pipeline(self, adapter, buy_message):
        adapter._session.post.return_value = mock_response(
            {"descr": {"order": "buy"}, "txid": ["ORDER-123"]}
        )
        response = adapter.send(buy_message)
        assert response.content["parameters"]["result"]["txid"][0] == "ORDER-123"

    def test_pipeline_tracks_requests(self, adapter, price_message):
        adapter._session.get.return_value = mock_response({"XXBTZUSD": {}})
        adapter.send(price_message)
        adapter.send(price_message)
        assert adapter._request_count == 2


# --- Test Signing ---


class TestSigning:

    def test_sign_generates_headers(self, adapter):
        headers = adapter._sign_request(
            "/0/private/Balance", "1234567890", {"nonce": "1234567890"}
        )
        assert "API-Key" in headers
        assert "API-Sign" in headers
        assert headers["API-Key"] == "test-key"


# --- Test Supported Actions ---


class TestSupportedActions:

    def test_supported_actions(self, adapter):
        actions = adapter.supported_actions
        assert "ACT.QUERY.DATA" in actions
        assert "ACT.TRANSACT.REQUEST" in actions
        assert "ACT.CANCEL" in actions
        assert len(actions) == 6

    def test_supports_check(self, adapter):
        assert adapter.supports("ACT.QUERY.DATA") is True
        assert adapter.supports("ACT.CREATE.TEXT") is False
