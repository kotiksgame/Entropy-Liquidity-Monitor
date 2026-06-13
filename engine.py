# -*- coding: utf-8 -*-
"""Binance Spot & Futures order book WebSocket engine, metrics and alerts."""

from __future__ import annotations

import json
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Literal, Optional, Tuple

import requests
import websocket

MarketType = Literal["spot", "futures"]

MARKET_CONFIG: Dict[MarketType, Dict[str, str]] = {
    "spot": {
        "rest": "https://api.binance.com",
        "ws": "wss://stream.binance.com:9443/stream",
        "exchange_info": "/api/v3/exchangeInfo",
        "ticker": "/api/v3/ticker/24hr",
    },
    "futures": {
        "rest": "https://fapi.binance.com",
        "ws": "wss://fstream.binance.com/stream",
        "exchange_info": "/fapi/v1/exchangeInfo",
        "ticker": "/fapi/v1/ticker/24hr",
    },
}

DEPTH_LEVELS = 20
SUBSCRIBE_BATCH = 180
RECONNECT_DELAY_SEC = 5
STABLE_BASES = {
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP", "FDUSD", "PYUSD", "USDE", "USD1",
}


@dataclass
class SymbolMetrics:
    symbol: str
    base_asset: str
    market: MarketType
    bid_volume: float = 0.0
    ask_volume: float = 0.0
    imbalance: float = 0.0
    weighted_imbalance: float = 0.0
    bid_entropy: float = 0.0
    ask_entropy: float = 0.0
    combined_entropy: float = 0.0
    health_score: float = 0.0
    spread_bps: float = 0.0
    mid_price: float = 0.0
    total_notional_usdt: float = 0.0
    updated_at: float = 0.0

    @property
    def key(self) -> str:
        return f"{self.market}:{self.symbol}"


@dataclass
class MarketSnapshot:
    market: MarketType
    symbols: Dict[str, SymbolMetrics] = field(default_factory=dict)
    connected: bool = False
    subscribed_count: int = 0
    messages_received: int = 0
    last_message_at: float = 0.0
    started_at: float = 0.0
    error: Optional[str] = None


@dataclass
class Alert:
    market: MarketType
    symbol: str
    base_asset: str
    imbalance_pct: float
    direction: Literal["bid", "ask"]
    severity: Literal["extreme", "critical"]
    notional_usdt: float
    timestamp: float
    message: str


class AlertManager:
    def __init__(
        self,
        threshold_pct: float = 40.0,
        critical_pct: float = 60.0,
        cooldown_sec: float = 60.0,
        max_history: int = 200,
        locale: str = "ru",
    ) -> None:
        self.threshold = threshold_pct / 100.0
        self.critical = critical_pct / 100.0
        self.cooldown = cooldown_sec
        self.locale = locale
        self._last_alert: Dict[str, float] = {}
        self._history: Deque[Alert] = deque(maxlen=max_history)

    def configure(
        self,
        threshold_pct: float,
        critical_pct: float,
        cooldown_sec: float,
        locale: Optional[str] = None,
    ) -> None:
        self.threshold = threshold_pct / 100.0
        self.critical = critical_pct / 100.0
        self.cooldown = cooldown_sec
        if locale is not None:
            self.locale = locale

    @property
    def history(self) -> List[Alert]:
        return list(self._history)

    def check(self, metrics: SymbolMetrics) -> Optional[Alert]:
        imb = metrics.imbalance
        if abs(imb) < self.threshold:
            return None

        now = time.time()
        alert_key = metrics.key
        last = self._last_alert.get(alert_key, 0.0)
        if now - last < self.cooldown:
            return None

        direction: Literal["bid", "ask"] = "bid" if imb > 0 else "ask"
        severity: Literal["extreme", "critical"] = "critical" if abs(imb) >= self.critical else "extreme"
        imb_pct = imb * 100
        market_label = "Futures" if metrics.market == "futures" else "Spot"
        arrow = "▲ BID" if direction == "bid" else "▼ ASK"
        if self.locale == "en":
            message = (
                f"[{severity.upper()}] {market_label} {metrics.symbol}: "
                f"{arrow} imbalance {imb_pct:+.1f}% · "
                f"notional ${metrics.total_notional_usdt:,.0f}"
            )
        else:
            message = (
                f"[{severity.upper()}] {market_label} {metrics.symbol}: "
                f"{arrow} дисбаланс {imb_pct:+.1f}% · "
                f"notional ${metrics.total_notional_usdt:,.0f}"
            )

        alert = Alert(
            market=metrics.market,
            symbol=metrics.symbol,
            base_asset=metrics.base_asset,
            imbalance_pct=imb_pct,
            direction=direction,
            severity=severity,
            notional_usdt=metrics.total_notional_usdt,
            timestamp=now,
            message=message,
        )
        self._last_alert[alert_key] = now
        self._history.appendleft(alert)
        return alert

    def scan(self, symbols: Dict[str, SymbolMetrics]) -> List[Alert]:
        alerts: List[Alert] = []
        for metrics in symbols.values():
            alert = self.check(metrics)
            if alert:
                alerts.append(alert)
        return alerts


def _fetch_json(url: str, context: str) -> Any:
    resp = requests.get(url, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"{context}: HTTP {resp.status_code} — {resp.text[:200]}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise RuntimeError(f"{context}: invalid JSON — {resp.text[:200]}") from exc
    if isinstance(data, dict) and "code" in data:
        raise RuntimeError(f"{context}: {data.get('msg', data)}")
    return data


def fetch_usdt_symbols(market: MarketType, min_quote_volume: float = 0.0) -> List[Tuple[str, str]]:
    """Return (symbol, base_asset) for active USDT pairs on spot or futures."""
    cfg = MARKET_CONFIG[market]
    info = _fetch_json(f"{cfg['rest']}{cfg['exchange_info']}", f"{market} exchangeInfo")
    if not isinstance(info, dict) or "symbols" not in info:
        raise RuntimeError(f"{market} exchangeInfo: unexpected response")

    raw_tickers = _fetch_json(f"{cfg['rest']}{cfg['ticker']}", f"{market} ticker/24hr")
    if not isinstance(raw_tickers, list):
        raise RuntimeError(f"{market} ticker/24hr: expected list, got {type(raw_tickers).__name__}")

    tickers = {
        t["symbol"]: float(t.get("quoteVolume", 0))
        for t in raw_tickers
        if isinstance(t, dict) and "symbol" in t
    }

    pairs: List[Tuple[str, str]] = []
    for item in info["symbols"]:
        if item["status"] != "TRADING":
            continue
        if item["quoteAsset"] != "USDT":
            continue
        if market == "spot":
            if not item.get("isSpotTradingAllowed", True):
                continue
        else:
            if item.get("contractType") != "PERPETUAL":
                continue

        base = item["baseAsset"]
        if base in STABLE_BASES:
            continue
        symbol = item["symbol"]
        if tickers.get(symbol, 0) < min_quote_volume:
            continue
        pairs.append((symbol, base))

    pairs.sort(key=lambda x: tickers.get(x[0], 0), reverse=True)
    return pairs


def _shannon_entropy(quantities: List[float]) -> float:
    positive = [q for q in quantities if q > 0]
    if not positive:
        return 0.0
    total = sum(positive)
    probs = [q / total for q in positive]
    return -sum(p * math.log2(p) for p in probs)


def _max_entropy(levels: int) -> float:
    return math.log2(levels) if levels > 1 else 1.0


def compute_metrics(
    symbol: str,
    base_asset: str,
    market: MarketType,
    bids: List,
    asks: List,
) -> SymbolMetrics:
    bid_levels = [(float(p), float(q)) for p, q in bids if float(q) > 0]
    ask_levels = [(float(p), float(q)) for p, q in asks if float(q) > 0]

    bid_volume = sum(q for _, q in bid_levels)
    ask_volume = sum(q for _, q in ask_levels)
    total_volume = bid_volume + ask_volume

    imbalance = 0.0
    if total_volume > 0:
        imbalance = (bid_volume - ask_volume) / total_volume

    best_bid = bid_levels[0][0] if bid_levels else 0.0
    best_ask = ask_levels[0][0] if ask_levels else 0.0
    mid_price = (best_bid + best_ask) / 2 if best_bid and best_ask else 0.0

    spread_bps = 0.0
    if mid_price > 0 and best_bid and best_ask:
        spread_bps = (best_ask - best_bid) / mid_price * 10_000

    weighted_bid = 0.0
    weighted_ask = 0.0
    if mid_price > 0:
        for price, qty in bid_levels:
            weight = 1.0 / (1.0 + abs(mid_price - price) / mid_price * 100)
            weighted_bid += qty * weight
        for price, qty in ask_levels:
            weight = 1.0 / (1.0 + abs(price - mid_price) / mid_price * 100)
            weighted_ask += qty * weight

    weighted_total = weighted_bid + weighted_ask
    weighted_imbalance = 0.0
    if weighted_total > 0:
        weighted_imbalance = (weighted_bid - weighted_ask) / weighted_total

    bid_entropy = _shannon_entropy([q for _, q in bid_levels])
    ask_entropy = _shannon_entropy([q for _, q in ask_levels])
    max_e = _max_entropy(DEPTH_LEVELS)
    bid_entropy_norm = bid_entropy / max_e if max_e else 0.0
    ask_entropy_norm = ask_entropy / max_e if max_e else 0.0
    combined_entropy = (bid_entropy_norm + ask_entropy_norm) / 2

    bid_notional = sum(p * q for p, q in bid_levels)
    ask_notional = sum(p * q for p, q in ask_levels)
    total_notional = bid_notional + ask_notional

    balance_score = 1.0 - abs(imbalance)
    spread_score = max(0.0, 1.0 - spread_bps / 50.0)
    depth_score = min(1.0, math.log10(total_notional + 1) / 7.0)
    health_score = (
        0.35 * balance_score
        + 0.30 * combined_entropy
        + 0.20 * depth_score
        + 0.15 * spread_score
    ) * 100.0

    return SymbolMetrics(
        symbol=symbol,
        base_asset=base_asset,
        market=market,
        bid_volume=bid_volume,
        ask_volume=ask_volume,
        imbalance=imbalance,
        weighted_imbalance=weighted_imbalance,
        bid_entropy=bid_entropy_norm,
        ask_entropy=ask_entropy_norm,
        combined_entropy=combined_entropy,
        health_score=health_score,
        spread_bps=spread_bps,
        mid_price=mid_price,
        total_notional_usdt=total_notional,
        updated_at=time.time(),
    )


class OrderBookEngine:
    def __init__(self, market: MarketType, min_quote_volume: float = 100_000.0) -> None:
        self.market = market
        self.min_quote_volume = min_quote_volume
        self._cfg = MARKET_CONFIG[market]
        self._lock = threading.Lock()
        self._snapshot = MarketSnapshot(market=market)
        self._base_map: Dict[str, str] = {}
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    @property
    def snapshot(self) -> MarketSnapshot:
        with self._lock:
            return MarketSnapshot(
                market=self.market,
                symbols=dict(self._snapshot.symbols),
                connected=self._snapshot.connected,
                subscribed_count=self._snapshot.subscribed_count,
                messages_received=self._snapshot.messages_received,
                last_message_at=self._snapshot.last_message_at,
                started_at=self._snapshot.started_at,
                error=self._snapshot.error,
            )

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name=f"ob-{self.market}")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._ws:
            self._ws.close()

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                pairs = fetch_usdt_symbols(self.market, self.min_quote_volume)
                self._base_map = {sym: base for sym, base in pairs}
                with self._lock:
                    self._snapshot.subscribed_count = len(pairs)
                    self._snapshot.error = None
                    if not self._snapshot.started_at:
                        self._snapshot.started_at = time.time()

                streams = [f"{sym.lower()}@depth{DEPTH_LEVELS}@100ms" for sym, _ in pairs]
                self._connect_and_listen(streams)
            except Exception as exc:
                with self._lock:
                    self._snapshot.connected = False
                    self._snapshot.error = str(exc)
            if not self._stop.is_set():
                time.sleep(RECONNECT_DELAY_SEC)

    def _connect_and_listen(self, streams: List[str]) -> None:
        done = threading.Event()

        def on_open(ws: websocket.WebSocketApp) -> None:
            with self._lock:
                self._snapshot.connected = True
            for i in range(0, len(streams), SUBSCRIBE_BATCH):
                batch = streams[i : i + SUBSCRIBE_BATCH]
                ws.send(json.dumps({"method": "SUBSCRIBE", "params": batch, "id": i // SUBSCRIBE_BATCH + 1}))
                time.sleep(0.15)

        def on_message(_ws: websocket.WebSocketApp, message: str) -> None:
            payload = json.loads(message)
            if "result" in payload or ("id" in payload and "data" not in payload):
                return

            stream_name = payload.get("stream", "")
            data = payload.get("data", payload)
            symbol = data.get("s") or stream_name.split("@", 1)[0].upper()
            if not symbol or symbol not in self._base_map:
                return

            metrics = compute_metrics(
                symbol,
                self._base_map[symbol],
                self.market,
                data.get("b", data.get("bids", [])),
                data.get("a", data.get("asks", [])),
            )
            with self._lock:
                self._snapshot.symbols[symbol] = metrics
                self._snapshot.messages_received += 1
                self._snapshot.last_message_at = time.time()

        def on_error(_ws: websocket.WebSocketApp, error: Any) -> None:
            with self._lock:
                self._snapshot.error = str(error)
                self._snapshot.connected = False

        def on_close(_ws: websocket.WebSocketApp, *_args: Any) -> None:
            with self._lock:
                self._snapshot.connected = False
            done.set()

        self._ws = websocket.WebSocketApp(
            self._cfg["ws"],
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        self._ws.run_forever(ping_interval=20, ping_timeout=10)
        done.wait(timeout=1)


class MarketHub:
    """Spot and/or Futures engines with shared alert manager."""

    def __init__(self, markets: Tuple[MarketType, ...], min_quote_volume: float = 100_000.0) -> None:
        self.markets = markets
        self.min_quote_volume = min_quote_volume
        self.engines: Dict[MarketType, OrderBookEngine] = {
            m: OrderBookEngine(m, min_quote_volume) for m in markets
        }
        self.alerts = AlertManager()
        for engine in self.engines.values():
            engine.start()

    def all_symbols(self) -> Dict[str, SymbolMetrics]:
        merged: Dict[str, SymbolMetrics] = {}
        for engine in self.engines.values():
            for sym, metrics in engine.snapshot.symbols.items():
                merged[metrics.key] = metrics
        return merged

    def snapshots(self) -> Dict[MarketType, MarketSnapshot]:
        return {m: self.engines[m].snapshot for m in self.markets}

    def aggregate_stats(self) -> Dict[str, float]:
        symbols = self.all_symbols()
        if not symbols:
            return {
                "avg_imbalance": 0.0,
                "avg_health": 0.0,
                "avg_entropy": 0.0,
                "bullish_count": 0,
                "bearish_count": 0,
                "neutral_count": 0,
                "total_notional_m": 0.0,
                "connected_markets": 0,
                "subscribed_total": 0,
                "messages_total": 0,
            }

        imbalances = [m.imbalance for m in symbols.values()]
        bullish = sum(1 for x in imbalances if x > 0.05)
        bearish = sum(1 for x in imbalances if x < -0.05)
        neutral = len(imbalances) - bullish - bearish
        snaps = self.snapshots()

        return {
            "avg_imbalance": sum(imbalances) / len(imbalances),
            "avg_health": sum(m.health_score for m in symbols.values()) / len(symbols),
            "avg_entropy": sum(m.combined_entropy for m in symbols.values()) / len(symbols),
            "bullish_count": bullish,
            "bearish_count": bearish,
            "neutral_count": neutral,
            "total_notional_m": sum(m.total_notional_usdt for m in symbols.values()) / 1_000_000,
            "connected_markets": sum(1 for s in snaps.values() if s.connected),
            "subscribed_total": sum(s.subscribed_count for s in snaps.values()),
            "messages_total": sum(s.messages_received for s in snaps.values()),
        }

    def poll_alerts(self) -> List[Alert]:
        return self.alerts.scan(self.all_symbols())


_HUBS: Dict[str, MarketHub] = {}
_HUB_LOCK = threading.Lock()


def _hub_key(market_mode: str, min_quote_volume: float) -> str:
    return f"{market_mode}:{min_quote_volume}"


def get_hub(market_mode: str = "both", min_quote_volume: float = 100_000.0) -> MarketHub:
    """market_mode: spot | futures | both"""
    if market_mode == "spot":
        markets: Tuple[MarketType, ...] = ("spot",)
    elif market_mode == "futures":
        markets = ("futures",)
    else:
        markets = ("spot", "futures")

    key = _hub_key(market_mode, min_quote_volume)
    with _HUB_LOCK:
        if key not in _HUBS:
            _HUBS[key] = MarketHub(markets, min_quote_volume)
        return _HUBS[key]
