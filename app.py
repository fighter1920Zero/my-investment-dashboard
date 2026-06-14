import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
import requests
import re
import io
from datetime import datetime

# Set up page configurations
st.set_page_config(
    page_title="Advanced Portfolio Analytics",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Premium Dark/Glassmorphic Aesthetics and Responsive Elements
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Noto+Sans+TC:wght@300;400;500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', 'Noto Sans TC', sans-serif;
    }
    
    /* Top Header Bar */
    .banner {
        background: linear-gradient(135deg, #090d16 0%, #1e1b4b 50%, #311042 100%);
        padding: 1.8rem;
        border-radius: 20px;
        margin-bottom: 1.5rem;
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
    }
    .banner-title {
        font-weight: 700;
        font-size: 2.2rem;
        background: linear-gradient(135deg, #38bdf8 0%, #c084fc 50%, #f43f5e 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.3rem;
    }
    .banner-subtitle {
        color: #94a3b8;
        font-size: 1rem;
        font-weight: 300;
    }
    
    /* Glassmorphic KPI Cards */
    .kpi-card {
        background: rgba(15, 23, 42, 0.55);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 1.2rem;
        text-align: center;
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.4);
        transition: all 0.3s ease;
    }
    .kpi-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 24px -5px rgba(99, 102, 241, 0.15);
        border-color: rgba(99, 102, 241, 0.3);
    }
    .kpi-label {
        font-size: 0.8rem;
        color: #94a3b8;
        margin-bottom: 0.4rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    .kpi-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #ffffff;
    }
    
    /* Recommendations & Signals */
    .rec-badge {
        display: inline-block;
        padding: 0.35rem 0.85rem;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 0.85rem;
        text-align: center;
    }
    .rec-strong-buy { background-color: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid #10b981; }
    .rec-buy { background-color: rgba(52, 211, 153, 0.15); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.4); }
    .rec-neutral { background-color: rgba(148, 163, 184, 0.15); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.4); }
    .rec-sell { background-color: rgba(244, 63, 94, 0.15); color: #f43f5e; border: 1px solid rgba(244, 63, 94, 0.4); }
    .rec-strong-sell { background-color: rgba(225, 29, 72, 0.2); color: #e11d48; border: 1px solid #e11d48; }

    /* Indicator Encyclopedia card */
    .encyclo-card {
        background: rgba(30, 41, 59, 0.3);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 8px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.5rem;
    }
    
    /* Mobile-specific lists */
    .mobile-list-item {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 0.75rem;
    }
    
    /* View mode button layout overrides */
    div[data-testid="stHorizontalBlock"] {
        align-items: center;
    }
</style>
""", unsafe_allow_html=True)

# --- Dynamic Slicing & Parsing Logic (Defensive) ---

def clean_val(val):
    if not val:
        return 0.0
    val_str = str(val).strip().replace(',', '').replace('$', '').replace('NT$', '').replace('%', '')
    if val_str in ['', '#N/A', '#REF!', '-', 'NaN', 'nan']:
        return 0.0
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def parse_tw_code_name(cell):
    cell_str = str(cell).strip()
    match = re.match(r"^(\d+)(.*)", cell_str)
    if match:
        return match.group(1), match.group(2).strip()
    return cell_str, ""

def parse_fund_code_name(cell):
    cell_str = str(cell).strip()
    match = re.match(r"^([A-Za-z0-9]+)(.*)", cell_str)
    if match:
        return match.group(1), match.group(2).strip()
    return cell_str, ""

def parse_sheet_to_sections(rows):
    """
    Dynamically scans rows for section headers (containing "起始日" and "持有股數").
    Splits rows list into 3 raw section blocks without index hardcoding.
    """
    sections = []
    current_section = []
    
    for row in rows:
        if not row:
            continue
        row_str_list = [str(cell).strip() for cell in row]
        
        # Check for header indicator
        if "起始日" in row_str_list and "持有股數" in row_str_list:
            if current_section:
                sections.append(current_section)
                current_section = []
            continue
            
        # Skip fully blank rows
        if all(cell.strip() == '' for cell in row):
            continue
            
        current_section.append(row)
        
    if current_section:
        sections.append(current_section)
        
    return sections

def clean_section_rows(section_rows, sec_type):
    """
    Filters out totals, subtotals, and empty ticker rows from sections.
    Standardizes ticker codes.
    """
    cleaned = []
    for r in section_rows:
        if not r or len(r) == 0:
            continue
        code_cell = str(r[0]).strip()
        
        # Filter out obvious subtotals or descriptions
        if not code_cell or any(k in code_cell for k in ["小計", "合計", "總計", "總成本", "起始日"]):
            continue
            
        shares = clean_val(r[3])
        if shares <= 0:
            continue
            
        # Type-specific validation and extraction
        if sec_type == 'TW':
            code, name = parse_tw_code_name(code_cell)
            if not code.isdigit(): # Taiwan stock must start with numeric digit
                continue
            cleaned.append({
                'code': code,
                'name': name,
                'shares': shares,
                'avg_cost': clean_val(r[4]),
                'cost_twd': clean_val(r[5]),
                'sheet_price': clean_val(r[8]),
                'start_date': str(r[1]).strip()
            })
        elif sec_type == 'US':
            code = code_cell
            if not code.isalpha(): # US stock must be letters only
                continue
            cleaned.append({
                'code': code,
                'shares': shares,
                'avg_cost': clean_val(r[4]),
                'cost_ntd': clean_val(r[5]),
                'cost_usd': clean_val(r[6]),
                'sheet_price': clean_val(r[8]),
                'start_date': str(r[1]).strip()
            })
        elif sec_type == 'FUND':
            code, name = parse_fund_code_name(code_cell)
            # Fund codes are typically 6-character alphanumeric (e.g. 002003, ABI043)
            if len(code) < 5:
                continue
            cleaned.append({
                'code': code,
                'name': name,
                'shares': shares,
                'avg_cost': clean_val(r[4]),
                'cost_ntd': clean_val(r[5]),
                'cost_usd': clean_val(r[6]),
                'sheet_price': clean_val(r[8]),
                'start_date': str(r[1]).strip()
            })
            
    return cleaned

# --- Custom Technical Indicator Calculations (Zero-dependency Pandas) ---

def calculate_technical_indicators(df):
    """
    Calculates 8 technical indicators using optimized pandas/numpy calculations.
    Returns a dictionary of Pandas Series.
    """
    close = df['Close'].ffill().bfill()
    high = df['High'].ffill().bfill()
    low = df['Low'].ffill().bfill()
    volume = df['Volume'].ffill().bfill()
    open_val = df['Open'].ffill().bfill()
    
    # Ensure they are flat Series
    if isinstance(close, pd.DataFrame): close = close.iloc[:, 0]
    if isinstance(high, pd.DataFrame): high = high.iloc[:, 0]
    if isinstance(low, pd.DataFrame): low = low.iloc[:, 0]
    if isinstance(volume, pd.DataFrame): volume = volume.iloc[:, 0]
    if isinstance(open_val, pd.DataFrame): open_val = open_val.iloc[:, 0]
    
    # 1. RSI (14-day Wilder's)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(50)
    
    # 2. Bias (20-day)
    sma_20 = close.rolling(window=20).mean()
    bias = ((close - sma_20) / sma_20) * 100
    bias = bias.fillna(0)
    
    # 3. MACD (12, 26, 9)
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - signal_line
    
    # 4. Bollinger Bands (20-day, 2 std) %B Value
    std_20 = close.rolling(window=20).std()
    upper_band = sma_20 + 2 * std_20
    lower_band = sma_20 - 2 * std_20
    percent_b = ((close - lower_band) / (upper_band - lower_band).replace(0, np.nan)) * 100
    percent_b = percent_b.fillna(50)
    
    # 5. KD (Stochastic 9, 3, 3)
    lowest_low = low.rolling(window=9).min()
    highest_high = high.rolling(window=9).max()
    rsv = ((close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)) * 100
    rsv = rsv.fillna(50)
    k_vals, d_vals = [], []
    curr_k, curr_d = 50.0, 50.0
    for r in rsv:
        curr_k = (2/3) * curr_k + (1/3) * r
        curr_d = (2/3) * curr_d + (1/3) * curr_k
        k_vals.append(curr_k)
        d_vals.append(curr_d)
    k_series = pd.Series(k_vals, index=close.index)
    d_series = pd.Series(d_vals, index=close.index)
    
    # 6. ATR (14-day)
    close_prev = close.shift(1)
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False).mean()
    atr_sma_20 = atr.rolling(window=20).mean().fillna(0)
    atr = atr.fillna(0)
    
    # 7. OBV
    direction = np.sign(close.diff()).fillna(0)
    obv = (direction * volume).cumsum()
    obv_sma_10 = obv.rolling(window=10).mean().fillna(0)
    
    # 8. CCI (20-day)
    tp = (high + low + close) / 3
    sma_tp = tp.rolling(window=20).mean()
    md = tp.rolling(window=20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    cci = (tp - sma_tp) / (0.015 * md.replace(0, np.nan))
    cci = cci.fillna(0)
    
    return {
        'RSI': rsi,
        'Bias': bias,
        'MACD_line': macd_line,
        'MACD_signal': signal_line,
        'MACD_hist': macd_hist,
        'BB_upper': upper_band,
        'BB_lower': lower_band,
        'BB_percent_b': percent_b,
        'K': k_series,
        'D': d_series,
        'ATR': atr,
        'ATR_SMA_20': atr_sma_20,
        'OBV': obv,
        'OBV_SMA_10': obv_sma_10,
        'CCI': cci,
        'SMA_20': sma_20,
        'Close': close,
        'Open': open_val,
        'High': high,
        'Low': low,
        'Volume': volume
    }

# --- yfinance Data Loader with Caching ---

@st.cache_data(ttl=300)
def fetch_indicators_dataset(tickers):
    """
    Downloads historical data and pre-computes indicators for a list of tickers.
    If downloading fails or returns empty for Taiwan stocks, falls back to .TWO (OTC market) automatically.
    Downloads 3 years of history to support portfolio performance trend charts.
    """
    dataset = {}
    for t in tickers:
        try:
            df = yf.download(t, period='3y', progress=False)
            if df.empty or len(df) < 20:
                if t.endswith('.TW'):
                    fallback_t = t.replace('.TW', '.TWO')
                    df = yf.download(fallback_t, period='3y', progress=False)
                    if df.empty or len(df) < 20:
                        continue
                else:
                    continue
            dataset[t] = calculate_technical_indicators(df)
        except Exception as e:
            st.sidebar.warning(f"無法下載 {t} 數據: {e}")
    return dataset


@st.cache_data(ttl=3600)
def fetch_stock_chart_data(ticker):
    """
    Downloads up to 10 years of historical data for a single stock.
    Falls back to .TWO (OTC market) for Taiwan stocks if .TW is empty.
    Calculates technical indicators on the full history.
    """
    try:
        df = yf.download(ticker, period='10y', progress=False)
        if df.empty or len(df) < 20:
            if ticker.endswith('.TW'):
                fallback_t = ticker.replace('.TW', '.TWO')
                df = yf.download(fallback_t, period='10y', progress=False)
                if df.empty or len(df) < 20:
                    return None
            else:
                return None
        return calculate_technical_indicators(df)
    except Exception as e:
        st.sidebar.warning(f"無法下載 {ticker} 10年數據: {e}")
        return None


@st.cache_data(ttl=600)
def generate_fund_market_data(funds_list_dict):
    """
    Simulates daily NAV data for funds and computes 5 fund technical metrics.
    Supports a 10-year period (or back to the buy date if older).
    All fields are read using .get() for absolute crash prevention.
    """
    results = {}
    for item in funds_list_dict:
        code = item.get('code', 'unknown')
        start_date = item.get('start_date', '')
        shares = item.get('shares', 0.0)
        cost_twd = item.get('cost_twd', 0.0)
        latest_nav = item.get('price', 0.0)
        currency = item.get('currency', 'TWD')
        start_nav = item.get('avg_cost', 0.0)
        name = item.get('name', '未命名基金')
        
        # Determine target end NAV and start NAV
        end_nav = latest_nav
        if start_nav <= 0:
            start_nav = end_nav if end_nav > 0 else 10.0
        if end_nav <= 0:
            end_nav = start_nav
            
        # Determine the date range: cover at least 10 years and the purchase date
        end_date = datetime.now()
        ten_years_ago = end_date - pd.Timedelta(days=10*365)
        
        try:
            buy_date_dt = pd.to_datetime(start_date)
            if pd.isna(buy_date_dt):
                buy_date_dt = end_date - pd.Timedelta(days=365)
        except Exception:
            buy_date_dt = end_date - pd.Timedelta(days=365)
            
        sim_start_date = min(ten_years_ago, buy_date_dt)
        
        # Generate business days
        dates = pd.date_range(start=sim_start_date, end=end_date, freq='B')
        num_days = len(dates)
        if num_days < 20:
            # Fallback to at least 252 days if somehow start_date is in the future
            dates = pd.date_range(end=end_date, periods=252, freq='B')
            num_days = len(dates)
            buy_date_dt = dates[0]
            
        # Find index closest to buy_date_dt
        idx_buy = int(np.argmin(np.abs((dates - buy_date_dt).days)))
        
        # Determine volatility
        daily_vol = 0.0025 if any(k in name for k in ["債", "固定收益", "多重收益", "收益成長"]) else 0.0075
        
        # Generate random walk
        np.random.seed(hash(code) % 10000)
        r = np.random.normal(0, daily_vol, num_days)
        W = np.cumsum(r)
        
        # Generate the simulated path using dual Brownian bridge
        nav_series = np.zeros(num_days)
        vol_factor = start_nav * 0.04
        
        # Forward part (buy_date_dt to today)
        if idx_buy < num_days - 1:
            L_fwd = num_days - 1 - idx_buy
            for t in range(idx_buy, num_days):
                tau = (t - idx_buy) / L_fwd
                bridge = W[t] - W[idx_buy] - tau * (W[num_days - 1] - W[idx_buy])
                nav_series[t] = start_nav + tau * (end_nav - start_nav) + bridge * vol_factor
        else:
            nav_series[num_days - 1] = end_nav
            
        # Backward part (start_date to buy_date_dt)
        if idx_buy > 0:
            L_bwd = idx_buy
            # Estimate init_nav based on annualized return during holding
            holding_days = (end_date - buy_date_dt).days
            holding_years = max(holding_days, 1) / 365.25
            annual_return = (end_nav - start_nav) / start_nav / holding_years if start_nav > 0 else 0.05
            annual_return = np.clip(annual_return, -0.2, 0.3)
            bwd_years = (buy_date_dt - sim_start_date).days / 365.25
            
            init_nav = start_nav / (1.0 + annual_return * bwd_years)
            if init_nav <= 0:
                init_nav = start_nav * 0.8
                
            for t in range(idx_buy + 1):
                tau = t / L_bwd
                bridge = W[t] - tau * W[idx_buy]
                nav_series[t] = init_nav + tau * (start_nav - init_nav) + bridge * vol_factor
                
        nav_series = np.clip(nav_series, a_min=0.001, a_max=None)
        close = pd.Series(nav_series, index=dates)
        
        # Compute Indicators
        # 1. RSI (14-day)
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = (100 - (100 / (1 + rs))).fillna(50)
        
        # 2. Bias (20-day)
        sma_20 = close.rolling(window=20).mean()
        bias_20 = (((close - sma_20) / sma_20) * 100).fillna(0)
        
        # 3. Bias (60-day)
        sma_60 = close.rolling(window=60).mean()
        bias_60 = (((close - sma_60) / sma_60) * 100).fillna(0)
        
        # 4. Drawdown
        peak = close.cummax()
        drawdown = (((close - peak) / peak) * 100).fillna(0)
        
        # 5. Volatility (annualized daily std over 30 days)
        daily_returns = close.pct_change().fillna(0)
        vol_30 = (daily_returns.rolling(window=30).std() * np.sqrt(252) * 100).fillna(0)
        
        results[code] = {
            'RSI': rsi,
            'Bias_20': bias_20,
            'Bias_60': bias_60,
            'Drawdown': drawdown,
            'Volatility': vol_30,
            'Close': close,
            'SMA_20': sma_20,
            'SMA_60': sma_60
        }
    return results

def render_purchase_card(row_data, title="個股買進日資訊", is_fund=False):
    """
    Renders a responsive, premium glassmorphic HTML card with purchase statistics.
    Includes simple annualized return (only calculated if holding >= 30 days).
    """
    # Defensive gets
    buy_date_str = str(row_data.get('start_date', 'N/A')).strip()
    shares = row_data.get('shares', 0.0)
    avg_cost = row_data.get('avg_cost', 0.0)
    cost_twd = row_data.get('cost_twd', 0.0)
    market_val_twd = row_data.get('market_val_twd', 0.0)
    price = row_data.get('price', 0.0)
    roi = row_data.get('roi', 0.0)
    pnl_twd = row_data.get('pnl_twd', 0.0)
    currency = row_data.get('currency', 'TWD')
    
    # Calculate holding days
    holding_days = 0
    holding_days_str = "N/A"
    if buy_date_str and buy_date_str != 'N/A':
        try:
            buy_date = pd.to_datetime(buy_date_str)
            holding_days = (datetime.now() - buy_date).days
            holding_days_str = f"{holding_days} 天"
        except Exception:
            pass
            
    # Format currency values
    price_format = f"{price:,.4f}" if is_fund else f"{price:,.2f}"
    
    # Color code ROI and PnL
    roi_color = "#10b981" if roi >= 0 else "#f43f5e"
    roi_sign = "+" if roi >= 0 else ""
    pnl_color = "#10b981" if pnl_twd >= 0 else "#f43f5e"
    pnl_sign = "+" if pnl_twd >= 0 else ""
    
    # Calculate simple annualized return
    if holding_days >= 30:
        ann_ret = roi * (365.25 / holding_days)
        ann_ret_sign = "+" if ann_ret >= 0 else ""
        ann_ret_color = "#10b981" if ann_ret >= 0 else "#f43f5e"
        annualized_return_html = f"<span style='color: {ann_ret_color}; font-weight: 700;'>{ann_ret_sign}{ann_ret:.2f}%</span>"
    else:
        annualized_return_html = "<span style='color: #94a3b8; font-weight: 500;'>未滿1個月</span>"
        
    st.markdown(f"""
    <div style="background: rgba(15, 23, 42, 0.65); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 16px; padding: 1.25rem; margin-bottom: 1.25rem; box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.4);">
        <div style="font-size: 1.05rem; font-weight: 600; color: #38bdf8; margin-bottom: 0.8rem; display: flex; align-items: center; gap: 0.5rem;">
            <span>💳</span> {title}
        </div>
        <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 1rem;">
            <div style="flex: 1; min-width: 140px;">
                <div style="font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em;">買進日期 / 歷程</div>
                <div style="font-size: 1.15rem; font-weight: 700; color: #ffffff; margin-top: 0.2rem;">{buy_date_str} <span style="font-size: 0.8rem; color: #38bdf8; font-weight: 500;">({holding_days_str})</span></div>
            </div>
            <div style="flex: 1; min-width: 140px;">
                <div style="font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em;">持股數量 / 均價</div>
                <div style="font-size: 1.15rem; font-weight: 700; color: #ffffff; margin-top: 0.2rem;">{shares:,.2f} <span style="font-size: 0.8rem; color: #94a3b8; font-weight: 500;">@ {avg_cost:,.2f} {currency}</span></div>
            </div>
            <div style="flex: 1; min-width: 140px;">
                <div style="font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em;">投入成本 / 市值</div>
                <div style="font-size: 1.15rem; font-weight: 700; color: #ffffff; margin-top: 0.2rem;">NT$ {cost_twd:,.0f} <span style="font-size: 0.8rem; color: #c084fc; font-weight: 500;">(NT$ {market_val_twd:,.0f})</span></div>
            </div>
            <div style="flex: 1; min-width: 140px;">
                <div style="font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em;">最新價格 / 未實現損益</div>
                <div style="font-size: 1.15rem; font-weight: 700; color: #ffffff; margin-top: 0.2rem;">{price_format} {currency} <span style="font-size: 0.85rem; color: {pnl_color}; font-weight: 700;">({pnl_sign}NT$ {pnl_twd:,.0f})</span></div>
            </div>
            <div style="flex: 1; min-width: 140px;">
                <div style="font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em;">投資報酬率 / 年化報酬率</div>
                <div style="font-size: 1.15rem; font-weight: 700; color: {roi_color}; margin-top: 0.2rem;">{roi_sign}{roi:.2f}% <span style="font-size: 0.85rem; color: #cbd5e1; font-weight: 500;">(年化: {annualized_return_html})</span></div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def clean_html_tags(text):
    if not text:
        return ""
    # Strip HTML tags
    clean = re.sub(r'<.*?>', '', text)
    # Remove HTML entity codes like &nbsp;
    clean = re.sub(r'&[a-zA-Z0-9#]+;', ' ', clean)
    return clean.strip()

def display_asset_news(code, name, asset_type):
    """
    Fetches and displays 3 key news articles for the asset.
    """
    import urllib.parse
    # 1. Clean query name
    query = name
    if asset_type == '美股':
        query = code
    else:
        # Taiwan stock or fund: extract Chinese characters
        query = re.sub(r'^\d+', '', query) # Remove leading numbers
        query = re.sub(r'[A-Za-z\s]+$', '', query) # Remove trailing English
        # Split by typical dividers and take the first valid Chinese part
        parts = re.split(r'[-–()]', query)
        for p in parts:
            p_clean = p.strip()
            if len(p_clean) >= 2:
                query = p_clean
                break
                
    st.markdown(f"##### 📰 {name} 相關重點新聞")
    
    news_items = []
    
    # 2. Try fetching from Google News RSS
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(r.content)
            items = root.findall('.//item')
            for item in items[:3]:
                title = item.find('title').text
                link = item.find('link').text
                desc_elem = item.find('description')
                raw_desc = desc_elem.text if desc_elem is not None else ""
                desc = clean_html_tags(raw_desc)
                
                # Format title: Google News titles often end with " - Publisher"
                title_clean = re.sub(r'\s+-\s+[^-]+$', '', title).strip()
                
                # Limit description to 100 characters
                desc_short = desc[:100]
                if len(desc) > 100:
                    desc_short += "..."
                    
                news_items.append({
                    'title': title_clean,
                    'link': link,
                    'summary': desc_short
                })
    except Exception:
        pass
        
    # 3. Fallback to yfinance news for stocks if Google News yielded nothing
    if len(news_items) == 0 and asset_type in ['台股', '美股']:
        try:
            ticker_obj = yf.Ticker(code + ".TW" if (asset_type == '台股' and not code.endswith('.TW') and not code.endswith('.TWO')) else code)
            yf_news = ticker_obj.news
            if yf_news:
                for item in yf_news[:3]:
                    content = item.get('content', {})
                    if not content:
                        content = item # Fallback for old format
                        
                    title = content.get('title', '無標題')
                    raw_desc = content.get('summary', content.get('description', ''))
                    desc = clean_html_tags(raw_desc)
                    
                    # Get link
                    link = ''
                    can_url = content.get('canonicalUrl', {})
                    if isinstance(can_url, dict):
                        link = can_url.get('url', '')
                    if not link:
                        click_url = content.get('clickThroughUrl', {})
                        if isinstance(click_url, dict):
                            link = click_url.get('url', '')
                    if not link:
                        link = content.get('link', '')
                        
                    desc_short = desc[:100]
                    if len(desc) > 100:
                        desc_short += "..."
                        
                    news_items.append({
                        'title': title,
                        'link': link,
                        'summary': desc_short
                    })
        except Exception:
            pass
            
    # 4. Render News in UI
    if len(news_items) > 0:
        news_html = '<div style="background: rgba(15, 23, 42, 0.4); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 12px; padding: 0.8rem 1rem; margin-bottom: 1.5rem;">'
        for item in news_items:
            news_html += f"""
            <div style="margin-bottom: 0.4rem; text-align: left; padding: 0.2rem 0;">
                <a href="{item['link']}" target="_blank" style="font-size: 0.9rem; font-weight: 500; color: #38bdf8; text-decoration: none;">🔗 {item['title']}</a>
            </div>
            """
        news_html += '</div>'
        st.markdown(news_html, unsafe_allow_html=True)
    else:
        st.info("ℹ️ 暫無此標的之重點新聞報導。")


# --- Google Sheet Loader with Caching ---



def make_export_url(url, gid="1981240361"):
    if "/export" in url:
        return url
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if match:
        spreadsheet_id = match.group(1)
        gid_match = re.search(r"gid=(\d+)", url)
        use_gid = gid_match.group(1) if gid_match else gid
        return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={use_gid}"
    return url

# Default spreadsheet structure fallback
MOCK_CSV_DATA = """2026/6/14,起始日,歷程(日),持有股數,成本均價,付出成本,USD成本,,最新股價,漲跌幅,最高,最低,成交量,本益比 (P/E),每股盈餘 (EPS),市值
00733富邦台灣中小,2025/3/26,445,500,59.63,"29,816",,,70.95,3.58,72.2,70.5,803941,#N/A,#N/A,#N/A
00910第一金太空衛星,2026/6/12,2,"2,000",74.91,"149,813",,,75.25,11.48,75.35,73.1,15208407,#N/A,#N/A,#N/A
00915凱基優選高股息30,2025/3/13,458,"3,000",22.64,"67,915",,,30.73,1.75,31.41,30.65,6109527,#N/A,#N/A,#N/A
1216統一,2025/8/27,291,"3,000",75.27,"225,820",,,76.5,1.19,76.7,75.6,14052495,20.76,3.68,434674147500
1218泰山,2025/10/1,256,"3,000",17.71,"53,121",,,18,-6.25,18.05,17.85,2991793,11.72,1.54,8999982000
2633台灣高鐵,2025/7/2,347,"6,000",26.19,"157,126",,,25.45,0.39,25.6,25.35,4363760,21.06,1.21,143240010244
2707晶華,2025/10/22,235,"1,000",174.38,"174,380",,,179.5,0,180.5,179,123537,12.88,13.93,22868874400
3218大學光,2025/7/2,347,"2,500",156.23,"390,574",,,#N/A,#N/A,#N/A,#N/A,#N/A,#N/A,#N/A,#N/A
9914美利達,2025/5/15,395,"2,000",87.98,"175,967",,,73.4,-0.41,75.4,72.7,3083751,19.91,3.69,21945411376
9921巨大,2025/5/15,395,"1,400",94.30,"132,023",,,75.4,-0.4,77.5,75.2,2613252,190.94,0.39,29561724218
,,,,,,,,,,,,,,,
2026/6/14,起始日,歷程(日),持有股數,成本均價,NTD成本,USD成本,,最新股價,漲跌幅,最高,最低,成交量,本益比 (P/E),每股盈餘 (EPS),市值
META,2025/10/30,227,0.82639,,,500,,566.98,#N/A,576.07,560.9,14347769,20.6,27.52,1439235022961
NVDA,2025/11/20,206,6.95463,,,"1,500",,205.19,#REF!,207.07,203.44,112345314,31.42,6.53,4965598000000
,,,,,,,,,,,,,,,
2026/6/14,起始日,歷程(日),持有股數,成本均價,NTD成本,USD成本,,最新淨值,每日變化,最高淨值(年),最低淨值(年),,,,
002003柏瑞環球基金-柏瑞環球動態資產配置基金 ADC,2020/4/17,2249,543.321,,,"5,000",,8.4414,0.072,8.8165,7.8155,,,,
007114摩根投資基金 - 環球非投資等級債券基金 - JPM環球非投資等級債券 (美元),2025/9/30,257,12.697,,,"1,000",,,,,,,,,
007117摩根投資基金 - 多重收益基金 - JPM多重收益(美元對沖) - A股(穩定月配),2024/10/7,615,12.798,,,"1,000",,,,,,,,,
019002安聯收益成長基金-AM穩定月收類股(美元),2024/7/22,692,360.945,,,"3,000",,,,,,,,,
019033安聯全球永續發展基金-A配息類股(美元),2023/06/28,1082,32.462,,"48,000",,,,,,,,,,
029036聯博-新興市場債券基金AA(穩定月配)級別美元,2020/9/14,2099,415.156,,,"4,000",,,,,,,,,
032099法巴水資源基金/月配RH(美元)【+3000NTD／月28】,2023/06/28,1082,17.953,,"90,000",,,,,,,,,,
033042高盛環球非投資等級債劵基金X股美元(月配息),2024/7/22,692,65.585,,,"3,000",,,,,,,,,
043140富達美元債券基金 (A股月配息美元),2020/9/14,2099,149.03,,,"2,000",,,,,,,,,
052147施羅德環球基金系列－環球目標回報(美元)A-月配固定,2023/06/28,1082,28.79,,"90,000",,,,,,,,,,
ABI043聯博多元資產收益組合基金-AI類型(美元),2024/9/30,622,212.77,,,"2,000",,,,,,,,,
ALI060安聯美國短年期非投資等級債券基金- B類型(月配息)-美元,2023/6/5,1105,348.9,,,"3,000",,,,,,,,,
CIT100好享退-群益積極型,2019/10/28,2421,"29,947.4",,"370,000",,,,,,,,,,
CSI093好享退-國泰2049,2020/9/28,2085,"12,727.8",,"189,000",,,,,,,,,,
FSI028第一金全球水電瓦斯及基礎建設收益基金-配台,2023/06/28,1082,"11,169.4",,"120,000",,,,,,,,,,
NBG029路博邁優質企業債劵證劵投資信託基金T月配(美元),2024/7/22,692,249.08,,,"2,000",,,,,,,,,
SKI021新光全球債券基金(B配息)美元,2023/4/11,1160,331.78,,,"3,000",,,,,,,,,
"""

@st.cache_data(ttl=300)
def load_data_from_sheet(export_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        r = requests.get(export_url, headers=headers, timeout=10)
        if r.status_code == 200:
            import csv
            csv_text = r.content.decode('utf-8-sig')
            reader = csv.reader(io.StringIO(csv_text))
            return list(reader), False
    except Exception:
        pass
    
    # Return mock data as fallback
    import csv
    reader = csv.reader(io.StringIO(MOCK_CSV_DATA))
    return list(reader), True

# --- Side Panel Control ---

st.sidebar.image("https://img.icons8.com/gradient/100/combo-chart.png", width=60)
st.sidebar.title("量化儀表板控制 Panel")

sheet_url = st.sidebar.text_input(
    "Google 試算表 URL",
    value="https://docs.google.com/spreadsheets/d/1jSqcWLStquSw9pYCOMU3niZ-sKwz9wWpZXnaOdPm3x8/edit?usp=sharing"
)

exchange_rate = st.sidebar.number_input(
    "美元匯率 (USD/TWD)",
    min_value=20.0,
    max_value=45.0,
    value=32.5,
    step=0.1
)

if st.sidebar.button("🔄 重載最新數據"):
    st.cache_data.clear()
    st.rerun()

# --- Page Header & Desktop/Mobile Layout Switcher (TOP RIGHT) ---

# Create title and switcher columns
col_title, col_layout = st.columns([5, 2])

with col_title:
    st.markdown("""
    <div style='margin-bottom: 0.5rem;'>
        <h1 style='font-size: 2.2rem; font-weight:700; background: linear-gradient(135deg, #38bdf8 0%, #c084fc 50%, #f43f5e 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>🔮 複合量化投資戰情儀表板</h1>
        <p style='color: #94a3b8; font-size: 0.95rem; margin-top: 0.15rem;'>融合動態試算表解析、8大技術指標與響應式版面切換</p>
    </div>
    """, unsafe_allow_html=True)

with col_layout:
    view_mode = st.radio(
        "版面配置模式 (Layout)",
        ["🖥️ 電腦版 (Desktop)", "📱 手機版 (Mobile)"],
        horizontal=True,
        label_visibility="visible"
    )

is_mobile = (view_mode == "📱 手機版 (Mobile)")

# Load data dynamically
exp_url = make_export_url(sheet_url)
raw_rows, is_using_mock = load_data_from_sheet(exp_url)

if is_using_mock:
    st.warning("⚠️ 載入 Google 試算表失敗，已顯示本機快取資料。請確認您的試算表已設為『知道連結的任何人都能檢視』。")

# Slice and parse sections
sections = parse_sheet_to_sections(raw_rows)

if len(sections) < 3:
    st.error("試算表解析結構不完整（未偵測到三個區塊）。請確認試算表格式包含三個帶有「起始日」及「持有股數」列。")
    st.stop()

# Clean all sections dynamically
tw_stocks = clean_section_rows(sections[0], 'TW')
us_stocks = clean_section_rows(sections[1], 'US')
funds = clean_section_rows(sections[2], 'FUND')

# Ticker setup
tw_tickers = [item['code'] + '.TW' for item in tw_stocks]
us_tickers = [item['code'] for item in us_stocks]
all_tickers = tw_tickers + us_tickers

# Fetch stock indicators
market_indicators = fetch_indicators_dataset(all_tickers)

# --- 8 Indicators Encyclopedia Expander ---
with st.expander("📈 量化技術指標百科與買賣信號說明"):
    st.markdown("""
    <div style='background: rgba(15, 23, 42, 0.3); padding: 1rem; border-radius: 10px; font-size: 0.9rem; line-height: 1.6;'>
        <div class="encyclo-card">
            <strong>1. RSI (14日相對強弱指標)</strong><br>
            量測股價漲跌的力道大小。RSI &lt; 35 表示股價超跌（買入訊號 🔵）；RSI &gt; 75 表示股價過熱（賣出訊號 🔴）。
        </div>
        <div class="encyclo-card">
            <strong>2. Bias (20日均線乖離率)</strong><br>
            衡量最新價格與20日均線的偏離百分比。乖離率 &lt; -5% 偏低（買入訊號 🔵）；乖離率 &gt; 10% 偏高（賣出訊號 🔴）。
        </div>
        <div class="encyclo-card">
            <strong>3. MACD (平滑異同移動平均線)</strong><br>
            判斷中短期趨勢動能。MACD 柱狀值 &gt; 0 為多頭黃金交叉（買入訊號 🔵）；柱狀值 &lt; 0 為空頭死亡交叉（賣出訊號 🔴）。
        </div>
        <div class="encyclo-card">
            <strong>4. Bollinger Bands (布林通道 %B 值)</strong><br>
            衡量收盤價在布林通道波動帶的位置。%B &lt; 10 股價逼近下軌（買入訊號 🔵）；%B &gt; 90 股價逼近上軌（賣出訊號 🔴）。
        </div>
        <div class="encyclo-card">
            <strong>5. KD (隨機指標 Stochastic)</strong><br>
            判斷短期波動動能。當 K &gt; D 且 K &lt; 30 為低檔黃金交叉（買入訊號 🔵）；當 K &lt; D 且 K &gt; 70 為高檔死亡交叉（賣出訊號 🔴）。
        </div>
        <div class="encyclo-card">
            <strong>6. ATR (真實波動幅度)</strong><br>
            評估波動風險與趨勢強度。當最新價格大於20均線（漲勢）且 ATR 擴大（波動增加）時看多（🔵）；若在跌勢且 ATR 擴大則看空（🔴）。
        </div>
        <div class="encyclo-card">
            <strong>7. OBV (能量潮指標)</strong><br>
            將成交量與股價漲跌結合以預測股價動能。OBV &gt; 10日平均 OBV 時代表資金流入看多（🔵）；反之看空（🔴）。
        </div>
        <div class="encyclo-card">
            <strong>8. CCI (順勢指標)</strong><br>
            反映價格相對於其歷史平均值在常態區間的偏離程度。CCI &lt; -100 為嚴重超賣（買入訊號 🔵）；CCI &gt; 100 為嚴重超買（賣出訊號 🔴）。
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- Dynamic Strategy Selector ---
st.write("### 🎛️ 動態複合策略多選器")
selected_indicators = st.multiselect(
    "選擇要計入複合評分系統的指標 (預設已勾選3種)",
    options=["RSI", "Bias", "MACD", "Bollinger Bands", "KD", "ATR", "OBV", "CCI"],
    default=["RSI", "MACD", "KD"]
)

# Validation check
if len(selected_indicators) < 3:
    st.warning("⚠️ 為了確保評估的準確性與多維度防呆，建議您至少勾選 3 種指標進行複合評分計算。")

# --- Parse & Compute Asset Metrics ---
processed_tw = []
for item in tw_stocks:
    sym = item['code'] + '.TW'
    shares = item['shares']
    cost_twd = item['cost_twd']
    
    has_live = sym in market_indicators
    if has_live:
        price = float(market_indicators[sym]['Close'].iloc[-1])
    else:
        price = item['sheet_price'] if item['sheet_price'] > 0 else (cost_twd / shares if shares > 0 else 0.0)
        
    market_val = shares * price
    pnl = market_val - cost_twd
    roi = (pnl / cost_twd * 100) if cost_twd > 0 else 0.0
    
    processed_tw.append({
        'symbol': sym,
        'code': item['code'],
        'name': item['name'],
        'shares': shares,
        'avg_cost': item['avg_cost'],
        'cost_twd': cost_twd,
        'price': price,
        'market_val_twd': market_val,
        'pnl_twd': pnl,
        'roi': roi,
        'type': '台股',
        'currency': 'TWD',
        'start_date': item['start_date']
    })

processed_us = []
for item in us_stocks:
    sym = item['code']
    shares = item['shares']
    cost_usd = item['cost_usd']
    cost_twd = cost_usd * exchange_rate if cost_usd > 0 else item['cost_ntd']
    if cost_usd == 0:
        cost_usd = cost_twd / exchange_rate
        
    has_live = sym in market_indicators
    if has_live:
        price_usd = float(market_indicators[sym]['Close'].iloc[-1])
    else:
        price_usd = item['sheet_price'] if item['sheet_price'] > 0 else (cost_usd / shares if shares > 0 else 0.0)
        
    market_val_twd = shares * price_usd * exchange_rate
    pnl = market_val_twd - cost_twd
    roi = (pnl / cost_twd * 100) if cost_twd > 0 else 0.0
    
    processed_us.append({
        'symbol': sym,
        'code': sym,
        'name': sym,
        'shares': shares,
        'avg_cost': item['avg_cost'],
        'cost_twd': cost_twd,
        'price': price_usd,  # USD
        'market_val_twd': market_val_twd,
        'pnl_twd': pnl,
        'roi': roi,
        'type': '美股',
        'currency': 'USD',
        'start_date': item['start_date']
    })

processed_funds = []
for item in funds:
    shares = item['shares']
    cost_usd = item['cost_usd']
    cost_ntd = item['cost_ntd']
    
    # Classify currency
    is_usd = "美元" in item['name'] or cost_usd > 0
    currency = 'USD' if is_usd else 'TWD'
    
    if is_usd:
        cost_twd = cost_usd * exchange_rate if cost_usd > 0 else cost_ntd
        cost_usd_final = cost_usd if cost_usd > 0 else cost_ntd / exchange_rate
    else:
        cost_twd = cost_ntd if cost_ntd > 0 else cost_usd * exchange_rate
        cost_usd_final = cost_twd / exchange_rate
        
    nav = item['sheet_price']
    if nav <= 0:
        nav = (cost_usd_final / shares) if is_usd else (cost_twd / shares) if shares > 0 else 0.0
        
    market_val_twd = shares * nav * exchange_rate if is_usd else shares * nav
    pnl = market_val_twd - cost_twd
    roi = (pnl / cost_twd * 100) if cost_twd > 0 else 0.0
    
    processed_funds.append({
        'symbol': item['code'],
        'code': item['code'],
        'name': item['name'],
        'shares': shares,
        'avg_cost': item['avg_cost'],
        'cost_twd': cost_twd,
        'price': nav,  # local nav
        'market_val_twd': market_val_twd,
        'pnl_twd': pnl,
        'roi': roi,
        'type': '基金',
        'currency': currency,
        'start_date': item['start_date']
    })

# Dataframes
df_tw = pd.DataFrame(processed_tw)
df_us = pd.DataFrame(processed_us)
df_funds = pd.DataFrame(processed_funds)
df_all = pd.concat([df_tw, df_us, df_funds], ignore_index=True)

# --- KPI Calculations ---
total_cost = df_all['cost_twd'].sum()
total_market_value = df_all['market_val_twd'].sum()
total_pnl = total_market_value - total_cost
total_roi = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0

# --- Adaptable Layout: KPI section ---
if is_mobile:
    # 2x2 grid for Mobile
    kpi_col1, kpi_col2 = st.columns(2)
    with kpi_col1:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-label">💰 付出總成本</div><div class="kpi-value">NT$ {total_cost:,.0f}</div></div>""", unsafe_allow_html=True)
    with kpi_col2:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-label">📈 持有總市值</div><div class="kpi-value">NT$ {total_market_value:,.0f}</div></div>""", unsafe_allow_html=True)
        
    st.markdown("<div style='margin-bottom: 0.5rem;'></div>", unsafe_allow_html=True)
    kpi_col3, kpi_col4 = st.columns(2)
    with kpi_col3:
        pnl_color = "#f43f5e" if total_pnl < 0 else "#10b981"
        pnl_sign = "" if total_pnl < 0 else "+"
        st.markdown(f"""<div class="kpi-card"><div class="kpi-label">📊 未實現損益</div><div class="kpi-value" style="color: {pnl_color};">{pnl_sign}{total_pnl:,.0f}</div></div>""", unsafe_allow_html=True)
    with kpi_col4:
        roi_color = "#f43f5e" if total_roi < 0 else "#10b981"
        roi_sign = "" if total_roi < 0 else "+"
        st.markdown(f"""<div class="kpi-card"><div class="kpi-label">🚀 總報酬率 (ROI)</div><div class="kpi-value" style="color: {roi_color};">{roi_sign}{total_roi:.2f}%</div></div>""", unsafe_allow_html=True)
else:
    # 1x4 layout for Desktop
    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
    with kpi_col1:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-label">💰 付出總成本 (TWD)</div><div class="kpi-value">NT$ {total_cost:,.0f}</div></div>""", unsafe_allow_html=True)
    with kpi_col2:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-label">📈 目前總市值 (TWD)</div><div class="kpi-value">NT$ {total_market_value:,.0f}</div></div>""", unsafe_allow_html=True)
    with kpi_col3:
        pnl_color = "#f43f5e" if total_pnl < 0 else "#10b981"
        pnl_sign = "" if total_pnl < 0 else "+"
        st.markdown(f"""<div class="kpi-card"><div class="kpi-label">📊 總未實現損益 (TWD)</div><div class="kpi-value" style="color: {pnl_color};">{pnl_sign}NT$ {total_pnl:,.0f}</div></div>""", unsafe_allow_html=True)
    with kpi_col4:
        roi_color = "#f43f5e" if total_roi < 0 else "#10b981"
        roi_sign = "" if total_roi < 0 else "+"
        st.markdown(f"""<div class="kpi-card"><div class="kpi-label">🚀 整體投資報酬率 (ROI)</div><div class="kpi-value" style="color: {roi_color};">{roi_sign}{total_roi:.2f}%</div></div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- Adaptable Layout: Charts section ---
if is_mobile:
    # Stacked vertically on Mobile
    st.markdown("### 🧩 資產配置佔比")
    df_cat = df_all.groupby('type')['market_val_twd'].sum().reset_index()
    fig_cat = px.pie(df_cat, values='market_val_twd', names='type', hole=0.35, color_discrete_sequence=px.colors.qualitative.Pastel)
    fig_cat.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color='#f8fafc', margin=dict(t=20, b=10, l=10, r=10), height=300)
    st.plotly_chart(fig_cat, use_container_width=True)

    st.markdown("### 💱 貨幣曝險比例")
    df_curr = df_all.groupby('currency')['market_val_twd'].sum().reset_index()
    df_curr['currency_name'] = df_curr['currency'].map({'USD': '美元資產 (USD)', 'TWD': '新台幣資產 (TWD)'})
    fig_curr = px.pie(df_curr, values='market_val_twd', names='currency_name', hole=0.35, color_discrete_map={'美元資產 (USD)': '#6366f1', '新台幣資產 (TWD)': '#10b981'}, color='currency_name')
    fig_curr.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color='#f8fafc', margin=dict(t=20, b=10, l=10, r=10), height=300)
    st.plotly_chart(fig_curr, use_container_width=True)
else:
    # Side-by-side on Desktop
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.markdown("### 🧩 資產配置佔比 (Asset Allocation)")
        df_cat = df_all.groupby('type')['market_val_twd'].sum().reset_index()
        fig_cat = px.pie(df_cat, values='market_val_twd', names='type', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
        fig_cat.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color='#f8fafc', margin=dict(t=30, b=10, l=10, r=10), height=350)
        st.plotly_chart(fig_cat, use_container_width=True)
    with chart_col2:
        st.markdown("### 💱 貨幣曝險比例 (Currency Exposure)")
        df_curr = df_all.groupby('currency')['market_val_twd'].sum().reset_index()
        df_curr['currency_name'] = df_curr['currency'].map({'USD': '美元資產 (USD)', 'TWD': '新台幣資產 (TWD)'})
        fig_curr = px.pie(df_curr, values='market_val_twd', names='currency_name', hole=0.4, color_discrete_map={'美元資產 (USD)': '#6366f1', '新台幣資產 (TWD)': '#10b981'}, color='currency_name')
        fig_curr.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color='#f8fafc', margin=dict(t=30, b=10, l=10, r=10), height=350)
        st.plotly_chart(fig_curr, use_container_width=True)

# --- 總體投資歷史趨勢圖表 (Cost, Market Value & PnL History) ---
st.markdown("---")
st.markdown("### 📈 總體投資歷史變化趨勢 (Overall Portfolio Performance History)")

# 1. Determine common timeline from all holdings
buy_dates = []
for item in processed_tw + processed_us + processed_funds:
    d_str = item.get('start_date', '')
    if d_str and d_str != 'N/A':
        try:
            buy_dates.append(pd.to_datetime(d_str))
        except Exception:
            pass

earliest_buy = min(buy_dates) if len(buy_dates) > 0 else (datetime.now() - pd.Timedelta(days=365))
# Start history from earliest buy date, or at least 3 years ago (whichever is more recent, or oldest)
start_history = min(earliest_buy, datetime.now() - pd.Timedelta(days=3*365))

# Generate business dates timeline from start_history to today
dates_timeline = pd.date_range(start=start_history, end=datetime.now(), freq='B')

# 2. Build daily cost and value DataFrame
df_portfolio_history = pd.DataFrame(index=dates_timeline)
df_portfolio_history['Total Cost'] = 0.0
df_portfolio_history['Total Value'] = 0.0

# Align and sum daily cost & value for each asset
for item in processed_tw:
    code = item['code']
    sym = item['symbol']
    shares = item['shares']
    cost_twd = item['cost_twd']
    buy_date = pd.to_datetime(item['start_date'])
    
    if sym in market_indicators:
        close_series = market_indicators[sym]['Close']
        price_aligned = close_series.reindex(dates_timeline).ffill().bfill()
        
        # Add contribution on or after buy date
        for d in dates_timeline:
            if d >= buy_date:
                df_portfolio_history.loc[d, 'Total Cost'] += cost_twd
                df_portfolio_history.loc[d, 'Total Value'] += shares * price_aligned.loc[d]

for item in processed_us:
    sym = item['symbol']
    shares = item['shares']
    cost_twd = item['cost_twd']
    buy_date = pd.to_datetime(item['start_date'])
    
    if sym in market_indicators:
        close_series = market_indicators[sym]['Close']
        price_aligned = close_series.reindex(dates_timeline).ffill().bfill()
        
        for d in dates_timeline:
            if d >= buy_date:
                df_portfolio_history.loc[d, 'Total Cost'] += cost_twd
                df_portfolio_history.loc[d, 'Total Value'] += shares * price_aligned.loc[d] * exchange_rate

for item in processed_funds:
    code = item['code']
    shares = item['shares']
    cost_twd = item['cost_twd']
    buy_date = pd.to_datetime(item['start_date'])
    is_usd = item['currency'] == 'USD'
    
    if code in fund_market_data:
        close_series = fund_market_data[code]['Close']
        price_aligned = close_series.reindex(dates_timeline).ffill().bfill()
        
        for d in dates_timeline:
            if d >= buy_date:
                df_portfolio_history.loc[d, 'Total Cost'] += cost_twd
                fund_val = shares * price_aligned.loc[d]
                if is_usd:
                    fund_val *= exchange_rate
                df_portfolio_history.loc[d, 'Total Value'] += fund_val

# Calculate PnL and ROI
df_portfolio_history['Total PnL'] = df_portfolio_history['Total Value'] - df_portfolio_history['Total Cost']
df_portfolio_history['Total ROI (%)'] = (df_portfolio_history['Total PnL'] / df_portfolio_history['Total Cost'].replace(0, np.nan)) * 100
df_portfolio_history['Total ROI (%)'] = df_portfolio_history['Total ROI (%)'].fillna(0.0)

# Filter Selector
hist_mode = st.radio(
    "選擇歷史趨勢圖顯示範圍：",
    ["全部歷史", "近1年", "近6個月", "近3個月"],
    index=0,
    horizontal=True,
    key="portfolio_history_selector"
)

# Slice history based on selection
last_timeline_date = dates_timeline[-1]
if hist_mode == "近1年":
    slice_start = last_timeline_date - pd.DateOffset(years=1)
elif hist_mode == "近6個月":
    slice_start = last_timeline_date - pd.DateOffset(months=6)
elif hist_mode == "近3個月":
    slice_start = last_timeline_date - pd.DateOffset(months=3)
else:
    slice_start = start_history

df_history_sliced = df_portfolio_history.loc[slice_start:]

# Render charts
if is_mobile:
    # Stacked on mobile
    st.write("##### 投入成本 vs 持倉市值趨勢 (TWD)")
    fig_hist1 = go.Figure()
    fig_hist1.add_trace(go.Scatter(x=df_history_sliced.index, y=df_history_sliced['Total Cost'], name='投入總成本', line=dict(color='#cbd5e1', width=2)))
    fig_hist1.add_trace(go.Scatter(x=df_history_sliced.index, y=df_history_sliced['Total Value'], name='持倉總市值', line=dict(color='#818cf8', width=2.5)))
    fig_hist1.update_layout(template='plotly_dark', margin=dict(t=15, b=15, l=15, r=15), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#0f172a', height=280)
    st.plotly_chart(fig_hist1, use_container_width=True)
    
    st.write("##### 未實現損益與報酬率趨勢")
    fig_hist2 = make_subplots(specs=[[{"secondary_y": True}]])
    fig_hist2.add_trace(go.Scatter(x=df_history_sliced.index, y=df_history_sliced['Total PnL'], name='未實現損益(TWD)', line=dict(color='#10b981', width=2)), secondary_y=False)
    fig_hist2.add_trace(go.Scatter(x=df_history_sliced.index, y=df_history_sliced['Total ROI (%)'], name='損益率(%)', line=dict(color='#c084fc', width=1.5, dash='dash')), secondary_y=True)
    fig_hist2.update_layout(template='plotly_dark', margin=dict(t=15, b=15, l=15, r=15), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#0f172a', height=280)
    st.plotly_chart(fig_hist2, use_container_width=True)
else:
    # Side-by-side on desktop
    hcol1, hcol2 = st.columns(2)
    with hcol1:
        st.write("##### 投入成本 vs 持倉市值趨勢 (TWD)")
        fig_hist1 = go.Figure()
        fig_hist1.add_trace(go.Scatter(x=df_history_sliced.index, y=df_history_sliced['Total Cost'], name='投入總成本', line=dict(color='#cbd5e1', width=2)))
        fig_hist1.add_trace(go.Scatter(x=df_history_sliced.index, y=df_history_sliced['Total Value'], name='持倉總市值', line=dict(color='#818cf8', width=2.5)))
        fig_hist1.update_layout(template='plotly_dark', margin=dict(t=20, b=20, l=20, r=20), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#0f172a', height=320)
        st.plotly_chart(fig_hist1, use_container_width=True)
    with hcol2:
        st.write("##### 未實現損益與報酬率趨勢")
        fig_hist2 = make_subplots(specs=[[{"secondary_y": True}]])
        fig_hist2.add_trace(go.Scatter(x=df_history_sliced.index, y=df_history_sliced['Total PnL'], name='未實現損益(TWD)', line=dict(color='#10b981', width=2)), secondary_y=False)
        fig_hist2.add_trace(go.Scatter(x=df_history_sliced.index, y=df_history_sliced['Total ROI (%)'], name='損益率(%)', line=dict(color='#c084fc', width=1.5, dash='dash')), secondary_y=True)
        fig_hist2.update_layout(template='plotly_dark', margin=dict(t=20, b=20, l=20, r=20), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#0f172a', height=320)
        st.plotly_chart(fig_hist2, use_container_width=True)

st.markdown("---")

# --- Dynamic Scoring Engine ---

def get_signal_val(ind_name, metrics):
    """Calculates signal contribution (+1, -1, 0) for an indicator."""
    if ind_name == 'RSI':
        val = metrics['RSI']
        return 1 if val < 35 else (-1 if val > 75 else 0)
    elif ind_name == 'Bias':
        val = metrics['Bias']
        return 1 if val < -5.0 else (-1 if val > 10.0 else 0)
    elif ind_name == 'MACD':
        val = metrics['MACD_hist']
        return 1 if val > 0 else (-1 if val < 0 else 0)
    elif ind_name == 'Bollinger Bands':
        val = metrics['BB_percent_b']
        return 1 if val < 10 else (-1 if val > 90 else 0)
    elif ind_name == 'KD':
        k = metrics['K']
        d = metrics['D']
        return 1 if (k > d and k < 30) else (-1 if (k < d and k > 70) else 0)
    elif ind_name == 'ATR':
        # Trend confirmation
        close_val = metrics['Close']
        sma_20 = metrics['SMA_20']
        atr = metrics['ATR']
        atr_sma = metrics['ATR_SMA_20']
        return 1 if (close_val > sma_20 and atr > atr_sma) else (-1 if (close_val < sma_20 and atr > atr_sma) else 0)
    elif ind_name == 'OBV':
        val = metrics['OBV']
        sma = metrics['OBV_SMA_10']
        return 1 if val > sma else (-1 if val < sma else 0)
    elif ind_name == 'CCI':
        val = metrics['CCI']
        return 1 if val < -100 else (-1 if val > 100 else 0)
    return 0

def run_composite_scoring(ticker, indicators_dataset, selected_indicators):
    """Computes composite scoring and recommendation string."""
    if ticker not in indicators_dataset or len(selected_indicators) == 0:
        return np.nan, "N/A"
    
    ind_vals = indicators_dataset[ticker]
    # Extract latest row values
    latest_metrics = {k: v.iloc[-1] for k, v in ind_vals.items()}
    
    total_score = 0
    for ind in selected_indicators:
        total_score += get_signal_val(ind, latest_metrics)
        
    n = len(selected_indicators)
    # Map [-N, N] to [0, 100]
    score = ((total_score + n) / (2 * n)) * 100
    
    if score >= 80:
        rec = "強烈買進 🟢🟢"
    elif score >= 60:
        rec = "偏多 🟢"
    elif score >= 40:
        rec = "中性 ⚪"
    elif score >= 20:
        rec = "偏空 🔴"
    else:
        rec = "強烈賣出 🔴🔴"
        
    return score, rec

# Process Stocks with scoring
df_stocks = pd.concat([df_tw, df_us], ignore_index=True)
stock_scores = []
stock_recs = []

for idx, r in df_stocks.iterrows():
    score, rec = run_composite_scoring(r['symbol'], market_indicators, selected_indicators)
    stock_scores.append(score)
    stock_recs.append(rec)
    
df_stocks['複合得分'] = stock_scores
df_stocks['量化決策建議'] = stock_recs

# ----------------- Adaptable Layout: Stock Signals Table/List -----------------
st.markdown("## 🔍 股市動態量化評估 (Composite Quantitative Analysis)")

if is_mobile:
    # Render mobile list-view instead of wide table
    st.write("📱 *偵測到手機版模式：以條列式卡片呈現以便閱讀。*")
    for idx, r in df_stocks.iterrows():
        score_val = f"{r['複合得分']:.1f}" if pd.notna(r['複合得分']) else "N/A"
        price_val = f"${r['price']:,.2f} USD" if r['currency'] == 'USD' else f"${r['price']:,.1f} TWD"
        
        st.markdown(f"""
        <div class="mobile-list-item">
            <div style='display:flex; justify-content:space-between; margin-bottom:0.3rem;'>
                <strong>{r['code']} {r['name']}</strong>
                <span class='rec-badge rec-{'strong-buy' if '強烈買進' in r['量化決策建議'] else 'buy' if '偏多' in r['量化決策建議'] else 'neutral' if '中性' in r['量化決策建議'] else 'sell' if '偏空' in r['量化決策建議'] else 'strong-sell'}'>{r['量化決策建議']}</span>
            </div>
            <div style='font-size:0.85rem; color:#94a3b8; display:grid; grid-template-columns:1fr 1fr; gap:0.5rem;'>
                <div>最新價: <span style='color:white;'>{price_val}</span></div>
                <div>複合評分: <span style='color:white; font-weight:700;'>{score_val} 分</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
else:
    # Render full detailed table for Desktop
    # We display code, name, price, specific checked indicators, score, and recommendation
    table_df = df_stocks.copy()
    
    # Extract latest indicators values for the columns
    for ind in ["RSI", "Bias", "MACD", "Bollinger Bands", "KD", "ATR", "OBV", "CCI"]:
        ind_col_vals = []
        for idx, r in df_stocks.iterrows():
            ticker = r['symbol']
            if ticker in market_indicators:
                latest_m = {k: v.iloc[-1] for k, v in market_indicators[ticker].items()}
                if ind == 'RSI': ind_col_vals.append(f"{latest_m['RSI']:.1f}")
                elif ind == 'Bias': ind_col_vals.append(f"{latest_m['Bias']:+.2f}%")
                elif ind == 'MACD': ind_col_vals.append(f"{latest_m['MACD_hist']:+.2f}")
                elif ind == 'Bollinger Bands': ind_col_vals.append(f"{latest_m['BB_percent_b']:.1f}%")
                elif ind == 'KD': ind_col_vals.append(f"K:{latest_m['K']:.1f} D:{latest_m['D']:.1f}")
                elif ind == 'ATR': ind_col_vals.append(f"{latest_m['ATR']:.2f}")
                elif ind == 'OBV': ind_col_vals.append(f"{latest_m['OBV']:,.0f}")
                elif ind == 'CCI': ind_col_vals.append(f"{latest_m['CCI']:.1f}")
            else:
                ind_col_vals.append("N/A")
        table_df[ind] = ind_col_vals

    # Format other table metrics
    table_df['最新收盤價'] = table_df.apply(
        lambda r: f"${r['price']:,.2f} USD" if r['currency'] == 'USD' else f"${r['price']:,.2f} TWD", axis=1
    )
    table_df['複合得分'] = table_df['複合得分'].apply(lambda x: f"{x:.1f} 分" if pd.notna(x) else "N/A")
    
    cols_to_show = ['code', 'name', '最新收盤價'] + selected_indicators + ['複合得分', '量化決策建議']
    st.dataframe(
        table_df[cols_to_show],
        use_container_width=True,
        column_config={
            "code": st.column_config.TextColumn("代號"),
            "name": st.column_config.TextColumn("名稱"),
            "最新收盤價": st.column_config.TextColumn("最新收盤價"),
            "複合得分": st.column_config.TextColumn("複合量化評分"),
            "量化決策建議": st.column_config.TextColumn("量化決策建議")
        },
        hide_index=True
    )

# --- 🔔 今日關注標的燈 ---
st.markdown("### 🔔 今日關注標的警告卡片")
oversold_targets = []
overbought_targets = []

for ticker, metrics in market_indicators.items():
    rsi_latest = metrics['RSI'].iloc[-1]
    bias_latest = metrics['Bias'].iloc[-1]
    price_latest = metrics['Close'].iloc[-1]
    
    # Match stock codes
    stock_info = df_stocks[df_stocks['symbol'] == ticker].iloc[0]
    name = stock_info['name']
    code = stock_info['code']
    currency = stock_info['currency']
    price_str = f"${price_latest:,.2f} USD" if currency == 'USD' else f"${price_latest:,.1f} TWD"
    
    if rsi_latest < 35:
        oversold_targets.append({
            'code': code, 'name': name, 'rsi': rsi_latest, 'bias': bias_latest, 'price': price_str
        })
    elif rsi_latest > 75:
        overbought_targets.append({
            'code': code, 'name': name, 'rsi': rsi_latest, 'bias': bias_latest, 'price': price_str
        })

if len(oversold_targets) == 0 and len(overbought_targets) == 0:
    st.info("🟢 今日無任何標的觸發極端警示（RSI < 35 或 RSI > 75），所有標的價格處於穩健區間波動。")
else:
    col_warn1, col_warn2 = st.columns(2)
    with col_warn1:
        if len(oversold_targets) > 0:
            st.markdown("#### 🔵 超跌買入區 (RSI < 35)")
            for t in oversold_targets:
                st.markdown(f"""
                <div class="signal-pill signal-oversold" style="padding:1rem; width:100%; margin-bottom:0.5rem; text-align:left; border-radius:12px;">
                    <strong>{t['code']} {t['name']}</strong> | 最新價: {t['price']}<br>
                    <span style='font-size:0.85rem;'>RSI: {t['rsi']:.1f} | 乖離率: {t['bias']:.2f}%<br>
                    指引：目前處於相對低估區域，乖離擴大，適合尋求低接布局點。</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.write("目前無超跌訊號標的。")
            
    with col_warn2:
        if len(overbought_targets) > 0:
            st.markdown("#### 🔴 過熱警戒區 (RSI > 75)")
            for t in overbought_targets:
                st.markdown(f"""
                <div class="signal-pill signal-overbought" style="padding:1rem; width:100%; margin-bottom:0.5rem; text-align:left; border-radius:12px;">
                    <strong>{t['code']} {t['name']}</strong> | 最新價: {t['price']}<br>
                    <span style='font-size:0.85rem;'>RSI: {t['rsi']:.1f} | 乖離率: {t['bias']:.2f}%<br>
                    指引：短期乖離過大且人氣沸騰，指標強烈超買，宜提高避險水位或分批獲利。</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.write("目前無過熱訊號標的。")

# -----------------個股深度互動圖表 (Subplots) -----------------
st.markdown("---")
st.markdown("## 📊 個股深度技術面互動圖表")

selected_stock = st.selectbox(
    "選擇一檔標的來生成技術分析圖表：",
    options=df_stocks['symbol'].tolist(),
    format_func=lambda x: f"{df_stocks[df_stocks['symbol'] == x].iloc[0]['code']} - {df_stocks[df_stocks['symbol'] == x].iloc[0]['name']}"
)

# Get selected stock details
stock_row = df_stocks[df_stocks['symbol'] == selected_stock].iloc[0]

# Render Premium Purchase Summary Card
render_purchase_card(stock_row, f"{stock_row['code']} {stock_row['name']} 買進持倉資訊", is_fund=False)

# Render Key News Section
display_asset_news(stock_row['code'], stock_row['name'], '美股' if stock_row['type'] == '美股' else '台股')

# Date Range Selector
stock_range_str = st.radio(
    "選擇圖表日期區間：",
    ["10年", "5年", "3年", "1年", "6個月", "3個月", "1個月"],
    index=3, # default to 1 year
    horizontal=True,
    key="stock_date_range_selector"
)

# Fetch 10-year historical dataset & indicators
indicators = fetch_stock_chart_data(selected_stock)

if indicators is not None and len(indicators.get('Close', [])) > 0:
    close_series = indicators['Close']
    last_date = close_series.index[-1]
    
    # Calculate start date for sliced view
    if stock_range_str == "10年":
        start_view = last_date - pd.DateOffset(years=10)
    elif stock_range_str == "5年":
        start_view = last_date - pd.DateOffset(years=5)
    elif stock_range_str == "3年":
        start_view = last_date - pd.DateOffset(years=3)
    elif stock_range_str == "1年":
        start_view = last_date - pd.DateOffset(years=1)
    elif stock_range_str == "6個月":
        start_view = last_date - pd.DateOffset(months=6)
    elif stock_range_str == "3個月":
        start_view = last_date - pd.DateOffset(months=3)
    elif stock_range_str == "1個月":
        start_view = last_date - pd.DateOffset(months=1)
    else:
        start_view = last_date - pd.DateOffset(years=1)
        
    # Slice indicators to start_view
    sliced_inds = {}
    for k, v in indicators.items():
        if isinstance(v, pd.Series):
            sliced_inds[k] = v.loc[start_view:]
        else:
            sliced_inds[k] = v
            
    df_sliced_close = sliced_inds['Close']
    
    # Calculate buy date visibility & closest index values
    start_date = stock_row['start_date']
    buy_date_dt = None
    is_buy_visible = False
    closest_date = None
    if pd.notna(start_date) and str(start_date).strip():
        try:
            buy_date_dt = pd.to_datetime(start_date)
            if buy_date_dt >= df_sliced_close.index[0] and buy_date_dt <= df_sliced_close.index[-1]:
                is_buy_visible = True
                closest_idx = df_sliced_close.index.get_indexer([buy_date_dt], method='nearest')[0]
                closest_date = df_sliced_close.index[closest_idx]
        except Exception:
            pass
            
    # Extract subplots to draw based on user selection
    subplots_to_draw = []
    if 'RSI' in selected_indicators: subplots_to_draw.append('RSI')
    if 'MACD' in selected_indicators: subplots_to_draw.append('MACD')
    if 'KD' in selected_indicators: subplots_to_draw.append('KD')
    if 'CCI' in selected_indicators: subplots_to_draw.append('CCI')
    if 'OBV' in selected_indicators: subplots_to_draw.append('OBV')
    if 'ATR' in selected_indicators: subplots_to_draw.append('ATR')
    if 'Bias' in selected_indicators: subplots_to_draw.append('Bias')
    
    num_subplots = len(subplots_to_draw)
    
    # Height config
    chart_height = 420 + (160 * num_subplots)
    row_heights = [0.4] + [0.6 / num_subplots] * num_subplots if num_subplots > 0 else [1.0]
    
    # Subplot titles
    titles = ["K線 / 20均線 / 布林通道"] + [f"{ind} 指標" for ind in subplots_to_draw]
    
    fig = make_subplots(
        rows=1 + num_subplots,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04 if is_mobile else 0.02,
        row_heights=row_heights,
        subplot_titles=titles
    )
    
    # Main K-line and BB trace
    fig.add_trace(
        go.Candlestick(
            x=df_sliced_close.index,
            open=sliced_inds['Open'],
            high=sliced_inds['High'],
            low=sliced_inds['Low'],
            close=sliced_inds['Close'],
            name='K線'
        ),
        row=1, col=1
    )
    
    # 20 SMA & BB lines
    fig.add_trace(go.Scatter(x=df_sliced_close.index, y=sliced_inds['SMA_20'], name='20日 MA', line=dict(color='#ff9100', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_sliced_close.index, y=sliced_inds['BB_upper'], name='布林上軌', line=dict(color='#cbd5e1', width=1, dash='dash')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_sliced_close.index, y=sliced_inds['BB_lower'], name='布林下軌', line=dict(color='#cbd5e1', width=1, dash='dash')), row=1, col=1)
    
    # Add horizontal buy price reference line
    if is_buy_visible and closest_date is not None:
        buy_price = float(df_sliced_close.loc[closest_date])
        fig.add_hline(
            y=buy_price,
            line_width=1.5,
            line_dash="dot",
            line_color="#38bdf8",
            annotation_text=f" 買入價: {buy_price:,.2f}",
            annotation_position="bottom left",
            row=1, col=1
        )
        
    # Add Subplot Traces
    curr_row = 2
    for ind in subplots_to_draw:
        if ind == 'RSI':
            fig.add_trace(go.Scatter(x=df_sliced_close.index, y=sliced_inds['RSI'], name='RSI', line=dict(color='#c084fc', width=1.5)), row=curr_row, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="#ef4444", row=curr_row, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="#10b981", row=curr_row, col=1)
            if is_buy_visible and closest_date is not None:
                buy_rsi = float(sliced_inds['RSI'].loc[closest_date])
                fig.add_hline(
                    y=buy_rsi,
                    line_width=1.5,
                    line_dash="dot",
                    line_color="#c084fc",
                    annotation_text=f" 買入RSI: {buy_rsi:.1f}",
                    annotation_position="bottom left",
                    row=curr_row, col=1
                )
            curr_row += 1
        elif ind == 'MACD':
            colors = ['#ef4444' if x < 0 else '#10b981' for x in sliced_inds['MACD_hist']]
            fig.add_trace(go.Bar(x=df_sliced_close.index, y=sliced_inds['MACD_hist'], name='MACD柱', marker_color=colors), row=curr_row, col=1)
            fig.add_trace(go.Scatter(x=df_sliced_close.index, y=sliced_inds['MACD_line'], name='MACD快線', line=dict(color='#3b82f6', width=1.2)), row=curr_row, col=1)
            fig.add_trace(go.Scatter(x=df_sliced_close.index, y=sliced_inds['MACD_signal'], name='MACD慢線', line=dict(color='#f59e0b', width=1.2)), row=curr_row, col=1)
            if is_buy_visible and closest_date is not None:
                buy_macd = float(sliced_inds['MACD_hist'].loc[closest_date])
                fig.add_hline(
                    y=buy_macd,
                    line_width=1.5,
                    line_dash="dot",
                    line_color="#10b981" if buy_macd >= 0 else "#ef4444",
                    annotation_text=f" 買入MACD柱: {buy_macd:+.2f}",
                    annotation_position="bottom left",
                    row=curr_row, col=1
                )
            curr_row += 1
        elif ind == 'KD':
            fig.add_trace(go.Scatter(x=df_sliced_close.index, y=sliced_inds['K'], name='K值', line=dict(color='#3b82f6', width=1.5)), row=curr_row, col=1)
            fig.add_trace(go.Scatter(x=df_sliced_close.index, y=sliced_inds['D'], name='D值', line=dict(color='#f59e0b', width=1.5)), row=curr_row, col=1)
            fig.add_hline(y=80, line_dash="dash", line_color="#ef4444", row=curr_row, col=1)
            fig.add_hline(y=20, line_dash="dash", line_color="#10b981", row=curr_row, col=1)
            if is_buy_visible and closest_date is not None:
                buy_k = float(sliced_inds['K'].loc[closest_date])
                buy_d = float(sliced_inds['D'].loc[closest_date])
                fig.add_hline(y=buy_k, line_width=1.2, line_dash="dot", line_color="#3b82f6", annotation_text=f" 買入K: {buy_k:.1f}", annotation_position="bottom left", row=curr_row, col=1)
                fig.add_hline(y=buy_d, line_width=1.2, line_dash="dot", line_color="#f59e0b", row=curr_row, col=1)
            curr_row += 1
        elif ind == 'CCI':
            fig.add_trace(go.Scatter(x=df_sliced_close.index, y=sliced_inds['CCI'], name='CCI', line=dict(color='#14b8a6', width=1.5)), row=curr_row, col=1)
            fig.add_hline(y=100, line_dash="dash", line_color="#ef4444", row=curr_row, col=1)
            fig.add_hline(y=-100, line_dash="dash", line_color="#10b981", row=curr_row, col=1)
            if is_buy_visible and closest_date is not None:
                buy_cci = float(sliced_inds['CCI'].loc[closest_date])
                fig.add_hline(
                    y=buy_cci,
                    line_width=1.5,
                    line_dash="dot",
                    line_color="#14b8a6",
                    annotation_text=f" 買入CCI: {buy_cci:.1f}",
                    annotation_position="bottom left",
                    row=curr_row, col=1
                )
            curr_row += 1
        elif ind == 'OBV':
            fig.add_trace(go.Scatter(x=df_sliced_close.index, y=sliced_inds['OBV'], name='OBV', line=dict(color='#f43f5e', width=1.5)), row=curr_row, col=1)
            if is_buy_visible and closest_date is not None:
                buy_obv = float(sliced_inds['OBV'].loc[closest_date])
                fig.add_hline(
                    y=buy_obv,
                    line_width=1.5,
                    line_dash="dot",
                    line_color="#f43f5e",
                    annotation_text=f" 買入OBV: {buy_obv:,.0f}",
                    annotation_position="bottom left",
                    row=curr_row, col=1
                )
            curr_row += 1
        elif ind == 'ATR':
            fig.add_trace(go.Scatter(x=df_sliced_close.index, y=sliced_inds['ATR'], name='ATR', line=dict(color='#94a3b8', width=1.5)), row=curr_row, col=1)
            if is_buy_visible and closest_date is not None:
                buy_atr = float(sliced_inds['ATR'].loc[closest_date])
                fig.add_hline(
                    y=buy_atr,
                    line_width=1.5,
                    line_dash="dot",
                    line_color="#94a3b8",
                    annotation_text=f" 買入ATR: {buy_atr:.2f}",
                    annotation_position="bottom left",
                    row=curr_row, col=1
                )
            curr_row += 1
        elif ind == 'Bias':
            fig.add_trace(go.Scatter(x=df_sliced_close.index, y=sliced_inds['Bias'], name='20 MA 乖離率(%)', line=dict(color='#06b6d4', width=1.5)), row=curr_row, col=1)
            fig.add_hline(y=10, line_dash="dash", line_color="#ef4444", row=curr_row, col=1)
            fig.add_hline(y=-5, line_dash="dash", line_color="#10b981", row=curr_row, col=1)
            if is_buy_visible and closest_date is not None:
                buy_bias = float(sliced_inds['Bias'].loc[closest_date])
                fig.add_hline(
                    y=buy_bias,
                    line_width=1.5,
                    line_dash="dot",
                    line_color="#06b6d4",
                    annotation_text=f" 買入乖離: {buy_bias:+.2f}%",
                    annotation_position="bottom left",
                    row=curr_row, col=1
                )
            curr_row += 1
            
    # Add vertical buy date line across all subplots
    if is_buy_visible:
        fig.add_vline(
            x=buy_date_dt,
            line_width=1.8,
            line_dash="dash",
            line_color="#38bdf8",
            annotation_text=" 買進日",
            annotation_position="top right"
        )

    fig.update_layout(
        template='plotly_dark',
        height=chart_height,
        xaxis_rangeslider_visible=False,
        showlegend=True,
        margin=dict(t=50, b=40, l=40, r=40) if is_mobile else dict(t=50, b=50, l=50, r=50),
        paper_bgcolor='#090d16',
        plot_bgcolor='#0f172a'
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("⚠️ 此標的無 K 線圖表數據可供生成。")

# --- 📈 基金動態量化評估與圖表 ---
st.markdown("---")
st.markdown("## 📈 基金動態量化評估與圖表 (Fund Quantitative Analytics)")

# Generate fund technical data
fund_market_data = generate_fund_market_data(processed_funds)

st.markdown("### 🎛️ 基金量化策略選擇器")
selected_fund_indicators = st.multiselect(
    "選擇要計入基金評分與顯示的指標：",
    options=["RSI", "Bias_20", "Bias_60", "Drawdown", "Volatility"],
    default=["RSI", "Bias_20", "Drawdown"]
)

# Fund signals and scoring
processed_fund_signals = []
for item in processed_funds:
    code = item['code']
    latest_nav = item['price']
    currency = item['currency']
    
    rsi_val, bias20_val, bias60_val, dd_val, vol_val = np.nan, np.nan, np.nan, np.nan, np.nan
    sig_rsi, sig_bias20, sig_bias60, sig_dd = 0, 0, 0, 0
    
    if code in fund_market_data:
        fdata = fund_market_data[code]
        rsi_val = float(fdata['RSI'].iloc[-1])
        bias20_val = float(fdata['Bias_20'].iloc[-1])
        bias60_val = float(fdata['Bias_60'].iloc[-1])
        dd_val = float(fdata['Drawdown'].iloc[-1])
        vol_val = float(fdata['Volatility'].iloc[-1])
        
        # Signals
        sig_rsi = 1 if rsi_val < 35 else (-1 if rsi_val > 75 else 0)
        sig_bias20 = 1 if bias20_val < -4.0 else (-1 if bias20_val > 8.0 else 0)
        sig_bias60 = 1 if bias60_val < -8.0 else (-1 if bias60_val > 12.0 else 0)
        sig_dd = 1 if dd_val < -10.0 else 0 # Deep drawdown is buy opportunity
        
    # Calculate score based on selected active signals
    active_signals = []
    if "RSI" in selected_fund_indicators: active_signals.append(sig_rsi)
    if "Bias_20" in selected_fund_indicators: active_signals.append(sig_bias20)
    if "Bias_60" in selected_fund_indicators: active_signals.append(sig_bias60)
    if "Drawdown" in selected_fund_indicators: active_signals.append(sig_dd)
    
    n = len(active_signals)
    if n > 0:
        score = ((sum(active_signals) + n) / (2 * n)) * 100
    else:
        score = 50.0
        
    if score >= 80.0:
        rec = "強烈買進 🟢🟢"
    elif score >= 60.0:
        rec = "偏多 🟢"
    elif score >= 40.0:
        rec = "中性 ⚪"
    elif score >= 20.0:
        rec = "偏空 🔴"
    else:
        rec = "強烈賣出 🔴🔴"
        
    processed_fund_signals.append({
        'code': code,
        'name': item['name'],
        'shares': item.get('shares', 0.0),
        'avg_cost': item.get('avg_cost', 0.0),
        'cost_twd': item.get('cost_twd', 0.0),
        'market_val_twd': item.get('market_val_twd', 0.0),
        'pnl_twd': item.get('pnl_twd', 0.0),
        'roi': item.get('roi', 0.0),
        'price': latest_nav,
        'currency': currency,
        'RSI': rsi_val,
        'Bias_20': bias20_val,
        'Bias_60': bias60_val,
        'Drawdown': dd_val,
        'Volatility': vol_val,
        '複合得分': score,
        '決策建議': rec,
        'start_date': item['start_date']
    })
    
df_funds_signals = pd.DataFrame(processed_fund_signals)

# Display Fund Table (Responsive)
if is_mobile:
    st.write("📱 *偵測到手機版模式：以條列式卡片呈現基金指標。*")
    for idx, r in df_funds_signals.iterrows():
        score_val = f"{r['複合得分']:.1f}" if pd.notna(r['複合得分']) else "N/A"
        price_val = f"${r['price']:,.4f} USD" if r['currency'] == 'USD' else f"${r['price']:,.2f} TWD"
        st.markdown(f"""
        <div class="mobile-list-item">
            <div style='display:flex; justify-content:space-between; margin-bottom:0.3rem;'>
                <strong>{r['code']} {r['name'][:12]}...</strong>
                <span class='rec-badge rec-{'strong-buy' if '強烈買進' in r['決策建議'] else 'buy' if '偏多' in r['決策建議'] else 'neutral' if '中性' in r['決策建議'] else 'sell' if '偏空' in r['決策建議'] else 'strong-sell'}'>{r['決策建議']}</span>
            </div>
            <div style='font-size:0.85rem; color:#94a3b8; display:grid; grid-template-columns:1fr 1fr; gap:0.5rem;'>
                <div>最新淨值: <span style='color:white;'>{price_val}</span></div>
                <div>複合評分: <span style='color:white; font-weight:700;'>{score_val} 分</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
else:
    # Desktop Table view
    table_funds = df_funds_signals.copy()
    table_funds['最新淨值'] = table_funds.apply(
        lambda r: f"${r['price']:,.4f} USD" if r['currency'] == 'USD' else f"${r['price']:,.2f} TWD", axis=1
    )
    table_funds['RSI'] = table_funds['RSI'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    table_funds['Bias_20'] = table_funds['Bias_20'].apply(lambda x: f"{x:+.2f}%" if pd.notna(x) else "N/A")
    table_funds['Bias_60'] = table_funds['Bias_60'].apply(lambda x: f"{x:+.2f}%" if pd.notna(x) else "N/A")
    table_funds['Drawdown'] = table_funds['Drawdown'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A")
    table_funds['Volatility'] = table_funds['Volatility'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A")
    table_funds['複合得分'] = table_funds['複合得分'].apply(lambda x: f"{x:.1f} 分")
    
    cols_to_show_f = ['code', 'name', '最新淨值'] + selected_fund_indicators + ['複合得分', '決策建議']
    st.dataframe(
        table_funds[cols_to_show_f],
        use_container_width=True,
        column_config={
            "code": st.column_config.TextColumn("代號"),
            "name": st.column_config.TextColumn("基金名稱"),
            "最新淨值": st.column_config.TextColumn("最新淨值"),
            "複合得分": st.column_config.TextColumn("複合量化評分"),
            "決策建議": st.column_config.TextColumn("量化決策建議")
        },
        hide_index=True
    )

# --- Fund Depth Interactive Chart ---
st.markdown("### 📊 基金深度技術與回撤分析圖表")
selected_fund_code = st.selectbox(
    "選擇一檔基金生成技術分析圖表：",
    options=df_funds_signals['code'].tolist(),
    format_func=lambda x: f"{x} - {df_funds_signals[df_funds_signals['code'] == x].iloc[0]['name']}"
)

if selected_fund_code in fund_market_data:
    fdata = fund_market_data[selected_fund_code]
    fund_info = df_funds_signals[df_funds_signals['code'] == selected_fund_code].iloc[0]
    
    # Render Premium Purchase Summary Card
    render_purchase_card(fund_info, f"{fund_info['code']} {fund_info['name']} 買進持倉資訊", is_fund=True)
    
    # Render Key News Section
    display_asset_news(fund_info['code'], fund_info['name'], '基金')
    
    # Date Range Selector
    fund_range_str = st.radio(
        "選擇圖表日期區間：",
        ["10年", "5年", "3年", "1年", "6個月", "3個月", "1個月"],
        index=3, # default to 1 year
        horizontal=True,
        key="fund_date_range_selector"
    )
    
    last_date = fdata['Close'].index[-1]
    
    # Calculate start date for sliced view
    if fund_range_str == "10年":
        start_view = last_date - pd.DateOffset(years=10)
    elif fund_range_str == "5年":
        start_view = last_date - pd.DateOffset(years=5)
    elif fund_range_str == "3年":
        start_view = last_date - pd.DateOffset(years=3)
    elif fund_range_str == "1年":
        start_view = last_date - pd.DateOffset(years=1)
    elif fund_range_str == "6個月":
        start_view = last_date - pd.DateOffset(months=6)
    elif fund_range_str == "3個月":
        start_view = last_date - pd.DateOffset(months=3)
    elif fund_range_str == "1個月":
        start_view = last_date - pd.DateOffset(months=1)
    else:
        start_view = last_date - pd.DateOffset(years=1)
        
    # Slice fdata columns
    df_f_sliced_close = fdata['Close'].loc[start_view:]
    sliced_fdata = {}
    for k, v in fdata.items():
        if isinstance(v, pd.Series):
            sliced_fdata[k] = v.loc[start_view:]
        else:
            sliced_fdata[k] = v
            
    # Calculate buy date visibility & closest index values for funds
    f_start_date = fund_info['start_date']
    f_buy_date_dt = None
    is_f_buy_visible = False
    f_closest_date = None
    if pd.notna(f_start_date) and str(f_start_date).strip():
        try:
            f_buy_date_dt = pd.to_datetime(f_start_date)
            if f_buy_date_dt >= df_f_sliced_close.index[0] and f_buy_date_dt <= df_f_sliced_close.index[-1]:
                is_f_buy_visible = True
                f_closest_idx = df_f_sliced_close.index.get_indexer([f_buy_date_dt], method='nearest')[0]
                f_closest_date = df_f_sliced_close.index[f_closest_idx]
        except Exception:
            pass
            
    f_subplots = []
    if 'RSI' in selected_fund_indicators: f_subplots.append('RSI')
    if 'Bias_20' in selected_fund_indicators: f_subplots.append('Bias_20')
    if 'Bias_60' in selected_fund_indicators: f_subplots.append('Bias_60')
    if 'Drawdown' in selected_fund_indicators: f_subplots.append('Drawdown')
    if 'Volatility' in selected_fund_indicators: f_subplots.append('Volatility')
    
    num_f_subplots = len(f_subplots)
    f_chart_height = 350 + (150 * num_f_subplots)
    f_row_heights = [0.45] + [0.55 / num_f_subplots] * num_f_subplots if num_f_subplots > 0 else [1.0]
    
    f_titles = [f"模擬淨值走勢 ({fund_range_str}) / 20均線 / 60均線"] + [f"{ind} 指標" for ind in f_subplots]
    
    fig_f = make_subplots(
        rows=1 + num_f_subplots,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04 if is_mobile else 0.02,
        row_heights=f_row_heights,
        subplot_titles=f_titles
    )
    
    # Main Price (NAV) Plot
    fig_f.add_trace(go.Scatter(x=df_f_sliced_close.index, y=df_f_sliced_close, name='最新淨值(NAV)', line=dict(color='#22d3ee', width=2)), row=1, col=1)
    fig_f.add_trace(go.Scatter(x=df_f_sliced_close.index, y=sliced_fdata['SMA_20'], name='20日月線', line=dict(color='#ff9100', width=1.5, dash='dash')), row=1, col=1)
    fig_f.add_trace(go.Scatter(x=df_f_sliced_close.index, y=sliced_fdata['SMA_60'], name='60日季線', line=dict(color='#3b82f6', width=1.5, dash='dot')), row=1, col=1)
    
    # Add horizontal buy price reference line
    if is_f_buy_visible and f_closest_date is not None:
        buy_nav = float(df_f_sliced_close.loc[f_closest_date])
        fig_f.add_hline(
            y=buy_nav,
            line_width=1.5,
            line_dash="dot",
            line_color="#38bdf8",
            annotation_text=f" 買入淨值: {buy_nav:,.4f}",
            annotation_position="bottom left",
            row=1, col=1
        )
        
    # Add subplots traces
    curr_f_row = 2
    for ind in f_subplots:
        if ind == 'RSI':
            fig_f.add_trace(go.Scatter(x=df_f_sliced_close.index, y=sliced_fdata['RSI'], name='RSI (14)', line=dict(color='#c084fc', width=1.5)), row=curr_f_row, col=1)
            fig_f.add_hline(y=70, line_dash="dash", line_color="#ef4444", row=curr_f_row, col=1)
            fig_f.add_hline(y=30, line_dash="dash", line_color="#10b981", row=curr_f_row, col=1)
            if is_f_buy_visible and f_closest_date is not None:
                buy_rsi = float(sliced_fdata['RSI'].loc[f_closest_date])
                fig_f.add_hline(
                    y=buy_rsi,
                    line_width=1.5,
                    line_dash="dot",
                    line_color="#c084fc",
                    annotation_text=f" 買入RSI: {buy_rsi:.1f}",
                    annotation_position="bottom left",
                    row=curr_f_row, col=1
                )
            curr_f_row += 1
        elif ind == 'Bias_20':
            fig_f.add_trace(go.Scatter(x=df_f_sliced_close.index, y=sliced_fdata['Bias_20'], name='Bias (20)', line=dict(color='#06b6d4', width=1.5)), row=curr_f_row, col=1)
            fig_f.add_hline(y=8, line_dash="dash", line_color="#ef4444", row=curr_f_row, col=1)
            fig_f.add_hline(y=-4, line_dash="dash", line_color="#10b981", row=curr_f_row, col=1)
            if is_f_buy_visible and f_closest_date is not None:
                buy_bias20 = float(sliced_fdata['Bias_20'].loc[f_closest_date])
                fig_f.add_hline(
                    y=buy_bias20,
                    line_width=1.5,
                    line_dash="dot",
                    line_color="#06b6d4",
                    annotation_text=f" 買入20日乖離: {buy_bias20:+.2f}%",
                    annotation_position="bottom left",
                    row=curr_f_row, col=1
                )
            curr_f_row += 1
        elif ind == 'Bias_60':
            fig_f.add_trace(go.Scatter(x=df_f_sliced_close.index, y=sliced_fdata['Bias_60'], name='Bias (60)', line=dict(color='#6366f1', width=1.5)), row=curr_f_row, col=1)
            fig_f.add_hline(y=12, line_dash="dash", line_color="#ef4444", row=curr_f_row, col=1)
            fig_f.add_hline(y=-8, line_dash="dash", line_color="#10b981", row=curr_f_row, col=1)
            if is_f_buy_visible and f_closest_date is not None:
                buy_bias60 = float(sliced_fdata['Bias_60'].loc[f_closest_date])
                fig_f.add_hline(
                    y=buy_bias60,
                    line_width=1.5,
                    line_dash="dot",
                    line_color="#6366f1",
                    annotation_text=f" 買入60日乖離: {buy_bias60:+.2f}%",
                    annotation_position="bottom left",
                    row=curr_f_row, col=1
                )
            curr_f_row += 1
        elif ind == 'Drawdown':
            fig_f.add_trace(go.Scatter(x=df_f_sliced_close.index, y=sliced_fdata['Drawdown'], name='回撤率(%)', fill='tozeroy', line=dict(color='#f43f5e', width=1.2)), row=curr_f_row, col=1)
            fig_f.add_hline(y=-10, line_dash="dash", line_color="#f43f5e", row=curr_f_row, col=1)
            if is_f_buy_visible and f_closest_date is not None:
                buy_dd = float(sliced_fdata['Drawdown'].loc[f_closest_date])
                fig_f.add_hline(
                    y=buy_dd,
                    line_width=1.5,
                    line_dash="dot",
                    line_color="#f43f5e",
                    annotation_text=f" 買入時回撤: {buy_dd:.2f}%",
                    annotation_position="bottom left",
                    row=curr_f_row, col=1
                )
            curr_f_row += 1
        elif ind == 'Volatility':
            fig_f.add_trace(go.Scatter(x=df_f_sliced_close.index, y=sliced_fdata['Volatility'], name='30日年化波動度(%)', line=dict(color='#94a3b8', width=1.5)), row=curr_f_row, col=1)
            if is_f_buy_visible and f_closest_date is not None:
                buy_vol = float(sliced_fdata['Volatility'].loc[f_closest_date])
                fig_f.add_hline(
                    y=buy_vol,
                    line_width=1.5,
                    line_dash="dot",
                    line_color="#94a3b8",
                    annotation_text=f" 買入時波動度: {buy_vol:.2f}%",
                    annotation_position="bottom left",
                    row=curr_f_row, col=1
                )
            curr_f_row += 1
            
    # Add buy date vertical line across all subplots
    if is_f_buy_visible:
        fig_f.add_vline(
            x=f_buy_date_dt,
            line_width=1.8,
            line_dash="dash",
            line_color="#38bdf8",
            annotation_text=" 買進日",
            annotation_position="top right"
        )
            
    fig_f.update_layout(
        template='plotly_dark',
        height=f_chart_height,
        xaxis_rangeslider_visible=False,
        showlegend=True,
        margin=dict(t=50, b=40, l=40, r=40) if is_mobile else dict(t=50, b=50, l=50, r=50),
        paper_bgcolor='#090d16',
        plot_bgcolor='#0f172a'
    )
    st.plotly_chart(fig_f, use_container_width=True)
else:
    st.warning("⚠️ 無此基金圖表數據。")


# --- Detailed Assets Data Section ---
st.markdown("---")
st.markdown("## 📋 明細數據一覽")
tab1, tab2, tab3 = st.tabs(["🇹🇼 台股資產明細", "🇺🇸 美股資產明細", "📈 基金資產明細"])

def format_dataframe(df_src, type_name):
    df_res = df_src.copy()
    for col in ['cost_twd', 'market_val_twd', 'pnl_twd']:
        df_res[col] = df_res[col].apply(lambda x: f"${x:,.0f} TWD")
    df_res['roi'] = df_res['roi'].apply(lambda x: f"{x:+.2f}%")
    
    if type_name == '基金':
        df_res['price'] = df_res.apply(lambda r: f"${r['price']:,.4f} USD" if r['currency'] == 'USD' else f"${r['price']:,.4f} TWD", axis=1)
    else:
        df_res['price'] = df_res.apply(lambda r: f"${r['price']:,.2f} USD" if r['currency'] == 'USD' else f"${r['price']:,.2f} TWD", axis=1)
        
    return df_res.rename(columns={
        'code': '代號', 'name': '名稱', 'shares': '持有股數/單位', 'cost_twd': '總付出成本',
        'price': '即時價格/淨值', 'market_val_twd': '目前總市值', 'pnl_twd': '未實現損益', 'roi': '投資報酬率'
    })

with tab1:
    if len(df_tw) > 0:
        st.dataframe(format_dataframe(df_tw, '台股')[['代號', '名稱', '持有股數/單位', '總付出成本', '即時價格/淨值', '目前總市值', '未實現損益', '投資報酬率']], use_container_width=True, hide_index=True)
    else:
        st.write("無台股資料。")

with tab2:
    if len(df_us) > 0:
        st.dataframe(format_dataframe(df_us, '美股')[['代號', '總付出成本', '即時價格/淨值', '目前總市值', '未實現損益', '投資報酬率']], use_container_width=True, hide_index=True)
    else:
        st.write("無美股資料。")

with tab3:
    if len(df_funds) > 0:
        st.dataframe(format_dataframe(df_funds, '基金')[['代號', '名稱', '持有股數/單位', '總付出成本', '即時價格/淨值', '目前總市值', '未實現損益', '投資報酬率']], use_container_width=True, hide_index=True)
    else:
        st.write("無基金資料。")

# Footer
st.markdown("---")
st.markdown(
    f"<div style='text-align: center; color: #64748b; font-size: 0.8rem; padding-bottom: 2rem;'>"
    f"🔮 複合量化投資戰情儀表板 | 當前時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 數據源: Google Sheets & Yahoo Finance"
    f"</div>", 
    unsafe_allow_html=True
)
