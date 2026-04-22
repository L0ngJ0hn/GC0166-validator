import streamlit as st
import pandas as pd
from datetime import datetime, time as dtime
from .models import AssetParams, PNSegment, BOAEvent, QRContract, DFRContract
from .scenarios import get_scenario

def init_state():
    """Initialise session state variables if they don't exist."""
    defaults = {
        "capacity_mwh": 100.0,
        "max_power_mw": 100.0,
        "efficiency_pct": 100.0,
        "initial_soe_pct": 50.0,
        "start_date": datetime(2024, 4, 10, 11, 0),
        "hours": 48,
        "pn_list": [],
        "boa_list": [],
        "qr_list": [],
        "dfr_list": [],
        "result_df": None,
        "scenario_loaded": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def load_scenario(name: str):
    """Populate session state from a scenario definition."""
    params, pn_segs, boa_evts, qr_cnts, dfr_cnts, start_dt, label, desc = get_scenario(name)
    st.session_state.capacity_mwh = params.capacity_mwh
    st.session_state.max_power_mw = params.max_power_mw
    st.session_state.efficiency_pct = params.efficiency_pct
    st.session_state.initial_soe_pct = params.initial_soe_pct
    st.session_state.start_date = start_dt.to_pydatetime()

    st.session_state.pn_list = [
        {"start": s.start_dt.to_pydatetime(), "end": s.end_dt.to_pydatetime(), "mw": s.mw}
        for s in pn_segs
    ]
    st.session_state.boa_list = [
        {"start": b.start_dt.to_pydatetime(), "end": b.end_dt.to_pydatetime(), "mw": b.mw}
        for b in boa_evts
    ]
    st.session_state.qr_list = [
        {
            "start": q.delivery_start.to_pydatetime(),
            "mw": q.mw,
            "mwh": q.mwh,
            "type": q.contract_type,
            "duration_sps": q.duration_sps,
        }
        for q in qr_cnts
    ]
    st.session_state.dfr_list = [
        {
            "start": d.delivery_start.to_pydatetime(),
            "mw": d.mw,
            "direction": d.direction,
            "service_type": d.service_type,
            "duration_sps": d.duration_sps,
        }
        for d in dfr_cnts
    ]
    st.session_state.scenario_loaded = name
    st.session_state.result_df = None

def build_inputs_from_state():
    """Converts UI session state into engine-compatible models."""
    params = AssetParams(
        capacity_mwh=st.session_state.capacity_mwh,
        max_power_mw=st.session_state.max_power_mw,
        efficiency_pct=st.session_state.efficiency_pct,
        initial_soe_pct=st.session_state.initial_soe_pct,
    )
    pn_segs = [
        PNSegment(
            start_dt=pd.Timestamp(p["start"]), 
            end_dt=pd.Timestamp(p["end"]), 
            mw=p["mw"]
        )
        for p in st.session_state.pn_list
    ]
    boa_evts = [
        BOAEvent(
            start_dt=pd.Timestamp(b["start"]), 
            end_dt=pd.Timestamp(b["end"]), 
            mw=b["mw"]
        )
        for b in st.session_state.boa_list
    ]
    qr_cnts = [
        QRContract(
            delivery_start=pd.Timestamp(q["start"]),
            mw=q["mw"],
            mwh=q["mwh"],
            contract_type=q["type"],
            duration_sps=q["duration_sps"]
        )
        for q in st.session_state.qr_list
    ]
    dfr_cnts = [
        DFRContract(
            delivery_start=pd.Timestamp(d["start"]),
            mw=d["mw"],
            direction=d["direction"],
            service_type=d["service_type"],
            duration_sps=d["duration_sps"]
        )
        for d in st.session_state.dfr_list
    ]
    return params, pn_segs, boa_evts, qr_cnts, dfr_cnts
