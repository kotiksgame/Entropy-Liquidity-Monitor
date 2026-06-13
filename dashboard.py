# -*- coding: utf-8 -*-
"""Shared Streamlit dashboard with RU / EN localization."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from engine import Alert, SymbolMetrics, get_hub

MIN_VOLUME_MAX = 15_000_000
MIN_VOLUME_STEP = 50_000

MARKET_LABELS = {"spot": "Spot", "futures": "Futures"}

TEXTS: Dict[str, Dict[str, Any]] = {
    "ru": {
        "page_title": "Crypto Entropy Analyzer",
        "subtitle": "Binance Spot & Futures · дисбаланс ликвидности, энтропия стакана и алерты",
        "sidebar_market": "Рынок",
        "data_source": "Источник данных",
        "market_both": "Spot + Futures",
        "sidebar_settings": "Настройки",
        "min_volume": "Мин. объём 24h (USDT)",
        "market_filter": "Фильтр рынка",
        "market_all": "Все",
        "search": "Поиск",
        "search_ph": "BTC, ETH, SOL…",
        "sort_by": "Сортировка",
        "show_rows": "Показать строк",
        "sidebar_alerts": "Алерты",
        "alerts_enable": "Включить алерты",
        "threshold_extreme": "Порог extreme (%)",
        "threshold_critical": "Порог critical (%)",
        "cooldown": "Cooldown (сек)",
        "metrics_help": """
            **Метрики**

            - **Дисбаланс** — (bid − ask) / (bid + ask) по 20 уровням
            - **Энтропия** — равномерность объёма (Shannon)
            - **Здоровье** — баланс + энтропия + глубина + спред

            **Алерты**: toast + лента при |дисбаланс| ≥ порога.
            """,
        "metric_connection": "Подключение",
        "metric_symbols": "Символов",
        "metric_avg_imbalance": "Ср. дисбаланс",
        "metric_avg_health": "Ср. здоровье",
        "metric_bid_pressure": "Bid pressure",
        "metric_ask_pressure": "Ask pressure",
        "metric_alerts": "Алертов",
        "ws_error": "{market} WebSocket: {error}",
        "alerts_disabled": "Алерты отключены",
        "alerts_empty": "Экстремальных дисбалансов пока нет",
        "alerts_header": "Алерты дисбаланса",
        "waiting": "Ожидание данных с Binance WebSocket…",
        "extreme_header": "Экстремальный дисбаланс (≥ {threshold:.0f}%)",
        "liquidity_map": "Карта ликвидности",
        "entropy_label": "Энтропия",
        "top_bid": "Сильнейший bid-давление",
        "top_ask": "Сильнейший ask-давление",
        "all_coins": "Все монеты",
        "symbol_detail": "Детализация по символу",
        "detail_metric": "Метрика",
        "detail_value": "Значение",
        "detail_imbalance": "Дисбаланс",
        "detail_weighted": "Взвешенный",
        "detail_health": "Здоровье",
        "detail_entropy": "Энтропия bid/ask",
        "detail_spread": "Спред",
        "detail_notional": "Notional",
        "detail_alert": "Алерт: {severity} · дисбаланс {imbalance:+.1f}%",
        "footer": (
            "Обновлено: {time} · сообщений: {msgs:,} · лаг: {lag:.1f}s · ликвидность: ${liq:.1f}M"
        ),
    },
    "en": {
        "page_title": "Crypto Entropy Analyzer",
        "subtitle": "Binance Spot & Futures · liquidity imbalance, order book entropy & alerts",
        "sidebar_market": "Market",
        "data_source": "Data source",
        "market_both": "Spot + Futures",
        "sidebar_settings": "Settings",
        "min_volume": "Min. 24h volume (USDT)",
        "market_filter": "Market filter",
        "market_all": "All",
        "search": "Search",
        "search_ph": "BTC, ETH, SOL…",
        "sort_by": "Sort by",
        "show_rows": "Show rows",
        "sidebar_alerts": "Alerts",
        "alerts_enable": "Enable alerts",
        "threshold_extreme": "Extreme threshold (%)",
        "threshold_critical": "Critical threshold (%)",
        "cooldown": "Cooldown (sec)",
        "metrics_help": """
            **Metrics**

            - **Imbalance** — (bid − ask) / (bid + ask) across 20 levels
            - **Entropy** — volume distribution uniformity (Shannon)
            - **Health** — balance + entropy + depth + spread

            **Alerts**: toast + feed when |imbalance| ≥ threshold.
            """,
        "metric_connection": "Connection",
        "metric_symbols": "Symbols",
        "metric_avg_imbalance": "Avg. imbalance",
        "metric_avg_health": "Avg. health",
        "metric_bid_pressure": "Bid pressure",
        "metric_ask_pressure": "Ask pressure",
        "metric_alerts": "Alerts",
        "ws_error": "{market} WebSocket: {error}",
        "alerts_disabled": "Alerts disabled",
        "alerts_empty": "No extreme imbalances yet",
        "alerts_header": "Imbalance alerts",
        "waiting": "Waiting for Binance WebSocket data…",
        "extreme_header": "Extreme imbalance (≥ {threshold:.0f}%)",
        "liquidity_map": "Liquidity map",
        "entropy_label": "Entropy",
        "top_bid": "Strongest bid pressure",
        "top_ask": "Strongest ask pressure",
        "all_coins": "All symbols",
        "symbol_detail": "Symbol details",
        "detail_metric": "Metric",
        "detail_value": "Value",
        "detail_imbalance": "Imbalance",
        "detail_weighted": "Weighted",
        "detail_health": "Health",
        "detail_entropy": "Bid/ask entropy",
        "detail_spread": "Spread",
        "detail_notional": "Notional",
        "detail_alert": "Alert: {severity} · imbalance {imbalance:+.1f}%",
        "footer": (
            "Updated: {time} · messages: {msgs:,} · lag: {lag:.1f}s · liquidity: ${liq:.1f}M"
        ),
    },
}


def _css() -> str:
    return """
    <style>
    .stApp { background: linear-gradient(160deg, #0b0f19 0%, #111827 45%, #0f172a 100%); }
    [data-testid="stSidebar"] { background: #0d1321; border-right: 1px solid #1e293b; }
    div[data-testid="stMetric"] {
        background: rgba(30, 41, 59, 0.65);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 12px 16px;
    }
    div[data-testid="stMetric"] label { color: #94a3b8 !important; font-size: 0.8rem; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #f8fafc !important; }
    h1, h2, h3 { color: #e2e8f0 !important; }
    .subtitle { color: #64748b; font-size: 1rem; margin-top: -0.5rem; }
    .alert-critical {
        background: rgba(239, 68, 68, 0.15);
        border-left: 4px solid #ef4444;
        padding: 8px 12px;
        border-radius: 6px;
        margin-bottom: 6px;
        color: #fecaca;
        font-size: 0.9rem;
    }
    .alert-extreme {
        background: rgba(245, 158, 11, 0.12);
        border-left: 4px solid #f59e0b;
        padding: 8px 12px;
        border-radius: 6px;
        margin-bottom: 6px;
        color: #fde68a;
        font-size: 0.9rem;
    }
    </style>
    """


@st.cache_resource
def _cached_hub(market_mode: str, min_volume: float):
    return get_hub(market_mode=market_mode, min_quote_volume=min_volume)


def _init_alert_state(locale: str) -> None:
    key = f"shown_alert_ids_{locale}"
    if key not in st.session_state:
        st.session_state[key] = set()


def _alert_id(alert: Alert) -> str:
    return f"{alert.market}:{alert.symbol}:{int(alert.timestamp)}:{alert.severity}"


def _metrics_to_df(symbols: dict[str, SymbolMetrics]) -> pd.DataFrame:
    rows = [
        {
            "Market": MARKET_LABELS.get(m.market, m.market),
            "Symbol": m.symbol,
            "Base": m.base_asset,
            "Imbalance %": m.imbalance * 100,
            "Weighted Imb. %": m.weighted_imbalance * 100,
            "Bid Entropy": m.bid_entropy,
            "Ask Entropy": m.ask_entropy,
            "Combined Entropy": m.combined_entropy,
            "Health": m.health_score,
            "Spread bps": m.spread_bps,
            "Bid Vol": m.bid_volume,
            "Ask Vol": m.ask_volume,
            "Notional USDT": m.total_notional_usdt,
            "Mid Price": m.mid_price,
            "Updated": datetime.fromtimestamp(m.updated_at, tz=timezone.utc),
        }
        for m in symbols.values()
    ]
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _imbalance_color(val: float) -> str:
    if val > 10:
        return "#22c55e"
    if val < -10:
        return "#ef4444"
    return "#94a3b8"


def _make_live_panel(locale: str) -> Callable[..., None]:
    t = TEXTS[locale]

    def _render_alerts(
        hub,
        alerts_enabled: bool,
        threshold_pct: float,
        critical_pct: float,
        cooldown_sec: float,
    ) -> None:
        hub.alerts.configure(threshold_pct, critical_pct, cooldown_sec, locale=locale)

        if not alerts_enabled:
            st.caption(t["alerts_disabled"])
            return

        state_key = f"shown_alert_ids_{locale}"
        new_alerts = hub.poll_alerts()
        for alert in new_alerts:
            aid = _alert_id(alert)
            if aid not in st.session_state[state_key]:
                st.session_state[state_key].add(aid)
                icon = "🔴" if alert.severity == "critical" else "🟠"
                st.toast(f"{icon} {alert.message}", icon="⚡")

        history = hub.alerts.history
        if not history:
            st.caption(t["alerts_empty"])
            return

        st.subheader(t["alerts_header"])
        for alert in history[:20]:
            css = "alert-critical" if alert.severity == "critical" else "alert-extreme"
            ts = datetime.fromtimestamp(alert.timestamp).strftime("%H:%M:%S")
            st.markdown(
                f'<div class="{css}"><b>{ts}</b> · {alert.message}</div>',
                unsafe_allow_html=True,
            )

    @st.fragment(run_every=2)
    def live_panel(
        market_mode: str,
        min_volume: float,
        search: str,
        market_filter: str,
        sort_by: str,
        top_n: int,
        alerts_enabled: bool,
        threshold_pct: float,
        critical_pct: float,
        cooldown_sec: float,
    ) -> None:
        _init_alert_state(locale)
        hub = _cached_hub(market_mode, min_volume)
        symbols = hub.all_symbols()
        snaps = hub.snapshots()
        agg = hub.aggregate_stats()
        df = _metrics_to_df(symbols)

        online = agg["connected_markets"]
        total_markets = len(snaps)
        c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
        c1.metric(t["metric_connection"], f"{online}/{total_markets}")
        c2.metric(t["metric_symbols"], f"{len(symbols)} / {agg['subscribed_total']}")
        c3.metric(t["metric_avg_imbalance"], f"{agg['avg_imbalance'] * 100:+.2f}%")
        c4.metric(t["metric_avg_health"], f"{agg['avg_health']:.1f}")
        c5.metric(t["metric_bid_pressure"], str(agg["bullish_count"]))
        c6.metric(t["metric_ask_pressure"], str(agg["bearish_count"]))
        c7.metric(t["metric_alerts"], str(len(hub.alerts.history)))

        for market, snap in snaps.items():
            if snap.error:
                st.warning(t["ws_error"].format(market=MARKET_LABELS[market], error=snap.error))

        _render_alerts(hub, alerts_enabled, threshold_pct, critical_pct, cooldown_sec)

        if df.empty:
            st.info(t["waiting"])
            return

        if market_filter != t["market_all"]:
            df = df[df["Market"] == market_filter]

        if search:
            mask = (
                df["Symbol"].str.contains(search.upper(), na=False)
                | df["Base"].str.contains(search.upper(), na=False)
            )
            df = df[mask]

        extreme_df = df[df["Imbalance %"].abs() >= threshold_pct]
        if not extreme_df.empty:
            st.subheader(t["extreme_header"].format(threshold=threshold_pct))
            ex_show = extreme_df.sort_values("Imbalance %", key=abs, ascending=False)[
                ["Market", "Symbol", "Imbalance %", "Health", "Notional USDT"]
            ].head(15)
            st.dataframe(ex_show, use_container_width=True, hide_index=True)

        df = df.sort_values(sort_by, ascending=False).head(top_n)

        st.subheader(t["liquidity_map"])
        fig_scatter = px.scatter(
            df,
            x="Imbalance %",
            y="Health",
            size="Notional USDT",
            color="Combined Entropy",
            symbol="Market",
            hover_name="Symbol",
            color_continuous_scale="Viridis",
            labels={"Combined Entropy": t["entropy_label"]},
        )
        fig_scatter.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(15,23,42,0.8)",
            height=420,
            xaxis=dict(zeroline=True, zerolinecolor="#475569"),
        )
        fig_scatter.add_vline(x=0, line_dash="dot", line_color="#64748b")
        fig_scatter.add_vline(x=threshold_pct, line_dash="dash", line_color="#22c55e", opacity=0.4)
        fig_scatter.add_vline(x=-threshold_pct, line_dash="dash", line_color="#ef4444", opacity=0.4)
        st.plotly_chart(fig_scatter, use_container_width=True)

        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader(t["top_bid"])
            st.dataframe(
                df.nlargest(15, "Imbalance %")[["Market", "Symbol", "Imbalance %", "Health", "Notional USDT"]],
                use_container_width=True,
                hide_index=True,
            )
        with col_r:
            st.subheader(t["top_ask"])
            st.dataframe(
                df.nsmallest(15, "Imbalance %")[["Market", "Symbol", "Imbalance %", "Health", "Notional USDT"]],
                use_container_width=True,
                hide_index=True,
            )

        st.subheader(t["all_coins"])
        display_df = df.copy()
        display_df["Imbalance %"] = display_df["Imbalance %"].map(lambda x: f"{x:+.2f}")
        display_df["Weighted Imb. %"] = display_df["Weighted Imb. %"].map(lambda x: f"{x:+.2f}")
        display_df["Health"] = display_df["Health"].map(lambda x: f"{x:.1f}")
        display_df["Combined Entropy"] = display_df["Combined Entropy"].map(lambda x: f"{x:.3f}")
        display_df["Spread bps"] = display_df["Spread bps"].map(lambda x: f"{x:.2f}")
        display_df["Notional USDT"] = display_df["Notional USDT"].map(lambda x: f"{x:,.0f}")
        st.dataframe(display_df, use_container_width=True, hide_index=True, height=480)

        symbols_list = [f"{row['Market']}:{row['Symbol']}" for _, row in df.iterrows()]
        if symbols_list:
            detail_key = f"detail_symbol_{locale}"
            selected = st.selectbox(t["symbol_detail"], symbols_list, key=detail_key)
            market_name, symbol = selected.split(":", 1)
            market_key = "futures" if market_name == "Futures" else "spot"
            m = symbols.get(f"{market_key}:{symbol}")
            if m:
                detail_col1, detail_col2 = st.columns([1, 2])
                with detail_col1:
                    st.markdown(f"### {market_name} · {symbol}")
                    st.markdown(
                        f"""
                        | {t['detail_metric']} | {t['detail_value']} |
                        |---------|----------|
                        | {t['detail_imbalance']} | **{m.imbalance * 100:+.2f}%** |
                        | {t['detail_weighted']} | **{m.weighted_imbalance * 100:+.2f}%** |
                        | {t['detail_health']} | **{m.health_score:.1f}** / 100 |
                        | {t['detail_entropy']} | {m.bid_entropy:.3f} / {m.ask_entropy:.3f} |
                        | {t['detail_spread']} | {m.spread_bps:.2f} bps |
                        | {t['detail_notional']} | ${m.total_notional_usdt:,.0f} |
                        """
                    )
                    if abs(m.imbalance * 100) >= threshold_pct:
                        sev = "CRITICAL" if abs(m.imbalance) >= critical_pct / 100 else "EXTREME"
                        st.error(t["detail_alert"].format(severity=sev, imbalance=m.imbalance * 100))

                with detail_col2:
                    gauge = go.Figure(
                        go.Indicator(
                            mode="gauge+number+delta",
                            value=m.imbalance * 100,
                            title={"text": "Liquidity Imbalance"},
                            delta={"reference": 0},
                            gauge={
                                "axis": {"range": [-100, 100]},
                                "bar": {"color": _imbalance_color(m.imbalance * 100)},
                                "steps": [
                                    {"range": [-100, -threshold_pct], "color": "rgba(239,68,68,0.25)"},
                                    {"range": [-threshold_pct, threshold_pct], "color": "rgba(148,163,184,0.15)"},
                                    {"range": [threshold_pct, 100], "color": "rgba(34,197,94,0.25)"},
                                ],
                            },
                        )
                    )
                    gauge.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", height=280)
                    st.plotly_chart(gauge, use_container_width=True)

        last_msg = max((s.last_message_at for s in snaps.values() if s.last_message_at), default=0.0)
        lag = time.time() - last_msg if last_msg else None
        if lag is not None:
            st.caption(
                t["footer"].format(
                    time=datetime.now().strftime("%H:%M:%S"),
                    msgs=agg["messages_total"],
                    lag=lag,
                    liq=agg["total_notional_m"],
                )
            )

    return live_panel


def run_dashboard(locale: str) -> None:
    t = TEXTS[locale]
    live_panel = _make_live_panel(locale)

    st.set_page_config(
        page_title=t["page_title"],
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(_css(), unsafe_allow_html=True)

    st.title(t["page_title"])
    st.markdown(f'<p class="subtitle">{t["subtitle"]}</p>', unsafe_allow_html=True)

    with st.sidebar:
        st.header(t["sidebar_market"])
        market_mode = st.radio(
            t["data_source"],
            options=["both", "spot", "futures"],
            format_func=lambda x: {"both": t["market_both"], "spot": "Spot", "futures": "Futures"}[x],
            horizontal=True,
        )

        st.header(t["sidebar_settings"])
        min_volume = st.slider(
            t["min_volume"],
            min_value=0,
            max_value=MIN_VOLUME_MAX,
            value=100_000,
            step=MIN_VOLUME_STEP,
        )
        market_filter = st.selectbox(t["market_filter"], [t["market_all"], "Spot", "Futures"])
        search = st.text_input(t["search"], placeholder=t["search_ph"])
        sort_by = st.selectbox(
            t["sort_by"],
            [
                "Imbalance %",
                "Weighted Imb. %",
                "Health",
                "Combined Entropy",
                "Notional USDT",
                "Spread bps",
            ],
            index=0,
        )
        top_n = st.selectbox(t["show_rows"], [50, 100, 200, 500, 1000], index=2)

        st.divider()
        st.header(t["sidebar_alerts"])
        alerts_enabled = st.toggle(t["alerts_enable"], value=True)
        threshold_pct = st.slider(t["threshold_extreme"], 20, 80, 40, 5)
        critical_pct = st.slider(t["threshold_critical"], 40, 95, 60, 5)
        cooldown_sec = st.slider(t["cooldown"], 15, 300, 60, 15)

        st.divider()
        st.markdown(t["metrics_help"])

    live_panel(
        market_mode,
        min_volume,
        search,
        market_filter,
        sort_by,
        top_n,
        alerts_enabled,
        threshold_pct,
        critical_pct,
        cooldown_sec,
    )
