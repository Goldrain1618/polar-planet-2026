import io
import os
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats
import streamlit as st

st.set_page_config(page_title="극지식물 생육 차이 분석", layout="wide")

# ---------- 한글 폰트 CSS ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR&display=swap');
html, body, [class*="css"] {
   font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif;
}
.banner {
   background: linear-gradient(90deg, #e6f7e6 0%, #c8e6c9 100%);
   border-radius: 14px;
   padding: 18px 22px;
   margin-bottom: 18px;
}
.banner h1 { margin: 0; font-size: 1.55rem; }
.kpi-card { background: #ffffffcc; border: 1px solid #e0e0e0; border-radius: 10px; padding: 12px 14px; }
.hypothesis-box {
   background: #f5f9ff; border-left: 6px solid #2196F3; border-radius: 8px;
   padding: 14px 16px; margin-bottom: 14px;
}
.conclusion-box {
   background: #f1f8e9; border-left: 6px solid #4CAF50; border-radius: 8px;
   padding: 12px 14px; margin-bottom: 14px;
}
.note-box {
   background: #fff8e1; border-left: 6px solid #FF9800; border-radius: 8px;
   padding: 11px 13px; margin-bottom: 12px; font-size: 0.92rem;
}
.warn-box {
   background: #fce4ec; border-left: 6px solid #E91E63; border-radius: 8px;
   padding: 11px 13px; margin-bottom: 12px;
}
.ts-line { font-size: 0.82rem; color: #666; font-style: italic; margin: 4px 0 10px 0; }
</style>
""", unsafe_allow_html=True)

# ---------- CSV 읽기 ----------
def read_csv_bytes(data):
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc)
        except Exception:
            pass
    return pd.DataFrame()

@st.cache_data(show_spinner=False)
def load_data(raw_bytes):
    return read_csv_bytes(raw_bytes)


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


# ---------- 사이드바 ----------
env_file = st.sidebar.file_uploader("🌡 환경 데이터 CSV", type="csv", help="학교 환경 측정 기록")
growth_file = st.sidebar.file_uploader("🌱 생육 결과 CSV", type="csv", help="개체별 생육 결과 기록")

school_name = ""
if env_file is not None:
    school_name = os.path.splitext(env_file.name)[0]
elif growth_file is not None:
    school_name = os.path.splitext(growth_file.name)[0]

if school_name:
    st.sidebar.markdown(f"**📌 분석 대상:** {school_name}")


env_raw = env_file.getvalue() if env_file is not None else None
growth_raw = growth_file.getvalue() if growth_file is not None else None

env_df = None
growth_df = None

if env_raw is not None:
    with st.spinner("환경 CSV 읽는 중..."):
        env_df = load_data(env_raw)
if growth_raw is not None:
    with st.spinner("생육 CSV 읽는 중..."):
        growth_df = load_data(growth_raw)

if env_df is not None and not env_df.empty:
    env_df = std_cols(env_df)
if growth_df is not None and not growth_df.empty:
    growth_df = std_cols(growth_df)


def get_cols(df, names):
    if df is None or df.empty:
        return []
    return [c for c in names if c in df.columns]


def pearson_corr(df, x, y):
    d = df[[x, y]].dropna()
    if len(d) < 2:
        return None
    return d[x].corr(d[y])


def spearman_rank_corr(df, x, y):
    d = df[[x, y]].dropna()
    if len(d) < 2:
        return None
    r = d[[x, y]].rank()
    return r[x].corr(r[y])


# ---------- 제목 배너 ----------
st.markdown(f"""
<div class="banner">
<h1>🌱 {school_name or '학교명 미확정'} 극지식물 개체별 생육 차이 분석 대시보드</h1>
<p style="margin-top:6px;color:#333;">
같은 스마트팜에서 함께 자란 극지식물도 개체마다 잎 수·길이·무게가 왜 다른지,
잎 수와 지상부 길이 중 무엇이 생중량을 더 잘 설명하는지(가설 1),
그리고 지상부·지하부 중 어느 부분이 개체 간 상대적 차이를 더 크게 만드는지(가설 2)를
데이터로 확인하는 대시보드입니다.
</p>
</div>
""", unsafe_allow_html=True)

tabs = st.tabs(["📋 개요", "🍃 가설 1 — 키보다 잎 수", "🌱 가설 2 — 숨은 차이는 땅속에",
                "📊 개체별 비교", "🌡️ 환경 데이터 (배경)"])

# ===================================================================
# TAB 1 — 개요
# ===================================================================
with tabs[0]:
    try:
        st.subheader("📋 실험 개요")
        st.markdown("""
<div class="hypothesis-box">
<h3 style="margin-top:0;">🔬 연구 배경 및 목적</h3>
<p>극지 환경에 사는 극지식물은 기온이 낮고 생장 기간이 짧아 환경 변화에 민감합니다.
이 대시보드에서는 <b>같은 스마트팜에서 함께 자란 개체들 사이에도 생장 차이가 생긴다</b>는 관찰을 바탕으로,</p>
<ul>
<li>잎 수와 지상부 길이 중 <b>생중량과 더 밀접한 지표</b>는 무엇인지 (가설 1)</li>
<li>지상부·지하부 중 <b>평균 대비 상대적 변동</b>이 더 큰 부분은 어디인지 (가설 2)</li>
</ul>
<p>를 데이터로 확인합니다. 1차시 보고서에서 세운 <b>탐색적 가설</b>이므로,
'증명'이 아니라 이번 표본에서 <b>지지됨 / 지지되지 않음</b>으로 판단합니다.</p>
</div>
""", unsafe_allow_html=True)

        col_h1, col_h2 = st.columns(2)
        with col_h1:
            st.markdown("""
<div class="hypothesis-box">
<b>가설 1 — 키보다 잎 수</b><br>
생중량은 지상부 길이보다 <b>잎 수</b>와 더 강한 양의 상관관계를 보일 것이다.
</div>
""", unsafe_allow_html=True)
        with col_h2:
            st.markdown("""
<div class="hypothesis-box">
<b>가설 2 — 숨은 차이는 땅속에</b><br>
개체 간 상대적 질량 변이(변동계수, CV)는 지상부보다 <b>지하부</b>에서 더 크게 나타날 것이다.
</div>
""", unsafe_allow_html=True)

        if growth_df is not None and not growth_df.empty:
            has_w = "생중량" in growth_df.columns
            has_l = "잎 수" in growth_df.columns
            has_s = "지상부 길이" in growth_df.columns
            has_smass = "지상부 질량" in growth_df.columns
            has_rmass = "지하부 질량" in growth_df.columns
        else:
            has_w = has_l = has_s = has_smass = has_rmass = False

        r_leaf = pearson_corr(growth_df, "잎 수", "생중량") if has_w and has_l else None
        r_shoot = pearson_corr(growth_df, "지상부 길이", "생중량") if has_w and has_s else None
        cv_shoot = None
        cv_root = None
        if has_smass and has_rmass:
            shoot = growth_df["지상부 질량"].dropna()
            root = growth_df["지하부 질량"].dropna()
            if len(shoot) >= 3 and shoot.mean() > 0:
                cv_shoot = shoot.std(ddof=1) / shoot.mean() * 100
            if len(root) >= 3 and root.mean() > 0:
                cv_root = root.std(ddof=1) / root.mean() * 100

        if has_w:
            conclusion_col1, conclusion_col2 = st.columns(2)
            with conclusion_col1:
                if r_leaf is not None and r_shoot is not None:
                    stronger = "잎 수" if abs(r_leaf) > abs(r_shoot) else "지상부 길이"
                    stronger_r = r_leaf if stronger == "잎 수" else r_shoot
                    verdict_h1 = "지지됨 ✅" if abs(r_leaf) > abs(r_shoot) else "지지되지 않음 ⚠️"
                    st.markdown(f"""
<div class="conclusion-box">
<b>📊 데이터로 본 가설 1</b><br>
 verdict: <b>{verdict_h1}</b><br>
 잎 수 r = {r_leaf:.3f}, 지상부 길이 r = {r_shoot:.3f} → 더 강한 쪽은 <b>{stronger}</b> (r = {stronger_r:.3f})
</div>
""", unsafe_allow_html=True)
                else:
                    st.info("가설 1 판정에 필요한 잎 수·지상부 길이·생중량 열이 모두 있어야 해요.")
            with conclusion_col2:
                if cv_shoot is not None and cv_root is not None:
                    verdict_h2 = "지지됨 ✅" if cv_root > cv_shoot else "지지되지 않음 ⚠️"
                    ratio_h2 = cv_root / cv_shoot if cv_shoot > 0 else float("nan")
                    st.markdown(f"""
<div class="conclusion-box">
<b>📊 데이터로 본 가설 2</b><br>
 verdict: <b>{verdict_h2}</b><br>
 지상부 CV = {cv_shoot:.2f}%, 지하부 CV = {cv_root:.2f}% → CV 비율(지하부 ÷ 지상부) = {ratio_h2:.2f}배
</div>
""", unsafe_allow_html=True)
                else:
                    st.info("가설 2 판정에 필요한 지상부·지하부 질량 열이 있어야 해요.")

        st.markdown('<div class="kpi-card"><h3 style="margin-top:0;">📌 핵심 숫자</h3></div>', unsafe_allow_html=True)
        c1, c2, c3, c4, c5, c6 = st.columns(6)

        n_ind = growth_df["개체번호"].nunique() if (growth_df is not None and not growth_df.empty and "개체번호" in growth_df.columns) else 0
        c1.metric("개체 수", f"{n_ind}개체" if n_ind else "—")
        if has_w and growth_df["생중량"].notna().sum() > 0:
            w = growth_df["생중량"]
            c2.metric("평균 생중량", f"{w.mean():.2f} g")
            c3.metric("생중량 범위", f"{w.min():.2f} ~ {w.max():.2f} g")
        else:
            c2.metric("평균 생중량", "—")
            c3.metric("생중량 범위", "—")

        if env_df is not None and not env_df.empty:
            if "temperature" in env_df.columns and env_df["temperature"].notna().sum() > 0:
                c4.metric("평균 온도", f"{env_df['temperature'].mean():.1f} °C")
            else:
                c4.metric("평균 온도", "—")
            c5.metric("환경 기록 수", f"{len(env_df)}건")
            if "time" in env_df.columns:
                tmin = env_df["time"].min()
                tmax = env_df["time"].max()
                c6.metric("기록 기간", f"{tmin.strftime('%Y-%m-%d')} ~ {tmax.strftime('%Y-%m-%d')}")
            else:
                c6.metric("기록 기간", "—")
        else:
            c4.metric("평균 온도", "—")
            c5.metric("환경 기록 수", "—")
            c6.metric("기록 기간", "—")

        st.markdown('<div class="kpi-card"><h3 style="margin-top:0;">🔍 데이터 점검</h3></div>', unsafe_allow_html=True)
        st.caption("각 열의 유효 값(유효 개수)과 빈 값 개수를 확인해요. 유효 개수가 0이면 그 열은 분석에 쓸 수 없어요.")
        rows = []
        for label, df in [("생육 결과", growth_df), ("환경 데이터", env_df)]:
            if df is not None and not df.empty:
                for col in df.columns:
                    series = df[col]
                    if pd.api.types.is_numeric_dtype(series):
                        valid = int(series.notna().sum())
                    else:
                        valid = int(series.astype(str).str.strip().ne("").sum())
                    na = len(df) - valid
                    rows.append({"데이터": label, "열": col, "유효 개수": valid, "빈 값 개수": na})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        st.markdown('<div class="kpi-card"><h3 style="margin-top:0;">📖 통계 용어 짧은 설명</h3></div>', unsafe_allow_html=True)
        st.write("• **평균**: 여러 값을 더해 개수로 나눈 대표값")
        st.write("• **중앙값**: 값을 크기순으로 나열했을 때 한가운데 있는 값 (이상치에 덜 영향)")
        st.write("• **표준편차**(표본, n−1): 값들이 평균에서 얼마나 퍼져 있는지 나타냄")
        st.write("• **분산**(표본, n−1): 표준편차를 제곱한 값 (단위가 제곱이라 직관적 비교는 어려움)")
        st.write("• **변동계수(CV)**: 표준편차 ÷ 평균 × 100 → 평균이 다른 것끼리 '상대적 퍼짐'을 비교")
        st.write("• **상관계수 r**(피어슨): 두 변수가 직선 모양으로 함께 변하는 정도 (−1 ~ 1)")
        st.write("• **스피어만 순위상관계수**: 값을 '순위'로 바꾼 뒤 상관 계산 → 직선 아닌 단조 관계도 반영")
        st.write("• **추세선**: 산점도 점들의 경향을 직선으로 근사한 선 (np.polyfit으로 기울기와 절편 구함)")
        st.write("• **RMSE**(교차검증): 개체 하나씩 빼고 예측해 오류 크기를 평균한 값 (낮을수록 예측 성능이 좋음)")

    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")

# ===================================================================
# TAB 2 — 가설 1
# ===================================================================
with tabs[1]:
    try:
        st.markdown("""
<div class="hypothesis-box">
<b>🍃 가설 1 — 키보다 잎 수</b><br>
생중량은 지상부 길이보다 **잎 수**와 더 강한 양의 상관관계를 보일 것이다.
(데이터를 먼저 보고 세운 탐색적 가설 → '증명'이 아니라 이번 표본에서 <b>지지됨 / 지지되지 않음</b>으로 표현)
</div>
""", unsafe_allow_html=True)

        has_w = "생중량" in growth_df.columns if (growth_df is not None and not growth_df.empty) else False
        has_l = "잎 수" in growth_df.columns if (growth_df is not None and not growth_df.empty) else False
        has_s = "지상부 길이" in growth_df.columns if (growth_df is not None and not growth_df.empty) else False
        has_r = "지하부 길이" in growth_df.columns if (growth_df is not None and not growth_df.empty) else False

        if not has_w or not has_l or not has_s or growth_df is None or growth_df.empty:
            st.info("가설 1을 확인하려면 생육 CSV에 **잎 수 · 지상부 길이 · 생중량**이 있어야 해요. 아직 데이터가 없어요.")
        else:
            w = growth_df["생중량"].dropna()
            leaf = growth_df["잎 수"].dropna()
            shoot = growth_df["지상부 길이"].dropna()

            r_leaf = pearson_corr(growth_df, "잎 수", "생중량")
            r_shoot = pearson_corr(growth_df, "지상부 길이", "생중량")
            sph_leaf = spearman_rank_corr(growth_df, "잎 수", "생중량")
            sph_shoot = spearman_rank_corr(growth_df, "지상부 길이", "생중량")

            c1, c2, c3 = st.columns(3)
            c1.metric("잎 수 — 피어슨 r", f"{r_leaf:.3f}" if r_leaf is not None else "—")
            c2.metric("지상부 길이 — 피어슨 r", f"{r_shoot:.3f}" if r_shoot is not None else "—")
            c3.metric("잎 수 — 스피어만 ρ", f"{sph_leaf:.3f}" if sph_leaf is not None else "—")
            c4, c5 = st.columns(2)
            c4.metric("지상부 길이 — 스피어만 ρ", f"{sph_shoot:.3f}" if sph_shoot is not None else "—")
            c5.metric("더 강한 지표", "잎 수 ✅" if r_leaf is not None and r_shoot is not None and abs(r_leaf) > abs(r_shoot) else ("지상부 길이 🟡" if r_leaf is not None and r_shoot is not None else "—"))
            st.caption("※ 스피어만 ρ는 값을 '순위'로 바꾼 뒤 상관 계산한 값이에요. 선형뿐 아니라 '한쪽이 커지면 다른 쪽도 커지는' 단조 관계도 반영해요.")

            fig2 = make_subplots(rows=1, cols=2, subplot_titles=("🍃 잎 수 vs 생중량", "📏 지상부 길이 vs 생중량"),
                                 horizontal_spacing=0.12)
            dL = growth_df[["잎 수", "생중량"]].dropna()
            dS = growth_df[["지상부 길이", "생중량"]].dropna()
            if len(dL) >= 2:
                sl, il = np.polyfit(dL["잎 수"], dL["생중량"], 1)
                fig2.add_trace(go.Scatter(x=dL["잎 수"], y=dL["생중량"], mode="markers", name="잎 수",
                                           marker=dict(color="#4CAF50", size=7)), row=1, col=1)
                fig2.add_trace(go.Scatter(x=dL["잎 수"], y=sl * dL["잎 수"] + il, mode="lines",
                                           name=f"추세선 (r={r_leaf:.2f})", line=dict(color="#E91E63", width=2)), row=1, col=1)
            if len(dS) >= 2:
                ss, is_ = np.polyfit(dS["지상부 길이"], dS["생중량"], 1)
                fig2.add_trace(go.Scatter(x=dS["지상부 길이"], y=dS["생중량"], mode="markers", name="지상부 길이",
                                           marker=dict(color="#2196F3", size=7)), row=1, col=2)
                fig2.add_trace(go.Scatter(x=dS["지상부 길이"], y=ss * dS["지상부 길이"] + is_, mode="lines",
                                           name=f"추세선 (r={r_shoot:.2f})", line=dict(color="#FF9800", width=2)), row=1, col=2)
            fig2.update_xaxes(title_text="잎 수 (장)", row=1, col=1)
            fig2.update_xaxes(title_text="지상부 길이 (mm)", row=1, col=2)
            fig2.update_yaxes(title_text="생중량 (g)", row=1, col=1)
            fig2.update_yaxes(title_text="생중량 (g)", row=1, col=2)
            fig2.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"), height=420)
            st.plotly_chart(fig2, width="stretch")
            st.markdown("<p class=\"ts-line\">이 그래프 읽는 법: 점 하나가 개체 하나예요. 점이 추세선 가까이에 모여 있을수록 두 지표가 함께 변하고, r 값이 1 또는 −1에 가까울수록 관계가 강해요.</p>", unsafe_allow_html=True)

            cand = []
            if has_l:
                cand.append(("잎 수", pearson_corr(growth_df, "잎 수", "생중량")))
            if has_s:
                cand.append(("지상부 길이", pearson_corr(growth_df, "지상부 길이", "생중량")))
            if has_r:
                cand.append(("지하부 길이", pearson_corr(growth_df, "지하부 길이", "생중량")))
            cand = [(n, r) for n, r in cand if r is not None]
            if cand:
                figr = px.bar(pd.DataFrame(cand, columns=["지표", "r"]), x="지표", y="r", color="r",
                              color_continuous_scale="RdYlGn", title="생중량과 각 생육 지표의 피어슨 r 비교")
                figr.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"))
                st.plotly_chart(figr, width="stretch")
                st.markdown("<p class=\"ts-line\">이 그래프 읽는 법: 막대 높이가 r 값의 크기예요. 잎 수 막대가 지상부 길이 막대보다 높고 양수면, 잎 수가 생중량과 더 강한 양의 관계라는 뜻이에요.</p>", unsafe_allow_html=True)

            if len(leaf) >= 2 and len(set(leaf)) >= 2:
                sl, il = np.polyfit(leaf, w, 1)
                min_leaf = int(leaf.min())
                max_leaf = int(leaf.max())
                sel = st.slider("🔮 잎 수 슬라이더 (관측 범위 안)", min_leaf, max_leaf, min_leaf, step=1)
                pred = sl * sel + il
                st.metric("🌿 선택 잎 수", f"{sel}장")
                st.metric("🧮 예측 생중량 (잎 수 모형)", f"{pred:.2f} g")
                st.warning("⚠️ 이 값은 잎 수와 생중량의 직선 관계만 반영한 추정치예요. 실제 무게를 보장하지 않아요.")

            mean_w = growth_df["생중량"].dropna().mean()
            rows_rmse = []
            err_leaf = []
            err_shoot = []
            err_mean = []
            for idx in growth_df.index:
                gt = growth_df.loc[idx, "생중량"]
                if pd.isna(gt):
                    continue
                xL = growth_df.loc[idx, "잎 수"]
                xS = growth_df.loc[idx, "지상부 길이"]
                m = growth_df.drop(idx)
                mL = m["잎 수"].dropna()
                wM = m["생중량"].dropna()
                mS = m["지상부 길이"].dropna()
                if len(mL) >= 2 and len(set(mL)) >= 2 and not pd.isna(xL):
                    a, b = np.polyfit(mL, wM, 1)
                    err_leaf.append(gt - (a * xL + b))
                if len(mS) >= 2 and len(set(mS)) >= 2 and not pd.isna(xS):
                    aS, bS = np.polyfit(mS, wM, 1)
                    err_shoot.append(gt - (aS * xS + bS))
                err_mean.append(gt - mean_w)
            rmse_leaf = np.sqrt(np.mean(np.array(err_leaf) ** 2)) if err_leaf else None
            rmse_shoot = np.sqrt(np.mean(np.array(err_shoot) ** 2)) if err_shoot else None
            rmse_mean = np.sqrt(np.mean(np.array(err_mean) ** 2)) if err_mean else None

            if rmse_leaf is not None or rmse_shoot is not None or rmse_mean is not None:
                rmse_tbl = pd.DataFrame({
                    "모형": ["평균으로만 찍는 기준", "🍃 잎 수 모형", "📏 지상부 길이 모형"],
                    "RMSE (g)": [f"{rmse_mean:.3f}" if rmse_mean is not None else "—",
                                 f"{rmse_leaf:.3f}" if rmse_leaf is not None else "—",
                                 f"{rmse_shoot:.3f}" if rmse_shoot is not None else "—"],
                    "설명": ["아무 정보 없이 평균으로 찍을 때 오류", "잎 수 1개로 예측 (LOOCV)", "지상부 길이 1개로 예측 (LOOCV)"]
                })
                st.dataframe(rmse_tbl, width="stretch", hide_index=True)
                st.caption("※ LOOCV: 개체 하나씩 빼고 나머지를 이용해 그 개체를 예측하는 방식. 표본이 작을수록 불확실성이 커요.")

            mean_w_per = growth_df.groupby("개체번호")["생중량"].mean().reset_index().sort_values("생중량", ascending=False).reset_index(drop=True)
            n_ind = len(mean_w_per)
            t25 = int(np.ceil(n_ind * 0.25))
            b25 = int(np.ceil(n_ind * 0.25))
            top_mean_w = mean_w_per.iloc[:t25]["생중량"].mean()
            bot_mean_w = mean_w_per.iloc[n_ind - b25:]["생중량"].mean()

            def group_mean(col):
                if col not in growth_df.columns:
                    return None
                g = growth_df.groupby("개체번호")[col].mean().reset_index().sort_values("생중량", ascending=False).reset_index(drop=True)
                return g.iloc[:t25][col].mean(), g.iloc[n_ind - b25:][col].mean()

            metrics_topbot = [("잎 수", "잎 수"), ("지상부 길이", "지상부 길이"), ("지하부 길이", "지하부 길이"),
                              ("지상부 질량", "지상부 질량"), ("지하부 질량", "지하부 질량")]
            rows_tb = []
            for col, name in metrics_topbot:
                if col not in growth_df.columns:
                    continue
                tm, bm = group_mean(col)
                if tm is None or bm is None or bm == 0:
                    continue
                rows_tb.append({"지표": name, "상위 25% 평균": tm, "하위 25% 평균": bm, "배율(하위→상위)": tm / bm})

            if rows_tb:
                st.markdown('<div class="kpi-card"><h3 style="margin-top:0;">📊 상위 25% vs 하위 25% 그룹 비교</h3></div>', unsafe_allow_html=True)
                st.dataframe(pd.DataFrame(rows_tb), width="stretch", hide_index=True)

                figtb = px.bar(pd.DataFrame(rows_tb), x="지표", y=["상위 25% 평균", "하위 25% 평균"],
                               barmode="group", title="상위 25% vs 하위 25% 그룹 평균 비교",
                               color_discrete_map={"상위 25% 평균": "#FF7B00", "하위 25% 평균": "#B0B0B0"})
                figtb.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"))
                st.plotly_chart(figtb, width="stretch")
                st.markdown("<p class=\"ts-line\">이 그래프 읽는 법: 주황 막대가 상위 25%, 회색 막대가 하위 25%예요. 잎 수·지상부 길이·질량 모두 상위 그룹이 높으면 생중량 차이와의 관련성을 보여줘요.</p>", unsafe_allow_html=True)

            if r_leaf is not None and r_shoot is not None:
                stronger_note = "잎 수가 지상부 길이보다 생중량과 더 강한 상관을 보였으므로" if abs(r_leaf) > abs(r_shoot) else "지상부 길이가 잎 수보다 생중량과 더 강한 상관을 보였으므로"
                verdict_word = "지지됨" if abs(r_leaf) > abs(r_shoot) else "지지되지 않음"
                st.markdown(f"""
<div class="conclusion-box">
<b>📊 판정: 가설 1 — {verdict_word} ✅</b><br>
 근거: 잎 수 r = {r_leaf:.3f}, 지상부 길이 r = {r_shoot:.3f} → {stronger_note} 가설 1이 {verdict_word}.<br>
 ⚠️ 상관관계일 뿐 <b>원인</b>을 뜻하지는 않아요. 잎 수가 많아서 무게가 큰지, 무게가 커서 잎이 많은지는 이 자료만으로 단정할 수 없어요.
</div>
""", unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")

# ===================================================================
# TAB 3 — 가설 2
# ===================================================================
with tabs[2]:
    try:
        st.markdown("""
<div class="hypothesis-box">
<b>🌱 가설 2 — 숨은 차이는 땅속에</b><br>
개체 간 상대적 질량 변이(변동계수, CV)는 지상부보다 **지하부**에서 더 크게 나타날 것이다.
(이번 표본에서 <b>지지됨 / 지지되지 않음</b>으로 표현. 분산·표준편차는 표본 기준 n−1 사용)
</div>
""", unsafe_allow_html=True)

        has_smass = "지상부 질량" in growth_df.columns if (growth_df is not None and not growth_df.empty) else False
        has_rmass = "지하부 질량" in growth_df.columns if (growth_df is not None and not growth_df.empty) else False

        if not has_smass or not has_rmass or growth_df is None or growth_df.empty:
            st.info("가설 2를 확인하려면 생육 CSV에 **지상부 질량 · 지하부 질량**이 있어야 해요.")
        else:
            shoot = growth_df["지상부 질량"].dropna()
            root = growth_df["지하부 질량"].dropna()
            m_shoot = shoot.mean()
            m_root = root.mean()
            sd_shoot = shoot.std(ddof=1)
            sd_root = root.std(ddof=1)
            var_shoot = shoot.var(ddof=1)
            var_root = root.var(ddof=1)
            cv_shoot = (sd_shoot / m_shoot * 100) if m_shoot > 0 and len(shoot) >= 3 else None
            cv_root = (sd_root / m_root * 100) if m_root > 0 and len(root) >= 3 else None

            if cv_shoot is None or cv_root is None:
                st.info("평균이 0 이하인 열이 있거나 유효 값이 3개 미만이라 CV를 계산할 수 없어요.")
            else:
                diff_cv = cv_root - cv_shoot
                ratio_cv = cv_root / cv_shoot if cv_shoot > 0 else None

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("지상부 CV", f"{cv_shoot:.2f}%")
                c2.metric("지하부 CV", f"{cv_root:.2f}%")
                c3.metric("차이 (%p)", f"{diff_cv:+.2f}%p")
                c4.metric("CV 비율 (지하부÷지상부)", f"{ratio_cv:.2f}배" if ratio_cv is not None else "—")

                figcv = px.bar(pd.DataFrame({"부분": ["지상부 질량", "지하부 질량"], "CV (%)": [cv_shoot, cv_root]}),
                               x="부분", y="CV (%)", color="부분", color_discrete_map={"지상부 질량": "#2196F3", "지하부 질량": "#795548"},
                               title="지상부·지하부 질량 변동계수(CV) 비교")
                figcv.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"))
                st.plotly_chart(figcv, width="stretch")
                st.markdown("<p class=\"ts-line\">이 그래프 읽는 법: CV가 클수록 '평균에 비해' 값이 들쭉날쭉하다는 뜻이에요. 지하부 CV 막대가 더 높으면 가설 2 방향이에요.</p>", unsafe_allow_html=True)

                rows_t = []
                for label, m, sd, var, cv in [("지상부 질량", m_shoot, sd_shoot, var_shoot, cv_shoot),
                                                ("지하부 질량", m_root, sd_root, var_root, cv_root)]:
                    rows_t.append({"부분": label, "평균 (g)": m, "표준편차 (g)": sd, "분산 (g²)": var, "CV (%)": cv})
                st.dataframe(pd.DataFrame(rows_t), width="stretch", hide_index=True)

                figbx = make_subplots(rows=1, cols=2, subplot_titles=("지상부 질량 분포", "지하부 질량 분포"), horizontal_spacing=0.15)
                figbx.add_trace(go.Box(y=shoot, name="지상부 질량", fillcolor="#2196F3", line=dict(color="#1565C0")), row=1, col=1)
                figbx.add_trace(go.Box(y=root, name="지하부 질량", fillcolor="#795548", line=dict(color="#5D4037")), row=1, col=2)
                figbx.update_yaxes(title_text="질량 (g)", row=1, col=1)
                figbx.update_yaxes(title_text="질량 (g)", row=1, col=2)
                figbx.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"), height=360)
                st.plotly_chart(figbx, width="stretch")
                st.markdown("<p class=\"ts-line\">이 그래프 읽는 법: 상자그림의 상자 높이는 중앙 50% 범위, 중앙선은 중앙값, 수염은 극단값을 제외한 범위예요.</p>", unsafe_allow_html=True)

                st.markdown(f"""
<div class="note-box">
<b>📌 주의: 평균 크기가 다른 두 부분을 비교할 때</b><br>
분산(절대적인 흩어짐, g²)은 평균 자체가 큰 지상부가 더 클 수 있어요.
그래서 이번 비교는 <b>평균에 '비한' 퍼짐</b>인 변동계수(CV)로 판단해요.<br>
현재 계산값: 지상부 평균 {m_shoot:.2f} g vs 지하부 평균 {m_root:.2f} g → 평균은 지상부가 더 크지만,
<b>CV</b>가 더 큰 쪽이 '상대적 차이'가 더 큰 쪽이에요.
</div>
""", unsafe_allow_html=True)

                has_zero_mask = growth_df["지하부 질량"] == 0
                zero_count = int(has_zero_mask.sum())
                if zero_count > 0:
                    zero_ids = growth_df.loc[has_zero_mask, "개체번호"].tolist()
                    st.markdown(f"""
<div class="warn-box">
<b>🔎 지하부 질량이 0 g인 개체 확인</b><br>
 지하부 질량 0 g 개체 수: <b>{zero_count}개체</b><br>
 해당 개체번호: {', '.join(str(i) for i in zero_ids)}<br>
 (측정 한계로 실제 질량 0일 수도 있고, 센서/기록 문제일 수도 있어요.)
</div>
""", unsafe_allow_html=True)
                    if st.checkbox("0 g 개체를 제외하고 CV를 다시 계산해 보기", value=False):
                        root_no0 = root[root > 0]
                        if len(root_no0) >= 3 and root_no0.mean() > 0:
                            cv_root_no0 = root_no0.std(ddof=1) / root_no0.mean() * 100
                            direction = "유지됨 ✅" if cv_root_no0 > cv_shoot else "바뀜 ⚠️"
                            st.metric("지하부 CV (0 g 제외 후)", f"{cv_root_no0:.2f}%")
                            verdict_dir = "지지" if cv_root_no0 > cv_shoot else "반전"
                            st.markdown(f"""
<div class="conclusion-box">
<b>📊 0 g 제외 후 방향 유지 여부</b><br>
 지상부 CV = {cv_shoot:.2f}%, 지하부 CV (0 g 제외) = {cv_root_no0:.2f}% → 가설 2 방향({verdict_dir}) = <b>{direction}</b>
</div>
""", unsafe_allow_html=True)
                        else:
                            st.info("0 g을 제외한 뒤에도 지하부 유효 값이 3개 미만이거나 평균이 0 이하라 CV를 다시 구할 수 없어요.")

                if cv_root > cv_shoot:
                    st.markdown(f"""
<div class="conclusion-box">
<b>📊 판정: 가설 2 — 지지됨 ✅</b><br>
 근거: 지상부 CV = {cv_shoot:.2f}%, 지하부 CV = {cv_root:.2f}% → 지하부 CV가 {diff_cv:.2f}%p 더 크고, CV 비율은 {ratio_cv:.2f}배예요.<br>
 '평균 대비 상대적 퍼짐' 기준으로 보면 땅속(지하부) 쪽 개체 차이가 더 크게 나타났어요.
</div>
""", unsafe_allow_html=True)
                else:
                    st.markdown(f"""
<div class="conclusion-box">
<b>📊 판정: 가설 2 — 지지되지 않음 ⚠️</b><br>
 근거: 지상부 CV = {cv_shoot:.2f}%, 지하부 CV = {cv_root:.2f}% → 이번 표본에서는 지상부 CV가 더 컸어요 (차이 {diff_cv:.2f}%p).<br>
 가설 2 방향은 '지하부 CV가 더 크다'였는데, 실제는 반대였거나 비슷했어요. 표본 조건(측정 범위, 개체 수)이 달라지면 결과가 달라질 수 있어요.
</div>
""", unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")

# ===================================================================
# TAB 4 — 개체별 비교
# ===================================================================
with tabs[3]:
    try:
        if growth_df is None or growth_df.empty:
            st.info("생육 CSV를 올려주세요. 사이드바에서 파일을 선택하면 이 탭이 채워져요.")
        else:
            has_w = "생중량" in growth_df.columns
            w = growth_df["생중량"].dropna() if has_w else pd.Series(dtype=float)

            if has_w and len(w) >= 2:
                mean_w = w.mean()
                med_w = w.median()
                std_w = w.std(ddof=1)
                cv_w = (std_w / mean_w * 100) if mean_w > 0 else None
                figh = px.histogram(w, nbins="sturges", title="생중량 분포 (히스토그램)")
                figh.add_vline(x=mean_w, line_dash="dash", line_color="#2196F3", annotation_text=f"평균 {mean_w:.2f} g")
                figh.add_vline(x=med_w, line_dash="dot", line_color="#FF9800", annotation_text=f"중앙값 {med_w:.2f} g")
                figh.update_yaxes(title_text="개체 수")
                figh.update_xaxes(title_text="생중량 (g)")
                figh.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"))
                st.plotly_chart(figh, width="stretch")
                st.markdown("<p class=\"ts-line\">이 그래프 읽는 법: 막대 높이가 그 구간(생중량 범위)에 속하는 개체 수예요. 파란색 점선(평균)과 주황색 점선(중앙값) 위치를 비교해 보세요.</p>", unsafe_allow_html=True)

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("평균 생중량", f"{mean_w:.2f} g")
                c2.metric("중앙값 생중량", f"{med_w:.2f} g")
                c3.metric("표준편차", f"{std_w:.2f} g")
                c4.metric("CV", f"{cv_w:.1f}%" if cv_w is not None else "—")
                st.caption("※ CV는 표준편차 ÷ 평균 × 100이에요. 평균이 다른 것끼리 상대적 퍼짐을 비교할 때 써요.")

            order_items = []
            if "지상부 길이" in growth_df.columns:
                order_items.append("지상부 길이")
            if "잎 수" in growth_df.columns:
                order_items.append("잎 수")
            if "지하부 길이" in growth_df.columns:
                order_items.append("지하부 길이")
            if "지상부 질량" in growth_df.columns:
                order_items.append("지상부 질량")
            if "지하부 질량" in growth_df.columns:
                order_items.append("지하부 질량")
            if "생중량" in growth_df.columns:
                order_items.append("생중량")
            if not order_items:
                st.info("개체별 비교에 쓸 숫자 열이 없어요.")
            else:
                sel = st.selectbox("📊 개체별 막대그래프의 측정 항목 선택", order_items)
                if sel in growth_df.columns:
                    gv = growth_df.groupby("개체번호")[sel].mean().reset_index()
                    gv = gv.sort_values(sel, ascending=False).reset_index(drop=True)
                    n = len(gv)
                    top_mask = gv.index < min(5, n)
                    bot_mask = gv.index >= max(0, n - 5)
                    colors = []
                    for i in range(n):
                        if top_mask.iloc[i]:
                            colors.append("#FF7B00")
                        elif bot_mask.iloc[i]:
                            colors.append("#FF4B4B")
                        else:
                            colors.append("#B0B0B0")
                    figb = px.bar(gv, x="개체번호", y=sel, title=f"개체별 {sel} (큰 순서, 상위 5 주황·하위 5 빨강 강조)")
                    figb.update_traces(marker_color=colors, marker_line_width=0.4)
                    figb.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"))
                    st.plotly_chart(figb, width="stretch")
                    st.markdown("<p class=\"ts-line\">이 그래프 읽는 법: 왼쪽이 가장 큰 개체, 오른쪽이 가장 작은 개체예요. 주황은 상위 5, 빨강은 하위 5예요. 개체번호는 숫자로 표시될 수도 있고 A1, A2처럼 글자로 표시될 수도 있어요.</p>", unsafe_allow_html=True)

            num_cols = [c for c in growth_df.columns if pd.api.types.is_numeric_dtype(growth_df[c]) and c != "개체번호"]
            if len(num_cols) >= 2:
                corr = growth_df[num_cols].corr()
                heat_colors = [[0, "#FF4B4B"], [0.5, "#FFFFFF"], [1, "#4CAF50"]]
                figh2 = px.imshow(corr, text_auto=".2f", color_continuous_scale=heat_colors, title="생육 변수 상관계수 히트맵 (개체번호 제외)")
                figh2.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"))
                st.plotly_chart(figh2, width="stretch")
                st.markdown("<p class=\"ts-line\">이 그래프 읽는 법: 1에 가까울수록 진한 초록(같이 증가), −1에 가까울수록 진한 빨강(하나 증가하면 다른 하나 감소), 0에 가까우면 흰색이에요.</p>", unsafe_allow_html=True)
            else:
                st.info("상관계수 히트맵을 그리려면 숫자 열이 2개 이상 필요해요.")

            with st.expander("🌱 생육 데이터 원본 및 CSV 다운로드"):
                st.dataframe(growth_df, width="stretch")
                csv_bytes = growth_df.to_csv(index=False).encode("utf-8-sig")
                fname = growth_file.name if growth_file is not None else "growth.csv"
                st.download_button("📥 생육 CSV 다운로드", csv_bytes, file_name=fname, mime="text/csv")

            st.markdown('<div class="kpi-card"><h3 style="margin-top:0;">🔍 생육 데이터 점검 (열별 유효·빈 값)</h3></div>', unsafe_allow_html=True)
            rows = []
            for col in growth_df.columns:
                s = growth_df[col]
                if pd.api.types.is_numeric_dtype(s):
                    valid = int(s.notna().sum())
                else:
                    valid = int(s.astype(str).str.strip().ne("").sum())
                na = len(growth_df) - valid
                rows.append({"열": col, "유효 개수": valid, "빈 값 개수": na})
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")

# ===================================================================
# TAB 5 — 환경 데이터
# ===================================================================
with tabs[4]:
    try:
        st.markdown("""
<div class="note-box">
<b>🌡️ 환경 데이터 안내</b><br>
온도·습도·pH·EC 같은 환경은 <b>같은 스마트팜에 있는 모든 개체가 함께 겪은 배경</b>예요.
그래서 환경 변화 자체가 '개체 차이의 직접 원인'이라고 바로 연결하지는 않아요.
(개체 차이는 개체별 위치·뿌리 상태·유전자 등 여러 요인이 함께 작용할 수 있어요.)
이 탭은 <b>실험 기간 동안 환경이 어떻게 변했는지</b>를 확인하는 용도로 봐 주세요.
</div>
""", unsafe_allow_html=True)

        if env_df is None or env_df.empty:
            st.info("환경 CSV를 아직 업로드하지 않았어요. 사이드바에서 환경 데이터 CSV를 올려주세요.")
        else:
            env_cols = get_cols(env_df, ["temperature", "humidity", "ph", "ec", "water_temp", "co2"])

            if "time" in env_df.columns and env_cols:
                env2 = env_df.copy()
                env2["date"] = env2["time"].dt.date
                daily = env_df.groupby(env2["date"])[env_cols].mean().reset_index()
                daily["date"] = pd.to_datetime(daily["date"])

                n_plots = len(env_cols)
                fig_env_daily = make_subplots(rows=1, cols=n_plots, subplot_titles=env_cols, horizontal_spacing=0.08)
                for j, c in enumerate(env_cols, start=1):
                    fig_env_daily.add_trace(go.Scatter(x=daily["date"], y=daily[c], mode="lines+markers", name=c,
                                                       line=dict(color="#1565C0", width=1.6),
                                                       marker=dict(size=3, color="#1565C0")), row=1, col=j)
                    fig_env_daily.update_xaxes(title_text="", row=1, col=j, showticklabels=False)
                    fig_env_daily.update_yaxes(title_text=c, row=1, col=j)
                fig_env_daily.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"), height=240,
                                            showlegend=False, margin=dict(t=30, b=30, l=30, r=10))
                st.plotly_chart(fig_env_daily, width="stretch")
                st.markdown("<p class=\"ts-line\">이 그래프 읽는 법: 각 작은 그래프가 환경 항목 하나씩이에요. 위로 올라가면 그날 평균이 높아진 것, 아래로 내려가면 낮아진 거예요.</p>", unsafe_allow_html=True)

            if env_cols:
                sel_env = st.selectbox("📊 날짜별 꺾은선으로 볼 환경 항목", env_cols, index=0 if "temperature" in env_cols else 0)
                if "time" in env_df.columns:
                    env2 = env_df.copy()
                    env2["date"] = env2["time"].dt.date
                    grp = env_df.groupby(env2["date"])[sel_env]
                    agg = pd.DataFrame({"평균": grp.mean(), "최고": grp.max()}).reset_index()
                    agg["date"] = pd.to_datetime(agg["date"])

                    fig_t = go.Figure()
                    fig_t.add_trace(go.Scatter(x=agg["date"], y=agg["평균"], mode="lines+markers", name=f"{sel_env} 평균",
                                                line=dict(color="#2196F3", width=2), marker=dict(size=5)))
                    fig_t.add_trace(go.Scatter(x=agg["date"], y=agg["최고"], mode="lines", name=f"{sel_env} 최고",
                                                line=dict(color="#FF9800", width=1.4, dash="dot")))
                    if sel_env == "temperature":
                        hi = env_df[sel_env].dropna()
                        if (hi >= 30).any():
                            hi30 = hi[hi >= 30]
                            n30 = len(hi30)
                            total = len(hi)
                            pct30 = n30 / total * 100 if total > 0 else 0
                            fig_t.add_hline(y=30, line_dash="dash", line_color="#E91E63", annotation_text="30 °C (탐색용 기준)")
                            dates30 = sorted(set(str(d.date()) for d in hi30.index.to_series().dt.date))
                            st.markdown(f"""
<div class="warn-box">
<b>🌡️ 온도 30 °C 이상 기록 (탐색용 기준, 피해 기준 아님)</b><br>
 30 °C 이상 기록 수: <b>{n30}건</b> / 전체 {total}건 → 비율 <b>{pct30:.1f}%</b><br>
 해당 날짜: {', '.join(dates30)}
</div>
""", unsafe_allow_html=True)
                            st.caption("※ 30 °C는 이 실험에서 '높은 온도 구간'을 살펴보기 위한 탐색용 기준일 뿐, 극지식물에 피해가 발생하는 온도 기준과는 달라요.")
                    fig_t.update_layout(xaxis_title="날짜", yaxis_title=sel_env, font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"))
                    st.plotly_chart(fig_t, width="stretch")
                    st.markdown("<p class=\"ts-line\">이 그래프 읽는 법: 파란 선이 날짜별 평균, 주황 점선이 그 날짜 중 최고값이에요. 온도가 30 °C를 넘는 날은 분홍 점선으로 표시했어요(있는 경우).</p>", unsafe_allow_html=True)

            if "time" in env_df.columns and env_cols:
                hc = st.selectbox("📅 날짜×시각 히트맵 항목", env_cols, index=0)
                hm = env_df.pivot_table(index=env_df["time"].dt.date, columns=env_df["time"].dt.hour, values=hc, aggfunc="mean")
                hm.index = pd.to_datetime(hm.index)
                fig_hm = px.imshow(hm, text_auto=".1f", color_continuous_scale="Viridis", title=f"{hc} 날짜×시각 히트맵 (빈 칸 = 센서 기록 없음)")
                fig_hm.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"))
                st.plotly_chart(fig_hm, width="stretch")
                st.markdown("<p class=\"ts-line\">이 그래프 읽는 법: 세로축이 날짜, 가로축이 시각(0~23시), 색이 진할수록 값이 큰 거예요. 빈 칸(하얀색)은 그 시각에 센서 기록이 없는 거예요.</p>", unsafe_allow_html=True)

            if env_cols:
                rows = []
                for c in env_cols:
                    s = env_df[c].dropna()
                    rows.append({"열": c, "유효 개수": int(s.count()), "평균": s.mean(), "표준편차": s.std(ddof=1) if len(s) >= 2 else 0,
                                 "최소": s.min(), "최대": s.max()})
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

            with st.expander("🌡️ 환경 데이터 원본 및 CSV 다운로드"):
                disp = ["time"] + env_cols
                st.dataframe(env_df[disp], width="stretch")
                csv_bytes = env_df[disp].to_csv(index=False).encode("utf-8-sig")
                fname = env_file.name if env_file is not None else "environment.csv"
                st.download_button("📥 환경 CSV 다운로드", csv_bytes, file_name=fname, mime="text/csv")

            st.markdown('<div class="kpi-card"><h3 style="margin-top:0;">🔍 환경 데이터 점검 (열별 유효·빈 값)</h3></div>', unsafe_allow_html=True)
            rows = []
            for col in env_df.columns:
                s = env_df[col]
                if pd.api.types.is_numeric_dtype(s):
                    valid = int(s.notna().sum())
                else:
                    valid = int(s.astype(str).str.strip().ne("").sum())
                na = len(env_df) - valid
                rows.append({"열": col, "유효 개수": valid, "빈 값 개수": na})
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")
