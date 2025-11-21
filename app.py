import streamlit as st
import pandas as pd
import requests
import xmltodict
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from supabase import create_client
import random
import time
import math
import html
import urllib.parse
import re
from bs4 import BeautifulSoup
import feedparser
import requests
import folium
from streamlit_folium import st_folium

# -----------------------------------------------------------------------------
# 0. 함수 정의 섹션
# -----------------------------------------------------------------------------

def do_login():
    """로그인 폼 제출 시 실행되는 콜백 함수."""
    team = st.session_state.get('login_team_input', '').strip()
    name = st.session_state.get('login_name_input', '').strip()
    
    if not team or not name:
        st.session_state.login_error = "팀 명과 이름을 모두 입력해주세요."
        return
        
    st.session_state.user_name = name
    st.session_state.team_name = team
    st.session_state.logged_in = True
    
    if 'login_error' in st.session_state: st.session_state.pop('login_error')
    
    # spinner는 콜백 내부에서 UI에 즉시 반영되지 않을 수 있으나 로직 유지를 위해 남겨둠
    with st.spinner("로그인 처리 중..."):
        time.sleep(0.6)
        
    st.session_state.onboarding_step = 2
    # st.rerun()  <-- [수정됨] 콜백 내부이므로 제거 (자동 리런됨)


def handle_onboard_step1():
    """Step 2: 역할 선택 후 Step 3로 이동"""
    choice = st.session_state.get('onboard_role_choice', '컨설턴트')
    if choice == '컨설턴트': 
        st.session_state.user_info['job'] = 'Consultant'
    else: 
        st.session_state.user_info['job'] = 'Broker'
    
    st.session_state.onboarding_step = 3 
    # st.rerun() 제거됨


def handle_onboard_step2():
    """Step 3: 업무 단계 선택 후 대시보드로 이동 (onboarding_step = 4)"""
    choice = st.session_state.get('onboard_status_choice', '시장 조사 중')
    
    if choice == '시장 조사 중':
        st.session_state.user_info['status'] = 'Research'
        st.session_state.app_config['mode'] = 'Regional Analysis'
        st.session_state.app_config['auto_run'] = True
    elif choice == '제안서 작성 중':
        st.session_state.user_info['status'] = 'Proposal'
        st.session_state.app_config['mode'] = 'Micro-Market Deep Dive'
        st.session_state.app_config['auto_run'] = True
    elif choice == '매물 탐색 중':
        st.session_state.user_info['status'] = 'Sourcing'
        st.session_state.app_config['mode'] = 'Micro-Market Deep Dive'
        st.session_state.app_config['default_tab'] = 1
        st.session_state.app_config['auto_run'] = True
        
    st.session_state.onboarding_step = 4 
    
    with st.spinner("설정 저장 및 대시보드 로딩 중..."):
        time.sleep(0.5)
    # st.rerun() <-- [수정됨] 콜백 내부이므로 제거 (자동 리런됨)


def do_logout():
    """Clear session and return to login screen."""
    st.session_state.logged_in = False
    st.session_state.user_name = ""
    st.session_state.team_name = ""
    st.session_state.onboarding_step = 1
    st.session_state.user_info = {"job": "", "status": ""}
    st.session_state.app_config = {"mode": "Regional Analysis", "auto_run": True, "default_tab": 0}
    if "reg_news_data" in st.session_state: del st.session_state["reg_news_data"]
    
    # 만약 do_logout이 on_click 콜백으로 불린다면 st.rerun()은 제거해야 함
    # 일반 버튼 로직(if st.button: do_logout())으로 불린다면 유지 가능
    with st.spinner("로그아웃 중..."):
        time.sleep(0.6)
    st.rerun()


def clean_google_news_description(html_content):
    """
    구글 뉴스 특화 클리너:
    본문에 포함된 '관련 기사 목록(ul/li)'을 통째로 제거하여
    메인 기사의 요약문만 남깁니다.
    """
    if not html_content: return ""
    
    try:
        soup = BeautifulSoup(str(html_content), "html.parser")
        
        # [핵심] <ul>, <ol>, <li> 태그(다른 기사 제목들)를 찾아서 삭제(decompose)
        for tag in soup.find_all(['ul', 'ol', 'li']):
            tag.decompose()
            
        # 남은 텍스트(순수 요약)만 추출
        text = soup.get_text(separator=" ")
        
        # HTML 엔티티(&quot; 등) 변환 및 공백 정리
        text = html.unescape(text)
        return " ".join(text.split())
        
    except:
        # 파싱 실패 시 기본 태그 제거만 시도
        return re.sub(r'<[^>]+>', '', str(html_content)).strip()

def extract_keywords(title):
    """제목에서 해시태그용 키워드 추출"""
    clean = re.sub(r'[^\w\s]', ' ', title)
    words = clean.split()
    # 불용어 사전 (계속 추가 가능)
    stop_words = ["뉴스", "종합", "속보", "오늘", "내일", "서울", "경기", "대박", "충격", "발표", "공개", "단독", "매일경제", "한국경제", "기자", "부동산", "오피스", "시장", "기록", "전망"]
    keywords = [w for w in words if len(w) >= 2 and w not in stop_words]
    return list(dict.fromkeys(keywords))[:4] 

def fetch_rss_news(query, max_results=20):
    """
    RSS 데이터를 가져오되, clean_google_news_description을 적용하여
    지저분한 '다른 기사 제목'들을 제거합니다.
    """
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
    
    try:
        feed = feedparser.parse(rss_url)
        articles = []
        
        for entry in feed.entries:
            if len(articles) >= max_results: break
            
            # 1. 제목 처리 (HTML 특수문자 해제)
            clean_title = html.unescape(entry.title)
            
            # 2. 본문 처리 (구글 뉴스 전용 클리너 적용)
            raw_summary = entry.get('summary', '')
            clean_body = clean_google_news_description(raw_summary)
            
            # 제목과 본문이 너무 비슷하면 본문 숨김 (구글 뉴스 특성)
            title_sig = clean_title.replace(" ", "")
            body_sig = clean_body.replace(" ", "")
            if len(clean_body) < 10 or title_sig in body_sig:
                display_body = "상세 내용은 아래 링크에서 확인하세요."
            else:
                display_body = clean_body[:200] + "..." # 너무 길면 자름

            pub_date = entry.get('published', 'Recent')[:16] # 날짜 포맷팅
            
            articles.append({
                'title': clean_title,
                'body': display_body,
                'url': entry.link,
                'date': pub_date,
                'source': entry.get('source', {}).get('title', 'Google News')
            })
            
        return articles

    except Exception as e:
        print(f"RSS Error: {e}")
        return []
    
def get_recent_months(base_date, n=6):
    months = []
    curr = base_date
    for _ in range(n):
        prev = curr - timedelta(days=30)
        months.append(prev.strftime("%Y%m"))
        curr = prev
    return months[::-1]

@st.cache_data(ttl=3600)
def fetch_molit_data(sector, district_code, ymd, _api_keys):
    try:
        if "Co-living" in sector:
            url = "http://apis.data.go.kr/1613000/RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade"
            key = _api_keys["officetel_trade"]; area_col = '전용면적'
        elif "Development" in sector:
            url = "http://apis.data.go.kr/1613000/RTMSDataSvcLandTrade/getRTMSDataSvcLandTrade"
            key = _api_keys["land_trade"]; area_col = '거래면적'
        else:
            url = "http://apis.data.go.kr/1613000/RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade"
            key = _api_keys["commercial_trade"]; area_col = '대지면적'

        params = {"serviceKey": requests.utils.unquote(key), "LAWD_CD": district_code, "DEAL_YMD": ymd, "numOfRows": 1000}
        response = requests.get(url, params=params)
        data_dict = xmltodict.parse(response.content)

        if 'response' in data_dict and 'body' in data_dict['response'] and 'items' in data_dict['response']['body']:
            items = data_dict['response']['body']['items']['item']
            if isinstance(items, dict): items = [items]
            df = pd.DataFrame(items)
            col_map = {'dealAmount': '거래금액', 'platArea': '대지면적', 'plottageAr': '대지면적', 'archArea': '건축면적', 'buildingAr': '건축면적', 'dealArea': '거래면적', 'excluUseAr': '전용면적', 'buildYear': '건축년도', 'bldgNm': '건물명', 'buildNm': '건물명', 'umdNm': '법정동', 'floor': '층', 'sggNm': '시군구', 'jibun': '지번'}
            df = df.rename(columns=col_map)
            for c in ['건물명', '법정동', '지번', '층']: 
                if c not in df.columns: df[c] = "-"
            df['거래금액'] = df['거래금액'].str.replace(',', '').astype(float)
            if area_col in df.columns:
                df[area_col] = df[area_col].astype(float)
                df = df[df[area_col] > 0]
                df['평당가'] = (df['거래금액'] / df[area_col] * 3.3058 / 10000).round(1)
            else: df['평당가'] = 0
            df['기준년월'] = ymd
            return df
        else: return pd.DataFrame()
    except: return pd.DataFrame()


def calculate_ai_rent_recommendation(district, sector, base_df=None):
    random.seed(hash(district + sector) % 100) 
    base_rent_factor = random.uniform(0.0008, 0.0012)
    
    if sector == "Retail":
        if district in ["강남구", "서초구", "송파구"]: premium = random.uniform(1.2, 1.5)
        elif district in ["종로구", "중구", "마포구"]: premium = random.uniform(0.9, 1.1)
        else: premium = random.uniform(0.7, 0.9)
    else: 
        base_rent_factor = random.uniform(0.0005, 0.0008)
        premium = random.uniform(0.8, 1.1)

    if base_df is not None and not base_df.empty and '평당가' in base_df.columns:
        avg_land_price = base_df['평당가'].mean() * 10000 
    else:
        base_prices = {"강남구": 50000, "서초구": 45000, "마포구": 30000, "Retail": 18000}
        avg_land_price = base_prices.get(district, base_prices.get(sector, 25000)) * 10000

    recommended_rent_manwon = round(avg_land_price * base_rent_factor * premium / 10000 * 10) / 10
    
    if recommended_rent_manwon < 10: recommended_rent_manwon = 10.0
    if recommended_rent_manwon > 30: recommended_rent_manwon = 30.0

    return recommended_rent_manwon

# Safe rerun helper
def try_rerun():
    try:
        if hasattr(st, 'experimental_rerun'):
            st.experimental_rerun()
        else:
            st.session_state._needs_rerun = True
            st.stop()
    except Exception:
        pass

# -----------------------------------------------------------------------------
# 1. 시스템 설정 & CSS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="REA 부동산 리서치 플랫폼",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

CBRE_NAVY = "#183567"
BG_COLOR = "#FFFFFF"

FALLBACK_SUPABASE_URL = "https://rgogkkcsykamhdxoazrt.supabase.co"
FALLBACK_SUPABASE_KEY = "sb_publishable_djiSJdYGXF8TGXXAP4bUdA_mVSiGpHb"

st.markdown(f"""
    <style>
    @font-face {{
        font-family: 'CorporateFont';
        src: url('fonts/MyFont.ttf') format('truetype');
    }}
    html, body, [class*="css"], button, input, select, textarea {{
        font-family: 'CorporateFont', 'Pretendard', sans-serif !important;
    }}
    .stApp {{ background-color: {BG_COLOR}; }}
    
    div.stButton > button:first-child {{
        background-color: white !important;
        color: {CBRE_NAVY} !important;
        border: 2px solid {CBRE_NAVY} !important;
        font-weight: 900 !important;
        font-size: 1.1rem !important;
        border-radius: 4px;
        padding: 0.5rem 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        width: 100%;
        height: 50px;
    }}
    div.stButton > button:first-child:hover {{
        background-color: {CBRE_NAVY} !important;
        color: white !important;
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        transform: translateY(-1px);
    }}

/* [사이드바 기본 설정] 글씨는 흰색 */
    section[data-testid="stSidebar"] {{ background-color: {CBRE_NAVY} !important; }}
    section[data-testid="stSidebar"] * {{ color: white !important; }}
    
    /* [핵심 수정] 텍스트 입력창(stTextInput, stTextArea) 내부만 콕 집어서 검은 글씨/흰 배경 적용 */
    section[data-testid="stSidebar"] div[data-testid="stTextInput"] input,
    section[data-testid="stSidebar"] div[data-testid="stTextArea"] textarea {{
        color: #000000 !important;              /* 글씨 검정 */
        background-color: #ffffff !important;   /* 배경 흰색 */
        -webkit-text-fill-color: #000000 !important;
        caret-color: #000000 !important;        /* 커서 깜빡임 검정 */
    }}

    /* 셀렉트박스 스타일 */
    section[data-testid="stSidebar"] .stSelectbox > div > div {{
        background-color: rgba(255, 255, 255, 0.1) !important;
        border: 1px solid rgba(255, 255, 255, 0.3) !important;
        color: white !important;
    }}
    
    /* 라디오 버튼 라벨 */
    section[data-testid="stSidebar"] .stRadio label {{
        font-size: 15px !important; font-weight: 600 !important; padding-bottom: 5px;
    }}
    
    section[data-testid="stSidebar"] button,
    section[data-testid="stSidebar"] div.stButton > button,
    section[data-testid="stSidebar"] button[kind="primary"],
    section[data-testid="stSidebar"] button[kind="secondary"] {{
        background: #f1f5f9 !important;
        color: #0f172a !important;
        border: none !important;
        font-weight: 900 !important;
        font-size: 1.05rem !important;
        padding: 14px 20px !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 8px rgba(0,0,0,0.3) !important;
        text-shadow: none !important;
        letter-spacing: 0.3px !important;
    }}
    
    section[data-testid="stSidebar"] button *,
    section[data-testid="stSidebar"] button span,
    section[data-testid="stSidebar"] button p {{
        color: #0f172a !important;
    }}
    
    section[data-testid="stSidebar"] .stDateInput label {{
        color: white !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        margin-bottom: 8px !important;
    }}
    section[data-testid="stSidebar"] .stDateInput > div > div,
    section[data-testid="stSidebar"] .stDateInput input {{
        background-color: white !important;
        color: {CBRE_NAVY} !important;
        border: 2px solid #cbd5e1 !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        padding: 10px !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2) !important;
    }}
    section[data-testid="stSidebar"] .stDateInput input::placeholder {{
        color: #64748b !important;
    }}

    .stTabs [data-baseweb="tab-list"] {{ gap: 2px; width: 100%; }}
    .stTabs [data-baseweb="tab"] {{
        height: 48px; background-color: white; border-radius: 4px 4px 0 0;
        color: #444; border: 1px solid #ddd; border-bottom: none; flex: 1; font-size: 15px; font-weight: 700;
    }}
    .stTabs [aria-selected="true"] {{
        background-color: {CBRE_NAVY} !important; color: white !important; border: none;
    }}
    
    .tooltip-icon {{
        display: inline-block;
        width: 16px;
        height: 16px;
        background-color: #94a3b8;
        color: white;
        border-radius: 50%;
        text-align: center;
        font-size: 12px;
        line-height: 16px;
        margin-left: 6px;
        cursor: help;
        position: relative;
    }}
    .tooltip-icon:hover::after {{
        content: attr(data-tooltip);
        position: absolute;
        left: 50%;
        bottom: 125%;
        transform: translateX(-50%);
        background-color: #1e293b;
        color: white;
        padding: 12px;
        border-radius: 6px;
        width: 280px;
        font-size: 0.85rem;
        line-height: 1.4;
        z-index: 1000;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        white-space: pre-line;
    }}
    .tooltip-icon:hover::before {{
        content: '';
        position: absolute;
        left: 50%;
        bottom: 115%;
        transform: translateX(-50%);
        border: 6px solid transparent;
        border-top-color: #1e293b;
        z-index: 1000;
    }}
    
    .css-card {{
        background-color: white; border-radius: 8px; padding: 24px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #e5e7eb; margin-bottom: 20px;
    }}
    .css-card:empty {{
        display: none !important;
        height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        border: none !important;
    }}
    .kpi-card {{
        background-color: white; border-radius: 6px; padding: 20px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1); border: 1px solid #e5e7eb; 
        text-align: center; 
        min-height: 160px;
        display: flex; flex-direction: column; justify-content: center;
    }}
    .kpi-value {{ font-size: 1.8rem; font-weight: 800; color: #111827; margin: 10px 0; }}
    .kpi-label {{ font-size: 0.9rem; color: #6b7280; font-weight: 600; }}
    .kpi-sub {{ font-size: 0.8rem; color: #059669; font-weight: 600; }}

    .news-card {{ 
        border-bottom: 1px solid #eee; 
        padding: 15px 0; 
        transition: background-color 0.2s;
        position: relative;
        padding-left: 35px;
    }}
    .news-card:hover {{ background-color: #f9fafb; }}
    .news-card::before {{
        content: attr(data-index);
        position: absolute;
        left: 0;
        top: 15px;
        width: 28px;
        height: 28px;
        background-color: {CBRE_NAVY};
        color: white;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        font-size: 0.85rem;
    }}
    .news-title {{ 
        font-size: 1.05rem; 
        font-weight: bold; 
        color: #111; 
        text-decoration: none; 
        display: block; 
        margin-bottom: 5px; 
    }}
    .news-title:hover {{ color: {CBRE_NAVY}; }}
    .news-meta {{ font-size: 0.8rem; color: #888; margin-bottom: 8px; }}
    .news-body {{ font-size: 0.9rem; color: #444; line-height: 1.5; }}
    
    .login-container {{
        background-color: white; padding: 40px; border-radius: 12px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.1); text-align: center; border-top: 5px solid {CBRE_NAVY};
    }}

    .onboarding-main-container {{
        background-color: white;
        padding: 40px;
        border-radius: 10px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        margin: 50px auto;
        max-width: 800px;
        display: flex;
        flex-direction: column;
    }}
    .onboarding-title {{
        color: {CBRE_NAVY};
        font-weight: 800;
        font-size: 2em;
        margin-bottom: 5px;
    }}
    .onboarding-subtitle {{
        color: #444;
        font-size: 1.1em;
        margin-bottom: 30px;
    }}
    .onboarding-step-box {{
        padding: 20px;
        border: 1px solid #ddd;
        border-radius: 8px;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        transition: all 0.3s;
    }}
    .onboarding-active-step {{
        background-color: #f1f5f9;
        border-left: 5px solid {CBRE_NAVY};
    }}
    .step-number {{
        font-size: 1.5em;
        font-weight: bold;
        color: {CBRE_NAVY};
        margin-right: 15px;
    }}
    .step-text {{
        font-size: 1.1em;
        color: #333;
    }}
    </style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. Supabase & Utils
# -----------------------------------------------------------------------------
@st.cache_resource
def init_supabase():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
    except Exception:
        try:
            url = FALLBACK_SUPABASE_URL
            key = FALLBACK_SUPABASE_KEY
        except Exception:
            return None

    try:
        return create_client(url, key)
    except: return None

supabase = init_supabase()

supabase_ready = False
if not supabase:
    try:
        supabase = create_client(FALLBACK_SUPABASE_URL, FALLBACK_SUPABASE_KEY)
    except Exception:
        supabase = None

if supabase:
    try:
        _test = supabase.table('market_insights').select('id').limit(1).execute()
        if isinstance(_test, dict):
            ok_data = _test.get('data')
            ok_err = _test.get('error')
        else:
            ok_data = getattr(_test, 'data', None)
            ok_err = getattr(_test, 'error', None)
        if ok_err is None and ok_data is not None:
            supabase_ready = True
    except Exception:
        supabase_ready = False

TRANS = {
    "KR": {
        "mode_macro": "지역별 시장 분석 (Regional Analysis)", "mode_micro": "마이크로 마켓 분석 (Micro-Market)",
        "filter_title": "검색 필터", "sector_label": "자산군", "district_label": "지역 선택",
        "period_label": "조회 기준일", "btn_search": "데이터 분석 실행", "unit_money": "억원",
        "tab1": "대시보드", "tab2": "지도", "tab3": "원본 데이터 추출", "tab4": "뉴스/규제", "tab5": "수익률 분석",
        "kpi1": "평균 평당가", "kpi2": "총 거래 건수", "kpi3": "시장 수익률(Cap)", "kpi4": "임대율(Occupancy)",
        "chart_trend": "가격 및 거래량 추이", "chart_dist": "지역별 거래 비중",
        "news_header": "부동산 주요 뉴스 & 규제", "search_ph": "검색어 (예: 오피스 전망)", "search_btn": "뉴스 검색",
        "role_consultant": "컨설턴트", "role_broker": "중개업자/투자자",
        "sido_label": "시/도 선택", "sigungu_label": "시/군/구 선택",
        "proj_mng": "📁 프로젝트 관리", "proj_new": "새 프로젝트 이름", "proj_add": "+ 프로젝트 추가",
        "save_btn": "💾 현재 분석 저장", "save_title": "📝 분석 저장",
        "save_label_proj": "프로젝트 선택", "save_label_title": "저장 제목", "save_label_memo": "메모 (선택사항)",
        "btn_save": "✅ 저장", "btn_cancel": "❌ 취소",
        "filter_dong": "세부 지역 필터",
        "calc_title": "🧮 수지분석 시뮬레이터 (Feasibility)",
        "calc_land": "토지 평당가 (만원)", "calc_rent": "예상 임대료 (만원/평)",
        "calc_far": "용적률 (FAR %)", "calc_const": "건축 평당가 (만원)",
        "calc_res": "예상 수익률 (Cap Rate)",
        # [새로 추가된 번역]
        "desc_main": "<b>부동산 마켓 인텔리전스 플랫폼 REA</b>는 국토교통부 실거래가 기반 상업용 부동산 분석 도구입니다. 지역별 시세 트렌드 파악, 매물 상세 분석, 최신 규제 및 뉴스 리서치 기능을 통합하여 데이터에 기반한 빠르고 정확한 의사결정을 지원합니다. 팀 베이스의 프로젝트 관리 기능을 지원하여 협업 효율성을 극대화합니다.",
        "btn_guide": "📄 이용 가이드",
        "drive_header": "드라이브"
    },
    "EN": {
        "mode_macro": "Regional Analysis", "mode_micro": "Micro-Market Deep Dive",
        "filter_title": "Filters", "sector_label": "Asset Class", "district_label": "District",
        "period_label": "Date", "btn_search": "Run Analysis", "unit_money": "B KRW",
        "tab1": "Dashboard", "tab2": "Map", "tab3": "Raw Data Export", "tab4": "News", "tab5": "Feasibility",
        "kpi1": "Avg Price", "kpi2": "Transactions", "kpi3": "Market Cap", "kpi4": "Occupancy",
        "chart_trend": "Price Trends", "chart_dist": "Distribution",
        "news_header": "Market News", "search_ph": "Keywords...", "search_btn": "Search",
        "role_consultant": "Consultant", "role_broker": "Broker/Investor",
        "sido_label": "Select Province", "sigungu_label": "Select District",
        "proj_mng": "📁 Project Management", "proj_new": "New Project Name", "proj_add": "+ Add Project",
        "save_btn": "💾 Save Analysis", "save_title": "📝 Save Analysis",
        "save_label_proj": "Select Project", "save_label_title": "Title", "save_label_memo": "Memo (Optional)",
        "btn_save": "✅ Save", "btn_cancel": "❌ Cancel",
        "filter_dong": "Filter by Neighborhood (Dong)",
        "calc_title": "🧮 Feasibility Simulator",
        "calc_land": "Land Price (10k KRW/p)", "calc_rent": "Est. Rent (10k KRW/p)",
        "calc_far": "FAR (%)", "calc_const": "Const. Cost (10k KRW/p)",
        "calc_res": "Est. Cap Rate",
        # [Added Translations]
        "desc_main": "<b>Real Estate Market Intelligence Platform</b> is a commercial real estate analysis tool based on MOLIT actual transaction data. It supports fast and accurate decision-making by integrating regional price trend analysis, detailed property analysis, and the latest regulation & news research. It also offers team-based project management features to maximize collaboration efficiency.",
        "btn_guide": "📄 User Guide",
        "drive_header": "Drive"
    }
}

SECTOR_MAP = {"KR": ["오피스 (Office)", "리테일 (Retail)", "호텔 (Hotel)", "코리빙 (Co-living)", "개발부지 (Land)"], "EN": ["Office", "Retail", "Hotel", "Co-living", "Development"]}
SECTOR_API_KEY_MAP = {"오피스 (Office)": "Office", "Office": "Office", "리테일 (Retail)": "Retail", "Retail": "Retail", "호텔 (Hotel)": "Hotel", "Hotel": "Hotel", "코리빙 (Co-living)": "Co-living", "Co-living": "Co-living", "개발부지 (Land)": "Development", "Development": "Development"}
SECTOR_TO_KR = {"Office": "오피스", "Retail": "상가", "Hotel": "호텔", "Co-living": "오피스텔", "Development": "토지"}
DISTRICT_HIERARCHY = {
    "서울특별시": {
        "강남구": "11680", "서초구": "11650", "송파구": "11710", "영등포구": "11560", 
        "마포구": "11440", "종로구": "11110", "중구": "11140", "용산구": "11170", 
        "성동구": "11200", "광진구": "11215", "동대문구": "11230", "중랑구": "11260", 
        "성북구": "11290", "강북구": "11305", "도봉구": "11320", "노원구": "11350", 
        "은평구": "11380", "서대문구": "11410", "양천구": "11470", "강서구": "11500", 
        "구로구": "11530", "금천구": "11545", "동작구": "11590", "관악구": "11620", 
        "강동구": "11740"
    },
    "부산광역시": {"해운대구": "26350", "수영구": "26290", "동래구": "26260", "부산진구": "26230"},
    "대구광역시": {"수성구": "27260", "달서구": "27290", "중구": "27110"},
    "인천광역시": {"연수구": "28185", "남동구": "28140", "서구": "28260"},
    "대전광역시": {"서구": "30170", "유성구": "30200", "중구": "30140"},
    "울산광역시": {"남구": "31140", "중구": "31110", "북구": "31200"},
    "세종특별자치시": {"세종특별자치시": "36110"},
    "경기도": {
        "성남 분당구": "41135", "수원 영통구": "41113", "화성시": "41590", "고양 일산동구": "41285",
        "용인 수지구": "41465", "안양 동안구": "41173", "평택시": "41220", "남양주시": "41360"
    },
    "강원특별자치도": {"춘천시": "42110", "원주시": "42130", "강릉시": "42150"},
    "충청남도": {"천안 서북구": "44133", "아산시": "44200"},
    "경상남도": {"창원 성산구": "48123", "김해시": "48250", "양산시": "48310"},
    "제주특별자치도": {"제주시": "50110", "서귀포시": "50130"}
}

DISTRICT_MAP = {}
for sido, sigungu_map in DISTRICT_HIERARCHY.items():
    for sigungu, code in sigungu_map.items():
        key_name = f"{sido} {sigungu}" if sigungu != sido else sido
        DISTRICT_MAP[key_name] = code


# -----------------------------------------------------------------------------
# 3. 상태 관리
# -----------------------------------------------------------------------------
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_name' not in st.session_state: st.session_state.user_name = ""
if 'team_name' not in st.session_state: st.session_state.team_name = ""
if 'onboarding_step' not in st.session_state: st.session_state.onboarding_step = 1 
if 'user_info' not in st.session_state: st.session_state.user_info = {"job": "", "status": ""}
if 'app_config' not in st.session_state: st.session_state.app_config = {"mode": "Regional Analysis", "auto_run": True, "default_tab": 0}
if "news_results" not in st.session_state: st.session_state.news_results = []
if "news_page" not in st.session_state: st.session_state.news_page = 0
if 'projects' not in st.session_state: 
    st.session_state.projects = ["프로젝트1", "프로젝트2", "프로젝트3"]
if 'show_save_modal' not in st.session_state: 
    st.session_state.show_save_modal = False
if 'current_district' not in st.session_state: st.session_state.current_district = "강남구"
if 'current_sector' not in st.session_state: st.session_state.current_sector = "Office"
if 'rent_input' not in st.session_state: st.session_state.rent_input = 15.0
if 'current_district' not in st.session_state: st.session_state.current_district = "서울특별시 강남구" 
if 'current_sector' not in st.session_state: st.session_state.current_sector = "Office"

# -----------------------------------------------------------------------------
# 4. 헬퍼 함수 (KPI 및 뉴스 렌더링)
# -----------------------------------------------------------------------------

KPI_TOOLTIPS = {
    "평균 평당가": "거래금액 / (면적 × 3.3058) ÷ 10,000\n• 토지/건물의 단위면적당 가격\n• 지역 간 가격 수준 비교에 활용\n• 투자 가치 판단의 기준 지표",
    "총 거래 건수": "해당 기간 내 실제 신고된 거래 건수\n• 시장 활성도를 나타내는 지표\n• 거래량 증가 시 유동성 개선 신호\n• 지역별 투자 관심도 파악",
    "시장 수익률(Cap)": "순영업소득(NOI) / 자산가치 × 100\n• 투자 수익성 평가 핵심 지표\n• 일반적으로 4~6% 수준\n• 시장 평균 대비 매력도 판단",
    "임대율(Occupancy)": "임대면적 / 전체면적 × 100\n• 자산 운영 효율성 지표\n• Prime 등급은 보통 90% 이상\n• 공실 리스크 평가에 활용"
}


def render_kpi_card(label, value, sub_text, tooltip_key):
    tooltip_html = html.escape(KPI_TOOLTIPS.get(tooltip_key, ""))
    html_card = f"""
    <div class="kpi-card">
        <div class="kpi-label">{label} 
            <span class="tooltip-icon" data-tooltip="{tooltip_html}">?</span>
        </div>
        <div class="kpi-value">{value}</div>
        <div class="kpi-sub">{sub_text}</div>
    </div>
    """
    st.markdown(html_card, unsafe_allow_html=True)

def render_news_section(T, query_type):
    # 1. 세션 및 기본 변수 로드
    district_name_full = st.session_state.current_district
    target_sector = st.session_state.current_sector
    
    parts = district_name_full.split()
    district_name = parts[-1] if len(parts) > 1 else district_name_full
    
    # 2. 쿼리 및 세션 키 설정
    if query_type == "reg":
        default_q = f" {district_name} {SECTOR_TO_KR.get(target_sector, '부동산')} 시장 동향"
        session_key = "reg_news_data"
        page_key = "news_page"
        max_results = 100 
    else: 
        default_q = f"{district_name} {SECTOR_TO_KR.get(target_sector, '부동산')} 개발 호재"
        session_key = "micro_news_data"
        page_key = "micro_news_page"
        max_results = 100 

    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.markdown(f"#### 📰 {T['news_header']}")

    # 3. 검색 폼 UI
    with st.form(f"{query_type}_news_form"):
        c_in, c_bt = st.columns([5, 1])
        with c_in:
            if f'{query_type}_news_query' not in st.session_state:
                 st.session_state[f'{query_type}_news_query'] = default_q
            news_query = st.text_input("Search", value=st.session_state[f'{query_type}_news_query'], label_visibility="collapsed", key=f"{query_type}_query_input")
        with c_bt:
            news_submit = st.form_submit_button(T['search_btn'], use_container_width=True)

    # 정렬 필터
    col_sort, _ = st.columns([1, 4])
    with col_sort:
        current_sort = st.radio("Sort", ["최신순", "관련도순"], horizontal=True, label_visibility="collapsed", key=f"{query_type}_sort_radio")
    
    # 4. 데이터 로드 로직
    if news_submit or not st.session_state.get(session_key): 
        current_query = news_query if news_submit else default_q
        st.session_state[f'{query_type}_news_query'] = current_query
        
        try:
            with st.spinner("News Searching..."):
                st.session_state[session_key] = fetch_rss_news(current_query, max_results=max_results)
            st.session_state[page_key] = 0
        except Exception as e: 
            st.session_state[session_key] = []
            st.error(f"Error: {e}")
            
    # 5. [핵심] 뉴스 리스트 렌더링 (변수 정의 포함)
    if st.session_state.get(session_key):
        # --- 여기서 current_news 변수를 정의합니다 ---
        items_per_page = 5 
        current_page = st.session_state.get(page_key, 0)
        start_idx = current_page * items_per_page
        end_idx = start_idx + items_per_page
        current_news = st.session_state[session_key][start_idx:end_idx]
        total_pages = math.ceil(len(st.session_state[session_key]) / items_per_page)
        # ---------------------------------------

        if current_news:
            st.markdown("---")
            for n in current_news:
                # Expander 라벨 (출처 + 제목)
                label = f"[{n['source']}] {n['title']}"
                
                # Expander 생성
                with st.expander(label):
                    st.caption(f"🕒 {n['date']}")
                    
                    # 본문 내용 출력
                    if n['body']:
                        st.markdown(n['body'])
                    else:
                        st.info("요약 내용을 불러올 수 없습니다.")
                        
                    # 원문 링크 버튼
                    st.link_button("🔗 기사 원문 보기", n['url'])
            
            # 페이징 컨트롤
            st.write("")
            c_prev, c_mid, c_next = st.columns([1, 4, 1])
            with c_prev:
                if st.button("◀ 이전", key=f"{query_type}_prev", disabled=current_page == 0):
                    st.session_state[page_key] -= 1; st.rerun()
            with c_mid:
                st.markdown(f"<div style='text-align:center; padding-top:5px; color:#666;'>{current_page + 1} / {total_pages}</div>", unsafe_allow_html=True)
            with c_next:
                if st.button("다음 ▶", key=f"{query_type}_next", disabled=current_page >= total_pages - 1):
                    st.session_state[page_key] += 1; st.rerun()
        else:
            st.info("검색된 뉴스가 없습니다.")
    else:
        st.info("검색된 뉴스가 없습니다.")
        
    st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# [PHASE 1, 2] LOGIN & ONBOARDING FLOW
# -----------------------------------------------------------------------------

if not st.session_state.logged_in or st.session_state.onboarding_step < 4:
    
    _, main_col, _ = st.columns([0.5, 9, 0.5])
    
    with main_col:
        
        try: st.image("FINAL-LOGO.png", width=150)
        except: pass
        
        st.markdown(f"""
            <h1 class="onboarding-title" style="text-align:left;">전국 부동산 리서치 플랫폼 REA</h1>
            <p class="onboarding-subtitle" style="text-align:left;">데이터 기반의 정확한 인사이트로 업무 효율을 극대화하세요.</p>
            <div style="border-top: 1px solid #eee; margin-bottom: 20px;"></div>
        """, unsafe_allow_html=True)
        
        col_info, col_controls = st.columns([2, 1]) 
        
        # 이렇게 변경하세요
        current_step = st.session_state.onboarding_step
        
        with col_info:
            st.subheader(f"정보 설정 {current_step}/3 단계")
            st.write("")
            
            def step_card(step_num, title, is_active):
                active_class = "onboarding-active-step" if is_active else ""
                st.markdown(f"""
                    <div class="onboarding-step-box {active_class}">
                        <span class="step-number">{step_num}</span>
                        <span class="step-text">{title}</span>
                    </div>
                """, unsafe_allow_html=True)

            step_card(1, "팀 로그인 (Team Login)", current_step == 1)
            step_card(2, "업무 담당 설정 (Role Setup)", current_step == 2)
            step_card(3, "진행 단계 설정 (Progress Setup)", current_step == 3)

        with col_controls:
            if current_step == 1:
                st.markdown("#### Step 1. 팀 로그인")
                with st.form("login_form", clear_on_submit=False):
                    st.text_input("팀 명", key="login_team_input", placeholder="예: V&A")
                    st.text_input("사용자 이름", key="login_name_input", placeholder="예: 김컨설")
                    
                    if st.session_state.get('login_error'):
                        st.error(st.session_state.login_error)
                    
                    st.form_submit_button("로그인 및 시작하기", use_container_width=True, on_click=do_login)
                            
            elif current_step == 2:
                st.markdown("#### Step 2. 업무 담당 선택")
                st.radio("역할", ["컨설턴트", "중개업자 / 투자자"], key='onboard_role_choice', label_visibility="collapsed")
                st.button("다음 (Step 3)", use_container_width=True, on_click=handle_onboard_step1, help="역할 설정 완료")
                
            elif current_step == 3:
                st.markdown("#### Step 3. 진행 단계 설정")
                
                job = st.session_state.user_info.get("job")
                if job == "Consultant":
                    options = ["시장 조사 중", "제안서 작성 중"]
                else:
                    options = ["매물 탐색 중"]
                    
                st.radio("단계", options, key='onboard_status_choice', label_visibility="collapsed")
                
                col_finish, col_back = st.columns(2)
                with col_finish:
                    st.button("완료 (대시보드 이동)", use_container_width=True, on_click=handle_onboard_step2, help="최종 설정 완료")
                with col_back:
                    if st.button("← 뒤로 가기", use_container_width=True):
                        st.session_state.onboarding_step = 2 
                        st.rerun()

    if st.session_state.onboarding_step <= 3:
        st.stop()
        
# =============================================================================
# [PHASE 3] MAIN DASHBOARD
# =============================================================================
current_job = st.session_state.user_info.get("job", "Consultant")
is_broker = (current_job == "Broker") or (current_job == "Investor")

# 1. [핵심 수정] 언어 설정 함수 및 변수 정의를 '먼저' 합니다.
def update_language():
    st.session_state.language = st.session_state.lang_radio

if 'language' not in st.session_state:
    st.session_state.language = "KR"

# T 변수를 화면 그리기 전에 미리 만들어둡니다. (NameError 방지)
LANG = st.session_state.language
T = TRANS[LANG]

# 2. 그 다음 화면 레이아웃을 잡습니다.
h_logo, h_desc, h_lang = st.columns([2, 5, 1.5])

with h_logo:
    try: st.image("LOGO.png", width=300)
    except: st.markdown("## 부동산 마켓 리서치 플랫폼")

with h_desc:
    # 이제 T가 이미 정의되어 있으므로 에러가 나지 않습니다.
    st.markdown(f"""
    <div style="padding-left: 20px; border-left: 3px solid #183567; color: #333; font-size: 0.95rem; line-height: 1.6;">
        {T['desc_main']}
    </div>
    """, unsafe_allow_html=True)

with h_lang:
    # 라디오 버튼 (콜백 함수 사용으로 깜빡임 방지)
    st.radio(
        "Lang", 
        ["KR", "EN"], 
        horizontal=True, 
        label_visibility="collapsed",
        index=0 if st.session_state.language == "KR" else 1,
        key="lang_radio",       
        on_change=update_language 
    )
    
    file_name = "user-guide.pdf" 
    
    try:
        with open(file_name, "rb") as pdf_file:
            pdf_bytes = pdf_file.read()
            
        st.download_button(
            label=T['btn_guide'], 
            data=pdf_bytes, 
            file_name="User_Guide.pdf", # 다운로드될 때 파일명
            mime="application/pdf", 
            use_container_width=True
        )
    except FileNotFoundError:
        # 파일이 없을 경우 에러 대신 비활성화된 버튼 표시 (앱 멈춤 방지)
        st.warning("PDF 파일 없음")
        st.download_button(T['btn_guide'], data="", disabled=True, use_container_width=True)

st.divider()

# Sidebar Layout
with st.sidebar:
    st.markdown(f"### 🏢 Team: {st.session_state.team_name}")
    role_display = T['role_consultant'] if current_job == "Consultant" else T['role_broker']
    st.caption(f"User: {st.session_state.user_name} | {role_display}")

    if st.button("로그아웃 (Logout)", use_container_width=True):
        do_logout()

    st.markdown("---")
    
    refresh_btn = st.button(T['btn_search'])
    st.write("")

    st.markdown("### ANALYSIS MODE")
    current_mode_en = st.session_state.app_config["mode"]
    mode_options_ui = [T['mode_macro'], T['mode_micro']]
    mode_mapping = {T['mode_macro']: "Regional Analysis", T['mode_micro']: "Micro-Market Deep Dive"}
    reverse_mapping = {"Regional Analysis": T['mode_macro'], "Micro-Market Deep Dive": T['mode_micro']}
    
    default_ui_mode = reverse_mapping.get(current_mode_en, T['mode_macro'])
    try: mode_idx = mode_options_ui.index(default_ui_mode)
    except: mode_idx = 0
    
    selected_mode_ui = st.radio("Mode", mode_options_ui, index=mode_idx, label_visibility="collapsed")
    analysis_mode = mode_mapping[selected_mode_ui]
    
    if analysis_mode != st.session_state.app_config["mode"]:
        st.session_state.app_config["mode"] = analysis_mode
        st.session_state.app_config["auto_run"] = True
        st.rerun()
    
    st.markdown("---")
    st.markdown(f"### {T['filter_title']}")
        
    target_sector_ui = st.selectbox(T['sector_label'], SECTOR_MAP[LANG])
    target_sector = SECTOR_API_KEY_MAP.get(target_sector_ui, "Office")

    selected_sido = st.selectbox("시/도 선택", list(DISTRICT_HIERARCHY.keys()), index=0)

    sigungu_options = list(DISTRICT_HIERARCHY[selected_sido].keys())
    default_sigungu_index = 0
    if "강남구" in sigungu_options:
        try:
            default_sigungu_index = sigungu_options.index("강남구") 
        except ValueError:
            pass 

    district_name_ui = st.selectbox("시/군/구 선택", sigungu_options, index=default_sigungu_index)

    lawd_cd = DISTRICT_HIERARCHY[selected_sido][district_name_ui]
    district_name = f"{selected_sido} {district_name_ui}".strip() 

    st.session_state.current_district = district_name
    st.session_state.current_sector = target_sector
        
    target_date = st.date_input(T['period_label'], value=datetime.now()-timedelta(days=60))
    deal_ymd = target_date.strftime("%Y%m")
        
    if analysis_mode == "Regional Analysis":
        trend_range = st.slider("Trend Range (Months)", 3, 12, 6)
        
    st.markdown("---")
    st.markdown(f"### 💾 {st.session_state.team_name} {T['drive_header']}")
    
    with st.expander(T['proj_mng'], expanded=False):
        new_project = st.text_input(T['proj_new'], key="new_project_input")
        if st.button(T['proj_add'], use_container_width=True):
            if new_project and new_project not in st.session_state.projects:
                st.session_state.projects.append(new_project)
                st.success(f"'{new_project}' Added!")
                st.rerun()
    
# [수정] 저장 버튼 번역 적용
    if st.button(T['save_btn'], use_container_width=True, key="save_analysis_btn"):
        st.session_state.show_save_modal = True
    
    if st.session_state.show_save_modal:
        st.markdown("---")
        st.markdown("#### 📝 분석 저장")
        
        save_project = st.selectbox("프로젝트 선택", st.session_state.projects, key="save_project_select")
        save_title = st.text_input("저장 제목", value=f"{district_name}_{target_sector}_{deal_ymd}", key="save_title_input")
        save_memo = st.text_area("메모 (선택사항)", placeholder="이 분석에 대한 메모를 입력하세요...", key="save_memo_input")
        
        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.button("✅ 저장", use_container_width=True):
                if supabase:
                    try:
                        data = {
                            "team_name": st.session_state.team_name,
                            "user_name": st.session_state.user_name,
                            "project": save_project,
                            "title": save_title,
                            "district": district_name,
                            "sector": target_sector,
                            "analysis_date": deal_ymd,
                            "mode": analysis_mode,
                            "memo": save_memo
                        }
                        supabase.table("favorites").insert(data).execute()
                        st.success(f"'{save_project}'에 저장 완료!")
                        st.session_state.show_save_modal = False
                        time.sleep(1)
                        st.rerun()
                    except Exception as e: 
                        st.error(f"저장 실패: {e}")
                else: 
                    st.warning("DB 연결 오류")
        with col_cancel:
            if st.button("❌ 취소", use_container_width=True):
                st.session_state.show_save_modal = False
                st.rerun()

should_run = True

if analysis_mode == "Regional Analysis":
    st.markdown(f"### {district_name} Market Overview")
    
    if should_run:
        months_to_fetch = get_recent_months(target_date, trend_range)
        all_data = []
        
        with st.spinner("Analyzing Market Trends..."):
            for m in months_to_fetch:
                df_m = fetch_molit_data(target_sector, lawd_cd, m, st.secrets["api_keys"])
                if not df_m.empty: all_data.append(df_m)

        if all_data:
            df_trend = pd.concat(all_data)
            latest = months_to_fetch[-1]
            df_latest = df_trend[df_trend['기준년월'] == latest]
            if df_latest.empty: df_latest = df_trend
                
            curr_avg = df_latest['평당가'].mean()
            curr_vol = len(df_latest)
            
            # 1. KPI 카드 영역
            k1, k2, k3, k4 = st.columns(4)
            with k1: 
                render_kpi_card(T['kpi1'], f"{curr_avg:,.1f} {T['unit_money']}", f"Based on {latest}", "평균 평당가")
            with k2: 
                render_kpi_card(T['kpi2'], f"{curr_vol} 건", "&nbsp;", "총 거래 건수")
            with k3: 
                render_kpi_card(T['kpi3'], "4.8%", "Market Est.", "시장 수익률(Cap)")
            with k4: 
                render_kpi_card(T['kpi4'], "95%", "Prime Grade", "임대율(Occupancy)")
            
            # 2. 차트 영역 (레이아웃 분리 수정됨)
            col_chart1, col_chart2 = st.columns([2, 1])
            
            with col_chart1:
                # 왼쪽 차트 카드 시작
                st.markdown('<div class="css-card">', unsafe_allow_html=True)
                st.markdown(f"##### {T['chart_trend']}")
                
                trend_grp = df_trend.groupby('기준년월').agg({'평당가':'mean', '거래금액':'count'}).reset_index()
                trend_grp['기준년월_날짜'] = pd.to_datetime(trend_grp['기준년월'], format='%Y%m')
                trend_grp = trend_grp.sort_values(by='기준년월_날짜')
                
                fig = make_subplots(specs=[[{"secondary_y": True}]])
                fig.add_trace(go.Scatter(x=trend_grp['기준년월_날짜'], y=trend_grp['평당가'], name=T['kpi1'], line=dict(color=CBRE_NAVY, width=3)), secondary_y=False)
                fig.add_trace(go.Bar(x=trend_grp['기준년월_날짜'], y=trend_grp['거래금액'], name=T['kpi2'], marker_color='#E0E0E0', opacity=0.6), secondary_y=True)
                
                fig.update_layout(height=350, margin=dict(t=10,b=0,l=0,r=0), paper_bgcolor='white', plot_bgcolor='white', showlegend=True, legend=dict(orientation="h", y=1.1))
                fig.update_xaxes(tickformat="%Y-%m")
                
                st.plotly_chart(fig, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True) # 카드 닫기

            with col_chart2:
                # 오른쪽 차트 카드 시작
                st.markdown('<div class="css-card">', unsafe_allow_html=True)
                st.markdown(f"##### {T['chart_dist']}")
                
                d_grp = df_latest['법정동'].value_counts().reset_index()
                d_grp.columns = ['법정동', '건수']
                
                fig2 = px.pie(d_grp, names='법정동', values='건수', hole=0.6, color_discrete_sequence=px.colors.sequential.RdBu)
                fig2.update_layout(height=350, margin=dict(t=10,b=0,l=0,r=0), showlegend=True, legend=dict(orientation="h", y=-0.1))
                
                st.plotly_chart(fig2, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True) # 카드 닫기

            # 3. 뉴스 영역 (차트 밖으로 완전히 분리)
            render_news_section(T, "reg")
            
        else:
            st.warning(f"📉 선택하신 기간({deal_ymd})에 국토교통부 신고 데이터가 없습니다.")

else:
    st.markdown(f"### {district_name} Detail Analysis")
    
    if should_run:
        df = fetch_molit_data(target_sector, lawd_cd, deal_ymd, st.secrets["api_keys"])
        if not df.empty:
            st.session_state.df = df
            st.session_state.micro_run = True
        else:
            st.error("데이터가 없습니다."); st.session_state.micro_run = False
    
    if st.session_state.get("micro_run"):
        df = st.session_state.df
        area_col = '전용면적' if "Co-living" in target_sector else '대지면적'
        if area_col not in df.columns: area_col = '거래면적'
        
        base_tabs = [T['tab1'], T['tab3'], T['tab4'], T['tab5']]
        if is_broker:
            base_tabs.insert(1, T['tab2']) 
            
        tabs = st.tabs(base_tabs)
        
        tab_dash = tabs[0]
        tab_data = tabs[1] if not is_broker else tabs[2]
        tab_news = tabs[2] if not is_broker else tabs[3]
        tab_calc = tabs[3] if not is_broker else tabs[4]
        
        if st.session_state.app_config.get("default_tab") == 1:
             st.toast("📍 지도 탭 확인", icon="🗺️")

        with tab_dash:
            st.markdown('<div class="css-card">', unsafe_allow_html=True)
            all_dongs = sorted(df['법정동'].unique().tolist())
            sel_dong = st.multiselect("세부 지역 필터", all_dongs, default=all_dongs, key="micro_dong_filter")
            if sel_dong: f_df = df[df['법정동'].isin(sel_dong)]
            else: f_df = df
            sub_avg = f_df['평당가'].mean()
            
            col_ch, col_dt = st.columns([1.5, 1])
            with col_ch:
                event = st.dataframe(f_df[['법정동', '건물명', '평당가', '거래금액', area_col, '건축년도']], use_container_width=True, hide_index=True, height=400, on_select="rerun", selection_mode="single-row", key="micro_dashboard_table")
            with col_dt:
                if len(event.selection.rows) > 0:
                    idx = event.selection.rows[0]
                    row = f_df.iloc[idx]
                    st.info(f"📌 **{row['건물명']}**")
                    st.metric("거래금액", f"{row['거래금액']/10000:,.1f}억")
                    st.metric("평당가", f"{row['평당가']:,.1f}억", delta=f"{row['평당가']-sub_avg:,.1f} vs Avg")
                else:
                    fig = px.scatter(f_df, x=area_col, y='평당가', size='거래금액', color='법정동', hover_data=['건물명'])
                    st.plotly_chart(fig, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        if is_broker:
            with tabs[1]:
                st.markdown('<div class="css-card">', unsafe_allow_html=True)
                
                # 데이터 준비
                map_df = df.copy()
                
                # [중요] 좌표가 없을 때만 생성하되, 매번 랜덤하게 바뀌지 않도록 시드 고정
                # 혹은 데이터프레임 자체를 세션에 저장하는 것이 좋으나, 일단 시각화 오류부터 잡습니다.
                base_lat, base_lon = 37.5172, 127.0473 
                
                # 좌표 데이터가 없으면 임시 생성
                if 'lat' not in map_df.columns:
                    # random.seed를 사용하여 리런되어도 좌표가 튀지 않게 고정
                    random.seed(42) 
                    map_df['lat'] = [base_lat + random.uniform(-0.02, 0.02) for _ in range(len(map_df))]
                    map_df['lon'] = [base_lon + random.uniform(-0.02, 0.02) for _ in range(len(map_df))]

                # 1. 지도 중심 설정
                center_lat = map_df['lat'].mean()
                center_lon = map_df['lon'].mean()
                
                # 2. Folium 지도 생성
                m = folium.Map(location=[center_lat, center_lon], zoom_start=14, tiles='CartoDB positron')

                # 3. 마커 추가
                for idx, row in map_df.iterrows():
                    # 1. 이름 보정 (건물명 없으면 주소 사용)
                    raw_name = str(row.get('건물명', '')).strip()
                    if not raw_name or raw_name == "-":
                        jibun = str(row.get('지번', '')).strip()
                        bldg_name = f"{row['법정동']} {jibun}" if jibun else f"{row['법정동']} 매물"
                    else:
                        bldg_name = raw_name

                    # 2. [핵심 수정] 평당가 단위 보정 (억원 데이터 -> 만원 표기)
                    # 데이터에는 '억원' 단위(예: 1.5)로 들어있으므로, 
                    # 만원 단위(15,000)로 보여주려면 10,000을 곱해야 합니다.
                    pyeong_price_manwon = row['평당가'] * 10000 

                    # 툴팁: 이름 + 평당가(만원)
                    tooltip_text = f"{bldg_name}\n({pyeong_price_manwon:,.0f}만원/평)"
                    
                    # 팝업 HTML
                    popup_html = f"""
                    <div style="width:200px; font-family:sans-serif;">
                        <h4 style="margin-bottom:5px; color:#183567;">{bldg_name}</h4>
                        <p style="margin:0; font-size:0.9em;"><b>거래금액:</b> {row['거래금액']/10000:,.1f}억</p>
                        <p style="margin:0; font-size:0.9em;"><b>평당가:</b> {pyeong_price_manwon:,.0f}만원</p>
                        <p style="margin:0; font-size:0.8em; color:#888;">{row['법정동']} {row['지번']}</p>
                    </div>
                    """
                    
                    # 원 크기 및 색상
                    radius = 5 + (row['평당가'] / 5000) # 여기는 상대적 크기라 그대로 둠
                    color = "#183567" if row['평당가'] > map_df['평당가'].mean() else "#3498db"
                    
                    folium.CircleMarker(
                        location=[row['lat'], row['lon']],
                        radius=radius,
                        popup=folium.Popup(popup_html, max_width=300),
                        tooltip=tooltip_text,
                        color=color,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.7
                    ).add_to(m)
                    
                    radius = 5 + (row['평당가'] / 5000)
                    color = "#183567" if row['평당가'] > map_df['평당가'].mean() else "#3498db"
                    
                    folium.CircleMarker(
                        location=[row['lat'], row['lon']],
                        radius=radius,
                        popup=folium.Popup(popup_html, max_width=300),
                        tooltip=tooltip_text,
                        color=color,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.7
                    ).add_to(m)

                # 4. [핵심 수정] returned_objects=[] 추가
                # 이 옵션이 없으면 지도가 로드될 때마다 앱을 재실행시켜 무한루프에 빠집니다.
                st_folium(m, width="100%", height=500, returned_objects=[])
                
                st.markdown('</div>', unsafe_allow_html=True)

        with tab_data:
            st.markdown('<div class="css-card">', unsafe_allow_html=True)
            st.subheader("📋 원본 데이터 추출 (Raw Data)")
            if "micro_dong_filter" in st.session_state and st.session_state.micro_dong_filter:
                export_df = df[df['법정동'].isin(st.session_state.micro_dong_filter)]
            else: export_df = df
            csv = export_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Excel Download", csv, "data.csv")
            st.dataframe(export_df, use_container_width=True, height=500, key="micro_export_table")
            st.markdown('</div>', unsafe_allow_html=True)

        with tab_news:
            st.markdown('<div class="css-card">', unsafe_allow_html=True)
            st.markdown(f"#### 📰 {T['news_header']}")
            
            c_in, c_bt = st.columns([5, 1])
            with c_in:
                sector_kr = SECTOR_TO_KR.get(target_sector, "부동산")
                default_q_micro = f"{district_name.split()[1]} {sector_kr} 개발 호재"
                if 'micro_news_query' not in st.session_state:
                    st.session_state.micro_news_query = default_q_micro
                q_micro = st.text_input("Search", value=st.session_state.micro_news_query, label_visibility="collapsed", key="micro_news_input")
            with c_bt:
                s_micro = st.button(T['search_btn'], key="micro_news_btn", use_container_width=True)
            
            if s_micro:
                st.session_state.micro_news_query = q_micro
                try:
                    st.session_state.micro_news_data = fetch_rss_news(q_micro, max_results=20)
                    st.session_state.micro_news_page = 0
                except: 
                    st.session_state.micro_news_data = []
            elif should_run and "micro_news_data" not in st.session_state:
                try:
                    st.session_state.micro_news_data = fetch_rss_news(default_q_micro, max_results=20)
                    st.session_state.micro_news_page = 0
                except:
                    st.session_state.micro_news_data = []
            
            if st.session_state.get("micro_news_data"):
                m_start = st.session_state.get("micro_news_page", 0) * 5
                m_end = m_start + 5
                m_news = st.session_state.micro_news_data[m_start:m_end]
                for idx, n in enumerate(m_news, start=m_start+1):
                    pub = n.get('date', 'Recent')
                    src = n.get('source', 'News')
                    title = html.escape(n.get('title', ''))
                    body = html.escape(n.get('body', ''))
                    url = n.get('url', '')
                    
                    st.markdown(f"""
                    <div class="news-card" data-index="{idx}">
                        <a href="{url}" class="news-title" target="_blank">{title}</a>
                        <div class="news-meta">
                            <span>🕒 {pub}</span> • <span>{src}</span>
                        </div>
                        <div class="news-body">{body}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                mc1, mc2, mc3 = st.columns([1, 4, 1])
                with mc1: 
                    if st.button("◀ 이전", key="m_prev", disabled=st.session_state.micro_news_page==0):
                         st.session_state.micro_news_page -= 1; st.rerun()
                with mc3:
                    if st.button("다음 ▶", key="m_next", disabled=m_end>=len(st.session_state.micro_news_data)):
                         st.session_state.micro_news_page += 1; st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        with tab_calc:
            st.markdown('<div class="css-card">', unsafe_allow_html=True)
            st.markdown("#### 🧮 수지분석 시뮬레이터 (Feasibility)")
            st.info("💡 좌측 변수(토지비, 건축비 등)를 조정하여 예상 Cap Rate를 확인하세요.")
            c1, c2 = st.columns(2)
            with c1: 
                lp=st.number_input("토지 평당가 (만원)", 15000, help="매입 예정 토지의 평당 가격")
                rp=st.number_input("예상 임대료 (만원/평)", 15.0, help="전용면적 기준 월 임대료")
            with c2: 
                far=st.slider("용적률 (FAR %)", 100, 800, 500, help="법정 상한 용적률")
                cp=st.number_input("건축 평당가 (만원)", 900, help="최근 시공비 반영")
            
            cost = 100*lp + (100*far/100*cp)*1.15
            noi = (100*far/100*rp*12*0.8)
            cap = (noi/cost)*100 if cost>0 else 0
            
            st.divider()
            st.metric("예상 수익률 (Cap Rate)", f"{cap:.2f}%", delta="Target 5.0%", help="NOI / 총사업비")
            st.markdown('</div>', unsafe_allow_html=True)

st.markdown("---")
with st.expander(f"📂 {st.session_state.team_name} {T['drive_header']}"):
    if supabase:
        try:
            # 1. 데이터 조회
            response = supabase.table("favorites").select("*").eq("team_name", st.session_state.team_name).order("created_at", desc=True).execute()
            
            if response and hasattr(response, 'data') and response.data:
                df_archive = pd.DataFrame(response.data)
                
                # 프로젝트 목록 추출
                if 'project' in df_archive.columns:
                    projects_in_db = df_archive['project'].unique().tolist()
                else:
                    projects_in_db = ["전체"]
                
                # 탭 생성
                tab_names = ["📊 전체"] + [f"📁 {p}" for p in projects_in_db if p != "전체"]
                tabs = st.tabs(tab_names)
                
                # 2. 탭별 데이터 표시 및 선택 로직 함수
                def show_drive_tab(tab_obj, data_df, key_suffix):
                    with tab_obj:
                        # 보여줄 컬럼만 선택 (사용자 친화적)
                        display_cols = ['title', 'district', 'sector', 'analysis_date', 'memo', 'user_name', 'created_at']
                        
                        # [핵심] 선택 가능한 데이터프레임 생성
                        selection = st.dataframe(
                            data_df[display_cols],
                            use_container_width=True,
                            hide_index=True,
                            on_select="rerun",      # 클릭 시 리런
                            selection_mode="single-row", # 한 번에 한 줄만 선택
                            key=f"drive_df_{key_suffix}"
                        )
                        
                        # 3. 선택된 행이 있을 경우 '불러오기' 버튼 표시
                        if selection.selection.rows:
                            idx = selection.selection.rows[0]
                            row = data_df.iloc[idx] # 전체 데이터(hidden 컬럼 포함) 가져오기
                            
                            st.info(f"📌 선택된 분석: **[{row['district']}] {row['title']}** ({row['analysis_date']})")
                            
                            if st.button("🚀 이 분석 내용 불러오기 (Load Analysis)", key=f"load_btn_{key_suffix}", use_container_width=True):
                                # [핵심 수정] 사이드바가 읽을 수 있는 'Preset' 변수에 값 주입
                                
                                # 1. 지역 분리 (예: "서울특별시 강남구" -> "서울특별시", "강남구")
                                dist_parts = row['district'].split()
                                if len(dist_parts) >= 2:
                                    st.session_state.preset_sido = dist_parts[0]
                                    st.session_state.preset_sigungu = dist_parts[1]
                                else:
                                    st.session_state.preset_sido = row['district'] # 세종시 같은 경우
                                
                                # 2. 섹터 및 날짜 주입
                                st.session_state.preset_sector = row['sector']
                                st.session_state.preset_date = row['analysis_date']
                                
                                # 3. 모드 설정
                                if 'mode' in row and row['mode']:
                                    st.session_state.app_config['mode'] = row['mode']
                                
                                # 성공 메시지 및 리런
                                st.toast("분석 환경을 불러오는 중...", icon="🔄")
                                time.sleep(0.5)
                                st.rerun()

                # 전체 탭 렌더링
                show_drive_tab(tabs[0], df_archive, "all")
                
                # 프로젝트별 탭 렌더링
                for i, p_name in enumerate([p for p in projects_in_db if p != "전체"]):
                    p_data = df_archive[df_archive['project'] == p_name]
                    show_drive_tab(tabs[i+1], p_data, f"proj_{i}")
                    
            else:
                st.info("저장된 분석이 없습니다. 사이드바에서 '현재 분석 저장' 버튼을 눌러 저장하세요.")
                
        except Exception as e:
            error_msg = str(e)
            if "PGRST205" in error_msg:
                st.warning("⚠️ 데이터베이스 연결 일시적 장애 (Schema Cache Error)")
                st.caption("서버가 테이블 정보를 갱신하지 못하고 있습니다. 잠시 후 다시 시도해주세요.")
            else:
                st.error(f"데이터 로딩 실패: {e}")
    else:
        st.warning("데이터베이스(Supabase)에 연결할 수 없습니다.")