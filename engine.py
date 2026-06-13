# -*- coding: utf-8 -*-
"""Multi-exchange order book engine: WebSocket, REST fallback, demo CSV."""

from __future__ import annotations

import csv
import json
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Literal, Optional, Tuple

import requests

__all__ = [
    "REGION_HINT", "SOURCES", "SourceConfig", "get_hub", "load_demo_csv",
    "demo_csv_bytes", "SymbolMetrics", "Alert",
]

MarketType = Literal["spot", "futures"]
DataMode = Literal["websocket", "rest", "demo", "offline"]

REGION_HINT = "Binance is restricted in your region. Please use a local version or a VPN"

STABLE_BASES = {
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP", "FDUSD", "PYUSD", "USDE", "USD1",
}


@dataclass(frozen=True)
class SourceConfig:
    source_id: str
    exchange: str
    market: str
    label: str
    rest_base: str
    ws_url: str
    depth_limit: int = 20


SOURCES: Dict[str, SourceConfig] = {
    "binance_spot": SourceConfig(
        "binance_spot", "binance", "spot", "Binance Spot",
        "https://api.binance.com", "wss://stream.binance.com:9443/stream",
    ),
    "binance_futures": SourceConfig(
        "binance_futures", "binance", "futures", "Binance Futures",
        "https://fapi.binance.com", "wss://fstream.binance.com/stream",
    ),
    "okx_swap": SourceConfig(
        "okx_swap", "okx", "futures", "OKX Swap",
        "https://www.okx.com", "wss://ws.okx.com:8443/ws/v5/public",
    ),
    "okx_spot": SourceConfig(
        "okx_spot", "okx", "spot", "OKX Spot",
        "https://www.okx.com", "wss://ws.okx.com:8443/ws/v5/public",
    ),
    "bybit_linear": SourceConfig(
        "bybit_linear", "bybit", "futures", "Bybit Linear",
        "https://api.bybit.com", "wss://stream.bybit.com/v5/public/linear",
    ),
    "bybit_spot": SourceConfig(
        "bybit_spot", "bybit", "spot", "Bybit Spot",
        "https://api.bybit.com", "wss://stream.bybit.com/v5/public/spot",
    ),
}


def is_access_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    markers = (
        "403", "451", "restricted", "banned", "forbidden",
        "cloudfront", "waf", "geographic", "invalid json",
        "connection", "timeout", "name or service not known",
    )
    return any(m in text for m in markers)


def _fetch_json(url: str, context: str) -> Any:
    resp = requests.get(url, timeout=20)
    if resp.status_code in (403, 451):
        raise RuntimeError(f"{REGION_HINT} ({context}: HTTP {resp.status_code})")
    if resp.status_code != 200:
        raise RuntimeError(f"{context}: HTTP {resp.status_code} — {resp.text[:200]}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise RuntimeError(f"{REGION_HINT} ({context}: invalid JSON)") from exc
    return data


def _binance_symbols(cfg: SourceConfig, min_volume: float) -> List[Tuple[str, str]]:
    ep = "/api/v3/exchangeInfo" if cfg.market == "spot" else "/fapi/v1/exchangeInfo"
    tk = "/api/v3/ticker/24hr" if cfg.market == "spot" else "/fapi/v1/ticker/24hr"
    info = _fetch_json(f"{cfg.rest_base}{ep}", cfg.label)
    if not isinstance(info, dict) or "symbols" not in info:
        raise RuntimeError(f"{cfg.label}: unexpected exchangeInfo")
    raw_tickers = _fetch_json(f"{cfg.rest_base}{tk}", cfg.label)
    if not isinstance(raw_tickers, list):
        raise RuntimeError(f"{cfg.label}: unexpected ticker response")
    tickers = {t["symbol"]: float(t.get("quoteVolume", 0)) for t in raw_tickers if isinstance(t, dict)}
    pairs: List[Tuple[str, str]] = []
    for item in info["symbols"]:
        if item.get("status") != "TRADING" or item.get("quoteAsset") != "USDT":
            continue
        if cfg.market == "spot":
            if not item.get("isSpotTradingAllowed", True):
                continue
        elif item.get("contractType") != "PERPETUAL":
            continue
        base = item["baseAsset"]
        if base in STABLE_BASES:
            continue
        sym = item["symbol"]
        if tickers.get(sym, 0) < min_volume:
            continue
        pairs.append((sym, base))
    pairs.sort(key=lambda x: tickers.get(x[0], 0), reverse=True)
    return pairs


def _okx_symbols(cfg: SourceConfig, min_volume: float) -> List[Tuple[str, str]]:
    inst = "SWAP" if cfg.market == "futures" else "SPOT"
    data = _fetch_json(f"{cfg.rest_base}/api/v5/public/instruments?instType={inst}", cfg.label)
    tick = _fetch_json(f"{cfg.rest_base}/api/v5/market/tickers?instType={inst}", cfg.label)
    if data.get("code") != "0" or tick.get("code") != "0":
        raise RuntimeError(f"{cfg.label}: {data.get('msg') or tick.get('msg')}")
    volumes = {
        row.get("instId", ""): float(row.get("volCcy24h") or row.get("vol24h") or 0)
        for row in tick.get("data", [])
    }
    pairs: List[Tuple[str, str]] = []
    for item in data.get("data", []):
        if item.get("state") != "live":
            continue
        inst_id = item["instId"]
        if not inst_id.endswith("-USDT") and not inst_id.endswith("-USDT-SWAP"):
            continue
        base = inst_id.split("-")[0]
        if base in STABLE_BASES or volumes.get(inst_id, 0) < min_volume:
            continue
        pairs.append((inst_id, base))
    pairs.sort(key=lambda x: volumes.get(x[0], 0), reverse=True)
    return pairs


def _bybit_symbols(cfg: SourceConfig, min_volume: float) -> List[Tuple[str, str]]:
    category = "linear" if cfg.market == "futures" else "spot"
    info = _fetch_json(f"{cfg.rest_base}/v5/market/instruments-info?category={category}", cfg.label)
    tick = _fetch_json(f"{cfg.rest_base}/v5/market/tickers?category={category}", cfg.label)
    if info.get("retCode") != 0 or tick.get("retCode") != 0:
        raise RuntimeError(f"{cfg.label}: API error")
    volumes = {
        row["symbol"]: float(row.get("turnover24h") or row.get("volume24h") or 0)
        for row in tick.get("result", {}).get("list", [])
    }
    pairs: List[Tuple[str, str]] = []
    for item in info.get("result", {}).get("list", []):
        if item.get("status") != "Trading":
            continue
        sym = item["symbol"]
        if not sym.endswith("USDT"):
            continue
        base = sym.replace("USDT", "")
        if base in STABLE_BASES or volumes.get(sym, 0) < min_volume:
            continue
        pairs.append((sym, base))
    pairs.sort(key=lambda x: volumes.get(x[0], 0), reverse=True)
    return pairs


def fetch_symbols(source_id: str, min_volume: float = 0.0) -> List[Tuple[str, str]]:
    cfg = SOURCES[source_id]
    if cfg.exchange == "binance":
        return _binance_symbols(cfg, min_volume)
    if cfg.exchange == "okx":
        return _okx_symbols(cfg, min_volume)
    if cfg.exchange == "bybit":
        return _bybit_symbols(cfg, min_volume)
    raise RuntimeError(f"Unknown exchange: {cfg.exchange}")


def fetch_depth_rest(source_id: str, symbol: str) -> Tuple[List, List]:
    cfg = SOURCES[source_id]
    if cfg.exchange == "binance":
        path = "/api/v3/depth" if cfg.market == "spot" else "/fapi/v1/depth"
        data = _fetch_json(f"{cfg.rest_base}{path}?symbol={symbol}&limit={cfg.depth_limit}", f"{cfg.label} depth")
        return data.get("bids", []), data.get("asks", [])
    if cfg.exchange == "okx":
        data = _fetch_json(
            f"{cfg.rest_base}/api/v5/market/books?instId={symbol}&sz={cfg.depth_limit}",
            f"{cfg.label} depth",
        )
        if data.get("code") != "0" or not data.get("data"):
            raise RuntimeError(f"{cfg.label} depth: {data.get('msg')}")
        book = data["data"][0]
        return book.get("bids", []), book.get("asks", [])
    if cfg.exchange == "bybit":
        category = "linear" if cfg.market == "futures" else "spot"
        data = _fetch_json(
            f"{cfg.rest_base}/v5/market/orderbook?category={category}&symbol={symbol}&limit={cfg.depth_limit}",
            f"{cfg.label} depth",
        )
        if data.get("retCode") != 0:
            raise RuntimeError(f"{cfg.label} depth: {data.get('retMsg')}")
        result = data.get("result", {})
        return result.get("b", []), result.get("a", [])
    raise RuntimeError(f"Unknown exchange: {cfg.exchange}")

DEPTH_LEVELS = 20
SUBSCRIBE_BATCH = 180
RECONNECT_DELAY_SEC = 5
REST_POLL_INTERVAL = 4.0
REST_MAX_SYMBOLS = 60
REST_REQUEST_DELAY = 0.05

DEMO_CSV_PATH = Path(__file__).parent / "demo_data.csv"


@dataclass
class SymbolMetrics:
    symbol: str
    base_asset: str
    exchange: str
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
    source_id: str = ""

    @property
    def key(self) -> str:
        return f"{self.source_id}:{self.symbol}"

    @property
    def label(self) -> str:
        return SOURCES.get(self.source_id, SourceConfig(self.source_id, self.exchange, self.market, self.source_id, "", "")).label


@dataclass
class SourceSnapshot:
    source_id: str
    label: str
    symbols: Dict[str, SymbolMetrics] = field(default_factory=dict)
    connected: bool = False
    subscribed_count: int = 0
    messages_received: int = 0
    last_message_at: float = 0.0
    started_at: float = 0.0
    data_mode: DataMode = "offline"
    error: Optional[str] = None
    region_blocked: bool = False


@dataclass
class Alert:
    exchange: str
    market: MarketType
    symbol: str
    base_asset: str
    imbalance_pct: float
    direction: Literal["bid", "ask"]
    severity: Literal["extreme", "critical"]
    notional_usdt: float
    timestamp: float
    message: str
    source_id: str = ""


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
        if now - self._last_alert.get(alert_key, 0.0) < self.cooldown:
            return None

        direction: Literal["bid", "ask"] = "bid" if imb > 0 else "ask"
        severity: Literal["extreme", "critical"] = "critical" if abs(imb) >= self.critical else "extreme"
        imb_pct = imb * 100
        arrow = "▲ BID" if direction == "bid" else "▼ ASK"
        if self.locale == "en":
            message = (
                f"[{severity.upper()}] {metrics.label} {metrics.symbol}: "
                f"{arrow} imbalance {imb_pct:+.1f}% · notional ${metrics.total_notional_usdt:,.0f}"
            )
        else:
            message = (
                f"[{severity.upper()}] {metrics.label} {metrics.symbol}: "
                f"{arrow} дисбаланс {imb_pct:+.1f}% · notional ${metrics.total_notional_usdt:,.0f}"
            )

        alert = Alert(
            exchange=metrics.exchange,
            market=metrics.market,
            symbol=metrics.symbol,
            base_asset=metrics.base_asset,
            imbalance_pct=imb_pct,
            direction=direction,
            severity=severity,
            notional_usdt=metrics.total_notional_usdt,
            timestamp=now,
            message=message,
            source_id=metrics.source_id,
        )
        self._last_alert[alert_key] = now
        self._history.appendleft(alert)
        return alert

    def scan(self, symbols: Dict[str, SymbolMetrics]) -> List[Alert]:
        return [a for m in symbols.values() if (a := self.check(m))]


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
    exchange: str,
    market: MarketType,
    source_id: str,
    bids: List,
    asks: List,
) -> SymbolMetrics:
    bid_levels = [(float(row[0]), float(row[1])) for row in bids if len(row) >= 2 and float(row[1]) > 0]
    ask_levels = [(float(row[0]), float(row[1])) for row in asks if len(row) >= 2 and float(row[1]) > 0]

    bid_volume = sum(q for _, q in bid_levels)
    ask_volume = sum(q for _, q in ask_levels)
    total_volume = bid_volume + ask_volume
    imbalance = (bid_volume - ask_volume) / total_volume if total_volume else 0.0

    best_bid = bid_levels[0][0] if bid_levels else 0.0
    best_ask = ask_levels[0][0] if ask_levels else 0.0
    mid_price = (best_bid + best_ask) / 2 if best_bid and best_ask else 0.0
    spread_bps = (best_ask - best_bid) / mid_price * 10_000 if mid_price and best_bid and best_ask else 0.0

    weighted_bid = weighted_ask = 0.0
    if mid_price > 0:
        for price, qty in bid_levels:
            weighted_bid += qty / (1.0 + abs(mid_price - price) / mid_price * 100)
        for price, qty in ask_levels:
            weighted_ask += qty / (1.0 + abs(price - mid_price) / mid_price * 100)
    weighted_total = weighted_bid + weighted_ask
    weighted_imbalance = (weighted_bid - weighted_ask) / weighted_total if weighted_total else 0.0

    max_e = _max_entropy(DEPTH_LEVELS)
    bid_e = _shannon_entropy([q for _, q in bid_levels]) / max_e if max_e else 0.0
    ask_e = _shannon_entropy([q for _, q in ask_levels]) / max_e if max_e else 0.0
    combined_entropy = (bid_e + ask_e) / 2

    total_notional = sum(p * q for p, q in bid_levels) + sum(p * q for p, q in ask_levels)
    health_score = (
        0.35 * (1.0 - abs(imbalance))
        + 0.30 * combined_entropy
        + 0.20 * min(1.0, math.log10(total_notional + 1) / 7.0)
        + 0.15 * max(0.0, 1.0 - spread_bps / 50.0)
    ) * 100.0

    return SymbolMetrics(
        symbol=symbol,
        base_asset=base_asset,
        exchange=exchange,
        market=market,
        bid_volume=bid_volume,
        ask_volume=ask_volume,
        imbalance=imbalance,
        weighted_imbalance=weighted_imbalance,
        bid_entropy=bid_e,
        ask_entropy=ask_e,
        combined_entropy=combined_entropy,
        health_score=health_score,
        spread_bps=spread_bps,
        mid_price=mid_price,
        total_notional_usdt=total_notional,
        updated_at=time.time(),
        source_id=source_id,
    )


def metrics_from_row(row: Dict[str, str]) -> SymbolMetrics:
    imb_pct = float(row.get("imbalance_pct", 0))
    w_imb_pct = float(row.get("weighted_imbalance_pct", imb_pct))
    return SymbolMetrics(
        symbol=row["symbol"],
        base_asset=row.get("base_asset", row["symbol"][:3]),
        exchange=row.get("exchange", "demo"),
        market=row.get("market", "spot"),  # type: ignore[arg-type]
        source_id=row.get("source_id", f"{row.get('exchange', 'demo')}_{row.get('market', 'spot')}"),
        bid_volume=float(row.get("bid_volume", 0)),
        ask_volume=float(row.get("ask_volume", 0)),
        imbalance=imb_pct / 100.0,
        weighted_imbalance=w_imb_pct / 100.0,
        bid_entropy=float(row.get("bid_entropy", 0.5)),
        ask_entropy=float(row.get("ask_entropy", 0.5)),
        combined_entropy=float(row.get("combined_entropy", 0.5)),
        health_score=float(row.get("health", 70)),
        spread_bps=float(row.get("spread_bps", 1)),
        mid_price=float(row.get("mid_price", 0)),
        total_notional_usdt=float(row.get("notional_usdt", 0)),
        updated_at=time.time(),
    )


def load_demo_csv(path: Path | str = DEMO_CSV_PATH) -> Dict[str, SymbolMetrics]:
    result: Dict[str, SymbolMetrics] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            m = metrics_from_row(row)
            result[m.key] = m
    return result


def demo_csv_bytes() -> bytes:
    return DEMO_CSV_PATH.read_bytes()


class SourceEngine:
    """WebSocket with automatic REST fallback per data source."""

    def __init__(self, source_id: str, min_quote_volume: float = 100_000.0) -> None:
        self.source_id = source_id
        self.cfg = SOURCES[source_id]
        self.min_quote_volume = min_quote_volume
        self._lock = threading.Lock()
        self._snapshot = SourceSnapshot(source_id=source_id, label=self.cfg.label)
        self._base_map: Dict[str, str] = {}
        self._pairs: List[Tuple[str, str]] = []
        self._ws: Any = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._prefer_rest = self.cfg.exchange != "binance"

    @property
    def snapshot(self) -> SourceSnapshot:
        with self._lock:
            return SourceSnapshot(
                source_id=self.source_id,
                label=self.cfg.label,
                symbols=dict(self._snapshot.symbols),
                connected=self._snapshot.connected,
                subscribed_count=self._snapshot.subscribed_count,
                messages_received=self._snapshot.messages_received,
                last_message_at=self._snapshot.last_message_at,
                started_at=self._snapshot.started_at,
                data_mode=self._snapshot.data_mode,
                error=self._snapshot.error,
                region_blocked=self._snapshot.region_blocked,
            )

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name=f"engine-{self.source_id}")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

    def _set_error(self, exc: Exception) -> None:
        with self._lock:
            self._snapshot.connected = False
            self._snapshot.error = str(exc)
            self._snapshot.region_blocked = is_access_error(exc) or REGION_HINT in str(exc)

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._pairs = fetch_symbols(self.source_id, self.min_quote_volume)
                self._base_map = {s: b for s, b in self._pairs}
                with self._lock:
                    self._snapshot.subscribed_count = len(self._pairs)
                    self._snapshot.error = None
                    self._snapshot.region_blocked = False
                    if not self._snapshot.started_at:
                        self._snapshot.started_at = time.time()

                if self._prefer_rest:
                    self._poll_rest_loop()
                else:
                    try:
                        streams = [f"{s.lower()}@depth{DEPTH_LEVELS}@100ms" for s, _ in self._pairs]
                        self._connect_ws(streams)
                    except Exception as ws_exc:
                        if is_access_error(ws_exc):
                            self._poll_rest_loop()
                        else:
                            raise
            except Exception as exc:
                self._set_error(exc)
            if not self._stop.is_set():
                time.sleep(RECONNECT_DELAY_SEC)

    def _poll_rest_loop(self) -> None:
        symbols = [s for s, _ in self._pairs[:REST_MAX_SYMBOLS]]
        with self._lock:
            self._snapshot.data_mode = "rest"
            self._snapshot.connected = True
        while not self._stop.is_set():
            for sym in symbols:
                if self._stop.is_set():
                    return
                try:
                    bids, asks = fetch_depth_rest(self.source_id, sym)
                    metrics = compute_metrics(
                        sym, self._base_map[sym], self.cfg.exchange,
                        self.cfg.market, self.source_id, bids, asks,
                    )
                    with self._lock:
                        self._snapshot.symbols[sym] = metrics
                        self._snapshot.messages_received += 1
                        self._snapshot.last_message_at = time.time()
                except Exception as exc:
                    with self._lock:
                        self._snapshot.error = str(exc)
                        self._snapshot.region_blocked = is_access_error(exc)
                time.sleep(REST_REQUEST_DELAY)
            time.sleep(REST_POLL_INTERVAL)

    def _connect_ws(self, streams: List[str]) -> None:
        websocket = _import_websocket()
        done = threading.Event()

        def on_open(ws) -> None:
            with self._lock:
                self._snapshot.connected = True
                self._snapshot.data_mode = "websocket"
            for i in range(0, len(streams), SUBSCRIBE_BATCH):
                batch = streams[i : i + SUBSCRIBE_BATCH]
                ws.send(json.dumps({"method": "SUBSCRIBE", "params": batch, "id": i // SUBSCRIBE_BATCH + 1}))
                time.sleep(0.15)

        def on_message(_ws, message: str) -> None:
            payload = json.loads(message)
            if "result" in payload or ("id" in payload and "data" not in payload):
                return
            stream_name = payload.get("stream", "")
            data = payload.get("data", payload)
            symbol = data.get("s") or stream_name.split("@", 1)[0].upper()
            if not symbol or symbol not in self._base_map:
                return
            metrics = compute_metrics(
                symbol, self._base_map[symbol], self.cfg.exchange,
                self.cfg.market, self.source_id,
                data.get("b", data.get("bids", [])),
                data.get("a", data.get("asks", [])),
            )
            with self._lock:
                self._snapshot.symbols[symbol] = metrics
                self._snapshot.messages_received += 1
                self._snapshot.last_message_at = time.time()

        def on_error(_ws, error: Any) -> None:
            self._set_error(Exception(str(error)))

        def on_close(_ws, *_args: Any) -> None:
            with self._lock:
                self._snapshot.connected = False
            done.set()

        self._ws = websocket.WebSocketApp(
            self.cfg.ws_url, on_open=on_open, on_message=on_message,
            on_error=on_error, on_close=on_close,
        )
        self._ws.run_forever(ping_interval=20, ping_timeout=10)
        done.wait(timeout=1)


def _import_websocket():
    try:
        import websocket
    except ImportError as exc:
        raise ImportError("pip install websocket-client") from exc
    return websocket


class MarketHub:
    def __init__(self, source_ids: Tuple[str, ...], min_quote_volume: float = 100_000.0) -> None:
        self.source_ids = source_ids
        self.min_quote_volume = min_quote_volume
        self.engines: Dict[str, SourceEngine] = {
            sid: SourceEngine(sid, min_quote_volume) for sid in source_ids
        }
        self.alerts = AlertManager()
        self._demo_symbols: Dict[str, SymbolMetrics] = {}
        self._demo_active = False
        for eng in self.engines.values():
            eng.start()

    @property
    def demo_active(self) -> bool:
        return self._demo_active

    @property
    def region_blocked(self) -> bool:
        if self._demo_active:
            return False
        return any(e.snapshot.region_blocked for e in self.engines.values())

    def activate_demo(self, symbols: Optional[Dict[str, SymbolMetrics]] = None) -> int:
        self._demo_symbols = symbols or load_demo_csv()
        self._demo_active = True
        return len(self._demo_symbols)

    def deactivate_demo(self) -> None:
        self._demo_active = False
        self._demo_symbols = {}

    def all_symbols(self) -> Dict[str, SymbolMetrics]:
        if self._demo_active:
            return dict(self._demo_symbols)
        merged: Dict[str, SymbolMetrics] = {}
        for engine in self.engines.values():
            for metrics in engine.snapshot.symbols.values():
                merged[metrics.key] = metrics
        return merged

    def snapshots(self) -> Dict[str, SourceSnapshot]:
        if self._demo_active:
            return {
                "demo": SourceSnapshot(
                    source_id="demo", label="Demo", symbols=self._demo_symbols,
                    connected=True, subscribed_count=len(self._demo_symbols),
                    data_mode="demo", messages_received=len(self._demo_symbols),
                    last_message_at=time.time(),
                )
            }
        return {sid: self.engines[sid].snapshot for sid in self.source_ids}

    def aggregate_stats(self) -> Dict[str, float]:
        symbols = self.all_symbols()
        snaps = self.snapshots()
        if not symbols:
            return {
                "avg_imbalance": 0.0, "avg_health": 0.0, "avg_entropy": 0.0,
                "bullish_count": 0, "bearish_count": 0, "neutral_count": 0,
                "total_notional_m": 0.0, "connected_markets": 0,
                "subscribed_total": 0, "messages_total": 0,
            }
        imbalances = [m.imbalance for m in symbols.values()]
        bullish = sum(1 for x in imbalances if x > 0.05)
        bearish = sum(1 for x in imbalances if x < -0.05)
        return {
            "avg_imbalance": sum(imbalances) / len(imbalances),
            "avg_health": sum(m.health_score for m in symbols.values()) / len(symbols),
            "avg_entropy": sum(m.combined_entropy for m in symbols.values()) / len(symbols),
            "bullish_count": bullish,
            "bearish_count": bearish,
            "neutral_count": len(imbalances) - bullish - bearish,
            "total_notional_m": sum(m.total_notional_usdt for m in symbols.values()) / 1_000_000,
            "connected_markets": sum(1 for s in snaps.values() if s.connected),
            "subscribed_total": sum(s.subscribed_count for s in snaps.values()),
            "messages_total": sum(s.messages_received for s in snaps.values()),
        }

    def poll_alerts(self) -> List[Alert]:
        if self._demo_active:
            return []
        return self.alerts.scan(self.all_symbols())


_HUBS: Dict[str, MarketHub] = {}
_HUB_LOCK = threading.Lock()

SOURCE_PRESETS: Dict[str, Tuple[str, ...]] = {
    "binance_both": ("binance_spot", "binance_futures"),
    "binance_spot": ("binance_spot",),
    "binance_futures": ("binance_futures",),
    "okx_both": ("okx_spot", "okx_swap"),
    "bybit_both": ("bybit_spot", "bybit_linear"),
    "all": ("binance_spot", "binance_futures", "okx_swap", "bybit_linear"),
}


def get_hub(preset: str = "binance_both", min_quote_volume: float = 100_000.0) -> MarketHub:
    sources = SOURCE_PRESETS.get(preset, SOURCE_PRESETS["binance_both"])
    key = f"{preset}:{min_quote_volume}"
    with _HUB_LOCK:
        if key not in _HUBS:
            _HUBS[key] = MarketHub(sources, min_quote_volume)
        return _HUBS[key]
