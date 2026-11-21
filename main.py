import io
import os

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# ---------------- 기본 설정 ----------------
st.set_page_config(page_title="극지식물 생육 차이 분석", page_icon="🌱", layout="wide")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
html, body, [class*="css"] {
   font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif;
}
.hero {background: linear-gradient(120deg, #EEE9FB 0%, #E3F4EC 100%); border-radius: 16px;
       padding: 22px 26px; margin-bottom: 8px;}
.hero h1 {font-size: 1.9rem; margin: 0 0 6px 0; color: #3B2E7E;}
.hero p {margin: 0; color: #555;}
.note {background: #F7F5FD; border-left: 4px solid #7B5CD6; border-radius: 8px; padding: 10px 14px; margin: 6px 0 2px 0;}
div[data-testid="stMetric"] {background: #FAFAFE; border-radius: 12px;}
</style>
""", unsafe_allow_html=True)

FONT = "Malgun Gothic, Apple SD Gothic Neo, Noto Sans KR, sans-serif"
PURPLE, ORANGE, BLUE, GREEN, BROWN = "#7B5CD6", "#E4572E", "#2E86AB", "#7FB069", "#A0522D"
GROWTH_COLS = ["잎 수", "지상부 길이", "지하부 길이", "생중량", "지상부 질량", "지하부 질량"]
UNIT = {"잎 수": "장", "지상부 길이": "mm", "지하부 길이": "mm", "생중량": "g", "지상부 질량": "g", "지하부 질량": "g"}
ENV_COLS = ["temperature", "humidity", "ph", "ec"]
ENV_NAME = {"temperature": "온도", "humidity": "습도", "ph": "pH", "ec": "EC"}
ENV_SCALE = {"temperature": "YlOrRd", "humidity": "Blues", "ph": "Purples", "ec": "Greens"}
HOT = 30


# ---------------- 데이터 읽기 ----------------
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


@st.cache_data
def load_csv(data):
    # 업로드 파일의 바이트를 utf-8-sig → cp949 순서로 읽고 바로 열 이름 표준화
    for enc in ("utf-8-sig", "cp949"):
        try:
            return std_cols(pd.read_csv(io.BytesIO(data), encoding=enc))
        except Exception:
            pass
    return pd.DataFrame()


def read_csv(file):
    if file is None:
        return pd.DataFrame()
    return load_csv(file.getvalue())


def school_name(file):
    # '송도고_환경데이터.csv' → '송도고'
    if file is None:
        return ""
    stem = os.path.splitext(os.path.basename(file.name))[0]
    return stem.split("_")[0].strip()


# ---------------- 도우미 함수 ----------------
def has(df, col):
    return (not df.empty) and col in df.columns and pd.api.types.is_numeric_dtype(df[col])


def label(col):
    unit = UNIT.get(col)
    return f"{col}({unit})" if unit else ENV_NAME.get(col, col)


def style(fig, title="", height=420):
    fig.update_layout(title=dict(text=title, font=dict(size=16)), height=height, font=dict(family=FONT),
                      margin=dict(l=40, r=20, t=60, b=40), template="plotly_white")
    return fig


def note(text):
    st.markdown(f'<div class="note">{text}</div>', unsafe_allow_html=True)


def id_text(s):
    # 개체번호를 56.0이 아니라 56, A1처럼 원래 모양으로 표시
    out = []
    for v in s:
        if isinstance(v, float) and not pd.isna(v) and v.is_integer():
            out.append(str(int(v)))
        else:
            out.append(str(v))
    return out


def corr_r(df, x, y):
    d = df[[x, y]].dropna()
    if len(d) < 2 or d[x].nunique() < 2 or d[y].nunique() < 2:
        return None
    return d[x].corr(d[y])


def add_scatter(fig, df, x, y, row=None, col=None):
    # 점 + np.polyfit 추세선 (빈 값 제거, 2개 미만이면 건너뜀)
    d = df[[x, y]].dropna()
    if len(d) < 2 or d[x].nunique() < 2:
        return None
    slope, intercept = np.polyfit(d[x], d[y], 1)
    kw = dict(row=row, col=col) if row else {}
    fig.add_trace(go.Scatter(x=d[x], y=d[y], mode="markers", marker=dict(size=8, color=PURPLE, opacity=0.65),
                             showlegend=False, hovertemplate=f"{x}: %{{x}}<br>{y}: %{{y}}<extra></extra>"), **kw)
    xs = np.linspace(d[x].min(), d[x].max(), 50)
    fig.add_trace(go.Scatter(x=xs, y=slope * xs + intercept, mode="lines", line=dict(color=ORANGE, width=2.5),
                             showlegend=False, hoverinfo="skip"), **kw)
    return d[x].corr(d[y])


def cv(s):
    v = s.dropna()
    if len(v) < 2 or v.mean() <= 0:
        return None
    return v.std() / v.mean() * 100


def csv_button(df, name, key):
    st.download_button("📥 CSV로 내려받기", df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=name, mime="text/csv", key=key)


# ---------------- 사이드바: 업로드는 여기서 딱 한 번 ----------------
st.sidebar.header("📁 데이터 업로드")
env_file = st.sidebar.file_uploader("환경 CSV", type="csv")
growth_file = st.sidebar.file_uploader("생육 CSV", type="csv")

with st.spinner("데이터를 불러오는 중..."):
    env_df = read_csv(env_file)
    growth_df = read_csv(growth_file)

school = school_name(growth_file) or school_name(env_file) or "우리 학교"
g_cols = [c for c in GROWTH_COLS if has(growth_df, c)]
e_cols = [c for c in ENV_COLS if has(env_df, c)]
has_time = (not env_df.empty) and "time" in env_df.columns and env_df["time"].notna().sum() >= 2

st.sidebar.header("🔎 생육 측정 항목")
if g_cols:
    default = g_cols.index("잎 수") if "잎 수" in g_cols else 0
    measure = st.sidebar.selectbox("개체별로 비교할 항목", g_cols, index=default, format_func=label)
else:
    measure = None
    st.sidebar.info("생육 CSV를 올리면 항목을 고를 수 있어요.")
st.sidebar.caption("파일 이름 앞부분(예: 송도고_생육결과데이터.csv → 송도고)이 학교명으로 표시돼요.")

st.markdown(f'<div class="hero"><h1>🌱 {school} 극지식물 개체별 생육 차이 분석 대시보드</h1>'
            '<p>같은 스마트팜에서 키운 극지식물끼리 무엇이 얼마나 다른지 살펴봅니다. '
            '개체번호는 이름표라서 분석에서 뺐어요.</p></div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["🔬 실험 소개", "🌡️ 환경 데이터", "🌱 생육 결과"])

# ---------------- 탭1: 실험 소개 ----------------
with tab1:
    try:
        left, right = st.columns([1.1, 1])
        with left:
            st.subheader("우리가 궁금했던 것")
            st.markdown("1. **잎 수**와 **지상부 길이** 중에 생중량이랑 더 관련 있는 건 뭘까?\n"
                        "2. **지상부**와 **지하부** 중에 개체끼리 질량 차이가 더 큰 쪽은 어디일까?")
        with right:
            st.subheader("데이터로 본 답")
            lines = []
            r_leaf = corr_r(growth_df, "잎 수", "생중량") if {"잎 수", "생중량"} <= set(g_cols) else None
            r_len = corr_r(growth_df, "지상부 길이", "생중량") if {"지상부 길이", "생중량"} <= set(g_cols) else None
            if r_leaf is not None and r_len is not None:
                win = "잎 수" if abs(r_leaf) > abs(r_len) else "지상부 길이"
                lines.append(f"① 생중량과 더 관련 있는 건 <b>{win}</b> (r = {r_leaf:.2f} vs {r_len:.2f})")
            cv_up = cv(growth_df["지상부 질량"]) if "지상부 질량" in g_cols else None
            cv_dn = cv(growth_df["지하부 질량"]) if "지하부 질량" in g_cols else None
            if cv_up is not None and cv_dn is not None:
                win = "지하부" if cv_dn > cv_up else "지상부"
                lines.append(f"② 개체끼리 차이가 더 큰 쪽은 <b>{win}</b> (변동계수 지하부 {cv_dn:.0f}% vs 지상부 {cv_up:.0f}%)")
            if lines:
                note("<br>".join(lines))
            else:
                st.info("생육 CSV를 올리면 여기에 답이 자동으로 정리돼요.")

        st.subheader("핵심 숫자")
        if growth_df.empty and env_df.empty:
            st.info("👈 왼쪽에서 환경 CSV와 생육 CSV를 올려 주세요. 하나만 올려도 그 부분은 바로 보여요.")
        else:
            c1, c2, c3 = st.columns(3)
            if not growth_df.empty:
                c1.metric("🌿 개체 수", f"{len(growth_df)}개", border=True)
            if has(growth_df, "생중량") and growth_df["생중량"].dropna().size > 0:
                w = growth_df["생중량"].dropna()
                c2.metric("⚖️ 평균 생중량", f"{w.mean():.2f} g", border=True)
                c3.metric("📏 생중량 범위 (g)", f"{w.min():.2f} ~ {w.max():.2f}", border=True)
            d1, d2, d3 = st.columns(3)
            if has(env_df, "temperature") and env_df["temperature"].dropna().size > 0:
                d1.metric("🌡️ 평균 온도", f"{env_df['temperature'].dropna().mean():.1f}", border=True)
            if not env_df.empty:
                d2.metric("🗂️ 환경 기록 수", f"{len(env_df):,}건", border=True)
                if has_time:
                    t = env_df["time"].dropna()
                    d3.metric("📅 기록 기간", f"{t.min():%m.%d} ~ {t.max():%m.%d}", border=True)
            if growth_df.empty:
                st.info("생육 CSV를 올리면 개체 수·생중량 카드가 보여요.")
            if env_df.empty:
                st.info("환경 CSV를 올리면 환경 기록 카드가 보여요.")
        with st.expander("📘 통계 용어 짧은 설명"):
            st.markdown(
                "- **평균**: 값을 모두 더해서 개수로 나눈 값 (전체적인 크기)\n"
                "- **중앙값**: 줄 세웠을 때 딱 가운데 값 (아주 큰 값 몇 개에 덜 흔들림)\n"
                "- **표준편차**: 값들이 평균에서 얼마나 흩어져 있는지\n"
                "- **변동계수(CV)**: 표준편차 ÷ 평균 × 100. 평균 크기가 다른 것끼리 흩어진 정도를 공평하게 비교\n"
                "- **상관계수(r)**: -1 ~ 1. 1에 가까울수록 '하나가 크면 다른 것도 크다'는 관계가 강함 (원인이라는 뜻은 아님)\n"
                "- **추세선**: 점들 사이를 가장 잘 지나가는 직선")
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")

# ---------------- 탭2: 환경 데이터 ----------------
with tab2:
    try:
        if env_df.empty:
            st.info("👈 환경 CSV를 올려 주세요.")
        elif not e_cols:
            st.info("온도·습도·pH·EC 중에 알아볼 수 있는 열이 없어요. 열 이름을 확인해 주세요.")
        else:
            note("환경 데이터는 모든 개체가 함께 겪은 <b>재배 환경</b>이에요. 개체끼리 차이의 원인으로 바로 연결하지는 않아요.")
            if not has_time:
                st.info("시간 열을 찾지 못해서 날짜별 그래프는 건너뛰었어요. 아래 요약 표는 볼 수 있어요.")
            else:
                env_t = env_df.dropna(subset=["time"]).copy()
                env_t["날짜"] = env_t["time"].dt.date
                env_t["시각"] = env_t["time"].dt.hour

                # (1) 네 항목 한눈에 보기
                st.subheader("① 환경 항목 한눈에 보기 (일별 평균)")
                n = len(e_cols)
                fig = make_subplots(rows=(n + 1) // 2, cols=2 if n > 1 else 1,
                                    subplot_titles=[ENV_NAME[c] for c in e_cols], vertical_spacing=0.16)
                colors = [ORANGE, BLUE, PURPLE, GREEN]
                for i, c in enumerate(e_cols):
                    daily = env_t.groupby("날짜")[c].mean().dropna()
                    if len(daily) >= 2:
                        fig.add_trace(go.Scatter(x=daily.index, y=daily.values, mode="lines", name=ENV_NAME[c],
                                                 line=dict(color=colors[i % 4], width=2), showlegend=False),
                                      row=i // 2 + 1, col=i % 2 + 1)
                style(fig, "", height=260 * ((n + 1) // 2))
                st.plotly_chart(fig, width="stretch")

                # (2) 고른 항목 자세히: 꺾은선 + 히트맵
                st.subheader("② 항목 하나 자세히 보기")
                var = st.selectbox("볼 항목", e_cols, format_func=lambda c: ENV_NAME.get(c, c))
                d = env_t[["time", "날짜", "시각", var]].dropna()
                if len(d) < 2:
                    st.info(f"{ENV_NAME[var]} 값이 2개 미만이라 그래프를 건너뛰었어요.")
                else:
                    daily = d.groupby("날짜")[var].agg(["mean", "max"]).reset_index()
                    fig = go.Figure()
                    if var == "temperature":
                        fig.add_hrect(y0=HOT, y1=max(HOT + 1, d[var].max() + 0.5), fillcolor=ORANGE,
                                      opacity=0.08, line_width=0, annotation_text=f"{HOT} 이상 구간")
                    fig.add_trace(go.Scatter(x=daily["날짜"], y=daily["max"], mode="lines", name="일별 최고",
                                             line=dict(color=ORANGE, dash="dot")))
                    fig.add_trace(go.Scatter(x=daily["날짜"], y=daily["mean"], mode="lines+markers", name="일별 평균",
                                             line=dict(color=PURPLE, width=2.5), marker=dict(size=4)))
                    style(fig, f"날짜별 {ENV_NAME[var]} (평균·최고)")
                    fig.update_layout(xaxis_title="날짜", yaxis_title=ENV_NAME[var],
                                      legend=dict(orientation="h", y=1.08, x=1, xanchor="right"))
                    st.plotly_chart(fig, width="stretch")
                    if var == "temperature":
                        hot = d[d[var] >= HOT]
                        if len(hot) > 0:
                            days = ", ".join(sorted({f"{x:%m/%d}" for x in hot["time"]}))
                            note(f"🔥 <b>{HOT} 이상 기록 {len(hot)}건</b> ({len(hot) / len(d) * 100:.1f}%) → {days}")
                        else:
                            note(f"{HOT} 이상인 기록은 없었어요.")

                    pivot = d.pivot_table(index="시각", columns="날짜", values=var, aggfunc="mean")
                    if pivot.shape[0] >= 2 and pivot.shape[1] >= 2:
                        fig = px.imshow(pivot, aspect="auto", color_continuous_scale=ENV_SCALE.get(var, "Viridis"),
                                        labels=dict(x="날짜", y="시각(시)", color=ENV_NAME[var]))
                        style(fig, f"날짜 × 시각 {ENV_NAME[var]} 히트맵 (흰 칸 = 센서 기록 없음)", height=420)
                        fig.update_yaxes(autorange="reversed", dtick=3)
                        st.plotly_chart(fig, width="stretch")
                        st.caption("세로로 진한 띠가 보이면 그 날짜에는 하루 종일 값이 높았다는 뜻이에요. 일별 평균은 남은 기록의 단순 평균이에요.")

            # (3) 요약 표
            st.subheader("③ 환경 데이터 요약 표")
            rows = []
            for c in e_cols:
                v = env_df[c].dropna()
                if len(v) > 0:
                    rows.append({"항목": ENV_NAME[c], "유효 개수": len(v), "평균": round(v.mean(), 2),
                                 "표준편차": round(v.std(), 2) if len(v) > 1 else None,
                                 "최소": round(v.min(), 2), "최대": round(v.max(), 2)})
            if rows:
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            else:
                st.info("요약할 값이 없어요.")
            csv_button(env_df, f"{school}_환경데이터_정리.csv", "env_dl")
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")

# ---------------- 탭3: 생육 결과 ----------------
with tab3:
    try:
        if growth_df.empty:
            st.info("👈 생육 CSV를 올려 주세요.")
        elif not g_cols:
            st.info("잎 수·길이·질량 중에 알아볼 수 있는 열이 없어요. 열 이름을 확인해 주세요.")
        else:
            # ① 잎 수 vs 지상부 길이
            st.subheader("① 잎 수와 지상부 길이 중 생중량과 더 관련 있는 건?")
            pair = [c for c in ["잎 수", "지상부 길이"] if c in g_cols]
            if "생중량" in g_cols and pair:
                rs = {}
                for c in pair:
                    rs[c] = corr_r(growth_df, c, "생중량")
                titles = [f"{label(c)}  (r = {rs[c]:.3f})" if rs[c] is not None else label(c) for c in pair]
                fig = make_subplots(rows=1, cols=len(pair), subplot_titles=titles, horizontal_spacing=0.08)
                for i, c in enumerate(pair, start=1):
                    add_scatter(fig, growth_df, c, "생중량", row=1, col=i)
                    fig.update_xaxes(title_text=label(c), row=1, col=i)
                fig.update_yaxes(title_text="생중량(g)", row=1, col=1)
                style(fig, "생중량과의 관계 (점 = 개체 1개, 주황 선 = 추세선)")
                st.plotly_chart(fig, width="stretch")
                note("점들이 추세선 가까이 모여 있을수록 r이 1에 가깝고, 그 항목으로 생중량을 더 잘 짐작할 수 있어요.")
            else:
                st.info("생중량, 잎 수, 지상부 길이 열이 있어야 이 비교를 할 수 있어요.")

            # ② 생중량 분포
            st.subheader("② 같은 스마트팜인데 개체마다 생중량 차이는 얼마나 클까?")
            if "생중량" in g_cols and growth_df["생중량"].dropna().size >= 2:
                w = growth_df["생중량"].dropna()
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("평균", f"{w.mean():.2f} g", border=True)
                m2.metric("중앙값", f"{w.median():.2f} g", border=True)
                m3.metric("표준편차", f"{w.std():.2f} g", border=True)
                m4.metric("변동계수(CV)", f"{cv(w):.1f}%" if cv(w) is not None else "-", border=True)
                fig = px.histogram(w, nbins=20, color_discrete_sequence=["#9B7FE6"])
                fig.add_vline(x=w.mean(), line_dash="dash", line_color=ORANGE, annotation_text="평균")
                fig.add_vline(x=w.median(), line_dash="dot", line_color=BLUE, annotation_text="중앙값",
                              annotation_position="top left")
                style(fig, "생중량 히스토그램 (어느 구간에 개체가 몰려 있나)")
                fig.update_layout(xaxis_title="생중량(g)", yaxis_title="개체 수", showlegend=False, bargap=0.05)
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("생중량 값이 2개 미만이라 히스토그램을 건너뛰었어요.")

            # ③ 상위·하위 개체
            st.subheader("③ 상위·하위 개체는 무엇이 다를까?")
            d = growth_df[[measure]].copy()
            if "개체번호" in growth_df.columns:
                d["개체"] = id_text(growth_df["개체번호"])
            else:
                d["개체"] = [str(i + 1) for i in range(len(d))]
            d = d.dropna(subset=[measure]).sort_values(measure, ascending=False).reset_index(drop=True)
            if len(d) >= 4:
                k = min(5, len(d) // 2)
                d["구분"] = "중간"
                d.loc[d.index[:k], "구분"] = f"상위 {k}"
                d.loc[d.index[len(d) - k:], "구분"] = f"하위 {k}"
                cmap = {f"상위 {k}": ORANGE, "중간": "#D9D2F5", f"하위 {k}": BLUE}
                fig = px.bar(d, x="개체", y=measure, color="구분", color_discrete_map=cmap)
                style(fig, f"개체별 {label(measure)} — 사이드바에서 항목을 바꿀 수 있어요")
                fig.update_layout(xaxis_title="개체번호", yaxis_title=label(measure), xaxis_type="category",
                                  legend=dict(orientation="h", y=1.08, x=1, xanchor="right", title=None))
                st.plotly_chart(fig, width="stretch")
                note(f"🔺 상위: {', '.join(d['개체'].head(k))} &nbsp;|&nbsp; 🔻 하위: {', '.join(d['개체'].tail(k))}")
            else:
                st.info(f"{measure} 값이 4개 미만이라 막대그래프를 건너뛰었어요.")

            if "생중량" in g_cols and growth_df["생중량"].dropna().size >= 8:
                w = growth_df["생중량"]
                q1, q3 = w.quantile(0.25), w.quantile(0.75)
                low, high = growth_df[w <= q1], growth_df[w >= q3]
                rows = []
                for c in g_cols:
                    if c == "생중량":
                        continue
                    lo, hi = low[c].dropna(), high[c].dropna()
                    if len(lo) > 0 and len(hi) > 0 and lo.mean() > 0:
                        rows.append({"항목": c, "하위 그룹 평균": round(lo.mean(), 2),
                                     "상위 그룹 평균": round(hi.mean(), 2), "몇 배": round(hi.mean() / lo.mean(), 2)})
                if rows:
                    ratio = pd.DataFrame(rows).sort_values("몇 배")
                    fig = px.bar(ratio, x="몇 배", y="항목", orientation="h", text="몇 배",
                                 color_discrete_sequence=[PURPLE])
                    fig.update_traces(texttemplate="%{text}배", textposition="outside")
                    style(fig, f"생중량 상위 25%(≥{q3:.2f}g, {len(high)}개) ÷ 하위 25%(≤{q1:.2f}g, {len(low)}개) 평균 비율",
                          height=360)
                    fig.update_layout(xaxis_title="상위 그룹이 하위 그룹의 몇 배인지", yaxis_title="")
                    st.plotly_chart(fig, width="stretch")
                    st.dataframe(ratio.sort_values("몇 배", ascending=False), width="stretch", hide_index=True)
                    st.caption("질량은 생중량의 일부라서 배수가 크게 나오는 게 당연해요. 잎 수·길이 배수를 중심으로 보면 좋아요.")

            # ④ 지상부 vs 지하부 변동계수
            st.subheader("④ 지상부와 지하부 중 개체끼리 차이가 더 큰 쪽은?")
            rows = []
            for c in ["지상부 질량", "지하부 질량"]:
                if c in g_cols and cv(growth_df[c]) is not None:
                    v = growth_df[c].dropna()
                    rows.append({"항목": c, "평균(g)": round(v.mean(), 3), "표준편차(g)": round(v.std(), 3),
                                 "변동계수(%)": round(cv(v), 1)})
            if len(rows) == 2:
                cvt = pd.DataFrame(rows)
                a, b = st.columns([1.3, 1])
                with a:
                    fig = px.bar(cvt, x="항목", y="변동계수(%)", text="변동계수(%)", color="항목",
                                 color_discrete_sequence=[GREEN, BROWN])
                    fig.update_traces(texttemplate="%{text}%", textposition="outside", width=0.5)
                    style(fig, "변동계수(CV) 비교", height=380)
                    fig.update_layout(showlegend=False, yaxis_title="변동계수(%)", xaxis_title="")
                    st.plotly_chart(fig, width="stretch")
                with b:
                    st.dataframe(cvt, width="stretch", hide_index=True)
                    note("지하부는 평균 무게가 작아서 표준편차만 보면 차이가 작아 보여요. "
                         "그래서 <b>평균에 비해 얼마나 들쭉날쭉한지</b>(변동계수)로 비교했어요.")
            else:
                st.info("지상부 질량과 지하부 질량이 둘 다 있어야 이 비교를 할 수 있어요.")

            # ⑤ 상관계수 히트맵
            st.subheader("⑤ 생육 변수끼리 상관계수 히트맵")
            num = growth_df[g_cols]
            if len(g_cols) >= 2 and len(num.dropna()) >= 3:
                corr = num.corr().round(2)
                corr.index = [label(c) for c in corr.index]
                corr.columns = [label(c) for c in corr.columns]
                fig = px.imshow(corr, text_auto=True, zmin=-1, zmax=1, color_continuous_scale="RdBu_r", aspect="auto")
                style(fig, "진한 빨강일수록 함께 커지는 관계가 강해요", height=480)
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("숫자 항목이 2개 이상, 값이 3개 이상 있어야 히트맵을 그릴 수 있어요.")

            csv_button(growth_df, f"{school}_생육결과_정리.csv", "growth_dl")
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")
