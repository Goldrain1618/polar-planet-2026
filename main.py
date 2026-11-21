import io
import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ============================================================
#  한글 폰트 CSS (Streamlit에서 한글이 깨지지 않도록)
# ============================================================
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR&display=swap');
html, body, [class*="css"] {
   font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif;
}
</style>""", unsafe_allow_html=True)


# ============================================================
#  페이지 설정 (wide mode)
# ============================================================
st.set_page_config(page_title="극지식물 생육 분석", layout="wide")
st.title("🌱 우리 학교 극지식물 개체별 생육 차이 분석")


# ============================================================
#  CSV 읽기 함수 (utf-8-sig → cp949 순서로 시도)
# ============================================================
@st.cache_data
def read_csv_bytes(file):
    """file.getvalue()로 바이트를 꺼내 인코딩 시도 후 DataFrame 반환"""
    if file is None:
        return pd.DataFrame()
    raw = file.getvalue()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=enc)
        except Exception:
            pass
    return pd.DataFrame()


# ============================================================
#  열 이름 표준화 함수 (문서에서 제공된 std_cols 그대로 사용)
# ============================================================
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
            num = pd.to_numeric(
                df[c].astype(str).str.replace(",", "")
                .str.extract(r"(-?\d+\.?\d*)")[0],
                errors="coerce",
            )
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
            parsed[bad] = pd.to_datetime(parts[0], format="%Y%m%d") + pd.to_timedelta(
                parts[1].astype(int), unit="h"
            )
        df["time"] = parsed
    return df


# ============================================================
#  CSV 다운로드 헬퍼 (한글 깨짐 방지: utf-8-sig)
# ============================================================
def csv_download_button(label, df, file_name):
    """df.to_csv(index=False).encode('utf-8-sig')로 다운로드 버튼 생성"""
    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(label=label, data=csv_bytes, file_name=file_name, mime="text/csv")


# ============================================================
#  사이드바: CSV 업로드 + 측정 항목 선택
# ============================================================
st.sidebar.header("📎 데이터 업로드")

env_file = st.sidebar.file_uploader("환경 CSV", type="csv")
growth_file = st.sidebar.file_uploader("생육 결과 CSV", type="csv")

if env_file is not None:
    env_df = read_csv_bytes(env_file)
    env_df = std_cols(env_df)
else:
    env_df = pd.DataFrame()

if growth_file is not None:
    growth_df = read_csv_bytes(growth_file)
    growth_df = std_cols(growth_df)
else:
    growth_df = pd.DataFrame()

# 파일명에서 학교명 추출 (하드코딩 금지)
both_names = []
if env_file is not None:
    both_names.append(os.path.splitext(env_file.name)[0])
if growth_file is not None:
    both_names.append(os.path.splitext(growth_file.name)[0])
school_name = both_names[0] if both_names else "우리 학교"

st.sidebar.markdown(f"🏫 학교명: **{school_name}**")
st.sidebar.divider()

st.sidebar.subheader("🌿 생육 측정 항목 선택 (복수 선택 가능)")
growth_options = {
    "잎 수": "잎 수",
    "지상부 길이": "지상부 길이",
    "지하부 길이": "지하부 길이",
    "생중량": "생중량",
}
selected_growth = []
for label, col in growth_options.items():
    if st.sidebar.checkbox(f"{label} ({col})", value=True):
        selected_growth.append(col)


# ============================================================
#  탭 구성
# ============================================================
tab1, tab2, tab3 = st.tabs(["📖 실험 개요", "🌡 환경 데이터", "📊 생육 결과"])


# ============================================================
#  Tab 1: 실험 개요
# ============================================================
with tab1:
    try:
        # --- 데이터가 아예 없을 때 안내 ---
        if env_df.empty and growth_df.empty:
            st.info("CSV 파일을 업로드하면 실험 개요가 표시됩니다.")
        else:
            # --- 개체 수 (생육 데이터가 있으면) ---
            if not growth_df.empty and "개체번호" in growth_df.columns:
                n_individuals = growth_df["개체번호"].nunique()
            else:
                n_individuals = 0

            # --- 평균 온도 / 습도 (환경 데이터에서) ---
            tmp_vals = env_df["temperature"].dropna() if "temperature" in env_df.columns else pd.Series(dtype=float)
            avg_temp = round(float(tmp_vals.mean()), 1) if len(tmp_vals) >= 2 else None
            hum_vals = env_df["humidity"].dropna() if "humidity" in env_df.columns else pd.Series(dtype=float)
            avg_hum = round(float(hum_vals.mean()), 1) if len(hum_vals) >= 2 else None

            # --- 평균 생중량 ---
            bio_vals = growth_df["생중량"].dropna() if "생중량" in growth_df.columns else pd.Series(dtype=float)
            avg_bio = round(float(bio_vals.mean()), 2) if len(bio_vals) >= 2 else None

            # --- 지표 카드 4개 (st.metric 사용) ---
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("총 개체수", f"{n_individuals}개체")
            with c2:
                if avg_temp is not None:
                    st.metric("평균 온도", f"{avg_temp} °C")
                else:
                    st.metric("평균 온도", "데이터 없음")
            with c3:
                if avg_hum is not None:
                    st.metric("평균 습도", f"{avg_hum} %")
                else:
                    st.metric("평균 습도", "데이터 없음")
            with c4:
                if avg_bio is not None:
                    st.metric("평균 생중량", f"{avg_bio} g")
                else:
                    st.metric("평균 생중량", "데이터 없음")

            st.divider()

            # --- 데이터 요약 표 ---
            rows = []
            # 개체 수
            rows.append(["항목", "값"])
            rows.append(["총 개체 수", f"{n_individuals}개체"])
            # 측정 기간
            if "time" in env_df.columns and not env_df["time"].isna().all():
                tmin = env_df["time"].min()
                tmax = env_df["time"].max()
                rows.append(["측정 기간", f"{tmin.strftime('%Y-%m-%d')} ~ {tmax.strftime('%Y-%m-%d')}"])
            else:
                rows.append(["측정 기간", "환경 데이터 없음"])
            # 측정 항목 (생육)
            growth_cols_found = [c for c in ["잎 수", "지상부 길이", "지하부 길이", "생중량"] if c in growth_df.columns]
            rows.append(["측정 항목 (생육)", " · ".join(growth_cols_found) if growth_cols_found else "데이터 없음"])
            # 측정 항목 (환경)
            env_cols_found = [c for c in ["temperature", "humidity", "ph", "ec"] if c in env_df.columns]
            env_label = " · ".join(env_cols_found) if env_cols_found else "데이터 없음"
            rows.append(["측정 항목 (환경)", env_label])
            # 학교명
            rows.append(["학교명", school_name])

            summary_df = pd.DataFrame(rows[1:], columns=rows[0])
            st.subheader("📋 데이터 요약")
            st.dataframe(summary_df, use_container_width=True)

            st.divider()

            # --- 연구 배경 및 목적 ---
            st.subheader("🔬 연구 배경 및 목적")
            st.markdown(
                f"""**연구 배경**
- 극지식물은 낮은 온도, 강한 자외선, 척박한 토양 등 열악한 환경에 적응한 식물입니다.
- 우리 학교({school_name})에서는 극지식물 개체를 재배하며 환경 조건과 생육 결과를 기록했습니다.

**연구 목적**
1. 개체별 생중량 차이와 분포 특성 파악 (평균·표준편차·CV)
2. 잎 수·지상부 길이와 생중량의 상관관계 확인
3. 생중량 상위 25% vs 하위 25% 개체 비교를 통한 생육 우수 개체 파악

**통계 용어 간단 설명**
- **평균**: 모든 값을 더해 개수로 나눈 대표값
- **표준편차(SD)**: 값이 평균에서 얼마나 퍼져있는지 나타내는 지표 (클수록 차이 큼)
- **변동계수(CV)**: 표준편차를 평균으로 나눈 값 (%) — 단위가 다른 그룹 간 비교에 유용
- **상관계수(r)**: 두 변수 간 직선 관계의 강도 (-1 ~ +1, 0에 가까울수록 관계 약함)
"""
            )
    except Exception as e:
        st.warning(f"⚠ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")


# ============================================================
#  Tab 2: 환경 데이터
# ============================================================
with tab2:
    try:
        if env_df.empty:
            st.info("환경 CSV를 업로드하면 환경 데이터가 표시됩니다.")
        else:
            # --- 환경 요약 (평균·최소·최대 표) ---
            env_num_cols = [c for c in ["temperature", "humidity", "ph", "ec"] if c in env_df.columns]
            if env_num_cols:
                summary_rows = []
                summary_rows.append(["측정 항목", "평균", "최소", "최대"])
                for col in env_num_cols:
                    s = env_df[col].dropna()
                    if len(s) >= 2:
                        summary_rows.append([
                            col,
                            round(float(s.mean()), 2),
                            round(float(s.min()), 2),
                            round(float(s.max()), 2),
                        ])
                env_summary_df = pd.DataFrame(summary_rows[1:], columns=summary_rows[0])
                st.subheader("🌡 환경 요약 (평균·최소·최대)")
                st.dataframe(env_summary_df, use_container_width=True)
            else:
                st.info("환경 데이터에 recognized 열이 없습니다.")

            st.divider()

            # --- 날짜별 시계열 ---
            if "time" in env_df.columns and not env_df["time"].isna().all():
                daily = env_df.set_index("time").resample("D").mean(numeric_only=True).reset_index()

                cols_to_plot = [c for c in ["temperature", "humidity"] if c in daily.columns and len(daily[c].dropna()) >= 2]

                if cols_to_plot:
                    fig_daily = go.Figure()
                    colors = {"temperature": "#e74c3c", "humidity": "#3498db"}
                    for col in cols_to_plot:
                        fig_daily.add_trace(
                            go.Scatter(
                                x=daily["time"],
                                y=daily[col],
                                mode="lines+markers",
                                name=col,
                                line=dict(color=colors.get(col, "#333333"), width=2),
                                markers=dict(size=5),
                                hovertemplate=f"{col}<br>x=%{{x|%Y-%m-%d}}<br>y=%{{y:.2f}}<extra></extra>",
                            )
                        )
                    fig_daily.update_layout(
                        title="📈 일별 평균 환경 변화",
                        xaxis_title="날짜",
                        yaxis_title="값",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                        font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"),
                        hovermode="x unified",
                        template="plotly_white",
                    )
                    st.plotly_chart(fig_daily, width="stretch")
                else:
                    st.info("일별 평균 계산에 필요한 숫자 열이 없습니다.")

                # pH·EC 서브플롯 (두 열이 모두 있을 때만)
                if "ph" in env_df.columns and "ec" in env_df.columns:
                    ph_daily = env_df.set_index("time")["ph"].resample("D").mean().reset_index()
                    ec_daily = env_df.set_index("time")["ec"].resample("D").mean().reset_index()
                    if len(ph_daily) >= 2 and len(ec_daily) >= 2:
                        fig_ph_ec = make_subplots(specs=[[{"secondary_y": True}]])
                        fig_ph_ec.add_trace(
                            go.Scatter(
                                x=ph_daily["time"],
                                y=ph_daily["ph"],
                                mode="lines+markers",
                                name="pH",
                                line=dict(color="#3498db", width=2),
                                markers=dict(size=5),
                                hovertemplate="pH<br>x=%{x|%Y-%m-%d}<br>y=%{y:.2f}<extra></extra>",
                            ),
                            secondary_y=False,
                        )
                        fig_ph_ec.add_trace(
                            go.Scatter(
                                x=ec_daily["time"],
                                y=ec_daily["ec"],
                                mode="lines+markers",
                                name="EC",
                                line=dict(color="#e67e22", width=2),
                                markers=dict(size=5),
                                hovertemplate="EC (dS/m)<br>x=%{x|%Y-%m-%d}<br>y=%{y:.2f}<extra></extra>",
                            ),
                            secondary_y=True,
                        )
                        fig_ph_ec.update_layout(
                            title="🧪 pH · EC 일별 변화",
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                            font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"),
                            template="plotly_white",
                        )
                        fig_ph_ec.update_yaxes(title_text="pH", secondary_y=False, title_text="EC (dS/m)", secondary_y=True)
                        st.plotly_chart(fig_ph_ec, width="stretch")
                    else:
                        st.info("pH·EC 일별 계산 데이터가 부족합니다.")
                else:
                    st.info("pH·EC 열이 없어 해당 그래프를 건너뛰었습니다.")
            else:
                st.info("time 열이 없어 시계열 그래프를 표시할 수 없습니다.")

            st.divider()

            # --- 환경 데이터 원본 테이블 + CSV 다운로드 ---
            with st.expander("📁 환경 데이터 원본 테이블 + CSV 다운로드"):
                if not env_df.empty:
                    st.dataframe(env_df, use_container_width=True)
                    if "time" in env_df.columns:
                        csv_download_button("📥 환경 데이터 CSV 다운로드", env_df, f"{school_name}_환경데이터.csv")
                    else:
                        csv_download_button("📥 환경 데이터 CSV 다운로드", env_df, f"{school_name}_환경데이터.csv")
                else:
                    st.info("환경 데이터가 없습니다.")
    except Exception as e:
        st.warning(f"⚠ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")


# ============================================================
#  Tab 3: 생육 결과
# ============================================================
with tab3:
    try:
        if growth_df.empty:
            st.info("생육 결과 CSV를 업로드하면 생육 분석 결과가 표시됩니다.")
        else:
            # --- 생중량 기본 통계 (dropna 후 2개 이상) ---
            bio_s = growth_df["생중량"].dropna() if "생중량" in growth_df.columns else pd.Series(dtype=float)
            if len(bio_s) >= 2:
                bio_mean = float(bio_s.mean())
                bio_std = float(bio_s.std())
                bio_cv = round(bio_std / bio_mean * 100, 1) if bio_mean > 0 else None
                bio_max = float(bio_s.max())
                bio_min = float(bio_s.min())

                # 최대/최소 개체번호 (원래 값 그대로)
                idx_max = growth_df["생중량"].idxmax()
                idx_min = growth_df["생중량"].idxmin()
                max_id = growth_df.loc[idx_max, "개체번호"]
                min_id = growth_df.loc[idx_min, "개체번호"]
            else:
                bio_mean = bio_std = bio_cv = bio_max = bio_min = None
                max_id = min_id = "N/A"

            # --- 🥇 핵심 결과 카드 ---
            st.subheader("🥇 핵심 결과")
            kc1, kc2, kc3, kc4 = st.columns(4)
            with kc1:
                if bio_mean is not None:
                    st.metric("평균 생중량", f"{bio_mean:.2f} g")
                else:
                    st.metric("평균 생중량", "데이터 없음")
            with kc2:
                if bio_max is not None:
                    st.metric("최대 생중량", f"{bio_max:.2f} g", f"개체 {max_id}")
                else:
                    st.metric("최대 생중량", "데이터 없음")
            with kc3:
                if bio_min is not None:
                    st.metric("최소 생중량", f"{bio_min:.2f} g", f"개체 {min_id}")
                else:
                    st.metric("최소 생중량", "데이터 없음")
            with kc4:
                if bio_cv is not None:
                    st.metric("변동계수(CV)", f"{bio_cv}%")
                else:
                    st.metric("변동계수(CV)", "데이터 없음")

            st.info(
                f"📊 **통계 설명**  ·  평균: {bio_mean:.2f}g  ·  표준편차(SD): {bio_std:.2f}g  ·  CV: {bio_cv}%"
                if bio_mean is not None
                else "📊 생중량 통계 계산에 필요한 데이터가 부족합니다."
            )

            st.divider()

            # --- 개체별 생육 비교 (막대 그래프) ---
            st.subheader("📊 개체별 생육 비교 (막대 그래프)")
            plot_cols = [c for c in selected_growth if c in growth_df.columns]
            if plot_cols:
                # 개체번호 정렬 키 (숫자면 숫자순, 글자면 그대로)
                id_vals = growth_df["개체번호"]
                try:
                    id_sort_key = pd.to_numeric(id_vals, errors="coerce")
                    sort_ok = id_sort_key.notna().all()
                except Exception:
                    sort_ok = False
                if sort_ok:
                    sort_idx = id_sort_key.argsort()
                    plot_df = growth_df.iloc[sort_idx].reset_index(drop=True)
                else:
                    plot_df = growth_df.reset_index(drop=True)

                # 상단/하위 25% 강조용 생중량 기준
                if "생중량" in growth_df.columns and len(growth_df["생중량"].dropna()) >= 4:
                    q75 = float(growth_df["생중량"].dropna().quantile(0.75))
                    q25 = float(growth_df["생중량"].dropna().quantile(0.25))
                else:
                    q75 = q25 = None

                for col in plot_cols:
                    fig_bar = go.Figure()
                    y_vals = plot_df[col].dropna()
                    if len(y_vals) < 2:
                        continue
                    fig_bar.add_trace(
                        go.Bar(
                            x=plot_df["개체번호"],
                            y=plot_df[col],
                            name=col,
                            marker_color=[
                                "#2ecc71"
                                if (q75 is not None and v >= q75)
                                else ("#e74c3c" if (q25 is not None and v <= q25) else "#95a5a6")
                                for v in plot_df[col]
                            ],
                            hovertemplate=f"{col}<br>개체=%{{x}}<br>값=%{{y:.2f}}<extra></extra>",
                        )
                    )
                    fig_bar.update_layout(
                        title=f"{col} — 개체별 비교 (초록: 상위 25% 이상 / 빨강: 하위 25% 이하)",
                        xaxis_title="개체번호",
                        yaxis_title=col,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                        font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"),
                        template="plotly_white",
                    )
                    st.plotly_chart(fig_bar, width="stretch")
            else:
                st.info("선택한 생육 측정 항목이 데이터에 없습니다.")

            st.divider()

            # --- 생중량 분포 (박스플롯 + 바이올린 플롯) ---
            st.subheader("📦 생중량 분포 (박스플롯 + 바이올린 플롯)")
            if "생중량" in growth_df.columns and len(growth_df["생중량"].dropna()) >= 2:
                bio_for_plot = growth_df["생중량"].dropna().reset_index(drop=True)
                fig_dist = make_subplots(
                    rows=1, cols=2, subplot_titles=["박스플롯", "바이올린 플롯"]
                )
                fig_dist.add_trace(
                    go.Box(y=bio_for_plot, name="생중량", fillcolor="#3498db",
                           boxpoints="outliers", hovertemplate="생중량<br>y=%{y:.2f}g<extra></extra>"),
                    row=1, col=1,
                )
                fig_dist.add_trace(
                    go.Violin(y=bio_for_plot, name="생중량", fillcolor="#3498db",
                              hovertemplate="생중량<br>y=%{y:.2f}g<extra></extra>"),
                    row=1, col=2,
                )
                fig_dist.update_layout(
                    title="🌿 생중량 분포 (박스플롯 · 바이올린 플롯)",
                    font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"),
                    template="plotly_white",
                )
                st.plotly_chart(fig_dist, width="stretch")

                # 통계 설명
                st.markdown(
                    f"""**분포 해석 참고**
- 박스플롯의 상자(body): 중위 50% 값의 범위 (Q1 ~ Q3)
- 상자 안의 선: 중앙값(median)
- 수염(whisker): 이상치를 제외한 최소·최대 범위
- 바이올린 플롯: 분포의 밀도 형태 (넓을수록 값이 많이 모여있음)
- 평균 {bio_mean:.2f}g, 표준편차 {bio_std:.2f}g, CV {bio_cv}%
"""
                )
            else:
                st.info("생중량 데이터가 부족해 분포 그래프를 표시할 수 없습니다.")

            st.divider()

            # --- 상관관계 분석 (산점도 2개 + 추세선) ---
            st.subheader("🔗 상관관계 분석 (산점도 + 추세선)")
            corr_pairs = []
            if "잎 수" in growth_df.columns and "생중량" in growth_df.columns:
                corr_pairs.append(("잎 수", "생중량"))
            if "지상부 길이" in growth_df.columns and "생중량" in growth_df.columns:
                corr_pairs.append(("지상부 길이", "생중량"))

            if corr_pairs:
                for x_col, y_col in corr_pairs:
                    df_c = growth_df[[x_col, y_col]].dropna()
                    if len(df_c) < 2:
                        st.info(f"{x_col} vs {y_col}: 데이터가 부족해 상관관계 계산 불가")
                        continue

                    x_arr = df_c[x_col].to_numpy(dtype=float)
                    y_arr = df_c[y_col].to_numpy(dtype=float)
                    r_val = float(np.corrcoef(x_arr, y_arr)[0, 1])

                    # 추세선: np.polyfit (degree 1)
                    try:
                        slope, intercept = np.polyfit(x_arr, y_arr, 1)
                        x_line = np.linspace(x_arr.min(), x_arr.max(), 100)
                        y_line = slope * x_line + intercept
                        has_trend = True
                    except Exception:
                        has_trend = False
                        slope = intercept = None

                    fig_sc = go.Figure()
                    fig_sc.add_trace(
                        go.Scatter(
                            x=x_arr,
                            y=y_arr,
                            mode="markers",
                            name=f"{x_col} vs {y_col}",
                            marker=dict(size=8, color="#3498db", opacity=0.7, line=dict(width=1, color="#2c3e50")),
                            hovertemplate=f"{x_col}=%{{x:.2f}}<br>{y_col}=%{{y:.2f}}g<extra></extra>",
                        )
                    )
                    if has_trend:
                        fig_sc.add_trace(
                            go.Scatter(
                                x=x_line,
                                y=y_line,
                                mode="lines",
                                name=f"추세선 (r={r_val:.3f})",
                                line=dict(color="#e74c3c", width=2, dash="dot"),
                            )
                        )
                    fig_sc.update_layout(
                        title=f"{x_col} vs {y_col}  ·  상관계수 r = {r_val:.3f}",
                        xaxis_title=x_col,
                        yaxis_title=f"{y_col} (g)",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                        font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"),
                        template="plotly_white",
                    )
                    st.plotly_chart(fig_sc, width="stretch")

                    direction = "양의 상관관계" if r_val > 0 else ("음의 상관관계" if r_val < 0 else "상관관계 거의 없음")
                    strength = (
                        "매우 강함"
                        if abs(r_val) >= 0.8
                        else ("강함" if abs(r_val) >= 0.6 else ("중간" if abs(r_val) >= 0.4 else ("약함" if abs(r_val) >= 0.2 else "매우 약함")))
                    )
                    st.markdown(
                        f"""**{x_col} vs {y_col}**
- 상관계수 r = **{r_val:.3f}** → {direction} ({strength})
- 추세선 기울기: {slope:.4f} (x가 1 증가할 때 y가 {slope:.4f}만큼 변함)
- **참고**: 상관계수는 인과관계를 의미하지 않습니다. 두 변수가 함께 변하는 경향만 나타냅니다.
"""
                    )
            else:
                st.info("잎 수·지상부 길이 중 생중량과 함께 분석할 열이 없습니다.")

            st.divider()

            # --- 생중량 상위 25% vs 하위 25% 비교 ---
            if "생중량" in growth_df.columns and len(growth_df["생중량"].dropna()) >= 4:
                bio_clean = growth_df["생중량"].dropna()
                q75v = float(bio_clean.quantile(0.75))
                q25v = float(bio_clean.quantile(0.25))
                top_df = growth_df[growth_df["생중량"] >= q75v].copy()
                bot_df = growth_df[growth_df["생중량"] <= q25v].copy()

                st.subheader("🏆 생중량 상위 25% vs 하위 25% 비교")
                comp_cols = []
                for col in ["잎 수", "지상부 길이", "지하부 길이", "생중량"]:
                    if col in growth_df.columns:
                        comp_cols.append(col)

                if comp_cols:
                    comp_rows = [["구분", "개체 수"] + comp_cols]
                    comp_rows.append(["상위 25% (≥ Q3)", f"{len(top_df)}개체"] +
                                      [f"{float(top_df[c].mean()):.2f}" for c in comp_cols])
                    comp_rows.append(["하위 25% (≤ Q1)", f"{len(bot_df)}개체"] +
                                      [f"{float(bot_df[c].mean()):.2f}" for c in comp_cols])
                    comp_df = pd.DataFrame(comp_rows[1:], columns=comp_rows[0])
                    st.dataframe(comp_df, use_container_width=True)

                    st.markdown(
                        f"""**비교 해석**
- 상위 25% 기준(생중량 ≥ Q3): **{q75v:.2f} g** 이상, {len(top_df)}개체
- 하위 25% 기준(생중량 ≤ Q1): **{q25v:.2f} g** 이하, {len(bot_df)}개체
- 상위 집단 평균 생중량: **{float(top_df['생중량'].mean()):.2f} g**
- 하위 집단 평균 생중량: **{float(bot_df['생중량'].mean()):.2f} g**
"""
                    )
                else:
                    st.info("비교할 측정 항목이 없습니다.")
            else:
                st.info("생중량 데이터가 부족해 상위·하위 25% 비교를 할 수 없습니다.")

            st.divider()

            # --- 생육 데이터 원본 + CSV 다운로드 ---
            with st.expander("📁 생육 데이터 원본 테이블 + CSV 다운로드"):
                if not growth_df.empty:
                    st.dataframe(growth_df, use_container_width=True)
                    csv_download_button("📥 생육 결과 CSV 다운로드", growth_df, f"{school_name}_생육결과데이터.csv")
                else:
                    st.info("생육 데이터가 없습니다.")
    except Exception as e:
        st.warning(f"⚠ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")
