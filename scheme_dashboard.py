"""
Scheme Dashboard Tracker
"""

import streamlit as st
import pandas as pd
import plotly.express as px


# PAGE CONFIG

st.set_page_config(
    page_title="Scheme Dashboard Tracker",
    page_icon="📊",
    layout="wide",
)

NOT_QUALIFIED = "Not qualified"

EXPECTED_COLS = [
    "Partner ID", "Partner Name", "Clients", "Total SIP Amount",
    "SIP Debit Clients", "SIP Debit Amount", "Actual ₹ Debited So Far",
    "Slab", "Slab #", "Hampers", "Slab (debit-confirmed)",
    "Hampers (debit-confirmed)", "RM Email", "Branch", "Group",
    "RM Name", "Gap", "Branch Name", "Cluster",
]

NUMERIC_COLS = [
    "Clients", "Total SIP Amount", "SIP Debit Clients", "SIP Debit Amount",
    "Actual ₹ Debited So Far", "Slab #", "Gap",
]


# DATA LOADING

# OPTION A (simplest): Publish the Google Sheet to the web as CSV
#   File > Share > Publish to web > select the sheet/tab > CSV
#   Paste that link below as SHEET_CSV_URL.
#
# OPTION B (private sheet, no publishing needed): use a Google service
#   account. See the commented `load_via_gspread()` function below and
#   store credentials in st.secrets["gcp_service_account"].

SHEET_CSV_URL = st.secrets.get("SHEET_CSV_URL", "") if hasattr(st, "secrets") else ""


@st.cache_data(ttl=300, show_spinner="Fetching latest scheme data...")
def load_data(csv_url: str) -> pd.DataFrame:
    df = pd.read_csv(csv_url)
    df.columns = [c.strip() for c in df.columns]

    # Keep only expected columns that actually exist (tolerant to minor
    # header drift), and coerce numerics.
    present_numeric = [c for c in NUMERIC_COLS if c in df.columns]
    for col in present_numeric:
        df[col] = (
            df[col].astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("₹", "", regex=False)
            .str.strip()
        )
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["Slab", "Slab (debit-confirmed)", "Cluster", "Branch Name",
                "Branch", "RM Name", "Group", "Partner Name"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    return df


# --- OPTION B: private sheet via service account (uncomment to use) ---
# import gspread
# from google.oauth2.service_account import Credentials
#
# @st.cache_data(ttl=300, show_spinner="Fetching latest scheme data...")
# def load_via_gspread(sheet_key: str, worksheet_name: str) -> pd.DataFrame:
#     scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
#     creds = Credentials.from_service_account_info(
#         st.secrets["gcp_service_account"], scopes=scopes
#     )
#     gc = gspread.authorize(creds)
#     ws = gc.open_by_key(sheet_key).worksheet(worksheet_name)
#     records = ws.get_all_records()
#     return pd.DataFrame(records)



# LOAD DATA

st.title("📊 Scheme Dashboard Tracker")

if not SHEET_CSV_URL:
    st.warning(
        "No sheet connected yet. Add your published-CSV link to "
        "`.streamlit/secrets.toml` as `SHEET_CSV_URL = \"...\"`, "
        "or swap in the `load_via_gspread()` function for a private sheet.",
        icon="⚠️",
    )
    uploaded = st.file_uploader("...or upload the sheet as CSV to preview the dashboard", type="csv")
    if uploaded is None:
        st.stop()
    raw_df = pd.read_csv(uploaded)
    raw_df.columns = [c.strip() for c in raw_df.columns]
else:
    raw_df = load_data(SHEET_CSV_URL)

missing_cols = [c for c in EXPECTED_COLS if c not in raw_df.columns]
if missing_cols:
    st.info(f"Note: these expected columns weren't found in the sheet and will be skipped: {missing_cols}")

df = raw_df.copy()


# SIDEBAR FILTERS (cascading: Cluster -> Branch -> RM)

st.sidebar.header("🔍 Filters")

def multiselect_filter(label, col, frame):
    if col not in frame.columns:
        return frame, []
    options = sorted(frame[col].dropna().unique().tolist())
    selected = st.sidebar.multiselect(label, options, default=[])
    if selected:
        frame = frame[frame[col].isin(selected)]
    return frame, selected

filtered_df = df.copy()
filtered_df, sel_cluster = multiselect_filter("Cluster", "Cluster", filtered_df)
filtered_df, sel_branch = multiselect_filter("Branch Name", "Branch Name", filtered_df)
filtered_df, sel_rm = multiselect_filter("RM Name", "RM Name", filtered_df)

if st.sidebar.button("🔄 Reset filters"):
    st.rerun()

st.sidebar.caption(f"Showing **{len(filtered_df):,}** of **{len(df):,}** partner rows")


# KPI CARDS

def qualified_count(frame, col):
    if col not in frame.columns:
        return 0
    return int((frame[col].str.strip().str.lower() != NOT_QUALIFIED.lower()).sum())

total_partners = len(filtered_df)
slab_qualified = qualified_count(filtered_df, "Slab")
slab_debit_confirmed_qualified = qualified_count(filtered_df, "Slab (debit-confirmed)")
conversion_rate = (
    (slab_debit_confirmed_qualified / slab_qualified * 100) if slab_qualified else 0
)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Partners (filtered)", f"{total_partners:,}")
k2.metric("Qualified — Slab", f"{slab_qualified:,}")
k3.metric("Qualified — Slab (Debit-Confirmed)", f"{slab_debit_confirmed_qualified:,}")
k4.metric("Debit Confirmation Rate", f"{conversion_rate:.1f}%")

st.divider()


# INSIGHTS — charts

st.subheader("📈 Insights")

c1, c2 = st.columns(2)

with c1:
    if "Slab" in filtered_df.columns:
        slab_dist = (
            filtered_df["Slab"]
            .value_counts()
            .reset_index()
        )
        slab_dist.columns = ["Slab", "Count"]
        fig1 = px.bar(
            slab_dist, x="Slab", y="Count", text="Count",
            title="Slab Distribution (Provisional)", color="Slab",
        )
        fig1.update_layout(showlegend=False)
        st.plotly_chart(fig1, use_container_width=True)

with c2:
    if "Slab (debit-confirmed)" in filtered_df.columns:
        slab_dc_dist = (
            filtered_df["Slab (debit-confirmed)"]
            .value_counts()
            .reset_index()
        )
        slab_dc_dist.columns = ["Slab (Debit-Confirmed)", "Count"]
        fig2 = px.bar(
            slab_dc_dist, x="Slab (Debit-Confirmed)", y="Count", text="Count",
            title="Slab Distribution (Debit-Confirmed)", color="Slab (Debit-Confirmed)",
        )
        fig2.update_layout(showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

# Branch / Cluster level qualification summary — flags branches where
# provisional qualification is running well ahead of confirmed debits,
# useful for follow-up calls before payout.
if {"Branch Name", "Slab", "Slab (debit-confirmed)"}.issubset(filtered_df.columns):
    branch_summary = (
        filtered_df.assign(
            slab_ok=(filtered_df["Slab"].str.strip().str.lower() != NOT_QUALIFIED.lower()),
            slab_dc_ok=(filtered_df["Slab (debit-confirmed)"].str.strip().str.lower() != NOT_QUALIFIED.lower()),
        )
        .groupby("Branch Name")
        .agg(Partners=("Partner ID", "count"), Qualified_Slab=("slab_ok", "sum"),
             Qualified_Debit_Confirmed=("slab_dc_ok", "sum"))
        .reset_index()
    )
    branch_summary["Gap (Qualified but not yet debit-confirmed)"] = (
        branch_summary["Qualified_Slab"] - branch_summary["Qualified_Debit_Confirmed"]
    )
    branch_summary = branch_summary.sort_values(
        "Gap (Qualified but not yet debit-confirmed)", ascending=False
    )

    st.markdown("**Branches with the biggest gap between provisional and debit-confirmed qualification**")
    st.dataframe(branch_summary, use_container_width=True, hide_index=True)

    top_gap = branch_summary.iloc[0] if not branch_summary.empty else None
    if top_gap is not None and top_gap["Gap (Qualified but not yet debit-confirmed)"] > 0:
        st.caption(
            f"💡 **{top_gap['Branch Name']}** has "
            f"{int(top_gap['Gap (Qualified but not yet debit-confirmed)'])} partner(s) "
            f"who qualify on paper but whose SIP debits haven't come through yet — "
            f"worth a nudge to those RMs before the scheme window closes."
        )

st.divider()


# DETAIL TABLE — selected RM(s)

st.subheader("📋 Partner-Level Detail")

if sel_rm:
    st.caption(f"Filtered to RM(s): {', '.join(sel_rm)}")
else:
    st.caption("No RM selected in the sidebar — showing all rows matching the Cluster/Branch filters. Pick an RM to narrow further.")

display_cols = [c for c in EXPECTED_COLS if c in filtered_df.columns]
st.dataframe(
    filtered_df[display_cols].sort_values(
        by="RM Name" if "RM Name" in display_cols else display_cols[0]
    ),
    use_container_width=True,
    hide_index=True,
)

csv_out = filtered_df[display_cols].to_csv(index=False).encode("utf-8")
st.download_button(
    "⬇️ Download filtered data as CSV",
    data=csv_out,
    file_name="scheme_dashboard_filtered.csv",
    mime="text/csv",
)
