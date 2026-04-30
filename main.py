import os
import streamlit as st
import pandas as pd
from datetime import datetime

# ─── Data Fetch (cached once per day) ─────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner="Loading data...")
def load_data():
    return pd.read_csv("data.csv")

# ─── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Summer Fest Dashboard", page_icon="📊", layout="wide")

# ─── Load Data ─────────────────────────────────────────────────────────────────
try:
    df = load_data()
except Exception as e:
    st.error(f"❌ Could not load data.csv: {e}")
    st.info("💡 Make sure to run `python update_data.py` first to fetch data from Redshift.")
    st.stop()

# ─── Prep ──────────────────────────────────────────────────────────────────────
df["transaction_date"] = pd.to_datetime(df["transaction_date"]).dt.date

# ─── Sidebar Filters ──────────────────────────────────────────────────────────
st.sidebar.header("🔍 Filters")

# Date range
min_date = df["transaction_date"].min()
max_date = df["transaction_date"].max()
date_range = st.sidebar.date_input(
    "Date Range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)
# handle single-date selection gracefully
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date

# MTD day cutoff (e.g. "up to 20th of each month")
mtd_day = st.sidebar.number_input(
    "MTD Day Cutoff (1–31)",
    min_value=1, max_value=31, value=31,
    help="Only include transactions up to this day-of-month. Set 31 for full month.",
)

# Line Manager
all_lms = sorted(df["line_manager"].dropna().unique())
selected_lms = st.sidebar.multiselect("Line Manager", all_lms, default=[], placeholder="Select Line Managers (leave empty for All)")

# ABO
all_abos = sorted(df["abo"].dropna().unique())
selected_abos = st.sidebar.multiselect("ABO", all_abos, default=[], placeholder="Select ABOs (leave empty for All)")

# ─── Apply Filters ─────────────────────────────────────────────────────────────
fdf = df.copy()
fdf = fdf[(fdf["transaction_date"] >= start_date) & (fdf["transaction_date"] <= end_date)]
fdf = fdf[pd.to_datetime(fdf["transaction_date"]).dt.day <= mtd_day]

if selected_lms:
    fdf = fdf[fdf["line_manager"].isin(selected_lms)]
if selected_abos:
    fdf = fdf[fdf["abo"].isin(selected_abos)]

# ─── Revenue & RGM Calculation ─────────────────────────────────────────────────
def calc_metrics(data):
    rev_with_tax   = data["rev_with_tax"].sum()
    rev_excl_tax   = data["revenue_excl_tax"].sum()
    gross_cogs     = data.loc[data["bill_flag"] == "gross", "purchase_excl_tax"].sum()
    zrf_gross      = data.loc[data["bill_flag"] == "gross", "zrf_purchase_excl_tax"].sum()
    return_cogs    = data.loc[data["bill_flag"] == "return", "purchase_excl_tax"].sum()
    rgm = rev_excl_tax - (gross_cogs - zrf_gross) - return_cogs
    return rev_with_tax, rev_excl_tax, rgm

# ─── Header ────────────────────────────────────────────────────────────────────
st.title("📊 Summer Fest Dashboard")
st.caption(f"Data refreshes once daily · Last loaded: {datetime.now().strftime('%d %b %Y, %I:%M %p')}")

# ─── Tabs ──────────────────────────────────────────────────────────────────────
tab_dashboard, tab_targets, tab_achieve = st.tabs(["📈 Dashboard", "🎯 Target Setting", "🏆 Target vs Achievement"])

# ══════════════════════════════════════════════════════════════════════════════
#  TAB 1 — DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
with tab_dashboard:
    total_rev, total_rev_excl, total_rgm = calc_metrics(fdf)
    gm_pct = (total_rgm / total_rev_excl * 100) if total_rev_excl else 0

    # KPI Cards
    st.subheader("Key Metrics")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Revenue", f"₹{total_rev:,.0f}")
    k2.metric("Revenue Excl Tax", f"₹{total_rev_excl:,.0f}")
    k3.metric("RGM", f"₹{total_rgm:,.0f}")
    k4.metric("GM %", f"{gm_pct:.1f}%")
    k5.metric("Rows (filtered)", f"{len(fdf):,}")

    st.divider()

    # Monthly Comparison
    st.subheader("📅 Month-wise Comparison")
    fdf["month"] = pd.to_datetime(fdf["transaction_date"]).dt.to_period("M").astype(str)
    months = sorted(fdf["month"].unique())

    mcols = st.columns(len(months) if months else 1)
    for i, m in enumerate(months):
        mdata = fdf[fdf["month"] == m]
        m_rev, m_rev_excl, m_rgm = calc_metrics(mdata)
        m_gm = (m_rgm / m_rev_excl * 100) if m_rev_excl else 0
        with mcols[i]:
            st.markdown(f"**{m}**")
            st.metric("Revenue", f"₹{m_rev:,.0f}")
            st.metric("Revenue Excl Tax", f"₹{m_rev_excl:,.0f}")
            st.metric("RGM", f"₹{m_rgm:,.0f}")
            st.metric("GM %", f"{m_gm:.1f}%")

    st.divider()

    # Store-level Breakdown
    st.subheader("🏪 Store-wise Breakdown")
    store_group = (
        fdf.groupby("store_name")
        .apply(lambda g: pd.Series({
            "Revenue": g["rev_with_tax"].sum(),
            "Revenue Excl Tax": g["revenue_excl_tax"].sum(),
            "RGM": calc_metrics(g)[2],
            "Rows": len(g),
        }), include_groups=False)
        .sort_values("Revenue", ascending=False)
        .reset_index()
    )
    store_group["GM %"] = (store_group["RGM"] / store_group["Revenue Excl Tax"].replace(0, float("nan")) * 100).round(1)
    store_group["Revenue"]          = store_group["Revenue"].apply(lambda x: f"₹{x:,.0f}")
    store_group["Revenue Excl Tax"] = store_group["Revenue Excl Tax"].apply(lambda x: f"₹{x:,.0f}")
    store_group["RGM"]              = store_group["RGM"].apply(lambda x: f"₹{x:,.0f}")
    st.dataframe(store_group, use_container_width=True, hide_index=True)

    # Raw Data
    with st.expander("🗂️ View Raw Data"):
        st.dataframe(fdf, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2 — TARGET SETTING
# ══════════════════════════════════════════════════════════════════════════════
with tab_targets:
    from datetime import date

    st.subheader("🎯 May Target Setting — based on 15–29 Apr baseline")
    GROWTH = 0.20
    st.info(
        "**Logic:** Revenue from 15 Apr – 29 Apr (15 days) ÷ 15 = per-day run rate → × 31 = May baseline.  \n"
        f"**May Target = Baseline × {1 + GROWTH:.2f}** (i.e. {int(GROWTH*100)}% growth on baseline).  \n"
        "This window is chosen because every store had the Summer Fest SKU inventory in this period."
    )

    BASELINE_START = date(2026, 4, 15)
    BASELINE_END   = date(2026, 4, 29)
    BASELINE_DAYS  = 15           # 15th to 29th inclusive
    MAY_DAYS       = 31

    # Filter full dataset (df) for the baseline window — ignore sidebar filters
    baseline = df[
        (df["transaction_date"] >= BASELINE_START) &
        (df["transaction_date"] <= BASELINE_END)
    ].copy()

    if baseline.empty:
        st.warning("⚠️ No data found for 15–29 Apr yet. Targets will appear once that data is available.")
    else:
        # ── Overall summary ────────────────────────────────────────────────
        total_base_rev = baseline["rev_with_tax"].sum()
        per_day_rev    = total_base_rev / BASELINE_DAYS
        may_baseline   = per_day_rev * MAY_DAYS
        may_target     = may_baseline * (1 + GROWTH)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("15–29 Apr Revenue", f"₹{total_base_rev:,.0f}")
        c2.metric("Per-Day Revenue", f"₹{per_day_rev:,.0f}")
        c3.metric("May Baseline (×31)", f"₹{may_baseline:,.0f}")
        c4.metric("May Target (+20%)", f"₹{may_target:,.0f}")

        st.divider()

        # ── ABO-level target table ────────────────────────────────────────
        st.subheader("📋 ABO-wise May Targets")
        abo_targets = (
            baseline.groupby(["line_manager", "abo"])["rev_with_tax"]
            .sum()
            .reset_index()
            .rename(columns={"rev_with_tax": "baseline_revenue"})
        )
        abo_targets["per_day_revenue"] = abo_targets["baseline_revenue"] / BASELINE_DAYS
        abo_targets["may_baseline"]    = abo_targets["per_day_revenue"] * MAY_DAYS
        abo_targets["may_target"]      = abo_targets["may_baseline"] * (1 + GROWTH)

        # Sort by Line Manager then target descending
        abo_targets = abo_targets.sort_values(
            ["line_manager", "may_target"], ascending=[True, False]
        ).reset_index(drop=True)

        # Display-friendly formatting
        display_targets = abo_targets.copy()
        display_targets.columns = ["Line Manager", "ABO", "15-29 Apr Rev", "Per Day Rev", "May Baseline", "May Target (+20%)"]
        for col in ["15-29 Apr Rev", "Per Day Rev", "May Baseline", "May Target (+20%)"]:
            display_targets[col] = display_targets[col].apply(lambda x: f"₹{x:,.0f}")

        st.dataframe(display_targets, use_container_width=True, hide_index=True)

        st.divider()

        # ── Line-Manager rollup ───────────────────────────────────────────
        st.subheader("👔 Line Manager-wise May Targets")
        lm_targets = (
            abo_targets.groupby("line_manager")[["baseline_revenue", "per_day_revenue", "may_baseline", "may_target"]]
            .sum()
            .sort_values("may_target", ascending=False)
            .reset_index()
        )
        display_lm = lm_targets.copy()
        display_lm.columns = ["Line Manager", "15-29 Apr Rev", "Per Day Rev", "May Baseline", "May Target (+20%)"]
        for col in ["15-29 Apr Rev", "Per Day Rev", "May Baseline", "May Target (+20%)"]:
            display_lm[col] = display_lm[col].apply(lambda x: f"₹{x:,.0f}")

        st.dataframe(display_lm, use_container_width=True, hide_index=True)

        st.divider()

        # ── Store-wise targets ────────────────────────────────────────────
        st.subheader("🏪 Store-wise May Targets")
        store_targets = (
            baseline.groupby(["line_manager", "abo", "store_name"])["rev_with_tax"]
            .sum()
            .reset_index()
            .rename(columns={"rev_with_tax": "baseline_revenue"})
        )
        store_targets["per_day_revenue"] = store_targets["baseline_revenue"] / BASELINE_DAYS
        store_targets["may_baseline"]    = store_targets["per_day_revenue"] * MAY_DAYS
        store_targets["may_target"]      = store_targets["may_baseline"] * (1 + GROWTH)

        store_targets = store_targets.sort_values(
            ["line_manager", "abo", "may_target"], ascending=[True, True, False]
        ).reset_index(drop=True)

        display_stores = store_targets.copy()
        display_stores.columns = ["Line Manager", "ABO", "Store", "15-29 Apr Rev", "Per Day Rev", "May Baseline", "May Target (+20%)"]
        for col in ["15-29 Apr Rev", "Per Day Rev", "May Baseline", "May Target (+20%)"]:
            display_stores[col] = display_stores[col].apply(lambda x: f"₹{x:,.0f}")

        st.dataframe(display_stores, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
#  TAB 3 — TARGET vs ACHIEVEMENT
# ══════════════════════════════════════════════════════════════════════════════
with tab_achieve:
    from datetime import date

    # ── Month selector ─────────────────────────────────────────────────────
    contest_option = st.selectbox(
        "Select Contest Month",
        ["April 2026", "May 2026"],
        index=0,
    )

    if contest_option == "April 2026":
        CONTEST_MONTH_LABEL = "April"
        CONTEST_START = date(2026, 4, 1)
        CONTEST_END   = date(2026, 4, 30)
        CONTEST_DAYS  = 30
    else:
        CONTEST_MONTH_LABEL = "May"
        CONTEST_START = date(2026, 5, 1)
        CONTEST_END   = date(2026, 5, 31)
        CONTEST_DAYS  = 31

    # Target params (same baseline for both months)
    BASELINE_START_A = date(2026, 4, 15)
    BASELINE_END_A   = date(2026, 4, 29)
    BASELINE_DAYS_A  = 15
    TARGET_DAYS_A    = CONTEST_DAYS
    GROWTH_A         = 0.20

    PRIZE_1ST = 6500
    PRIZE_2ND = 3500

    st.subheader(f"🏆 {CONTEST_MONTH_LABEL} — Target vs Achievement")
    st.info(
        f"**Contest:** Top 2 ABOs under each Line Manager win prizes.  \n"
        f"🥇 1st Prize: **₹{PRIZE_1ST:,}**  |  🥈 2nd Prize: **₹{PRIZE_2ND:,}**  \n"
        f"⚠️ **Note:** An ABO will only qualify for the prize if they achieve at least **95%** of their Target.  \n"
        f"MTD Achievement % = Actual Revenue ÷ MTD Target × 100"
    )

    # ── Build targets ──────────────────────────────────────────────────────
    baseline_a = df[
        (df["transaction_date"] >= BASELINE_START_A) &
        (df["transaction_date"] <= BASELINE_END_A)
    ].copy()

    actuals_a = df[
        (df["transaction_date"] >= CONTEST_START) &
        (df["transaction_date"] <= CONTEST_END)
    ].copy()

    # Days elapsed
    today = date.today()
    if today > CONTEST_END:
        days_elapsed = CONTEST_DAYS
    elif today >= CONTEST_START:
        days_elapsed = (today - CONTEST_START).days  # today excluded (data < current_date)
    else:
        days_elapsed = 0

    if baseline_a.empty:
        st.warning("⚠️ Baseline data (15–29 Apr) not yet available.")
    elif actuals_a.empty and days_elapsed > 0:
        st.warning(f"⚠️ No actual sales data for {CONTEST_MONTH_LABEL} yet.")
    else:
        # --- ABO-level targets ---
        tgt = (
            baseline_a.groupby(["line_manager", "abo"])["rev_with_tax"]
            .sum().reset_index()
            .rename(columns={"rev_with_tax": "baseline_rev"})
        )
        tgt["target"] = (tgt["baseline_rev"] / BASELINE_DAYS_A) * TARGET_DAYS_A * (1 + GROWTH_A)
        tgt["mtd_target"] = (tgt["target"] / CONTEST_DAYS) * days_elapsed

        # --- ABO-level actuals ---
        act = (
            actuals_a.groupby(["line_manager", "abo"])["rev_with_tax"]
            .sum().reset_index()
            .rename(columns={"rev_with_tax": "actual"})
        )

        # --- Merge ---
        perf = tgt.merge(act, on=["line_manager", "abo"], how="left")
        perf["actual"] = perf["actual"].fillna(0)
        perf["mtd_achieve_pct"] = (perf["actual"] / perf["mtd_target"].replace(0, float("nan")) * 100).round(1).fillna(0)
        perf["full_achieve_pct"] = (perf["actual"] / perf["target"].replace(0, float("nan")) * 100).round(1).fillna(0)
        perf["mtd_gap"] = perf["actual"] - perf["mtd_target"].fillna(0)

        # --- Rank within each LM (by MTD achievement %) ---
        perf["rank"] = perf.groupby("line_manager")["mtd_achieve_pct"].rank(
            ascending=False, method="min"
        ).fillna(999).astype(int)

        perf["prize"] = perf["rank"].map({1: f"🥇 ₹{PRIZE_1ST:,}", 2: f"🥈 ₹{PRIZE_2ND:,}"}).fillna("")

        # ── Overall KPIs ──────────────────────────────────────────────────
        total_tgt     = perf["target"].sum()
        total_mtd_tgt = perf["mtd_target"].sum()
        total_act     = perf["actual"].sum()
        mtd_pct = (total_act / total_mtd_tgt * 100) if total_mtd_tgt else 0

        o1, o2, o3, o4, o5 = st.columns(5)
        o1.metric("Month Target", f"₹{total_tgt:,.0f}")
        o2.metric("MTD Target", f"₹{total_mtd_tgt:,.0f}")
        o3.metric("Actual", f"₹{total_act:,.0f}")
        o4.metric("MTD Achievement %", f"{mtd_pct:.1f}%")
        o5.metric("Days Elapsed", f"{days_elapsed} / {CONTEST_DAYS}")

        st.divider()

        # ── Leaderboard per Line Manager ──────────────────────────────────
        lm_list = sorted(perf["line_manager"].unique())

        for lm in lm_list:
            st.subheader(f"👔 {lm}")
            lm_data = perf[perf["line_manager"] == lm].sort_values("rank").copy()

            # LM-level totals
            lm_tgt     = lm_data["target"].sum()
            lm_mtd_tgt = lm_data["mtd_target"].sum()
            lm_act     = lm_data["actual"].sum()
            lm_pct = (lm_act / lm_mtd_tgt * 100) if lm_mtd_tgt else 0

            lc1, lc2, lc3, lc4 = st.columns(4)
            lc1.metric("Month Target", f"₹{lm_tgt:,.0f}")
            lc2.metric("MTD Target", f"₹{lm_mtd_tgt:,.0f}")
            lc3.metric("Actual", f"₹{lm_act:,.0f}")
            lc4.metric("MTD Achievement %", f"{lm_pct:.1f}%")

            # ABO table
            disp = lm_data[["rank", "abo", "target", "mtd_target", "actual", "mtd_achieve_pct", "mtd_gap", "prize"]].copy()
            disp.columns = ["Rank", "ABO", "Month Target", "MTD Target", "Actual", "MTD Ach %", "MTD Gap", "Prize"]
            disp["Month Target"] = disp["Month Target"].apply(lambda x: f"₹{x:,.0f}")
            disp["MTD Target"]   = disp["MTD Target"].apply(lambda x: f"₹{x:,.0f}")
            disp["Actual"]       = disp["Actual"].apply(lambda x: f"₹{x:,.0f}")
            disp["MTD Gap"]      = lm_data["mtd_gap"].apply(lambda x: f"₹{x:,.0f}")
            st.dataframe(disp, use_container_width=True, hide_index=True)

            st.divider()

        # ── Store-level achievement (collapsible) ─────────────────────────
        with st.expander("🏪 Store-wise Achievement"):
            s_tgt = (
                baseline_a.groupby(["line_manager", "abo", "store_name"])["rev_with_tax"]
                .sum().reset_index()
                .rename(columns={"rev_with_tax": "baseline_rev"})
            )
            s_tgt["target"]     = (s_tgt["baseline_rev"] / BASELINE_DAYS_A) * TARGET_DAYS_A * (1 + GROWTH_A)
            s_tgt["mtd_target"] = (s_tgt["target"] / CONTEST_DAYS) * days_elapsed

            s_act = (
                actuals_a.groupby(["line_manager", "abo", "store_name"])["rev_with_tax"]
                .sum().reset_index()
                .rename(columns={"rev_with_tax": "actual"})
            )

            s_perf = s_tgt.merge(s_act, on=["line_manager", "abo", "store_name"], how="left")
            s_perf["actual"] = s_perf["actual"].fillna(0)
            s_perf["mtd_achieve_pct"] = (s_perf["actual"] / s_perf["mtd_target"].replace(0, float("nan")) * 100).round(1)
            s_perf["mtd_gap"] = s_perf["actual"] - s_perf["mtd_target"]
            s_perf = s_perf.sort_values(
                ["line_manager", "abo", "mtd_achieve_pct"], ascending=[True, True, False]
            ).reset_index(drop=True)

            disp_s = s_perf[["line_manager", "abo", "store_name", "target", "mtd_target", "actual", "mtd_achieve_pct", "mtd_gap"]].copy()
            disp_s.columns = ["Line Manager", "ABO", "Store", "Month Target", "MTD Target", "Actual", "MTD Ach %", "MTD Gap"]
            disp_s["Month Target"] = disp_s["Month Target"].apply(lambda x: f"₹{x:,.0f}")
            disp_s["MTD Target"]   = disp_s["MTD Target"].apply(lambda x: f"₹{x:,.0f}")
            disp_s["Actual"]       = disp_s["Actual"].apply(lambda x: f"₹{x:,.0f}")
            disp_s["MTD Gap"]      = s_perf["mtd_gap"].apply(lambda x: f"₹{x:,.0f}")
            st.dataframe(disp_s, use_container_width=True, hide_index=True)