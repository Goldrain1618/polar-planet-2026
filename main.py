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

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR&display=swap');
html, body, [class*="css"] {
   font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif;
}
</style>
""",
    unsafe_allow_html=True,
)

st.title("🌱 우리 학교 극지식물 개체별 생육 차이 분석")

# ---- 파일 읽기 ----
def read_csv(file):
    data = file.getvalue()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc)
        except Exception:
            pass
    return pd.DataFrame()

@st.cache_data(show_spinner=False)
def load_csv(data):
    return read_csv(io.BytesIO(data))

env_file = st.sidebar.file_uploader("환경 데이터 CSV", type="csv", help="학교의 환경 측정 기록(CSV)을 올려주세요.")
growth_file = st.sidebar.file_uploader("생육 결과 CSV", type="csv", help="개체별 생육 결과(CSV)를 올려주세요.")

school_name = ""
if env_file is not None:
    school_name = os.path.splitext(env_file.name)[0]
if school_name == "" and growth_file is not None:
    school_name = os.path.splitext(growth_file.name)[0]
if school_name:
    st.sidebar.caption(f"📌 학교명: {school_name}")

env_df = None
growth_df = None

if env_file is not None:
    with st.spinner("환경 CSV를 읽는 중..."):
        env_df = load_csv(env_file.getvalue())

if growth_file is not None:
    with st.spinner("생육 CSV를 읽는 중..."):
        growth_df = load_csv(growth_file.getvalue())

# ---- 열 이름 표준화 ----
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

if env_df is not None and not env_df.empty:
    env_df = std_cols(env_df)

if growth_df is not None and not growth_df.empty:
    growth_df = std_cols(growth_df)

# ---- 탭 ----
tab1, tab2, tab3 = st.tabs(["📖 실험 개요", "🌡 환경 데이터", "📊 생육 결과"])

def get_cols(df, names):
    if df is None:
        return []
    return [c for c in names if c in df.columns]

# ---- Tab 1 ----
with tab1:
    try:
        st.subheader("🎯 실험 개요")
        st.write("### 📖 연구 배경 및 목적")
        st.write(
            "극지 환경에 사는 극지식물은 기온이 낮고 생장 기간이 짧아 환경 변화에 매우 민감합니다. "
            "이 대시보드에서는 온도·습도 같은 환경 조건이 극지식물의 생장에 어떤 영향을 주는지 살펴봅니다. "
            "개체마다 잎 수·길이·무게(생중량)가 어떻게 다른지 평균·표준편차·분포로 비교하고, "
            "생중량이 높은 상위 25% 개체와 하위 25% 개체의 차이를 확인합니다."
        )

        st.write("### 📋 데이터 요약")
        growth_cols = get_cols(growth_df, ["잎 수", "지상부 길이", "지하부 길이", "생중량"])
        env_cols = get_cols(env_df, ["temperature", "humidity", "ph", "ec", "water_temp", "co2"])

        if growth_df is not None and not growth_df.empty and "개체번호" in growth_df.columns:
            n_individuals = growth_df["개체번호"].nunique()
        else:
            n_individuals = 0

        if env_df is not None and not env_df.empty and "time" in env_df.columns:
            tmin = env_df["time"].min()
            tmax = env_df["time"].max()
            period = f"{tmin.strftime('%Y-%m-%d')} ~ {tmax.strftime('%Y-%m-%d')}"
        else:
            period = "—"

        summary_rows = {
            "구분": ["환경 데이터", "생육 결과"],
            "개체 수": ["—", f"{n_individuals}개체" if n_individuals else "—"],
            "측정 기간": [period, "—"],
            "측정 항목": [", ".join(env_cols) if env_cols else "—", ", ".join(growth_cols) if growth_cols else "—"],
        }
        st.dataframe(pd.DataFrame(summary_rows), width="stretch")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("총 개체수", f"{n_individuals}개체" if n_individuals else "데이터 없음")
        with col2:
            if env_df is not None and not env_df.empty and "temperature" in env_df.columns and env_df["temperature"].notna().sum() > 0:
                st.metric("평균 온도", f"{env_df['temperature'].mean():.1f} °C")
            else:
                st.metric("평균 온도", "—")
        with col3:
            if env_df is not None and not env_df.empty and "humidity" in env_df.columns and env_df["humidity"].notna().sum() > 0:
                st.metric("평균 습도", f"{env_df['humidity'].mean():.1f} %")
            else:
                st.metric("평균 습도", "—")
        with col4:
            if growth_df is not None and not growth_df.empty and "생중량" in growth_df.columns and growth_df["생중량"].notna().sum() > 0:
                st.metric("평균 생중량", f"{growth_df['생중량'].mean():.2f} g")
            else:
                st.metric("평균 생중량", "—")

        st.write("### 📊 주요 결과 요약")
        if growth_df is not None and not growth_df.empty and "생중량" in growth_df.columns:
            w = growth_df["생중량"].dropna()
            if len(w) >= 2:
                st.metric("생중량 평균", f"{w.mean():.2f} g")
                st.metric("생중량 표준편차", f"{w.std():.2f} g")
                cv = w.std() / w.mean() * 100 if w.mean() != 0 else 0
                st.metric("생중량 CV", f"{cv:.1f} %")

        st.write("### 📖 통계 용어 설명")
        st.write("• 평균: 여러 값의 합을 개수로 나눈 값")
        st.write("• 표준편차: 값들이 평균으로부터 얼마나 퍼져 있는지 나타냄")
        st.write("• 상관계수: 두 변수가 함께 증가하거나 감소하는 정도(-1 ~ 1)")
    except Exception as e:
        st.warning(f"⚠ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")

# ---- Tab 2 ----
with tab2:
    try:
        st.subheader("🌡 환경 데이터")
        if env_df is None or env_df.empty:
            st.info("환경 데이터가 아직 없어요. 사이드바에서 환경 CSV를 올려주세요.")
        else:
            env_cols = get_cols(env_df, ["temperature", "humidity", "ph", "ec", "water_temp", "co2"])
            if not env_cols:
                st.info("환경 데이터에 숫자 열이 없어요. 파일 이름을 확인해 주세요.")
            else:
                env_summary = env_df[env_cols].agg(["mean", "min", "max"]).T
                env_summary.columns = ["평균", "최소", "최대"]
                st.write("### 🌡 환경 요약 (평균·최소·최대)")
                st.dataframe(env_summary, width="stretch")

                if "time" in env_df.columns:
                    env_data = env_df.copy()
                    env_data["date"] = env_data["time"].dt.date
                    daily = env_data.groupby("date")[env_cols].mean().reset_index()
                    daily["date"] = pd.to_datetime(daily["date"])

                    for c in ["temperature", "humidity"]:
                        if c in daily.columns:
                            fig = px.line(daily, x="date", y=c, markers=False, title=f"일별 평균 {c}")
                            fig.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"))
                            st.plotly_chart(fig, width="stretch")

                    chem = [c for c in ["ph", "ec"] if c in daily.columns]
                    if chem:
                        fig = go.Figure()
                        for c in chem:
                            fig.add_trace(go.Scatter(x=daily["date"], y=daily[c], mode="lines+markers", name=c))
                        fig.update_layout(
                            title="일별 평균 pH·EC",
                            xaxis_title="날짜",
                            yaxis_title="값",
                            font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"),
                        )
                        st.plotly_chart(fig, width="stretch")

                with st.expander("🌱 환경 데이터 원본 및 다운로드"):
                    show_env = ["time"] + env_cols
                    st.dataframe(env_df[show_env], width="stretch")
                    csv = env_df[show_env].to_csv(index=False).encode("utf-8-sig")
                    st.download_button("환경 CSV 다운로드", csv, file_name=env_file.name, mime="text/csv")
    except Exception as e:
        st.warning(f"⚠ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")

# ---- Tab 3 ----
with tab3:
    try:
        st.subheader("📊 생육 결과")
        if growth_df is None or growth_df.empty:
            st.info("생육 데이터가 아직 없어요. 사이드바에서 생육 CSV를 올려주세요.")
        else:
            growth_cols = get_cols(growth_df, ["잎 수", "지상부 길이", "지하부 길이", "생중량"])
            has_weight = "생중량" in growth_df.columns
            has_leaves = "잎 수" in growth_df.columns
            has_shoot_len = "지상부 길이" in growth_df.columns
            has_root_len = "지하부 길이" in growth_df.columns

            if not growth_cols:
                st.info("생육 데이터에 숫자 열이 없어요. 파일 이름을 확인해 주세요.")
            else:
                col1, col2, col3 = st.columns(3)
                with col1:
                    if has_weight and growth_df["생중량"].notna().sum() >= 1:
                        st.metric("평균 생중량", f"{growth_df['생중량'].mean():.2f} g")
                    else:
                        st.metric("평균 생중량", "—")
                with col2:
                    if has_weight and growth_df["생중량"].notna().sum() >= 1:
                        top = growth_df.loc[growth_df["생중량"].idxmax()]
                        st.metric("최대 개체", f"{top['개체번호']} ({top['생중량']:.2f} g)")
                    else:
                        st.metric("최대 개체", "—")
                with col3:
                    if has_weight and growth_df["생중량"].notna().sum() >= 1:
                        bottom = growth_df.loc[growth_df["생중량"].idxmin()]
                        st.metric("최소 개체", f"{bottom['개체번호']} ({bottom['생중량']:.2f} g)")
                    else:
                        st.metric("최소 개체", "—")

                # 상위 25% vs 하위 25% 비교
                if has_weight and growth_df["생중량"].notna().sum() >= 2:
                    mean_w = growth_df.groupby("개체번호")["생중량"].mean().reset_index()
                    mean_w = mean_w.sort_values("생중량", ascending=False).reset_index(drop=True)
                    n = len(mean_w)
                    top_n = int(np.ceil(n * 0.25))
                    bot_n = int(np.ceil(n * 0.25))
                    top_mean = mean_w.iloc[:top_n]["생중량"].mean()
                    bot_mean = mean_w.iloc[n - bot_n:]["생중량"].mean()
                    c1, c2 = st.columns(2)
                    with c1:
                        st.metric("상위 25% 평균 생중량", f"{top_mean:.2f} g")
                    with c2:
                        st.metric("하위 25% 평균 생중량", f"{bot_mean:.2f} g")

                    fig = px.bar(x=["상위 25%", "하위 25%"], y=[top_mean, bot_mean], color=["상위 25%", "하위 25%"])
                    fig.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"))
                    st.plotly_chart(fig, width="stretch")

                # 개체별 평균 비교 바 차트
                def mean_bar_chart(df, value_col, title):
                    mean_vals = df.groupby("개체번호")[value_col].mean().reset_index()
                    mean_vals = mean_vals.sort_values(value_col, ascending=False).reset_index(drop=True)
                    fig = px.bar(mean_vals, x="개체번호", y=value_col, title=title)
                    fig.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"))
                    return fig

                if has_weight and growth_df["생중량"].notna().sum() >= 2:
                    mean_vals = growth_df.groupby("개체번호")["생중량"].mean().reset_index()
                    mean_vals = mean_vals.sort_values("생중량", ascending=False).reset_index(drop=True)
                    n = len(mean_vals)
                    if n >= 6:
                        top_n = max(3, n // 10)
                        bottom_n = max(3, n // 10)
                        colors = []
                        for i in range(n):
                            if i < top_n:
                                colors.append("#FF7B00")
                            elif i >= n - bottom_n:
                                colors.append("#FF4B4B")
                            else:
                                colors.append("#B0B0B0")
                        fig = px.bar(mean_vals, x="개체번호", y="생중량", title="⭐ 개체별 평균 생중량 (가장 중요)")
                        fig.update_traces(marker_color=colors)
                    else:
                        fig = mean_bar_chart(growth_df, "생중량", "⭐ 개체별 평균 생중량 (가장 중요)")
                    fig.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"))
                    st.plotly_chart(fig, width="stretch")

                measure_items = []
                if has_leaves: measure_items.append(("잎 수", "개체별 평균 잎 수"))
                if has_shoot_len: measure_items.append(("지상부 길이", "개체별 평균 지상부 길이"))
                if has_root_len: measure_items.append(("지하부 길이", "개체별 평균 지하부 길이"))

                if measure_items:
                    focus = st.sidebar.selectbox("생육 측정 항목 선택", [name for _, name in measure_items], index=0)
                    for col, title in measure_items:
                        if col == focus:
                            fig = mean_bar_chart(growth_df, col, title)
                            fig.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"))
                            st.plotly_chart(fig, width="stretch")
                    if len(measure_items) > 1:
                        with st.expander("다른 생육 항목도 함께 비교"):
                            for col, title in measure_items:
                                if col != focus:
                                    fig = mean_bar_chart(growth_df, col, title)
                                    fig.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"))
                                    st.plotly_chart(fig, width="stretch")

                # 생중량 분포
                if has_weight and growth_df["생중량"].notna().sum() >= 2:
                    fig = px.box(growth_df, y="생중량", title="생중량 분포 (박스플롯)")
                    fig.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"))
                    st.plotly_chart(fig, width="stretch")
                    w = growth_df["생중량"].dropna()
                    cv = w.std() / w.mean() * 100 if w.mean() != 0 else 0
                    st.metric("생중량 CV", f"{cv:.1f} %")

                # 상관관계 분석 (산점도 2개 + 추세선)
                corr_pairs = []
                if has_weight and has_leaves:
                    corr_pairs.append(("잎 수", "잎 수 vs 생중량"))
                if has_weight and has_shoot_len:
                    corr_pairs.append(("지상부 길이", "지상부 길이 vs 생중량"))
                if corr_pairs:
                    fig = make_subplots(rows=1, cols=len(corr_pairs), subplot_titles=[t for _, t in corr_pairs])
                    r_list = []
                    for j, (x_col, title) in enumerate(corr_pairs, start=1):
                        d = growth_df[[x_col, "생중량"]].dropna()
                        if len(d) < 2:
                            st.info(f"'{x_col}'와 생중량 데이터가 2개 미만이라 추세선을 그릴 수 없어요.")
                            continue
                        slope, intercept = np.polyfit(d[x_col], d["생중량"], 1)
                        trend = slope * d[x_col] + intercept
                        fig.add_trace(go.Scatter(x=d[x_col], y=d["생중량"], mode="markers", name=x_col, marker=dict(color="#1f77b4")), row=1, col=j)
                        fig.add_trace(go.Scatter(x=d[x_col], y=trend, mode="lines", name="추세선", line=dict(color="red")), row=1, col=j)
                        r, p = stats.pearsonr(d[x_col], d["생중량"])
                        r_list.append((title, r, p))
                        fig.update_xaxes(title_text=x_col, row=1, col=j)
                        fig.update_yaxes(title_text="생중량", row=1, col=j)
                    fig.update_layout(hovermode="closest", font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"))
                    st.plotly_chart(fig, width="stretch")
                    r_cols = st.columns(len(r_list))
                    for k, (title, r, p) in enumerate(r_list):
                        r_cols[k].metric(title, f"r = {r:.3f}  (p = {p:.2e})")

                with st.expander("🌱 생육 데이터 원본 및 다운로드"):
                    st.dataframe(growth_df, width="stretch")
                    csv = growth_df.to_csv(index=False).encode("utf-8-sig")
                    st.download_button("생육 CSV 다운로드", csv, file_name=(growth_file.name if growth_file is not None else "growth.csv"), mime="text/csv")
    except Exception as e:
        st.warning(f"⚠ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")
