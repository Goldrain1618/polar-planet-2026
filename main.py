import io
import os
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

st.set_page_config(page_title="송도고 새싹 2팀 | 극지식물 생육 차이 분석", page_icon="🌱", layout="wide")

# ---------- 한글 폰트 + 디자인 CSS ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR&display=swap');
html, body, [class*="css"] {
   font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif;
}
.banner {background: linear-gradient(120deg, #1b5e20 0%, #2e7d32 45%, #00897b 100%); border-radius: 20px; padding: 26px 30px; margin-bottom: 16px; box-shadow: 0 10px 28px rgba(27,94,32,.28); position: relative; overflow: hidden;} .banner::after {content: "🌱"; position: absolute; right: 26px; top: -6px; font-size: 130px; opacity: .16;} .banner h1 {margin: 0; font-size: 1.95rem; font-weight: 800; color: #fff;} .banner p {color: #e8f5e9 !important; margin: 8px 0 0 0; max-width: 85%;} .team {display: inline-block; margin-left: 10px; padding: 3px 14px; border-radius: 999px; background: rgba(255,255,255,.2); border: 1px solid rgba(255,255,255,.45); font-size: 1rem; font-weight: 700; vertical-align: middle;}
.chip {display: inline-block; background: rgba(255,255,255,.17); border: 1px solid rgba(255,255,255,.4); color: #fff; border-radius: 999px; padding: 5px 14px; margin: 14px 8px 0 0; font-size: .88rem; font-weight: 600;} .hypothesis-box, .conclusion-box, .note-box, .warn-box {border-radius: 14px; padding: 16px 18px; margin-bottom: 14px; box-shadow: 0 3px 12px rgba(0,0,0,.06);}
.hypothesis-box {background: linear-gradient(135deg, #e3f2fd, #f5f9ff); border-left: 7px solid #1e88e5;} .conclusion-box {background: linear-gradient(135deg, #e8f5e9, #f9fdf6); border-left: 7px solid #43a047;} .note-box {background: #fff8e1; border-left: 7px solid #fb8c00; font-size: 0.92rem;} .warn-box {background: #fce4ec; border-left: 7px solid #e91e63;}
.badge {display: inline-block; padding: 4px 14px; border-radius: 999px; font-weight: 800; color: #fff; background: #2e7d32; margin: 0 4px 6px 0; box-shadow: 0 2px 6px rgba(46,125,50,.35);} .badge.no {background: #ef6c00;} .ts-line {font-size: 0.83rem; color: #607d8b; background: #f6f8fa; border-radius: 8px; padding: 6px 12px; margin: 2px 0 18px 0;}
div[data-testid="stMetric"] {background: #fff; border-top: 5px solid #43a047 !important; box-shadow: 0 4px 14px rgba(0,0,0,.07);} div[data-testid="stMetricValue"] {font-weight: 800; color: #1b5e20;} .stTabs [role="tab"] {padding: 10px 16px; border-radius: 12px 12px 0 0;} .stTabs [role="tab"] p {font-size: 1.05rem; font-weight: 700;} .stTabs [role="tab"][aria-selected="true"] {background: #e8f5e9;}
h3 {border-left: 6px solid #43a047; padding-left: 12px !important;} section[data-testid="stSidebar"] {background: linear-gradient(180deg, #e8f5e9 0%, #ffffff 60%);}
</style>
""", unsafe_allow_html=True)

FONT = "Malgun Gothic, Apple SD Gothic Neo, sans-serif"
GROWTH = ["잎 수", "지상부 길이", "지하부 길이", "생중량", "지상부 질량", "지하부 질량"]
UNIT = {"잎 수": "장", "지상부 길이": "mm", "지하부 길이": "mm", "생중량": "g", "지상부 질량": "g", "지하부 질량": "g"}
ENV = ["temperature", "humidity", "ph", "ec"]
ENV_KO = {"temperature": "온도", "humidity": "습도", "ph": "pH", "ec": "EC"}
HOT = 30

# ---------- CSV 읽기 + 열 이름 표준화 ----------
def std_cols(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    rename = {}
    for c in df.columns:
        k = c.lower().replace(" ", "")
        if k in ("time", "categories", "시간", "날짜", "datetime", "date"):
            rename[c] = "time"
        elif k in ("temperature", "온도"):
            rename[c] = "temperature"
        elif k in ("humidity", "습도"):
            rename[c] = "humidity"
        elif k == "ph":
            rename[c] = "ph"
        elif k == "ec":
            rename[c] = "ec"
        elif "생중량" in k:
            rename[c] = "생중량"
        elif "잎" in k:
            rename[c] = "잎 수"
        elif "지상부" in k and "길이" in k:
            rename[c] = "지상부 길이"
        elif "지하부" in k and "길이" in k:
            rename[c] = "지하부 길이"
        elif "지상부" in k and ("질량" in k or "무게" in k):
            rename[c] = "지상부 질량"
        elif "지하부" in k and ("질량" in k or "무게" in k):
            rename[c] = "지하부 질량"
        elif "개체" in k:
            rename[c] = "개체번호"
    df = df.rename(columns=rename)
    for c in df.columns:
        if c in ("time", "개체번호"):
            continue
        if not pd.api.types.is_numeric_dtype(df[c]):
            num = pd.to_numeric(df[c].astype(str).str.replace(",", "").str.extract(r"(-?\d+\.?\d*)")[0], errors="coerce")
            if num.notna().mean() >= 0.5:
                df[c] = num
    if "생중량" not in df.columns and {"지상부 질량", "지하부 질량"} <= set(df.columns):
        df["생중량"] = df["지상부 질량"] + df["지하부 질량"]
    if "time" in df.columns:
        t = df["time"].astype(str).str.strip()
        parsed = pd.to_datetime(t, errors="coerce", format="mixed")
        bad = parsed.isna() & t.str.match(r"^\d{8}_\d{1,2}$")
        if bad.any():
            parts = t[bad].str.split("_", expand=True)
            parsed[bad] = pd.to_datetime(parts[0], format="%Y%m%d") + pd.to_timedelta(parts[1].astype(int), unit="h")
        df["time"] = parsed
    return df
@st.cache_data(show_spinner=False)
def load_data(raw):
    # 바이트를 utf-8-sig → cp949 순서로 읽고 바로 표준화
    for enc in ("utf-8-sig", "cp949"):
        try:
            return std_cols(pd.read_csv(io.BytesIO(raw), encoding=enc))
        except Exception:
            pass
    return pd.DataFrame()

# ---------- 도우미 함수 ----------
def box(kind, html):
    st.markdown(f'<div class="{kind}">{html}</div>', unsafe_allow_html=True)
def verdict(ok):  # 판정 배지
    return '<span class="badge">지지됨 ✅</span>' if ok else '<span class="badge no">지지되지 않음 ⚠️</span>'
def how_to_read(text):
    st.markdown(f'<p class="ts-line">이 그래프 읽는 법: {text}</p>', unsafe_allow_html=True)

def show(fig, height=420, title=None):
    fig.update_layout(font=dict(family=FONT, size=13), height=height, template="plotly_white", margin=dict(l=40, r=20, t=64, b=40),
                      title_font=dict(size=18, color="#1b5e20"), hoverlabel=dict(bgcolor="white", font_size=13), plot_bgcolor="#fcfdfc")
    if title:
        fig.update_layout(title=dict(text=f"<b>{title}</b>", font=dict(size=18, color="#1b5e20")))
    st.plotly_chart(fig, width="stretch")

def has(df, c):
    return (not df.empty) and c in df.columns and pd.api.types.is_numeric_dtype(df[c])
def lab(c):
    return f"{c}({UNIT[c]})" if c in UNIT else ENV_KO.get(c, c)
def pair(df, x, y):
    # x·y 둘 다 값이 있는 행만 (짝이 맞아야 polyfit·상관 오류가 없음)
    return df[[x, y]].dropna()

def corr(df, x, y, rank=False):
    # rank=True면 순위로 바꾼 뒤 계산 = 스피어먼 상관계수
    d = pair(df, x, y)
    d = d.rank() if rank else d
    if len(d) < 2 or d[x].nunique() < 2 or d[y].nunique() < 2:
        return None
    return d[x].corr(d[y])

def cv(s):
    v = s.dropna()
    if len(v) < 2 or v.mean() <= 0:
        return None
    return v.std(ddof=1) / v.mean() * 100

def loo_rmse(df, x, y):
    # 개체 하나씩 빼고 나머지로 식을 만든 뒤 뺀 개체를 예측 (x=None이면 평균으로만 찍기)
    d = df[[y]].dropna() if x is None else pair(df, x, y)
    if len(d) < 3:
        return None
    errs = []
    for i in range(len(d)):
        rest = d.drop(d.index[i])
        if x is not None and rest[x].nunique() < 2:
            return None
        pred = rest[y].mean() if x is None else np.polyval(np.polyfit(rest[x], rest[y], 1), d[x].iloc[i])
        errs.append(d[y].iloc[i] - pred)
    return float(np.sqrt(np.mean(np.square(errs))))

def id_text(s):
    # 개체번호를 56.0이 아니라 56, A1처럼 원래 모양으로
    return [str(int(v)) if isinstance(v, float) and not pd.isna(v) and v.is_integer() else str(v) for v in s]

def add_scatter(fig, df, x, y, color, row, col):
    d = pair(df, x, y)
    if len(d) < 2 or d[x].nunique() < 2:
        return
    b, a = np.polyfit(d[x], d[y], 1)
    xs = np.linspace(d[x].min(), d[x].max(), 50)
    fig.add_trace(go.Scatter(x=d[x], y=d[y], mode="markers", marker=dict(color=color, size=7, opacity=0.7), showlegend=False), row=row, col=col)
    fig.add_trace(go.Scatter(x=xs, y=a + b * xs, mode="lines", line=dict(color="#E91E63", width=2), showlegend=False), row=row, col=col)

# ---------- 사이드바: 파일은 여기서 한 번만 읽기 ----------
st.sidebar.header("📁 데이터 업로드")
env_file = st.sidebar.file_uploader("🌡 환경 데이터 CSV", type="csv")
growth_file = st.sidebar.file_uploader("🌱 생육 결과 CSV", type="csv")
with st.spinner("CSV 읽는 중..."):
    env_df = load_data(env_file.getvalue()) if env_file is not None else pd.DataFrame()
    growth_df = load_data(growth_file.getvalue()) if growth_file is not None else pd.DataFrame()

# 학교명: 파일명 앞부분 ('송도고_생육결과데이터.csv' → '송도고')
first = growth_file if growth_file is not None else env_file
school = (os.path.splitext(os.path.basename(first.name))[0].split("_")[0].strip() if first is not None else "") or "송도고"
g_cols = [c for c in GROWTH if has(growth_df, c)]
e_cols = [c for c in ENV if has(env_df, c)]
has_time = (not env_df.empty) and "time" in env_df.columns and env_df["time"].notna().sum() >= 2
ids = id_text(growth_df["개체번호"]) if "개체번호" in growth_df.columns else [str(i + 1) for i in range(len(growth_df))]

st.sidebar.header("🔎 생육 측정 항목")
if g_cols:
    measure = st.sidebar.selectbox("개체별 막대그래프 항목", g_cols, index=g_cols.index("생중량") if "생중량" in g_cols else 0, format_func=lab)
else:
    measure = None
    st.sidebar.info("생육 CSV를 올리면 항목을 고를 수 있어요.")
if school:
    st.sidebar.markdown(f"**📌 분석 대상:** {school}")

# 가설 판정용 값은 맨 위에서 한 번만 계산해서 모든 탭에서 같이 씀
r_leaf = corr(growth_df, "잎 수", "생중량") if {"잎 수", "생중량"} <= set(g_cols) else None
r_shoot = corr(growth_df, "지상부 길이", "생중량") if {"지상부 길이", "생중량"} <= set(g_cols) else None
cv_up = cv(growth_df["지상부 질량"]) if "지상부 질량" in g_cols else None
cv_dn = cv(growth_df["지하부 질량"]) if "지하부 질량" in g_cols else None
h1_ok = (r_leaf is not None and r_shoot is not None and r_leaf > 0 and r_leaf > r_shoot)
h2_ok = (cv_up is not None and cv_dn is not None and cv_dn > cv_up)

chips = "".join(f'<span class="chip">{t}</span>' for t in [f"🌿 개체 {len(growth_df)}개" if not growth_df.empty else "",
    f"🍃 잎 수 r = {r_leaf:.2f}" if r_leaf is not None else "", f"🟤 지하부 CV {cv_dn:.0f}%" if cv_dn is not None else "",
    f"🗂️ 환경 기록 {len(env_df):,}건" if not env_df.empty else ""] if t)
st.markdown(f"""<div class="banner"><h1>🌱 {school} 극지식물 개체별 생육 차이 분석 대시보드<span class="team">송도고 새싹 2팀</span></h1>
<p>같은 스마트팜에서 자란 극지식물도 개체마다 잎 수·길이·무게가 다릅니다. 무엇이 생중량을 더 잘 설명하는지(가설 1),
지상부·지하부 중 어느 쪽의 개체 간 상대적 차이가 더 큰지(가설 2)를 데이터로 확인합니다.</p>{chips}</div>""", unsafe_allow_html=True)

tabs = st.tabs(["📋 개요", "🍃 가설 1 — 키보다 잎 수", "🌱 가설 2 — 숨은 차이는 땅속에", "📊 개체별 비교", "🌡️ 환경 데이터"])

# ================= TAB 1 — 개요 =================
with tabs[0]:
    try:
        box("hypothesis-box", "<b>🔬 연구 목적</b><br>같은 스마트팜에서 함께 자란 개체들 사이에도 생장 차이가 생긴다는 관찰에서 출발했어요. "
            "1차시 보고서에서 세운 <b>탐색적 가설</b>이라 '증명'이 아니라 이번 표본에서 <b>지지됨 / 지지되지 않음</b>으로 판단해요.")
        h1, h2 = st.columns(2)
        with h1:
            box("hypothesis-box", "<b>가설 1 — 키보다 잎 수</b><br>생중량은 지상부 길이보다 <b>잎 수</b>와 더 강한 양의 상관관계를 보일 것이다.")
            if r_leaf is not None and r_shoot is not None:
                box("conclusion-box", f"{verdict(h1_ok)}<br>잎 수 r = {r_leaf:.3f}, 지상부 길이 r = {r_shoot:.3f}")
            else:
                st.info("가설 1 판정에는 잎 수·지상부 길이·생중량 열이 필요해요.")
        with h2:
            box("hypothesis-box", "<b>가설 2 — 숨은 차이는 땅속에</b><br>개체 간 상대적 질량 변이(변동계수)는 지상부보다 <b>지하부</b>에서 더 클 것이다.")
            if cv_up is not None and cv_dn is not None:
                box("conclusion-box", f"{verdict(h2_ok)}<br>"
                    f"지상부 CV = {cv_up:.1f}%, 지하부 CV = {cv_dn:.1f}% (지하부 ÷ 지상부 = {cv_dn / cv_up:.2f}배)")
            else:
                st.info("가설 2 판정에는 지상부·지하부 질량 열이 필요해요.")

        st.subheader("📌 핵심 숫자")
        if growth_df.empty and env_df.empty:
            st.info("👈 사이드바에서 환경 CSV와 생육 CSV를 올려 주세요. 하나만 올려도 그 부분은 바로 보여요.")
        else:
            c1, c2, c3 = st.columns(3)
            c4, c5, c6 = st.columns(3)
            if not growth_df.empty:
                c1.metric("🌿 개체 수", f"{len(growth_df)}개", border=True)
            if "생중량" in g_cols and growth_df["생중량"].dropna().size > 0:
                w = growth_df["생중량"].dropna()
                c2.metric("⚖️ 평균 생중량", f"{w.mean():.2f} g", border=True)
                c3.metric("📏 생중량 범위 (g)", f"{w.min():.2f} ~ {w.max():.2f}", border=True)
            if "temperature" in e_cols and env_df["temperature"].dropna().size > 0:
                c4.metric("🌡️ 평균 온도", f"{env_df['temperature'].dropna().mean():.1f}", border=True)
            if not env_df.empty:
                c5.metric("🗂️ 환경 기록 수", f"{len(env_df):,}건", border=True)
            if has_time:
                t = env_df["time"].dropna()
                c6.metric("📅 기록 기간", f"{t.min():%m.%d} ~ {t.max():%m.%d}", border=True)

        st.subheader("🔍 데이터 점검")
        rows = []
        for name, df in [("생육 결과", growth_df), ("환경 데이터", env_df)]:
            for c in df.columns:
                rows.append({"데이터": name, "열": c, "유효 개수": int(df[c].notna().sum()), "빈 값 개수": int(df[c].isna().sum())})
        if rows:
            st.caption("열마다 값이 있는 개수와 빈 칸 개수예요. 빈 칸은 0으로 바꾸지 않고 계산에서 빼요.")
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        with st.expander("📖 통계 용어 짧은 설명"):
            st.markdown("""
- **평균**: 모두 더해서 개수로 나눈 값 / **중앙값**: 줄 세웠을 때 가운데 값 (극단값에 덜 흔들림)
- **표준편차·분산**(표본, n−1): 평균에서 얼마나 흩어졌는지 (분산은 단위가 제곱)
- **변동계수(CV)**: 표준편차 ÷ 평균 × 100 → 평균 크기가 다른 것끼리 상대적인 흩어짐 비교
- **상관계수 r**(피어슨): 두 값이 직선 모양으로 함께 변하는 정도 (−1 ~ 1, 원인이라는 뜻은 아님)
- **스피어먼 상관계수**: 값을 순위로 바꾼 뒤 계산 → 직선이 아니어도 '같이 커지는' 경향을 반영
- **추세선**: 점들을 가장 잘 지나는 직선 / **RMSE**: 예측이 평균적으로 얼마나 빗나갔는지 (작을수록 좋음)""")
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")

# ================= TAB 2 — 가설 1 =================
with tabs[1]:
    try:
        box("hypothesis-box", "<b>🍃 가설 1 — 키보다 잎 수</b><br>생중량은 지상부 길이보다 <b>잎 수</b>와 더 강한 양의 상관관계를 보일 것이다.")
        if r_leaf is None or r_shoot is None:
            st.info("가설 1을 확인하려면 생육 CSV에 잎 수 · 지상부 길이 · 생중량이 있어야 해요.")
        else:
            s_leaf = corr(growth_df, "잎 수", "생중량", rank=True)
            s_shoot = corr(growth_df, "지상부 길이", "생중량", rank=True)
            cards = [("🍃 잎 수 r", r_leaf), ("📏 지상부 길이 r", r_shoot), ("🍃 잎 수 스피어먼", s_leaf), ("📏 지상부 길이 스피어먼", s_shoot)]
            for col, (name, v) in zip(st.columns(4), cards):
                col.metric(name, f"{v:.3f}" if v is not None else "—", border=True)

            fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.1,
                                subplot_titles=(f"🍃 잎 수 vs 생중량 (r = {r_leaf:.2f})", f"📏 지상부 길이 vs 생중량 (r = {r_shoot:.2f})"))
            add_scatter(fig, growth_df, "잎 수", "생중량", "#4CAF50", 1, 1)
            add_scatter(fig, growth_df, "지상부 길이", "생중량", "#2196F3", 1, 2)
            fig.update_layout(xaxis_title="잎 수(장)", xaxis2_title="지상부 길이(mm)", yaxis_title="생중량(g)")
            show(fig)
            how_to_read("점 하나가 개체 하나예요. 점이 분홍 추세선 가까이 모여 있을수록 r이 1에 가깝고 관계가 강해요.")

            rows = []
            for c in ["잎 수", "지상부 길이", "지하부 길이"]:
                r = corr(growth_df, c, "생중량") if c in g_cols else None
                if r is not None:
                    rows.append({"지표": c, "r": round(r, 3)})
            if rows:
                fig = px.bar(pd.DataFrame(rows), x="지표", y="r", text_auto=".3f", color="지표", color_discrete_sequence=["#4CAF50", "#2196F3", "#795548"])
                fig.update_layout(showlegend=False, yaxis_range=[min(0, min(r["r"] for r in rows)) - 0.1, 1.1])
                show(fig, 360, "생중량과 각 생육 지표의 상관계수 r")
                how_to_read("막대가 높을수록 그 지표가 클 때 생중량도 큰 경향이 강해요.")

            st.subheader("🔮 잎 수로 생중량 예측해 보기")
            d = pair(growth_df, "잎 수", "생중량")
            b, a = np.polyfit(d["잎 수"], d["생중량"], 1)
            lo, hi = int(np.floor(d["잎 수"].min())), int(np.ceil(d["잎 수"].max()))
            st.markdown(f"예측식: **생중량(g) = {a:.4f} + {b:.5f} × 잎 수(장)**")
            if lo < hi:
                leaf_in = st.slider("잎 수 (관측 범위 안)", lo, hi, int(round(d["잎 수"].median())))
                st.metric("🧮 예측 생중량", f"{max(a + b * leaf_in, 0):.2f} g", border=True)
            box("note-box", "직선 관계만 반영한 짐작값이라 특정 개체의 실제 무게를 보장하지 않아요. 관측 범위 밖은 예측하지 않아요.")

            rows = []
            for k, x in [("평균으로만 찍는 기준", None), ("🍃 잎 수 모형", "잎 수"), ("📏 지상부 길이 모형", "지상부 길이")]:
                v = loo_rmse(growth_df, x, "생중량")
                if v is not None:
                    rows.append({"모형": k, "교차검증 RMSE (g)": round(v, 3)})
            if rows:
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
                st.caption("개체 하나씩 빼고 나머지로 식을 만든 뒤 뺀 개체를 맞혀 보는 방식(교차검증)이에요. 기준보다 작을수록 쓸모 있는 지표예요.")

            st.subheader("📊 생중량 상위 25% vs 하위 25%")
            w = growth_df["생중량"]
            q1, q3 = w.quantile(0.25), w.quantile(0.75)
            low, high = growth_df[w <= q1], growth_df[w >= q3]
            rows = []
            for c in g_cols:
                if c != "생중량" and low[c].dropna().size > 0 and high[c].dropna().size > 0 and low[c].mean() > 0:
                    rows.append({"지표": c, "하위 25% 평균": round(low[c].mean(), 2),
                                 "상위 25% 평균": round(high[c].mean(), 2), "몇 배": round(high[c].mean() / low[c].mean(), 2)})
            if rows and len(low) > 0 and len(high) > 0:
                tb = pd.DataFrame(rows)
                fig = px.bar(tb.sort_values("몇 배"), x="몇 배", y="지표", orientation="h", text="몇 배", color_discrete_sequence=["#FF7B00"])
                fig.update_traces(texttemplate="%{text}배", textposition="outside")
                show(fig, 340, f"상위 25%(≥{q3:.2f}g, {len(high)}개) ÷ 하위 25%(≤{q1:.2f}g, {len(low)}개) 평균")
                how_to_read("막대가 길수록 무거운 그룹과 가벼운 그룹의 차이가 큰 항목이에요. 질량은 생중량의 일부라 크게 나오는 게 당연하니 잎 수·길이를 중심으로 보세요.")
                st.dataframe(tb, width="stretch", hide_index=True)
            else:
                st.info("그룹 비교를 할 값이 부족해요.")

            box("conclusion-box", f"<b style='font-size:1.1rem'>📊 판정: 가설 1</b> {verdict(h1_ok)}<br>"
                f"잎 수 r = {r_leaf:.3f}, 지상부 길이 r = {r_shoot:.3f} → 생중량과 더 강하게 관련된 쪽은 "
                f"<b>{'잎 수' if abs(r_leaf) > abs(r_shoot) else '지상부 길이'}</b>예요.<br>⚠️ 상관관계일 뿐 원인을 뜻하지는 않아요.")
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")

# ================= TAB 3 — 가설 2 =================
with tabs[2]:
    try:
        box("hypothesis-box", "<b>🌱 가설 2 — 숨은 차이는 땅속에</b><br>개체 간 상대적 질량 변이(변동계수)는 지상부보다 <b>지하부</b>에서 더 크게 나타날 것이다.")
        if cv_up is None or cv_dn is None:
            st.info("가설 2를 확인하려면 생육 CSV에 지상부 질량 · 지하부 질량이 있어야 해요 (평균이 0보다 커야 해요).")
        else:
            up, dn = growth_df["지상부 질량"].dropna(), growth_df["지하부 질량"].dropna()
            cards = [("🌿 지상부 CV", f"{cv_up:.1f}%"), ("🟤 지하부 CV", f"{cv_dn:.1f}%"), ("차이", f"{cv_dn - cv_up:+.1f}%p"), ("지하부 ÷ 지상부", f"{cv_dn / cv_up:.2f}배")]
            for col, (name, v) in zip(st.columns(4), cards):
                col.metric(name, v, border=True)

            cvt = pd.DataFrame({"부분": ["지상부 질량", "지하부 질량"], "CV (%)": [round(cv_up, 1), round(cv_dn, 1)]})
            fig = px.bar(cvt, x="부분", y="CV (%)", text="CV (%)", color="부분", color_discrete_map={"지상부 질량": "#4CAF50", "지하부 질량": "#795548"})
            fig.update_traces(texttemplate="%{text}%", textposition="outside", width=0.5)
            fig.update_layout(showlegend=False)
            show(fig, 380, "변동계수(CV) 비교")
            how_to_read("CV가 클수록 평균에 비해 개체끼리 들쭉날쭉해요.")
            rows = []
            for name, v in [("지상부 질량", up), ("지하부 질량", dn)]:
                rows.append({"부분": name, "평균(g)": round(v.mean(), 3), "표준편차(g)": round(v.std(ddof=1), 3), "분산(g²)": round(v.var(ddof=1), 3), "CV(%)": round(cv(v), 1)})
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            box("note-box", f"<b>📌 주의</b><br>분산(절대적인 흩어짐)은 <b>{'지상부' if up.var(ddof=1) > dn.var(ddof=1) else '지하부'}</b>가 더 커요 "
                f"(지상부 {up.var(ddof=1):.3f} g², 지하부 {dn.var(ddof=1):.3f} g²). "
                f"평균도 지상부 {up.mean():.2f} g, 지하부 {dn.mean():.2f} g로 달라서, 이번 비교는 <b>평균에 비한 흩어짐(CV)</b>으로 판단해요.")

            fig = go.Figure()
            fig.add_trace(go.Box(y=up, name="지상부 질량", fillcolor="rgba(76,175,80,0.35)", line=dict(color="#2E7D32"), boxpoints="outliers"))
            fig.add_trace(go.Box(y=dn, name="지하부 질량", fillcolor="rgba(121,85,72,0.35)", line=dict(color="#5D4037"), boxpoints="outliers"))
            fig.update_layout(yaxis_title="질량(g)", showlegend=False)
            show(fig, 380, "지상부·지하부 질량 상자그림 (원래 단위)")
            how_to_read("상자는 가운데 50% 개체가 있는 범위, 가운데 선은 중앙값, 점은 다른 개체보다 크게 벗어난 값이에요 (오류라는 뜻은 아님).")

            zero = growth_df["지하부 질량"] == 0
            if zero.any():
                zero_ids = [ids[i] for i in range(len(ids)) if zero.iloc[i]]
                both = growth_df.loc[~zero, ["지상부 질량", "지하부 질량"]].dropna()
                cu, cd = cv(both["지상부 질량"]), cv(both["지하부 질량"])
                msg = f"<b>🔎 지하부 질량이 0 g인 개체 {len(zero_ids)}개</b>: {', '.join(zero_ids)}번<br>측정 확인이 필요한 개체라 빼고도 다시 계산해 봤어요."
                if cu is not None and cd is not None:
                    msg += f"<br>0 g 개체를 뺀 {len(both)}개체: 지상부 CV {cu:.1f}%, 지하부 CV {cd:.1f}% → 가설 2 방향 <b>{'유지됨 ✅' if cd > cu else '바뀜 ⚠️'}</b>"
                box("warn-box", msg)

            box("conclusion-box", f"<b style='font-size:1.1rem'>📊 판정: 가설 2</b> {verdict(h2_ok)}<br>"
                f"지상부 CV = {cv_up:.1f}%, 지하부 CV = {cv_dn:.1f}% → 평균에 비한 개체 차이는 "
                f"<b>{'지하부' if cv_dn > cv_up else '지상부'}</b>에서 더 컸어요 ({abs(cv_dn - cv_up):.1f}%p 차이).")
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")

# ================= TAB 4 — 개체별 비교 =================
with tabs[3]:
    try:
        if growth_df.empty or not g_cols:
            st.info("👈 생육 CSV를 올려 주세요. (잎 수·길이·질량 열이 있어야 해요)")
        else:
            if "생중량" in g_cols and growth_df["생중량"].dropna().size >= 2:
                w = growth_df["생중량"].dropna()
                cards = [("평균", f"{w.mean():.2f} g"), ("중앙값", f"{w.median():.2f} g"), ("표준편차", f"{w.std(ddof=1):.2f} g"),
                         ("변동계수(CV)", f"{cv(w):.1f}%" if cv(w) is not None else "—")]
                for col, (name, v) in zip(st.columns(4), cards):
                    col.metric(name, v, border=True)
                fig = px.histogram(w, nbins=20, color_discrete_sequence=["#81C784"])
                fig.add_vline(x=w.mean(), line_dash="dash", line_color="#2196F3", annotation_text=f"평균 {w.mean():.2f}")
                fig.add_vline(x=w.median(), line_dash="dot", line_color="#FF9800", annotation_text=f"중앙값 {w.median():.2f}", annotation_position="top left")
                fig.update_layout(xaxis_title="생중량(g)", yaxis_title="개체 수", showlegend=False, bargap=0.05)
                show(fig, 400, "생중량 히스토그램")
                how_to_read("막대 높이는 그 무게 구간에 있는 개체 수예요. 평균이 중앙값보다 오른쪽이면 아주 무거운 개체 몇 개가 평균을 끌어올린 거예요.")

            d = pd.DataFrame({"개체": ids, measure: growth_df[measure].values}).dropna(subset=[measure])
            d = d.sort_values(measure, ascending=False).reset_index(drop=True)
            if len(d) >= 4:
                k = min(5, len(d) // 2)
                d["구분"] = "중간"
                d.loc[d.index[:k], "구분"] = f"상위 {k}"
                d.loc[d.index[len(d) - k:], "구분"] = f"하위 {k}"
                fig = px.bar(d, x="개체", y=measure, color="구분", color_discrete_map={f"상위 {k}": "#FF7B00", "중간": "#C8E6C9", f"하위 {k}": "#E91E63"})
                fig.update_layout(xaxis_type="category", xaxis_title="개체번호", yaxis_title=lab(measure),
                                  legend=dict(orientation="h", y=1.08, x=1, xanchor="right", title=None))
                show(fig, 420, f"개체별 {lab(measure)} (큰 순서) — 사이드바에서 항목 변경")
                box("conclusion-box", f"🔺 상위 {k}: {', '.join(d['개체'].head(k))} &nbsp;|&nbsp; 🔻 하위 {k}: {', '.join(d['개체'].tail(k))}")
            else:
                st.info(f"{measure} 값이 4개 미만이라 막대그래프를 건너뛰었어요.")

            if len(g_cols) >= 2 and len(growth_df[g_cols].dropna()) >= 3:
                cm = growth_df[g_cols].corr().round(2)
                cm.index = [lab(c) for c in cm.index]
                cm.columns = [lab(c) for c in cm.columns]
                fig = px.imshow(cm, text_auto=True, zmin=-1, zmax=1, color_continuous_scale="RdBu_r", aspect="auto")
                show(fig, 460, "생육 변수 상관계수 히트맵 (개체번호 제외)")
                how_to_read("진한 빨강일수록 함께 커지는 관계, 파랑은 반대로 움직이는 관계, 흰색은 관계가 거의 없다는 뜻이에요.")
            else:
                st.info("히트맵을 그리려면 숫자 항목이 2개 이상, 값이 3개 이상 필요해요.")

            st.download_button("📥 생육 데이터 CSV 다운로드", growth_df.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"{school}_생육결과_정리.csv", mime="text/csv")
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")

# ================= TAB 5 — 환경 데이터 =================
with tabs[4]:
    try:
        box("note-box", "🌡️ 환경은 <b>모든 개체가 함께 겪은 배경</b>이에요. 개체끼리 차이의 원인으로 바로 연결하지 않고, 실험 기간 환경이 어땠는지 확인하는 용도로 봐 주세요.")
        if env_df.empty:
            st.info("👈 환경 CSV를 올려 주세요.")
        elif not e_cols:
            st.info("온도·습도·pH·EC 중에 알아볼 수 있는 열이 없어요.")
        else:
            if has_time:
                et = env_df.dropna(subset=["time"]).assign(날짜=lambda x: x["time"].dt.date, 시각=lambda x: x["time"].dt.hour)
                daily = et.groupby("날짜")[e_cols].mean()
                n, colors = len(e_cols), ["#E64A19", "#1976D2", "#7B1FA2", "#388E3C"]
                fig = make_subplots(rows=(n + 1) // 2, cols=2 if n > 1 else 1, vertical_spacing=0.18, subplot_titles=[ENV_KO[c] for c in e_cols])
                for j, c in enumerate(e_cols):
                    s = daily[c].dropna()
                    fig.add_trace(go.Scatter(x=s.index, y=s.values, mode="lines", line=dict(color=colors[j % 4], width=2),
                                             showlegend=False), row=j // 2 + 1, col=j % 2 + 1)
                show(fig, 250 * ((n + 1) // 2), "환경 항목 한눈에 보기 (일별 평균)")
                how_to_read("작은 그래프 하나가 환경 항목 하나예요. 갑자기 튀어 오른 구간이 환경이 크게 바뀐 시기예요.")

                var = st.selectbox("자세히 볼 환경 항목", e_cols, format_func=lambda c: ENV_KO[c])
                d = et[["time", "날짜", "시각", var]].dropna()
                if len(d) >= 2:
                    agg = d.groupby("날짜")[var].agg(["mean", "max"])
                    fig = go.Figure()
                    if var == "temperature":
                        fig.add_hrect(y0=HOT, y1=max(HOT + 1, d[var].max() + 0.5), fillcolor="#E91E63", opacity=0.08,
                                      line_width=0, annotation_text=f"{HOT} 이상 구간")
                    fig.add_trace(go.Scatter(x=agg.index, y=agg["max"], mode="lines", name="일별 최고", line=dict(color="#FF9800", dash="dot")))
                    fig.add_trace(go.Scatter(x=agg.index, y=agg["mean"], mode="lines+markers", name="일별 평균",
                                             line=dict(color="#2196F3", width=2), marker=dict(size=4)))
                    fig.update_layout(xaxis_title="날짜", yaxis_title=ENV_KO[var], legend=dict(orientation="h", y=1.08, x=1, xanchor="right"))
                    show(fig, 400, f"날짜별 {ENV_KO[var]} (평균·최고)")
                    how_to_read("파란 선은 그날 기록의 단순 평균, 주황 점선은 그날 최고값이에요.")
                    if var == "temperature":
                        hot = d[d[var] >= HOT]
                        if len(hot) > 0:
                            days = ", ".join(sorted({f"{x:%m/%d}" for x in hot["time"]}))
                            box("warn-box", f"🌡️ <b>{HOT} 이상 기록 {len(hot)}건</b> / 전체 {len(d)}건 ({len(hot) / len(d) * 100:.1f}%) → {days}<br>"
                                f"{HOT}은 높은 구간을 살펴보려는 탐색용 기준이고, 식물 피해 기준으로 확인된 값은 아니에요.")
                    pv = d.pivot_table(index="시각", columns="날짜", values=var, aggfunc="mean")
                    if pv.shape[0] >= 2 and pv.shape[1] >= 2:
                        fig = px.imshow(pv, aspect="auto", color_continuous_scale="YlOrRd" if var == "temperature" else "Viridis",
                                        labels=dict(x="날짜", y="시각(시)", color=ENV_KO[var]))
                        fig.update_yaxes(autorange="reversed", dtick=3)
                        show(fig, 400, f"날짜 × 시각 {ENV_KO[var]} 히트맵 (빈 칸 = 센서 기록 없음)")
                        how_to_read("세로로 진한 띠가 보이면 그 날짜에는 하루 종일 값이 높았다는 뜻이에요.")
                else:
                    st.info(f"{ENV_KO[var]} 값이 2개 미만이라 그래프를 건너뛰었어요.")
            else:
                st.info("시간 열을 찾지 못해서 날짜별 그래프는 건너뛰었어요. 아래 요약 표는 볼 수 있어요.")

            rows = []
            for c in e_cols:
                s = env_df[c].dropna()
                if len(s) > 0:
                    rows.append({"항목": ENV_KO[c], "유효 개수": len(s), "평균": round(s.mean(), 2), "표준편차": round(s.std(ddof=1), 2) if len(s) >= 2 else None,
                                 "최소": round(s.min(), 2), "최대": round(s.max(), 2)})
            if rows:
                st.subheader("📋 환경 데이터 요약")
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            st.download_button("📥 환경 데이터 CSV 다운로드", env_df.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"{school}_환경데이터_정리.csv", mime="text/csv")
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")
