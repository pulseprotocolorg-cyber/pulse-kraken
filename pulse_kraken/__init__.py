"""
PULSE-Kraken Adapter.

Bridge PULSE Protocol messages to Kraken REST API.
Same interface as pulse-binance — swap exchanges in one line.

Example:
    >>> from pulse_kraken import KrakenAdapter
    >>> adapter = KrakenAdapter(api_key="...", api_secret="...")
    >>> from pulse import PulseMessage
    >>> msg = PulseMessage(
    ...     action="ACT.QUERY.DATA",
    ...     parameters={"symbol": "XBTUSD"}
    ... )
    >>> response = adapter.send(msg)
"""

from pulse_kraken.adapter import KrakenAdapter
from pulse_kraken.version import __version__

__all__ = ["KrakenAdapter", "__version__"]
