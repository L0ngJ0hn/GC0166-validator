import streamlit as st
import pandas as pd
from datetime import datetime, time as dtime
from .models import DFR_DURATION_MINS
from .scenarios import get_scenario_names
from .state_utils import load_scenario

def render_sidebar():
    """
    Renders the sidebar with scenario loader, asset parameters, and event forms.
    Returns the calculate button state and current start datetime.
    """
    with st.sidebar:
        st.markdown("## ⚡ GC0166 Validation Tool")
        st.markdown("---")

        # ── Scenario Loader ────────────────────────────────────────────────────
        st.markdown("### 📂 Load Scenario")
        sel_scenario = st.selectbox(
            "Worked Example",
            options=["(custom)"] + get_scenario_names(),
            key="scenario_select",
            label_visibility="collapsed",
        )
        if st.button("Load Scenario", width="stretch", type="primary"):
            if sel_scenario != "(custom)":
                load_scenario(sel_scenario)
                st.success(f"Loaded: {sel_scenario}")
                st.rerun()

        if st.session_state.scenario_loaded:
            st.caption(f"✅ Active: {st.session_state.scenario_loaded}")

        st.markdown("---")

        # ── Asset Parameters ───────────────────────────────────────────────────
        st.markdown("### 🔋 Asset Parameters")
        st.session_state.capacity_mwh = st.number_input(
            "Max Capacity (MWh)", value=float(st.session_state.capacity_mwh),
            min_value=0.1, step=10.0, format="%.1f",
        )
        st.session_state.max_power_mw = st.number_input(
            "Max Power (MW)", value=float(st.session_state.max_power_mw),
            min_value=0.1, step=10.0, format="%.1f",
        )
        st.session_state.efficiency_pct = st.number_input(
            "Efficiency (%)", value=float(st.session_state.efficiency_pct),
            min_value=50.0, max_value=100.0, step=1.0, format="%.1f",
        )
        st.session_state.initial_soe_pct = st.number_input(
            "Initial SoE (%)", value=float(st.session_state.initial_soe_pct),
            min_value=0.0, max_value=100.0, step=5.0, format="%.1f",
        )

        # ── Simulation window ──────────────────────────────────────────────────
        st.markdown("### ⏱ Simulation Window")
        st.session_state.start_date = st.date_input(
            "Start Date",
            value=st.session_state.start_date,
            key="start_date_input",
        )
        _start_time = st.time_input(
            "Start Time",
            value=dtime(11, 0),
            key="start_time_input",
            step=1800,
        )
        st.session_state.hours = st.number_input(
            "Window (hours)", value=int(st.session_state.hours),
            min_value=1, max_value=72, step=1,
        )

        # Combine date + time into a single datetime
        _sd = st.session_state.start_date
        if isinstance(_sd, datetime):
            _sd = _sd.date()
        start_dt = datetime.combine(_sd, _start_time)

        st.markdown("---")

        # ── PN Profile ────────────────────────────────────────────────────────
        st.markdown("### 📈 Physical Notifications (PN)")
        with st.expander("➕ Add PN Segment", expanded=False):
            pn_start = dt_selector("PN Start", start_dt, "pn_s")
            pn_end   = dt_selector("PN End", start_dt + pd.Timedelta(hours=1).to_pytimedelta(), "pn_e")
            pn_mw    = st.number_input("PN MW (+ve=export)", value=0.0, step=5.0, format="%.1f", key="pn_mw_in")
            if st.button("Add PN", width="stretch"):
                from .models import PNSegment
                try:
                    # Validate by creating a temporary object with keyword arguments for Pydantic V2
                    PNSegment(start_dt=pd.Timestamp(pn_start), end_dt=pd.Timestamp(pn_end), mw=pn_mw)
                    st.session_state.pn_list.append({"start": pn_start, "end": pn_end, "mw": pn_mw})
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

        for i, pn in enumerate(st.session_state.pn_list):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.caption(f"PN {i+1}: {pn['mw']:+.0f} MW  {pn['start'].strftime('%Y-%m-%d %H:%M')}→{pn['end'].strftime('%H:%M')}")
            with c2:
                if st.button("✕", key=f"del_pn_{i}"):
                    st.session_state.pn_list.pop(i)
                    st.rerun()

        # ── BOA Events ────────────────────────────────────────────────────────
        st.markdown("### ⚡ BOA Instructions")
        with st.expander("➕ Add BOA Event", expanded=False):
            boa_start = dt_selector("BOA Start", start_dt, "boa_s")
            boa_end   = dt_selector("BOA End", start_dt + pd.Timedelta(minutes=30).to_pytimedelta(), "boa_e")
            boa_mw    = st.number_input("BOA MW (+ve=export/discharge, -ve=import/charge)", value=0.0, step=10.0, format="%.1f", key="boa_mw_in")
            if st.button("Add BOA", width="stretch"):
                from .models import BOAEvent
                try:
                    # Validate by creating a temporary object with keyword arguments for Pydantic V2
                    BOAEvent(start_dt=pd.Timestamp(boa_start), end_dt=pd.Timestamp(boa_end), mw=boa_mw)
                    st.session_state.boa_list.append({"start": boa_start, "end": boa_end, "mw": boa_mw})
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

        for i, b in enumerate(st.session_state.boa_list):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.caption(f"BOA {i+1}: {b['mw']:+.0f} MW  {b['start'].strftime('%Y-%m-%d %H:%M')}→{b['end'].strftime('%H:%M')}")
            with c2:
                if st.button("✕", key=f"del_boa_{i}"):
                    st.session_state.boa_list.pop(i)
                    st.rerun()

        # ── QR Contracts ──────────────────────────────────────────────────────
        st.markdown("### 🔁 Quick Reserve (QR) Contracts")
        with st.expander("➕ Add QR Contract", expanded=False):
            qr_type     = st.selectbox("Type", ["PQR", "NQR"], key="qr_type_sel")
            qr_start    = dt_selector("Delivery Start", start_dt, "qr_s")
            qr_dur      = st.number_input("Duration (SPs, 1 SP=30min)", value=1, min_value=1, max_value=16, key="qr_dur")
            qr_mw       = st.number_input("MW", value=20.0, step=5.0, format="%.1f", key="qr_mw")
            qr_mwh      = st.number_input("MWh (protected volume)", value=10.0, step=1.0, format="%.2f", key="qr_mwh")
            if st.button("Add QR", width="stretch"):
                st.session_state.qr_list.append({
                    "start": qr_start, "mw": qr_mw, "mwh": qr_mwh,
                    "type": qr_type, "duration_sps": int(qr_dur),
                })
                st.rerun()

        for i, q in enumerate(st.session_state.qr_list):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.caption(f"{q['type']} {i+1}: {q['mw']:.0f}MW/{q['mwh']:.1f}MWh  @{q['start'].strftime('%Y-%m-%d %H:%M')} ({q['duration_sps']}SP)")
            with c2:
                if st.button("✕", key=f"del_qr_{i}"):
                    st.session_state.qr_list.pop(i)
                    st.rerun()

        # ── DFR Contracts ─────────────────────────────────────────────────────
        st.markdown("### 🌊 DFR / Response Contracts")
        with st.expander("➕ Add DFR Contract", expanded=False):
            dfr_service  = st.selectbox("Service", ["DC", "DM", "DR"], key="dfr_service_sel",
                                         help="DC=Dynamic Containment (15min), DM=Moderation (30min), DR=Regulation (60min)")
            dfr_dir      = st.selectbox("Direction", ["Low Frequency (DCL/Export)", "High Frequency (DCH/Import)"], key="dfr_dir_sel")
            dfr_start    = dt_selector("Delivery Start (EFA block start)", start_dt, "dfr_s")
            dfr_dur      = st.number_input("Duration (SPs, 8SPs=4h standard)", value=8, min_value=1, max_value=48, key="dfr_dur")
            dfr_mw       = st.number_input("MW", value=50.0, step=5.0, format="%.1f", key="dfr_mw")
            _dfr_vol     = dfr_mw * DFR_DURATION_MINS[dfr_service] / 60
            st.caption(f"Protected volume: **{_dfr_vol:.2f} MWh**")
            if st.button("Add DFR", width="stretch"):
                direction = "Export" if dfr_dir.startswith("Low") else "Import"
                st.session_state.dfr_list.append({
                    "start": dfr_start, "mw": dfr_mw, "direction": direction,
                    "service_type": dfr_service, "duration_sps": int(dfr_dur),
                })
                st.rerun()

        for i, d in enumerate(st.session_state.dfr_list):
            c1, c2 = st.columns([4, 1])
            with c1:
                vol = d["mw"] * DFR_DURATION_MINS[d["service_type"]] / 60
                st.caption(f"{d['service_type']}{d['direction'][0]} {i+1}: {d['mw']:.0f}MW/{vol:.1f}MWh @{d['start'].strftime('%Y-%m-%d %H:%M')}")
            with c2:
                if st.button("✕", key=f"del_dfr_{i}"):
                    st.session_state.dfr_list.pop(i)
                    st.rerun()

        st.markdown("---")
        calc_btn = st.button("▶ Calculate", width="stretch", type="primary")
        return calc_btn, start_dt

def dt_selector(label, value, key):
    """Helper to display date and time inputs side-by-side and return a datetime."""
    c1, c2 = st.columns(2)
    d = c1.date_input(f"{label} Date", value=value.date(), key=f"{key}_date")
    t = c2.time_input(f"{label} Time", value=value.time(), key=f"{key}_time", step=300)
    return datetime.combine(d, t)
