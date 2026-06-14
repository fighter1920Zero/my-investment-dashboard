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
                'sheet_price': clean_val(r[8])
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
                'sheet_price': clean_val(r[8])
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
                'sheet_price': clean_val(r[8])
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
    
    # Ensure they are flat Series
    if isinstance(close, pd.DataFrame): close = close.iloc[:, 0]
    if isinstance(high, pd.DataFrame): high = high.iloc[:, 0]
    if isinstance(low, pd.DataFrame): low = low.iloc[:, 0]
    if isinstance(volume, pd.DataFrame): volume = volume.iloc[:, 0]
    
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
        'Close': close
    }

# --- yfinance Data Loader with Caching ---

@st.cache_data(ttl=300)
def fetch_indicators_dataset(tickers):
    """
    Downloads historical data and pre-computes indicators for a list of tickers.
    If downloading fails for a stock, skips it gracefully.
    """
    dataset = {}
    for t in tickers:
        try:
            df = yf.download(t, period='1y', progress=False)
            if df.empty or len(df) < 20:
                continue
            dataset[t] = calculate_technical_indicators(df)
        except Exception as e:
            st.sidebar.warning(f"無法下載 {t} 數據: {e}")
    return dataset

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
        'cost_twd': cost_twd,
        'price': price,
        'market_val_twd': market_val,
        'pnl_twd': pnl,
        'roi': roi,
        'type': '台股',
        'currency': 'TWD'
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
        'cost_twd': cost_twd,
        'price': price_usd,  # USD
        'market_val_twd': market_val_twd,
        'pnl_twd': pnl,
        'roi': roi,
        'type': '美股',
        'currency': 'USD'
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
        'cost_twd': cost_twd,
        'price': nav,  # local nav
        'market_val_twd': market_val_twd,
        'pnl_twd': pnl,
        'roi': roi,
        'type': '基金',
        'currency': currency
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

if selected_stock in market_indicators:
    df_hist = yf.download(selected_stock, period='1y', progress=False)
    indicators = market_indicators[selected_stock]
    
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
            x=df_hist.index,
            open=df_hist['Open'],
            high=df_hist['High'],
            low=df_hist['Low'],
            close=df_hist['Close'],
            name='K線'
        ),
        row=1, col=1
    )
    
    # 20 SMA & BB lines
    fig.add_trace(go.Scatter(x=df_hist.index, y=indicators['SMA_20'], name='20日 MA', line=dict(color='#ff9100', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_hist.index, y=indicators['BB_upper'], name='布林上軌', line=dict(color='#cbd5e1', width=1, dash='dash')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_hist.index, y=indicators['BB_lower'], name='布林下軌', line=dict(color='#cbd5e1', width=1, dash='dash')), row=1, col=1)
    
    # Add Subplot Traces
    curr_row = 2
    for ind in subplots_to_draw:
        if ind == 'RSI':
            fig.add_trace(go.Scatter(x=df_hist.index, y=indicators['RSI'], name='RSI', line=dict(color='#c084fc', width=1.5)), row=curr_row, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="#ef4444", row=curr_row, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="#10b981", row=curr_row, col=1)
            curr_row += 1
        elif ind == 'MACD':
            colors = ['#ef4444' if x < 0 else '#10b981' for x in indicators['MACD_hist']]
            fig.add_trace(go.Bar(x=df_hist.index, y=indicators['MACD_hist'], name='MACD柱', marker_color=colors), row=curr_row, col=1)
            fig.add_trace(go.Scatter(x=df_hist.index, y=indicators['MACD_line'], name='MACD快線', line=dict(color='#3b82f6', width=1.2)), row=curr_row, col=1)
            fig.add_trace(go.Scatter(x=df_hist.index, y=indicators['MACD_signal'], name='MACD慢線', line=dict(color='#f59e0b', width=1.2)), row=curr_row, col=1)
            curr_row += 1
        elif ind == 'KD':
            fig.add_trace(go.Scatter(x=df_hist.index, y=indicators['K'], name='K值', line=dict(color='#3b82f6', width=1.5)), row=curr_row, col=1)
            fig.add_trace(go.Scatter(x=df_hist.index, y=indicators['D'], name='D值', line=dict(color='#f59e0b', width=1.5)), row=curr_row, col=1)
            fig.add_hline(y=80, line_dash="dash", line_color="#ef4444", row=curr_row, col=1)
            fig.add_hline(y=20, line_dash="dash", line_color="#10b981", row=curr_row, col=1)
            curr_row += 1
        elif ind == 'CCI':
            fig.add_trace(go.Scatter(x=df_hist.index, y=indicators['CCI'], name='CCI', line=dict(color='#14b8a6', width=1.5)), row=curr_row, col=1)
            fig.add_hline(y=100, line_dash="dash", line_color="#ef4444", row=curr_row, col=1)
            fig.add_hline(y=-100, line_dash="dash", line_color="#10b981", row=curr_row, col=1)
            curr_row += 1
        elif ind == 'OBV':
            fig.add_trace(go.Scatter(x=df_hist.index, y=indicators['OBV'], name='OBV', line=dict(color='#f43f5e', width=1.5)), row=curr_row, col=1)
            curr_row += 1
        elif ind == 'ATR':
            fig.add_trace(go.Scatter(x=df_hist.index, y=indicators['ATR'], name='ATR', line=dict(color='#94a3b8', width=1.5)), row=curr_row, col=1)
            curr_row += 1
        elif ind == 'Bias':
            fig.add_trace(go.Scatter(x=df_hist.index, y=indicators['Bias'], name='20 MA 乖離率(%)', line=dict(color='#06b6d4', width=1.5)), row=curr_row, col=1)
            fig.add_hline(y=10, line_dash="dash", line_color="#ef4444", row=curr_row, col=1)
            fig.add_hline(y=-5, line_dash="dash", line_color="#10b981", row=curr_row, col=1)
            curr_row += 1
            
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
