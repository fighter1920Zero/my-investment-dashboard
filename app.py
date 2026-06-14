import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import yfinance as yf
import requests
import re
import io
from datetime import datetime

# Set up page configurations
st.set_page_config(
    page_title="Macro Portfolio Dashboard",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Premium Dark/Glassmorphic Aesthetics
st.markdown("""
<style>
    /* Font style */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Noto+Sans+TC:wght@300;400;500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', 'Noto Sans TC', sans-serif;
    }
    
    /* Top Banner Gradient */
    .banner {
        background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #311042 100%);
        padding: 2.2rem;
        border-radius: 20px;
        text-align: center;
        margin-bottom: 2rem;
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
    }
    .banner-title {
        font-weight: 700;
        font-size: 2.4rem;
        background: linear-gradient(135deg, #38bdf8 0%, #c084fc 50%, #f43f5e 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    .banner-subtitle {
        color: #94a3b8;
        font-size: 1.1rem;
        font-weight: 300;
    }
    
    /* Premium KPI Card */
    .kpi-card {
        background: rgba(17, 24, 39, 0.6);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 1.5rem;
        text-align: center;
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.4);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .kpi-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 12px 24px -5px rgba(99, 102, 241, 0.15);
        border-color: rgba(99, 102, 241, 0.3);
    }
    .kpi-label {
        font-size: 0.85rem;
        color: #94a3b8;
        margin-bottom: 0.6rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    .kpi-value {
        font-size: 1.9rem;
        font-weight: 700;
        color: #ffffff;
        font-family: 'Outfit', sans-serif;
    }
    
    /* Signal Lights */
    .signal-pill {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
        text-align: center;
    }
    .signal-oversold {
        background-color: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .signal-overbought {
        background-color: rgba(244, 63, 94, 0.15);
        color: #f43f5e;
        border: 1px solid rgba(244, 63, 94, 0.3);
    }
    .signal-neutral {
        background-color: rgba(100, 116, 139, 0.15);
        color: #94a3b8;
        border: 1px solid rgba(100, 116, 139, 0.3);
    }
</style>
""", unsafe_allow_html=True)

# --- Helper Functions ---

def clean_val(val):
    """Clean string values and return floats, replacing error codes or NaNs."""
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
    """Split '00733富邦台灣中小' -> '00733', '富邦台灣中小'"""
    cell_str = str(cell).strip()
    match = re.match(r"^(\d+)(.*)", cell_str)
    if match:
        return match.group(1), match.group(2).strip()
    return cell_str, ""

def parse_fund_code_name(cell):
    """Split '002003柏瑞環球基金...' -> '002003', '柏瑞環球基金...'"""
    cell_str = str(cell).strip()
    match = re.match(r"^([A-Za-z0-9]+)(.*)", cell_str)
    if match:
        return match.group(1), match.group(2).strip()
    return cell_str, ""

def make_export_url(url, gid="1981240361"):
    """Convert spreadsheet view URL to CSV export URL."""
    if "/export" in url:
        return url
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if match:
        spreadsheet_id = match.group(1)
        gid_match = re.search(r"gid=(\d+)", url)
        use_gid = gid_match.group(1) if gid_match else gid
        return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={use_gid}"
    return url

# --- Hardcoded Fallback Mock Data (Matches structure of target Google Sheet) ---
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

# --- Loading and Parsing Functions ---

def get_fallback_rows():
    """Load hardcoded mock data."""
    import csv
    f = io.StringIO(MOCK_CSV_DATA)
    reader = csv.reader(f)
    return list(reader)

@st.cache_data(ttl=300)
def load_sheet_rows(export_url):
    """Download Google Sheets CSV data, with fallback to mock data."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(export_url, headers=headers, timeout=10)
        if response.status_code == 200:
            csv_data = response.content.decode('utf-8')
            import csv
            f = io.StringIO(csv_data)
            reader = csv.reader(f)
            return list(reader), False
    except Exception as e:
        pass
    
    return get_fallback_rows(), True

def parse_blocks(rows):
    """Slices the CSV rows list of lists into TW stock, US stock, and Fund lists of dicts."""
    tw_list = []
    us_list = []
    fund_list = []
    
    state = None
    for i, r in enumerate(rows):
        if not r or len(r) == 0 or not r[0].strip():
            continue
        
        first_cell = r[0].strip()
        
        # Section markers are rows containing "起始日"
        if "起始日" in r:
            if i < 11:
                state = 'TW'
            elif i < 16:
                state = 'US'
            else:
                state = 'FUND'
            continue
            
        if state == 'TW':
            code, name = parse_tw_code_name(first_cell)
            shares = clean_val(r[3])
            avg_cost = clean_val(r[4])
            cost = clean_val(r[5])
            sheet_price = clean_val(r[8])
            
            if code:
                tw_list.append({
                    'code': code,
                    'name': name,
                    'shares': shares,
                    'avg_cost': avg_cost,
                    'cost_twd': cost,
                    'sheet_price': sheet_price
                })
        elif state == 'US':
            code = first_cell
            shares = clean_val(r[3])
            avg_cost = clean_val(r[4])
            cost_ntd = clean_val(r[5])
            cost_usd = clean_val(r[6])
            sheet_price = clean_val(r[8])
            
            if code:
                us_list.append({
                    'code': code,
                    'shares': shares,
                    'avg_cost': avg_cost,
                    'cost_ntd': cost_ntd,
                    'cost_usd': cost_usd,
                    'sheet_price': sheet_price
                })
        elif state == 'FUND':
            code, name = parse_fund_code_name(first_cell)
            shares = clean_val(r[3])
            avg_cost = clean_val(r[4])
            cost_ntd = clean_val(r[5])
            cost_usd = clean_val(r[6])
            sheet_price = clean_val(r[8])
            
            if code:
                fund_list.append({
                    'code': code,
                    'name': name,
                    'shares': shares,
                    'avg_cost': avg_cost,
                    'cost_ntd': cost_ntd,
                    'cost_usd': cost_usd,
                    'sheet_price': sheet_price
                })
                
    return tw_list, us_list, fund_list

# --- live Stock Market Fetching with Technical Indicators ---

@st.cache_data(ttl=180)
def fetch_market_data(ticker_list):
    """Downloads historical data for stocks and calculates current price, SMA 20, Bias 20, and RSI 14."""
    results = {}
    for t in ticker_list:
        try:
            # Fetch 3 months of daily historical data to ensure we have enough rows for SMA20 and RSI14
            df = yf.download(t, period='3mo', progress=False)
            if df.empty or len(df) < 20:
                results[t] = {'success': False}
                continue
            
            # Flatten columns if MultiIndex
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            close_series = df['Close'].ffill().bfill()
            if isinstance(close_series, pd.DataFrame):
                close_series = close_series.iloc[:, 0]
            
            # 20-day SMA & Bias
            sma_20 = close_series.rolling(window=20).mean()
            bias_20 = ((close_series - sma_20) / sma_20) * 100
            
            # 14-day Wilder's RSI
            delta = close_series.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            rsi = 100 - (100 / (1 + rs))
            rsi = rsi.fillna(50)
            
            # Extracted values
            latest_price = float(close_series.iloc[-1])
            latest_sma = float(sma_20.iloc[-1])
            latest_bias = float(bias_20.iloc[-1])
            latest_rsi = float(rsi.iloc[-1])
            
            results[t] = {
                'latest_price': latest_price,
                'sma_20': latest_sma,
                'bias_20': latest_bias,
                'rsi_14': latest_rsi,
                'success': True
            }
        except Exception as e:
            results[t] = {'success': False, 'error': str(e)}
            
    return results

# --- Main App ---

# Sidebar setup
st.sidebar.image("https://img.icons8.com/gradient/100/globe.png", width=60)
st.sidebar.title("儀表板設定 Panel")

sheet_url_input = st.sidebar.text_input(
    "Google 試算表連結",
    value="https://docs.google.com/spreadsheets/d/1jSqcWLStquSw9pYCOMU3niZ-sKwz9wWpZXnaOdPm3x8/edit?usp=sharing"
)

usd_rate = st.sidebar.number_input(
    "動態匯率 (USD/TWD)",
    min_value=20.0,
    max_value=45.0,
    value=32.5,
    step=0.1
)

refresh_btn = st.sidebar.button("🔄 手動更新數據")
if refresh_btn:
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("""
### 💡 信號燈基準定義：
- 🔵 **超跌燈 (Oversold)**: RSI < 35
- 🔴 **過熱燈 (Overbought)**: RSI > 75
- ⚪ **中性 (Neutral)**: 35 ≤ RSI ≤ 75
""")

# Resolve and Fetch Data
export_url = make_export_url(sheet_url_input)
rows, is_fallback = load_sheet_rows(export_url)

# Display Top Banner
st.markdown("""
<div class="banner">
    <div class="banner-title">🌍 總體投資效應動態儀表板</div>
    <div class="banner-subtitle">即時串接 Google Sheets 與 Yahoo Finance 的投資組合量化與貨幣曝險分析</div>
</div>
""", unsafe_allow_html=True)

if is_fallback:
    st.warning("⚠️ 載入 Google 試算表失敗，已顯示本機快取備用資料。請確認您的試算表已設為『知道連結的任何人都能檢視』。")
else:
    st.success("✅ 成功從 Google Sheets 載入投資組合資料。")

# Parse sections
tw_raw, us_raw, fund_raw = parse_blocks(rows)

# Fetch yfinance prices
tw_symbols = [item['code'] + '.TW' for item in tw_raw]
us_symbols = [item['code'] for item in us_raw]
market_results = fetch_market_data(tw_symbols + us_symbols)

# Process Taiwan Stocks Data
processed_tw = []
for item in tw_raw:
    symbol = item['code'] + '.TW'
    cost_twd = item['cost_twd']
    shares = item['shares']
    
    # Try fetching live price
    if symbol in market_results and market_results[symbol]['success']:
        mdata = market_results[symbol]
        price = mdata['latest_price']
        sma_20 = mdata['sma_20']
        bias_20 = mdata['bias_20']
        rsi_14 = mdata['rsi_14']
    else:
        # Fallback to sheet price
        price = item['sheet_price'] if item['sheet_price'] > 0 else (cost_twd / shares if shares > 0 else 0)
        sma_20 = np.nan
        bias_20 = np.nan
        rsi_14 = np.nan
        
    market_val = shares * price
    unrealized_pnl = market_val - cost_twd
    roi = (unrealized_pnl / cost_twd * 100) if cost_twd > 0 else 0.0
    
    processed_tw.append({
        '代號': item['code'],
        '名稱': item['name'],
        '持有股數': shares,
        '平均成本': item['avg_cost'] if item['avg_cost'] > 0 else (cost_twd / shares if shares > 0 else 0.0),
        '總成本 (TWD)': cost_twd,
        '即時價格': price,
        '目前市值 (TWD)': market_val,
        '未實現損益 (TWD)': unrealized_pnl,
        '投資報酬率 (%)': roi,
        '20日均線': sma_20,
        '乖離率 (%)': bias_20,
        'RSI_14': rsi_14,
        '幣別': 'TWD',
        '類別': '台股'
    })

# Process US Stocks Data
processed_us = []
for item in us_raw:
    symbol = item['code']
    shares = item['shares']
    
    # Calculate costs
    cost_usd = item['cost_usd']
    cost_twd = cost_usd * usd_rate if cost_usd > 0 else item['cost_ntd']
    if cost_usd == 0:
        cost_usd = cost_twd / usd_rate
        
    if symbol in market_results and market_results[symbol]['success']:
        mdata = market_results[symbol]
        price_usd = mdata['latest_price']
        sma_20 = mdata['sma_20']
        bias_20 = mdata['bias_20']
        rsi_14 = mdata['rsi_14']
    else:
        price_usd = item['sheet_price'] if item['sheet_price'] > 0 else cost_usd / shares if shares > 0 else 0
        sma_20 = np.nan
        bias_20 = np.nan
        rsi_14 = np.nan
        
    market_val_usd = shares * price_usd
    market_val_twd = market_val_usd * usd_rate
    unrealized_pnl_twd = market_val_twd - cost_twd
    roi = (unrealized_pnl_twd / cost_twd * 100) if cost_twd > 0 else 0.0
    
    processed_us.append({
        '代號': item['code'],
        '名稱': item['code'],  # US stocks name defaults to Ticker
        '持有股數': shares,
        '平均成本': item['avg_cost'] if item['avg_cost'] > 0 else cost_usd / shares if shares > 0 else 0.0,
        '總成本 (TWD)': cost_twd,
        '即時價格': price_usd,  # USD
        '目前市值 (TWD)': market_val_twd,
        '未實現損益 (TWD)': unrealized_pnl_twd,
        '投資報酬率 (%)': roi,
        '20日均線': sma_20,
        '乖離率 (%)': bias_20,
        'RSI_14': rsi_14,
        '幣別': 'USD',
        '類別': '美股'
    })

# Process Funds Data
processed_funds = []
for item in fund_raw:
    shares = item['shares']
    cost_usd = item['cost_usd']
    cost_ntd = item['cost_ntd']
    
    # Determine Currency
    # USD asset if name contains "美元" or has non-zero cost_usd
    is_usd = "美元" in item['name'] or cost_usd > 0
    currency = 'USD' if is_usd else 'TWD'
    
    # Calculate costs
    if is_usd:
        cost_twd = cost_usd * usd_rate if cost_usd > 0 else cost_ntd
        cost_usd_final = cost_usd if cost_usd > 0 else cost_ntd / usd_rate
    else:
        cost_twd = cost_ntd if cost_ntd > 0 else cost_usd * usd_rate
        cost_usd_final = cost_twd / usd_rate
        
    # Get latest NAV
    nav = item['sheet_price']
    if nav == 0.0:
        # Fallback to purchase cost price if missing from sheet
        nav = (cost_usd_final / shares) if is_usd else (cost_twd / shares) if shares > 0 else 0.0
        
    if is_usd:
        market_val_twd = shares * nav * usd_rate
    else:
        market_val_twd = shares * nav
        
    unrealized_pnl_twd = market_val_twd - cost_twd
    roi = (unrealized_pnl_twd / cost_twd * 100) if cost_twd > 0 else 0.0
    
    processed_funds.append({
        '代號': item['code'],
        '名稱': item['name'],
        '持有股數': shares,
        '平均成本': item['avg_cost'] if item['avg_cost'] > 0 else (cost_usd_final / shares if is_usd else cost_twd / shares) if shares > 0 else 0.0,
        '總成本 (TWD)': cost_twd,
        '即時價格': nav,  # Local NAV
        '目前市值 (TWD)': market_val_twd,
        '未實現損益 (TWD)': unrealized_pnl_twd,
        '投資報酬率 (%)': roi,
        '20日均線': np.nan,  # Funds don't compute yfinance indicators
        '乖離率 (%)': np.nan,
        'RSI_14': np.nan,
        '幣別': currency,
        '類別': '基金'
    })

# Convert to dataframes
df_tw = pd.DataFrame(processed_tw)
df_us = pd.DataFrame(processed_us)
df_funds = pd.DataFrame(processed_funds)

# Merge all for macro calculation
df_all = pd.concat([df_tw, df_us, df_funds], ignore_index=True)

# ----------------- KPI Area (Macro Metrics) -----------------
total_cost = df_all['總成本 (TWD)'].sum()
total_market_value = df_all['目前市值 (TWD)'].sum()
total_pnl = total_market_value - total_cost
total_roi = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">💰 總投資付出成本</div>
        <div class="kpi-value">NT$ {total_cost:,.0f}</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-value-box">
            <div class="kpi-label">📈 目前投資總市值</div>
            <div class="kpi-value">NT$ {total_market_value:,.0f}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    pnl_color = "#f43f5e" if total_pnl < 0 else "#10b981"
    pnl_sign = "" if total_pnl < 0 else "+"
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">📊 總未實現損益</div>
        <div class="kpi-value" style="color: {pnl_color};">{pnl_sign}NT$ {total_pnl:,.0f}</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    roi_color = "#f43f5e" if total_roi < 0 else "#10b981"
    roi_sign = "" if total_roi < 0 else "+"
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">🚀 整體投資報酬率 (ROI)</div>
        <div class="kpi-value" style="color: {roi_color};">{roi_sign}{total_roi:.2f}%</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ----------------- Visualization Area -----------------
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.markdown("### 🧩 資產配置佔比 (Asset Allocation)")
    # Group by category
    df_cat = df_all.groupby('類別')['目前市值 (TWD)'].sum().reset_index()
    fig_cat = px.pie(
        df_cat,
        values='目前市值 (TWD)',
        names='類別',
        hole=0.4,
        color_discrete_sequence=px.colors.qualitative.Pastel
    )
    fig_cat.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_color='#f8fafc',
        margin=dict(t=30, b=10, l=10, r=10),
        legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5)
    )
    st.plotly_chart(fig_cat, use_container_width=True)

with chart_col2:
    st.markdown("### 💱 貨幣曝險比例 (Currency Exposure)")
    # Group by currency exposure
    # All assets marked as USD (US stocks & USD funds) vs TWD (Taiwan stocks & TWD funds)
    df_curr = df_all.groupby('幣別')['目前市值 (TWD)'].sum().reset_index()
    df_curr['貨幣名稱'] = df_curr['幣別'].map({'USD': '美元資產 (USD)', 'TWD': '新台幣資產 (TWD)'})
    
    fig_curr = px.pie(
        df_curr,
        values='目前市值 (TWD)',
        names='貨幣名稱',
        hole=0.4,
        color_discrete_map={'美元資產 (USD)': '#6366f1', '新台幣資產 (TWD)': '#10b981'},
        color='貨幣名稱'
    )
    fig_curr.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_color='#f8fafc',
        margin=dict(t=30, b=10, l=10, r=10),
        legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5)
    )
    st.plotly_chart(fig_curr, use_container_width=True)

# ----------------- Quantitative Decision Signals Section -----------------
st.markdown("---")
st.markdown("## 🔍 股市量化決策訊號燈 (Stocks Technical Signals)")

# Filter stocks only (TW & US)
df_stocks = df_all[df_all['類別'].isin(['台股', '美股'])].copy()

# Add signal mapping
def get_signal_label(rsi):
    if pd.isna(rsi):
        return 'N/A'
    if rsi < 35:
        return '超跌 🔵'
    elif rsi > 75:
        return '過熱 🔴'
    else:
        return '中性 ⚪'

def get_signal_class(rsi):
    if pd.isna(rsi):
        return 'signal-neutral'
    if rsi < 35:
        return 'signal-oversold'
    elif rsi > 75:
        return 'signal-overbought'
    else:
        return 'signal-neutral'

df_stocks['信號'] = df_stocks['RSI_14'].apply(get_signal_label)
df_stocks['信號類別'] = df_stocks['RSI_14'].apply(get_signal_class)

# Display stocks signal table
display_stocks = df_stocks[[
    '代號', '名稱', '即時價格', '幣別', '20日均線', '乖離率 (%)', 'RSI_14', '信號'
]].copy()

# Formatting numbers for visual presentation
display_stocks['即時價格'] = display_stocks.apply(
    lambda r: f"${r['即時價格']:,.2f} USD" if r['幣別'] == 'USD' else f"${r['即時價格']:,.2f} TWD", axis=1
)
display_stocks['20日均線'] = display_stocks.apply(
    lambda r: f"${r['20日均線']:,.2f}" if pd.notna(r['20日均線']) else "N/A", axis=1
)
display_stocks['乖離率 (%)'] = display_stocks['乖離率 (%)'].apply(
    lambda x: f"{x:+.2f}%" if pd.notna(x) else "N/A"
)
display_stocks['RSI_14'] = display_stocks['RSI_14'].apply(
    lambda x: f"{x:.2f}" if pd.notna(x) else "N/A"
)

# Output Table
st.dataframe(
    display_stocks,
    use_container_width=True,
    column_config={
        "代號": st.column_config.TextColumn("代號"),
        "名稱": st.column_config.TextColumn("標的名稱"),
        "即時價格": st.column_config.TextColumn("最新即時價格"),
        "20日均線": st.column_config.TextColumn("20日月均線"),
        "乖離率 (%)": st.column_config.TextColumn("月線乖離率"),
        "RSI_14": st.column_config.TextColumn("14日 RSI"),
        "信號": st.column_config.TextColumn("量化決策信號"),
    },
    hide_index=True
)

# 今日關注標的卡片
st.markdown("### 🔔 今日極端信號關注標的")
oversold_targets = df_stocks[df_stocks['RSI_14'] < 35]
overbought_targets = df_stocks[df_stocks['RSI_14'] > 75]

if len(oversold_targets) == 0 and len(overbought_targets) == 0:
    st.info("🟢 今日無極端訊號標的，所有標的均在常態區間波動。")
else:
    focus_col1, focus_col2 = st.columns(2)
    
    with focus_col1:
        if len(oversold_targets) > 0:
            st.markdown("#### 🔵 超跌關注區 (RSI < 35)")
            for idx, r in oversold_targets.iterrows():
                st.markdown(f"""
                <div class="signal-pill signal-oversold" style="padding: 1rem; width: 100%; margin-bottom: 0.5rem; text-align: left;">
                    <strong>{r['代號']} {r['名稱']}</strong> (RSI: {r['RSI_14']:.2f} | 乖離率: {r['乖離率 (%)']:.2f}%)<br>
                    <span style="font-size: 0.85rem; opacity: 0.9;">技術分析指引：短期股價過度修正，動能指標低於超賣區，具備高度技術反彈契機。</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.write("目前無超跌標的。")
            
    with focus_col2:
        if len(overbought_targets) > 0:
            st.markdown("#### 🔴 過熱警戒區 (RSI > 75)")
            for idx, r in overbought_targets.iterrows():
                st.markdown(f"""
                <div class="signal-pill signal-overbought" style="padding: 1rem; width: 100%; margin-bottom: 0.5rem; text-align: left;">
                    <strong>{r['代號']} {r['名稱']}</strong> (RSI: {r['RSI_14']:.2f} | 乖離率: {r['乖離率 (%)']:.2f}%)<br>
                    <span style="font-size: 0.85rem; opacity: 0.9;">技術分析指引：股價短期強勢噴發且大幅偏離月線，指標進入超買區，需嚴防拉回修正風險。</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.write("目前無過熱標的。")

# ----------------- Detailed Data Section -----------------
st.markdown("---")
st.markdown("## 📋 原始數據與明細細項")
tab1, tab2, tab3 = st.tabs(["🇹🇼 台股明細", "🇺🇸 美股明細", "📈 基金明細"])

with tab1:
    # Display formatted Taiwan Stocks
    df_tw_formatted = df_tw.copy()
    for col in ['總成本 (TWD)', '目前市值 (TWD)', '未實現損益 (TWD)']:
        df_tw_formatted[col] = df_tw_formatted[col].apply(lambda x: f"${x:,.0f} TWD")
    df_tw_formatted['即時價格'] = df_tw_formatted['即時價格'].apply(lambda x: f"${x:,.2f}")
    df_tw_formatted['平均成本'] = df_tw_formatted['平均成本'].apply(lambda x: f"${x:,.2f}")
    df_tw_formatted['投資報酬率 (%)'] = df_tw_formatted['投資報酬率 (%)'].apply(lambda x: f"{x:+.2f}%")
    st.dataframe(df_tw_formatted.drop(columns=['20日均線', '乖離率 (%)', 'RSI_14', '類別']), use_container_width=True, hide_index=True)

with tab2:
    # Display formatted US Stocks
    df_us_formatted = df_us.copy()
    for col in ['總成本 (TWD)', '目前市值 (TWD)', '未實現損益 (TWD)']:
        df_us_formatted[col] = df_us_formatted[col].apply(lambda x: f"${x:,.0f} TWD")
    df_us_formatted['即時價格'] = df_us_formatted['即時價格'].apply(lambda x: f"${x:,.2f} USD")
    df_us_formatted['平均成本'] = df_us_formatted['平均成本'].apply(lambda x: f"${x:,.2f} USD")
    df_us_formatted['投資報酬率 (%)'] = df_us_formatted['投資報酬率 (%)'].apply(lambda x: f"{x:+.2f}%")
    st.dataframe(df_us_formatted.drop(columns=['20日均線', '乖離率 (%)', 'RSI_14', '類別']), use_container_width=True, hide_index=True)

with tab3:
    # Display formatted Funds
    df_funds_formatted = df_funds.copy()
    for col in ['總成本 (TWD)', '目前市值 (TWD)', '未實現損益 (TWD)']:
        df_funds_formatted[col] = df_funds_formatted[col].apply(lambda x: f"${x:,.0f} TWD")
    df_funds_formatted['即時價格'] = df_funds_formatted.apply(
        lambda r: f"${r['即時價格']:,.4f} USD" if r['幣別'] == 'USD' else f"${r['即時價格']:,.4f} TWD", axis=1
    )
    df_funds_formatted['平均成本'] = df_funds_formatted.apply(
        lambda r: f"${r['平均成本']:,.4f} USD" if r['幣別'] == 'USD' else f"${r['平均成本']:,.4f} TWD", axis=1
    )
    df_funds_formatted['投資報酬率 (%)'] = df_funds_formatted['投資報酬率 (%)'].apply(lambda x: f"{x:+.2f}%")
    st.dataframe(df_funds_formatted.drop(columns=['20日均線', '乖離率 (%)', 'RSI_14', '類別']), use_container_width=True, hide_index=True)

# Footer
st.markdown("---")
st.markdown(
    f"<div style='text-align: center; color: #64748b; font-size: 0.8rem; padding-bottom: 2rem;'>"
    f"總體投資效應儀表板 | 當前系統時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 數據源: Google Sheets & Yahoo Finance"
    f"</div>", 
    unsafe_allow_html=True
)
