# -*- coding: utf-8 -*-
"""Shared Streamlit dashboard with RU / EN localization."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Callable, Dict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from engine import (
    REGION_HINT,
    Alert,
    SymbolMetrics,
    demo_csv_bytes,
    get_hub,
    load_demo_csv,
)
from exchanges import SOURCES

MIN_VOLUME_MAX = 15_000_000
MIN_VOLUME_STEP = 50_000

TEXTS: Dict[str, Dict[str, Any]] = {
    "ru": {
        "page_title": "Crypto Entropy Analyzer",
        "subtitle": "Binance · OKX · Bybit · дисбаланс ликвидности, энтропия стакана и алерты",
        "sidebar_exchange": "Биржи",
        "exchange_preset": "Пресет",
        "presets": {
            "binance_both": "Binance Spot + Futures",
            "binance_spot": "Binance Spot",
            "binance_futures": "Binance Futures",
            "okx_both": "OKX Spot + Swap",
            "bybit_both": "Bybit Spot + Linear",
            "all": "Все биржи",
        },
        "sidebar_settings": "Настройки",
        "min_volume": "Мин. объём 24h (USDT)",
        "market_filter": "Фильтр рынка",
        "market_all": "Все",
        "search": "Поиск",
        "search_ph": "BTC, ETH, SOL…",
        "sort_by": "Сортировка",
        "show_rows": "Показать строк",
        "sidebar_demo": "Демо-режим",
        "load_demo": "Загрузить демо-данные",
        "download_demo": "Скачать demo_data.csv",
        "upload_csv": "Или загрузите свой CSV",
        "exit_demo": "Выйти из демо",
        "demo_active": "Демо-режим активен — {count} символов",
        "sidebar_alerts": "Алерты",
        "alerts_enable": "Включить алерты",
        "threshold_extreme": "Порог extreme (%)",
        "threshold_critical": "Порог critical (%)",
        "cooldown": "Cooldown (сек)",
        "no_email_note": "Локальный запуск (`streamlit run app.py`) — без почты и регистрации.",
        "metrics_help": """
            **Метрики**

            - **Дисбаланс** — (bid − ask) / (bid + ask) по 20 уровням
            - **Энтропия** — равномерность объёма (Shannon)
            - **Здоровье** — баланс + энтропия + глубина + спред

            **При блокировке API**: REST-fallback или демо-данные.
            """,
        "metric_connection": "Подключение",
        "metric_mode": "Режим",
        "metric_symbols": "Символов",
        "metric_avg_imbalance": "Ср. дисбаланс",
        "metric_avg_health": "Ср. здоровье",
        "metric_bid_pressure": "Bid pressure",
        "metric_ask_pressure": "Ask pressure",
        "metric_alerts": "Алертов",
        "region_title": "Доступ к API ограничен",
        "region_body": REGION_HINT,
        "region_hint": "Попробуйте OKX/Bybit, демо-данные или локальный запуск с VPN.",
        "source_error": "{label} ({mode}): {error}",
        "alerts_disabled": "Алерты отключены",
        "alerts_empty": "Экстремальных дисбалансов пока нет",
        "alerts_header": "Алерты дисбаланса",
        "waiting": "Ожидание данных…",
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
        "footer": "Обновлено: {time} · режим: {mode} · сообщений: {msgs:,} · лаг: {lag:.1f}s · ${liq:.1f}M",
        "modes": {"websocket": "WebSocket", "rest": "REST", "demo": "Demo", "offline": "Offline"},
    },
    "en": {
        "page_title": "Crypto Entropy Analyzer",
        "subtitle": "Binance · OKX · Bybit · liquidity imbalance, order book entropy & alerts",
        "sidebar_exchange": "Exchanges",
        "exchange_preset": "Preset",
        "presets": {
            "binance_both": "Binance Spot + Futures",
            "binance_spot": "Binance Spot",
            "binance_futures": "Binance Futures",
            "okx_both": "OKX Spot + Swap",
            "bybit_both": "Bybit Spot + Linear",
            "all": "All exchanges",
        },
        "sidebar_settings": "Settings",
        "min_volume": "Min. 24h volume (USDT)",
        "market_filter": "Market filter",
        "market_all": "All",
        "search": "Search",
        "search_ph": "BTC, ETH, SOL…",
        "sort_by": "Sort by",
        "show_rows": "Show rows",
        "sidebar_demo": "Demo mode",
        "load_demo": "Load demo data",
        "download_demo": "Download demo_data.csv",
        "upload_csv": "Or upload your CSV",
        "exit_demo": "Exit demo",
        "demo_active": "Demo mode active — {count} symbols",
        "sidebar_alerts": "Alerts",
        "alerts_enable": "Enable alerts",
        "threshold_extreme": "Extreme threshold (%)",
        "threshold_critical": "Critical threshold (%)",
        "cooldown": "Cooldown (sec)",
        "no_email_note": "Local run (`streamlit run app_en.py`) — no email or sign-up required.",
        "metrics_help": """
            **Metrics**

            - **Imbalance** — (bid − ask) / (bid + ask) across 20 levels
            - **Entropy** — volume distribution uniformity (Shannon)
            - **Health** — balance + entropy + depth + spread

            **If API is blocked**: REST fallback or demo data.
            """,
        "metric_connection": "Connection",
        "metric_mode": "Mode",
        "metric_symbols": "Symbols",
        "metric_avg_imbalance": "Avg. imbalance",
        "metric_avg_health": "Avg. health",
        "metric_bid_pressure": "Bid pressure",
        "metric_ask_pressure": "Ask pressure",
        "metric_alerts": "Alerts",
        "region_title": "API access restricted",
        "region_body": REGION_HINT,
        "region_hint": "Try OKX/Bybit, demo data, or local run with VPN.",
        "source_error": "{label} ({mode}): {error}",
        "alerts_disabled": "Alerts disabled",
        "alerts_empty": "No extreme imbalances yet",
        "alerts_header": "Imbalance alerts",
        "waiting": "Waiting for data…",
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
        "footer": "Updated: {time} · mode: {mode} · messages: {msgs:,} · lag: {lag:.1f}s · ${liq:.1f}M",
        "modes": {"websocket": "WebSocket", "rest": "REST", "demo": "Demo", "offline": "Offline"},
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
    .region-banner {
        background: linear-gradient(135deg, rgba(239,68,68,0.18), rgba(245,158,11,0.12));
        border: 1px solid rgba(239,68,68,0.35);
        border-radius: 14px;
        padding: 20px 24px;
        margin: 12px 0 20px 0;
        color: #fecaca;
    }
    .region-banner h3 { color: #fca5a5 !important; margin: 0 0 8px 0; font-size: 1.15rem; }
    .region-banner p { margin: 4px 0; color: #fde68a; font-size: 0.95rem; }
    .demo-banner {
        background: rgba(59,130,246,0.15);
        border: 1px solid rgba(59,130,246,0.35);
        border-radius: 10px;
        padding: 10px 16px;
        color: #93c5fd;
        margin-bottom: 12px;
    }
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
def _cached_hub(preset: str, min_volume: float):
    return get_hub(preset=preset, min_quote_volume=min_volume)


def _init_alert_state(locale: str) -> None:
    key = f"shown_alert_ids_{locale}"
    if key not in st.session_state:
        st.session_state[key] = set()


def _alert_id(alert: Alert) -> str:
    return f"{alert.source_id}:{alert.symbol}:{int(alert.timestamp)}:{alert.severity}"


def _metrics_to_df(symbols: dict[str, SymbolMetrics]) -> pd.DataFrame:
    rows = [
        {
            "Market": m.label,
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
            "_key": m.key,
        }
        for m in symbols.values()
    ]
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _imbalance_color(val: float) -> str:
    if val > 10:
        return "#22c55e"
    if val < -10:
        return "#ef4444"
    return "#94a3b8"


def _render_region_banner(t: Dict[str, Any]) -> None:
    st.markdown(
        f"""
        <div class="region-banner">
            <h3>🌍 {t['region_title']}</h3>
            <p><b>{t['region_body']}</b></p>
            <p>{t['region_hint']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _make_live_panel(locale: str) -> Callable[..., None]:
    t = TEXTS[locale]
    modes = t["modes"]

    def _render_alerts(hub, alerts_enabled, threshold_pct, critical_pct, cooldown_sec) -> None:
        hub.alerts.configure(threshold_pct, critical_pct, cooldown_sec, locale=locale)
        if hub.demo_active or not alerts_enabled:
            if not alerts_enabled:
                st.caption(t["alerts_disabled"])
            return

        state_key = f"shown_alert_ids_{locale}"
        for alert in hub.poll_alerts():
            aid = _alert_id(alert)
            if aid not in st.session_state[state_key]:
                st.session_state[state_key].add(aid)
                icon = "🔴" if alert.severity == "critical" else "🟠"
                st.toast(f"{icon} {alert.message}", icon="⚡")

        if not hub.alerts.history:
            st.caption(t["alerts_empty"])
            return

        st.subheader(t["alerts_header"])
        for alert in hub.alerts.history[:20]:
            css = "alert-critical" if alert.severity == "critical" else "alert-extreme"
            ts = datetime.fromtimestamp(alert.timestamp).strftime("%H:%M:%S")
            st.markdown(f'<div class="{css}"><b>{ts}</b> · {alert.message}</div>', unsafe_allow_html=True)

    @st.fragment(run_every=2)
    def live_panel(
        preset: str,
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
        hub = _cached_hub(preset, min_volume)

        if st.session_state.get(f"demo_active_{locale}"):
            if not hub.demo_active:
                hub.activate_demo(st.session_state.get(f"demo_data_{locale}"))
        elif hub.demo_active:
            hub.deactivate_demo()

        symbols = hub.all_symbols()
        snaps = hub.snapshots()
        agg = hub.aggregate_stats()
        df = _metrics_to_df(symbols)

        if hub.demo_active:
            st.markdown(
                f'<div class="demo-banner">📂 {t["demo_active"].format(count=len(symbols))}</div>',
                unsafe_allow_html=True,
            )
        elif hub.region_blocked and not symbols:
            _render_region_banner(t)

        active_modes = {modes.get(s.data_mode, s.data_mode) for s in snaps.values()}
        mode_label = modes["demo"] if hub.demo_active else (", ".join(sorted(active_modes)) or modes["offline"])

        c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)
        c1.metric(t["metric_connection"], f"{agg['connected_markets']}/{len(snaps)}")
        c2.metric(t["metric_mode"], mode_label)
        c3.metric(t["metric_symbols"], f"{len(symbols)} / {agg['subscribed_total']}")
        c4.metric(t["metric_avg_imbalance"], f"{agg['avg_imbalance'] * 100:+.2f}%")
        c5.metric(t["metric_avg_health"], f"{agg['avg_health']:.1f}")
        c6.metric(t["metric_bid_pressure"], str(agg["bullish_count"]))
        c7.metric(t["metric_ask_pressure"], str(agg["bearish_count"]))
        c8.metric(t["metric_alerts"], str(len(hub.alerts.history)))

        if not hub.demo_active:
            for snap in snaps.values():
                if snap.error and not snap.symbols:
                    st.warning(t["source_error"].format(
                        label=snap.label,
                        mode=modes.get(snap.data_mode, snap.data_mode),
                        error=snap.error,
                    ))

        _render_alerts(hub, alerts_enabled, threshold_pct, critical_pct, cooldown_sec)

        if df.empty:
            st.info(t["waiting"])
            return

        labels = sorted({m.label for m in symbols.values()})
        if market_filter != t["market_all"]:
            df = df[df["Market"] == market_filter]

        if search:
            mask = df["Symbol"].str.contains(search.upper(), na=False) | df["Base"].str.contains(search.upper(), na=False)
            df = df[mask]

        extreme_df = df[df["Imbalance %"].abs() >= threshold_pct]
        if not extreme_df.empty:
            st.subheader(t["extreme_header"].format(threshold=threshold_pct))
            st.dataframe(
                extreme_df.sort_values("Imbalance %", key=abs, ascending=False)[
                    ["Market", "Symbol", "Imbalance %", "Health", "Notional USDT"]
                ].head(15),
                use_container_width=True, hide_index=True,
            )

        df = df.sort_values(sort_by, ascending=False).head(top_n)

        st.subheader(t["liquidity_map"])
        fig = px.scatter(
            df, x="Imbalance %", y="Health", size="Notional USDT",
            color="Combined Entropy", symbol="Market", hover_name="Symbol",
            color_continuous_scale="Viridis", labels={"Combined Entropy": t["entropy_label"]},
        )
        fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(15,23,42,0.8)", height=420,
                          xaxis=dict(zeroline=True, zerolinecolor="#475569"))
        fig.add_vline(x=0, line_dash="dot", line_color="#64748b")
        fig.add_vline(x=threshold_pct, line_dash="dash", line_color="#22c55e", opacity=0.4)
        fig.add_vline(x=-threshold_pct, line_dash="dash", line_color="#ef4444", opacity=0.4)
        st.plotly_chart(fig, use_container_width=True)

        col_l, col_r = st.columns(2)
        cols = ["Market", "Symbol", "Imbalance %", "Health", "Notional USDT"]
        with col_l:
            st.subheader(t["top_bid"])
            st.dataframe(df.nlargest(15, "Imbalance %")[cols], use_container_width=True, hide_index=True)
        with col_r:
            st.subheader(t["top_ask"])
            st.dataframe(df.nsmallest(15, "Imbalance %")[cols], use_container_width=True, hide_index=True)

        st.subheader(t["all_coins"])
        display_df = df.drop(columns=["_key"], errors="ignore").copy()
        for col, fmt in [
            ("Imbalance %", lambda x: f"{x:+.2f}"),
            ("Weighted Imb. %", lambda x: f"{x:+.2f}"),
            ("Health", lambda x: f"{x:.1f}"),
            ("Combined Entropy", lambda x: f"{x:.3f}"),
            ("Spread bps", lambda x: f"{x:.2f}"),
            ("Notional USDT", lambda x: f"{x:,.0f}"),
        ]:
            display_df[col] = display_df[col].map(fmt)
        st.dataframe(display_df, use_container_width=True, hide_index=True, height=480)

        options = [f"{row['Market']}:{row['Symbol']}" for _, row in df.iterrows()]
        if options:
            selected = st.selectbox(t["symbol_detail"], options, key=f"detail_{locale}")
            label, sym = selected.split(":", 1)
            m = next((x for x in symbols.values() if x.label == label and x.symbol == sym), None)
            if m:
                d1, d2 = st.columns([1, 2])
                with d1:
                    st.markdown(f"### {m.label} · {m.symbol}")
                    st.markdown(f"""
| {t['detail_metric']} | {t['detail_value']} |
|---------|----------|
| {t['detail_imbalance']} | **{m.imbalance * 100:+.2f}%** |
| {t['detail_weighted']} | **{m.weighted_imbalance * 100:+.2f}%** |
| {t['detail_health']} | **{m.health_score:.1f}** / 100 |
| {t['detail_entropy']} | {m.bid_entropy:.3f} / {m.ask_entropy:.3f} |
| {t['detail_spread']} | {m.spread_bps:.2f} bps |
| {t['detail_notional']} | ${m.total_notional_usdt:,.0f} |
""")
                    if abs(m.imbalance * 100) >= threshold_pct:
                        sev = "CRITICAL" if abs(m.imbalance) >= critical_pct / 100 else "EXTREME"
                        st.error(t["detail_alert"].format(severity=sev, imbalance=m.imbalance * 100))
                with d2:
                    gauge = go.Figure(go.Indicator(
                        mode="gauge+number+delta", value=m.imbalance * 100,
                        title={"text": "Liquidity Imbalance"}, delta={"reference": 0},
                        gauge={
                            "axis": {"range": [-100, 100]},
                            "bar": {"color": _imbalance_color(m.imbalance * 100)},
                            "steps": [
                                {"range": [-100, -threshold_pct], "color": "rgba(239,68,68,0.25)"},
                                {"range": [-threshold_pct, threshold_pct], "color": "rgba(148,163,184,0.15)"},
                                {"range": [threshold_pct, 100], "color": "rgba(34,197,94,0.25)"},
                            ],
                        },
                    ))
                    gauge.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", height=280)
                    st.plotly_chart(gauge, use_container_width=True)

        last_msg = max((s.last_message_at for s in snaps.values() if s.last_message_at), default=0.0)
        lag = time.time() - last_msg if last_msg else 0.0
        st.caption(t["footer"].format(
            time=datetime.now().strftime("%H:%M:%S"), mode=mode_label,
            msgs=int(agg["messages_total"]), lag=lag, liq=agg["total_notional_m"],
        ))

    return live_panel


def run_dashboard(locale: str) -> None:
    t = TEXTS[locale]
    live_panel = _make_live_panel(locale)

    st.set_page_config(page_title=t["page_title"], page_icon="📊", layout="wide", initial_sidebar_state="expanded")
    st.markdown(_css(), unsafe_allow_html=True)
    st.title(t["page_title"])
    st.markdown(f'<p class="subtitle">{t["subtitle"]}</p>', unsafe_allow_html=True)

    demo_key = f"demo_active_{locale}"
    demo_data_key = f"demo_data_{locale}"

    with st.sidebar:
        st.header(t["sidebar_exchange"])
        preset = st.selectbox(
            t["exchange_preset"],
            options=list(t["presets"].keys()),
            format_func=lambda k: t["presets"][k],
        )

        st.header(t["sidebar_settings"])
        min_volume = st.slider(t["min_volume"], 0, MIN_VOLUME_MAX, 100_000, MIN_VOLUME_STEP)
        all_labels = [t["market_all"]] + [cfg.label for cfg in SOURCES.values()]
        market_filter = st.selectbox(t["market_filter"], sorted(set(all_labels), key=lambda x: (x != t["market_all"], x)))
        search = st.text_input(t["search"], placeholder=t["search_ph"])
        sort_by = st.selectbox(t["sort_by"], [
            "Imbalance %", "Weighted Imb. %", "Health", "Combined Entropy", "Notional USDT", "Spread bps",
        ], index=0)
        top_n = st.selectbox(t["show_rows"], [50, 100, 200, 500, 1000], index=2)

        st.divider()
        st.header(t["sidebar_demo"])
        if st.button(t["load_demo"], use_container_width=True, type="primary"):
            data = load_demo_csv()
            st.session_state[demo_data_key] = data
            st.session_state[demo_key] = True
            st.rerun()

        st.download_button(
            t["download_demo"], data=demo_csv_bytes(),
            file_name="demo_data.csv", mime="text/csv", use_container_width=True,
        )

        uploaded = st.file_uploader(t["upload_csv"], type=["csv"])
        if uploaded is not None:
            try:
                df_up = pd.read_csv(uploaded)
                data = {metrics_from_upload_row(r).key: metrics_from_upload_row(r) for r in df_up.to_dict("records")}
                st.session_state[demo_data_key] = data
                st.session_state[demo_key] = True
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        if st.session_state.get(demo_key):
            if st.button(t["exit_demo"], use_container_width=True):
                st.session_state[demo_key] = False
                st.session_state.pop(demo_data_key, None)
                st.rerun()

        st.divider()
        st.header(t["sidebar_alerts"])
        alerts_enabled = st.toggle(t["alerts_enable"], value=True)
        threshold_pct = st.slider(t["threshold_extreme"], 20, 80, 40, 5)
        critical_pct = st.slider(t["threshold_critical"], 40, 95, 60, 5)
        cooldown_sec = st.slider(t["cooldown"], 15, 300, 60, 15)

        st.divider()
        st.caption(t["no_email_note"])
        st.markdown(t["metrics_help"])

    live_panel(preset, min_volume, search, market_filter, sort_by, top_n,
               alerts_enabled, threshold_pct, critical_pct, cooldown_sec)


def metrics_from_upload_row(row: dict) -> SymbolMetrics:
    from engine import metrics_from_row
    return metrics_from_row({k: str(v) for k, v in row.items()})
