import streamlit as st
import streamlit.components.v1 as components
import requests
import yfinance as yf
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

st.set_page_config(
    page_title="Oil Alerts",
    page_icon="🛢️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

STORAGE_FILE = Path(__file__).parent / "alerts_config.json"

def load_config():
    defaults = {
        "wti_high": 105.0,
        "wti_low": 95.0,
        "brent_high": 115.0,
        "brent_low": 105.0,
        "sound_enabled": True,
        "vibrate_enabled": True,
        "telegram_enabled": False,
        "telegram_token": "",
        "telegram_chat_id": ""
    }
    if STORAGE_FILE.exists():
        try:
            with open(STORAGE_FILE, "r") as f:
                data = json.load(f)
                defaults.update(data)
        except Exception:
            pass
    return defaults

def save_config(cfg: dict):
    try:
        with open(STORAGE_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        st.warning(f"Could not save settings: {e}")

if "config" not in st.session_state:
    st.session_state.config = load_config()

cfg = st.session_state.config

def send_telegram(message: str) -> bool:
    token = cfg.get("telegram_token", "").strip()
    chat_id = cfg.get("telegram_chat_id", "").strip()
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception:
        return False

st.markdown("""
<style>
    .stApp { background-color: #0f172a !important; color: #e2e8f0 !important; }
    header[data-testid="stHeader"] { background-color: #0f172a !important; }
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 4rem !important;
        max-width: 480px !important;
    }
    h1, h2, h3, p, span, label, div { color: #e2e8f0 !important; }
    .price-card {
        background: linear-gradient(145deg, #1e293b, #0f172a);
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 1.1rem 0.8rem;
        text-align: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    }
    .price-label {
        font-size: 0.85rem;
        color: #94a3b8 !important;
        margin-bottom: 0.3rem;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }
    .price-value {
        font-size: 2.4rem;
        font-weight: 700;
        line-height: 1.1;
        margin: 0.15rem 0;
    }
    .price-change { font-size: 1.05rem; font-weight: 600; }
    .up { color: #22c55e !important; }
    .down { color: #ef4444 !important; }
    .event-card {
        background: #1e293b;
        border-radius: 12px;
        padding: 0.85rem 1rem;
        margin-bottom: 0.7rem;
        border-left: 4px solid #64748b;
    }
    .event-high { border-left-color: #ef4444 !important; }
    .event-medium { border-left-color: #f59e0b !important; }
    .stButton > button {
        width: 100%;
        border-radius: 12px;
        height: 3.1rem;
        font-size: 1.05rem;
        font-weight: 600;
        background: #1e40af !important;
        color: white !important;
        border: none !important;
    }
    .stButton > button:hover { background: #1d4ed8 !important; }
    .stNumberInput input, .stTextInput input {
        background-color: #1e293b !important;
        color: #e2e8f0 !important;
        border: 1px solid #334155 !important;
        border-radius: 10px !important;
    }
    .section-title {
        font-size: 1.05rem;
        font-weight: 600;
        color: #94a3b8 !important;
        margin: 1.4rem 0 0.7rem 0;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    .alert-banner {
        background: #7f1d1d;
        color: #fecaca !important;
        padding: 0.9rem 1rem;
        border-radius: 12px;
        margin: 0.6rem 0;
        font-weight: 600;
        text-align: center;
    }
    #MainMenu, footer, header {visibility: hidden;}
    .stDeployButton {display: none;}
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=45)
def get_prices():
    result = {"wti": None, "brent": None}
    try:
        r = requests.get("https://americasoilwatch.com/api/v1/wti", timeout=7)
        if r.ok:
            d = r.json()
            price = d.get("price") or d.get("value") or d.get("wti")
            if price:
                result["wti"] = {"price": float(price), "source": "AmericasOilWatch"}
    except Exception:
        pass

    try:
        tickers = yf.Tickers("CL=F BZ=F")
        for symbol, key in [("CL=F", "wti"), ("BZ=F", "brent")]:
            hist = tickers.tickers[symbol].history(period="5d")
            if not hist.empty:
                last = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else last
                change = float(last["Close"] - prev["Close"])
                pct = (change / float(prev["Close"])) * 100
                result[key] = {
                    "price": round(float(last["Close"]), 2),
                    "change": round(change, 2),
                    "pct": round(pct, 2),
                    "high": round(float(last["High"]), 2),
                    "low": round(float(last["Low"]), 2),
                    "source": "Yahoo Finance"
                }
    except Exception as e:
        st.error(f"Price error: {e}")
    return result

@st.cache_data(ttl=300)
def get_calendar_events():
    try:
        r = requests.get("https://pipatlas.com/api/calendar", timeout=10)
        r.raise_for_status()
        return r.json().get("events", [])
    except Exception:
        return []

def is_oil_relevant(name: str) -> bool:
    keys = ["eia", "crude", "inventory", "inventories", "opec", "nfp",
            "non-farm", "payroll", "fomc", "fed", "rate decision",
            "pce", "cpi", "petroleum", "oil"]
    name = name.lower()
    return any(k in name for k in keys)

def parse_event_time(date_str):
    if not date_str:
        return None
    try:
        if date_str.endswith("Z"):
            date_str = date_str[:-1] + "+00:00"
        return datetime.fromisoformat(date_str).astimezone(timezone.utc)
    except Exception:
        return None

def play_alert_sound_and_vibrate(enabled_sound=True, enabled_vibrate=True):
    js = f"""
    <script>
    (function() {{
        if ({str(enabled_sound).lower()}) {{
            try {{
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.frequency.value = 880;
                osc.type = "sine";
                gain.gain.setValueAtTime(0.3, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.4);
            }} catch(e) {{}}
        }}
        if ({str(enabled_vibrate).lower()} && navigator.vibrate) {{
            navigator.vibrate([200, 100, 200]);
        }}
    }})();
    </script>
    """
    components.html(js, height=0)

st.markdown("<h1 style='text-align:center; font-size:1.6rem; margin-bottom:0.3rem;'>🛢️ Oil Alerts</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center; color:#64748b; font-size:0.9rem; margin-top:0;'>WTI + Brent • Telegram push</p>", unsafe_allow_html=True)

if st.button("🔄 Refresh Prices & Events"):
    st.cache_data.clear()
    st.rerun()

prices = get_prices()
wti = prices.get("wti")
brent = prices.get("brent")

st.markdown('<div class="section-title">Current Prices</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)
alert_messages = []

def render_price_card(col, label, data, high_key, low_key):
    with col:
        if data:
            price = data["price"]
            pct = data.get("pct", 0) or 0
            change = data.get("change", 0) or 0
            cls = "up" if pct >= 0 else "down"
            arrow = "▲" if pct >= 0 else "▼"

            st.markdown(f"""
            <div class="price-card">
                <div class="price-label">{label}</div>
                <div class="price-value">${price:.2f}</div>
                <div class="price-change {cls}">{arrow} {change:+.2f} ({pct:+.2f}%)</div>
            </div>
            """, unsafe_allow_html=True)

            high = cfg[high_key]
            low = cfg[low_key]
            if price >= high:
                msg = f"🚨 {label} ABOVE ${high:.2f} → now ${price:.2f}"
                st.markdown(f'<div class="alert-banner">{msg}</div>', unsafe_allow_html=True)
                alert_messages.append(msg)
                return True
            elif price <= low:
                msg = f"🚨 {label} BELOW ${low:.2f} → now ${price:.2f}"
                st.markdown(f'<div class="alert-banner">{msg}</div>', unsafe_allow_html=True)
                alert_messages.append(msg)
                return True
        else:
            st.markdown(f"""
            <div class="price-card">
                <div class="price-label">{label}</div>
                <div class="price-value">—</div>
                <div style="color:#64748b;">No data</div>
            </div>
            """, unsafe_allow_html=True)
        return False

triggered = False
triggered |= render_price_card(col1, "WTI", wti, "wti_high", "wti_low")
triggered |= render_price_card(col2, "Brent", brent, "brent_high", "brent_low")

if triggered:
    if cfg.get("sound_enabled") or cfg.get("vibrate_enabled"):
        play_alert_sound_and_vibrate(
            enabled_sound=cfg.get("sound_enabled", True),
            enabled_vibrate=cfg.get("vibrate_enabled", True)
        )
    if cfg.get("telegram_enabled") and alert_messages:
        full_msg = "<b>Oil Alert</b>\n\n" + "\n".join(alert_messages)
        full_msg += f"\n\n{datetime.now().strftime('%Y-%m-%d %H:%M')}"
        ok = send_telegram(full_msg)
        if ok:
            st.success("Telegram alert sent")
        else:
            st.warning("Telegram failed – check token & chat ID")

st.markdown('<div class="section-title">Alert Levels (Saved)</div>', unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    new_wti_high = st.number_input("WTI High $", value=float(cfg["wti_high"]), step=0.5, format="%.2f", key="wti_h")
    new_wti_low = st.number_input("WTI Low $", value=float(cfg["wti_low"]), step=0.5, format="%.2f", key="wti_l")
with c2:
    new_brent_high = st.number_input("Brent High $", value=float(cfg["brent_high"]), step=0.5, format="%.2f", key="brent_h")
    new_brent_low = st.number_input("Brent Low $", value=float(cfg["brent_low"]), step=0.5, format="%.2f", key="brent_l")

sound_on = st.checkbox("🔊 Sound on alert", value=cfg.get("sound_enabled", True))
vibrate_on = st.checkbox("📳 Vibrate on alert (mobile)", value=cfg.get("vibrate_enabled", True))

st.markdown('<div class="section-title">Telegram Push Alerts</div>', unsafe_allow_html=True)
tg_enabled = st.checkbox("Enable Telegram alerts", value=cfg.get("telegram_enabled", False))
tg_token = st.text_input("Bot Token", value=cfg.get("telegram_token", ""), type="password")
tg_chat = st.text_input("Chat ID", value=cfg.get("telegram_chat_id", ""))

if st.button("💾 Save All Settings"):
    new_cfg = {
        "wti_high": new_wti_high,
        "wti_low": new_wti_low,
        "brent_high": new_brent_high,
        "brent_low": new_brent_low,
        "sound_enabled": sound_on,
        "vibrate_enabled": vibrate_on,
        "telegram_enabled": tg_enabled,
        "telegram_token": tg_token.strip(),
        "telegram_chat_id": tg_chat.strip()
    }
    st.session_state.config = new_cfg
    save_config(new_cfg)
    st.success("Settings saved permanently")
    st.rerun()

if cfg.get("telegram_token") and cfg.get("telegram_chat_id"):
    if st.button("📤 Send Test Telegram Message"):
        ok = send_telegram("✅ Oil Alerts test message – your Telegram is connected.")
        if ok:
            st.success("Test message sent successfully")
        else:
            st.error("Failed. Double-check token and chat ID.")

st.markdown('<div class="section-title">Upcoming Oil Events</div>', unsafe_allow_html=True)

events = get_calendar_events()
now = datetime.now(timezone.utc)
relevant = []

for e in events:
    name = e.get("name") or ""
    if not is_oil_relevant(name):
        continue
    etime = parse_event_time(e.get("date"))
    if etime and etime > now - timedelta(hours=8):
        hours = (etime - now).total_seconds() / 3600
        relevant.append({
            "name": name,
            "impact": e.get("impact", "Unknown"),
            "currency": e.get("currency", ""),
            "date": etime,
            "hours": hours,
            "forecast": e.get("forecast"),
            "previous": e.get("previous"),
            "actual": e.get("actual")
        })

relevant.sort(key=lambda x: x["date"])

if relevant:
    for ev in relevant[:10]:
        impact = (ev["impact"] or "").lower()
        css = "event-high" if impact == "high" else "event-medium"
        time_str = ev["date"].strftime("%a %b %d • %H:%M UTC")
        hours_txt = f"in {ev['hours']:.1f}h" if ev["hours"] > 0 else "recent"
        st.markdown(f"""
        <div class="event-card {css}">
            <strong>{ev['name']}</strong> <span style="color:#94a3b8">({ev['currency']})</span><br>
            <small style="color:#94a3b8">{time_str} • {hours_txt} • {ev['impact']}</small><br>
            <small>Prev: {ev.get('previous') or '—'} | Fcst: {ev.get('forecast') or '—'} | Act: {ev.get('actual') or '—'}</small>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("No major oil-related events in the current window.")

st.markdown("<br>", unsafe_allow_html=True)
st.caption("Free public data • Not financial advice")
