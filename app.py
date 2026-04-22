"""
app.py – GC0166 MDO/MDB/MEL/MIL Validation Tool
================================================
Streamlit application providing:
  - Sidebar: asset parameters + dynamic event injectors
  - Main panel: KPI cards, dual-axis Plotly chart, data table, CSV export
  - Scenario loader: all 18 NESO worked examples
"""

import io
import pandas as pd
import numpy as np
import streamlit as st

from src.engine import run_engine
from src.state_utils import init_state, build_inputs_from_state
from src import components
from src import visualizations

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GC0166 MDO/MDB Validation Tool",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Custom CSS
# ─────────────────────────────────────────────────────────────────────────────
def apply_custom_css():
    import os
    css_path = os.path.join(os.path.dirname(__file__), "style.css")
    with open(css_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

apply_custom_css()

# ─────────────────────────────────────────────────────────────────────────────
# Execution
# ─────────────────────────────────────────────────────────────────────────────
init_state()
calc_btn, start_dt_from_sidebar = components.render_sidebar()

# Main Panel Header
st.markdown(
    "<h1 style='font-size:1.7rem;font-weight:700;color:#f0f6fc;margin-bottom:0.2rem;'>"
    "⚡ GC0166 MDO/MDB/MEL/MIL Validation Tool"
    "</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='color:#8b949e;font-size:0.85rem;margin-top:0;'>"
    "1-minute forward-looking State of Energy model · NESO GC0166 Grid Code"
    "</p>",
    unsafe_allow_html=True,
)

# Run Engine
if calc_btn:
    with st.spinner("Running calculation engine…"):
        params, pn_segs, boa_evts, qr_cnts, dfr_cnts = build_inputs_from_state()
        # Determine simulation length based on scenario name
        sim_hours = 48.0
        if st.session_state.scenario_loaded:
            prefix = st.session_state.scenario_loaded.split(".")[0]
            if prefix in ["1", "2", "3"]:
                sim_hours = 42.0
            elif prefix == "4":
                sim_hours = 6.5

        df = run_engine(
            params=params,
            pn_segments=pn_segs,
            boa_events=boa_evts,
            qr_contracts=qr_cnts,
            dfr_contracts=dfr_cnts,
            start_dt=pd.Timestamp(start_dt_from_sidebar),
            hours=sim_hours,
        )
        st.session_state.result_df = df
        
        # DEBUG: Show contract counts to verify engine received them
        with st.expander("🛠  Debug: Engine Inputs"):
            st.write(f"PN Segments: {len(pn_segs)}")
            st.write(f"BOA Events: {len(boa_evts)}")
            st.write(f"QR Contracts: {len(qr_cnts)}")
            st.write(f"DFR Contracts: {len(dfr_cnts)}")
            if len(qr_cnts) > 0:
                st.write("QR Contracts Detail:", qr_cnts)
            if len(dfr_cnts) > 0:
                st.write("DFR Contracts Detail:", dfr_cnts)

df = st.session_state.result_df

if df is not None and not df.empty:
    # ── CSV Export ───────────────────────────────────────────────────────
    col_dl1, col_dl2 = st.columns(2)
    scenario_tag = (st.session_state.scenario_loaded or "custom").replace(" ", "_").replace(".", "_")

    with col_dl1:
        csv_buf_full = io.BytesIO()
        df.reset_index().rename(columns={"Time": "Timestamp"}).to_csv(csv_buf_full, index=False)
        csv_buf_full.seek(0)
        st.download_button(
            label="⬇  Download Full Data (1-min)",
            data=csv_buf_full,
            file_name=f"GC0166_{scenario_tag}_full_1min.csv",
            mime="text/csv",
            width="stretch",
        )

    # Calculate SP-aggregated (30-min) for both download and UI
    # Use .last() for state/energy to reflect end-of-period values (aligns with tests)
    # but use .mean() for BOA power to reflect average dispatch across the SP.
    agg_dict = {c: "last" for c in df.columns}
    agg_dict["PN_MW"] = "mean"
    agg_dict["PN_MWh"] = "sum"
    agg_dict["BOA_MW"] = "mean"
    agg_dict["BOA_MWh"] = "sum"
    agg_dict["DFR_MW"] = "mean"
    agg_dict["DFR_MWh"] = "mean"
    agg_dict["QR_MW"] = "mean"
    agg_dict["QR_MWh"] = "mean"
    
    sp_df = df.resample("30min").agg(agg_dict).reset_index().rename(columns={"Time": "Timestamp"})
    sp_df = sp_df.sort_values("Timestamp")
    num_cols = sp_df.select_dtypes(include=[np.number]).columns
    sp_df[num_cols] = sp_df[num_cols].round(2)

    with col_dl2:
        csv_buf_sp = io.BytesIO()
        sp_df.to_csv(csv_buf_sp, index=False)
        csv_buf_sp.seek(0)
        st.download_button(
            label="⬇  Download Summary (30-min SP)",
            data=csv_buf_sp,
            file_name=f"GC0166_{scenario_tag}_summary_30min.csv",
            mime="text/csv",
            width="stretch",
        )

    st.markdown("---")

    # ── Visualisation ────────────────────────────────────────────────────
    full_range = [df.index.min(), df.index.max()]
    
    st.markdown("<div class='section-header'>📂 Contractual MW Profile (Context)</div>", unsafe_allow_html=True)
    visualizations.plot_contract_profile(df, st.session_state.qr_list, st.session_state.dfr_list, full_range)

    st.markdown("<div class='section-header'>📊 Power Dispatch (MW)</div>", unsafe_allow_html=True)
    visualizations.plot_power_dispatch(df, full_range)

    st.markdown("<div class='section-header'>📉 Energy Limits (MWh)</div>", unsafe_allow_html=True)
    visualizations.plot_energy_limits(df, full_range)

    st.markdown("<div class='section-header'>🔋 State of Energy & Operating Margins (MWh)</div>", unsafe_allow_html=True)
    visualizations.plot_soe_margins(df, st.session_state.capacity_mwh, full_range)

    # ── Data Table ───────────────────────────────────────────────────────
    st.markdown("<div class='section-header'>📋 Output Data</div>", unsafe_allow_html=True)
    tab_sum, tab_full, tab_mdo_mdb, tab_mel_mil = st.tabs([
        "Summary View", "Full Minute Data", "MDO/MDB Protected Volumes", "MEL/MIL Protected Powers"
    ])

    with tab_sum:
        # Remove protected data columns and SoE_pct from the summary view
        sp_summary_df = sp_df[[c for c in sp_df.columns if "Protected" not in c and c != "SoE_pct"]]
        st.dataframe(sp_summary_df, width="stretch", height=400, hide_index=True)

    with tab_full:
        # Display with Timestamp pinned to the left, remove protected volumes/powers,
        # and move MDO/MDB after MEL/MIL
        full_df = df.reset_index().rename(columns={"Time": "Timestamp"})
        num_cols = full_df.select_dtypes(include=[np.number]).columns
        full_df[num_cols] = full_df[num_cols].round(3)
        full_cols = [
            "Timestamp", "SP", "SoE_pct", "SoE_MWh", "PN_MW", "PN_MWh", "BOA_MW", "BOA_MWh",
            "DFR_MW", "DFR_MWh", "QR_MW", "QR_MWh", 
            "MEL_MW", "MIL_MW", "MDO_MWh", "MDB_MWh", "Headroom_MWh", "Footroom_MWh"
        ]
        # Filter for existing columns only in case of slight variations
        full_cols = [c for c in full_cols if c in full_df.columns]
        st.dataframe(full_df[full_cols], width="stretch", height=400, hide_index=True)

    with tab_mdo_mdb:
        # Reordered: Timestamp, SoE, MDO, MDB, Total Protected, Individual Services
        prot_cols = [
            "Timestamp", "SoE_MWh", "MDO_MWh", "MDB_MWh", 
            "Total_Protected_MDO_MWh", "Total_Protected_MDB_MWh",
            "QR_Protected_MDO_MWh", "QR_Protected_MDB_MWh", 
            "DFR_Protected_MDO_MWh", "DFR_Protected_MDB_MWh", 
            "PN_Protected_MDO_MWh", "PN_Protected_MDB_MWh",
        ]
        mdo_display_df = df.reset_index().rename(columns={"Time": "Timestamp"})[prot_cols]
        num_cols = mdo_display_df.select_dtypes(include=[np.number]).columns
        mdo_display_df[num_cols] = mdo_display_df[num_cols].round(3)
        st.dataframe(mdo_display_df, width="stretch", height=400, hide_index=True)

    with tab_mel_mil:
        # Reordered: Timestamp, SoE, MEL, MIL, Total Protected Power, Individual Services
        mel_cols = [
            "Timestamp", "SoE_MWh", "MEL_MW", "MIL_MW", 
            "Total_Protected_MEL_MW", "Total_Protected_MIL_MW",
            "DFR_Protected_MEL_MW", "DFR_Protected_MIL_MW"
        ]
        st.caption("Power limits (MEL/MIL) reflecting DFR contract reductions.")
        mel_display_df = df.reset_index().rename(columns={"Time": "Timestamp"})[mel_cols]
        num_cols = mel_display_df.select_dtypes(include=[np.number]).columns
        mel_display_df[num_cols] = mel_display_df[num_cols].round(3)
        st.dataframe(mel_display_df, width="stretch", height=400, hide_index=True)

else:
    # Welcome / empty state
    st.markdown(
        """
<div style="text-align:center;padding:4rem 2rem;background:#161b22;border:1px solid #21262d; border-radius:12px;margin-top:2rem;">
  <div style="font-size:3rem;margin-bottom:1rem;">⚡</div>
  <h2 style="color:#f0f6fc;font-weight:600;margin-bottom:0.5rem;">Ready to Calculate</h2>
  <p style="color:#8b949e;max-width:500px;margin:0 auto 1.5rem auto;">
    Configure your asset parameters and events in the sidebar, or load one of the
    <strong style="color:#58a6ff;">18 NESO worked example scenarios</strong>,
    then click <strong style="color:#3fb950;">Calculate</strong> to run the GC0166 engine.
  </p>
  <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
    <div style="background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:12px 20px;min-width:130px;">
      <div style="font-size:0.65rem;color:#8b949e;text-transform:uppercase;letter-spacing:.08em;">Scenarios</div>
      <div style="font-size:1.5rem;font-weight:700;color:#58a6ff;">18</div>
    </div>
    <div style="background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:12px 20px;min-width:130px;">
      <div style="font-size:0.65rem;color:#8b949e;text-transform:uppercase;letter-spacing:.08em;">Resolution</div>
      <div style="font-size:1.5rem;font-weight:700;color:#3fb950;">1 min</div>
    </div>
    <div style="background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:12px 20px;min-width:130px;">
      <div style="font-size:0.65rem;color:#8b949e;text-transform:uppercase;letter-spacing:.08em;">Window</div>
      <div style="font-size:1.5rem;font-weight:700;color:#d29922;">48 h</div>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

# Footer
st.markdown(
    """
<div style="margin-top:3rem;padding-top:1rem;border-top:1px solid #21262d; text-align:center;color:#484f58;font-size:0.72rem;">
GC0166 Validation Tool · NESO Grid Code Changes · Protected Period: SP−4 → SP+2
</div>
""",
    unsafe_allow_html=True,
)
