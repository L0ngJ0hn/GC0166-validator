"""
engine.py – GC0166 MDO/MDB/MEL/MIL Calculation Engine
=======================================================
Pure pandas/numpy module; zero Streamlit dependencies.

Key rules (from NESO GC0166 Calculation Logic PDF):
  - MDO/MDB = Energy offering/bidding in MWh
  - MEL/MIL = Power limits in MW
  - SoE tracked minute-by-minute via PN + BOA
  - Protected windows: SP-4 before contract → through delivery → SP+2 after
  - QR volume: protected before/after but RELEASED (visible for dispatch) during window
  - DFR volume: protected throughout (pre, during, post) — frequency response not instructed
  - MEL = MaxPower - sum(DFR_High_MW active)
  - MIL = MaxPower - sum(DFR_Low_MW active)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd


from .models import (
    AssetParams,
    PNSegment,
    BOAEvent,
    QRContract,
    DFRContract,
    MINS_PER_SP,
    MINS_PER_HOUR,
    SP_PRE_WINDOW,
    SP_POST_WINDOW,
    DFR_DURATION_MINS
)

# ---------------------------------------------------------------------------
# Timeline builder
# ---------------------------------------------------------------------------

def build_timeline(start_dt: pd.Timestamp, hours: float = 48.0) -> pd.DatetimeIndex:
    """Create a 1-minute DatetimeIndex covering `hours` hours, with one preceding prep minute."""
    n_mins = int(hours * 60) + 1  # +1 for the single prep minute before start_dt
    return pd.date_range(
        start=start_dt - pd.Timedelta(minutes=1),
        periods=n_mins,
        freq="1min",
    )


# ---------------------------------------------------------------------------
# SoE Baseline
# ---------------------------------------------------------------------------

def compute_soe_baseline(
    params: AssetParams,
    pn_segments: List[PNSegment],
    boa_events: List[BOAEvent],
    timeline: pd.DatetimeIndex,
) -> pd.Series:
    """
    Simulate the expected SoE (MWh) at each minute.
    SoE[t] = SoE[t-1] - (PN_MW[t] + BOA_MW[t]) / 60
    Export = positive MW → depletes SoE.
    Import = negative MW → charges SoE.
    Efficiency: on discharge (export) we lose energy; on charge we gain less.
    Clamped to [0, capacity_mwh].
    """
    n = len(timeline)
    eff = params.efficiency

    # Build MW arrays
    pn_mw = np.zeros(n)
    boa_mw = np.zeros(n)

    # Map PN segments onto timeline
    for seg in pn_segments:
        mask = (timeline >= seg.start_dt) & (timeline < seg.end_dt)
        pn_mw[mask] += seg.mw

    # Map BOA events onto timeline
    for boa in boa_events:
        mask = (timeline >= boa.start_dt) & (timeline < boa.end_dt)
        boa_mw[mask] += boa.mw

    total_mw = pn_mw + boa_mw  # combined dispatch signal

    # Iterative SoE integration
    soe = np.zeros(n)
    soe[0] = params.initial_soe_mwh

    for i in range(1, n):
        mw = total_mw[i]
        if mw >= 0:  # exporting (discharging)
            delta = mw / MINS_PER_HOUR  # energy delivered per minute
        else:  # importing (charging)
            delta = mw * eff / MINS_PER_HOUR  # effective energy stored per minute

        soe[i] = np.clip(soe[i - 1] - delta, 0.0, params.capacity_mwh)

    return pd.Series(soe, index=timeline, name="SoE_MWh"), pn_mw, boa_mw


# ---------------------------------------------------------------------------
# Protection volume computation
# ---------------------------------------------------------------------------

def _apply_qr_protection(
    timeline: pd.DatetimeIndex,
    contracts: List[QRContract],
    mdo_vol: np.ndarray,
    mdb_vol: np.ndarray,
    qr_mw_active: np.ndarray,
    qr_mwh_active: np.ndarray,
) -> None:
    """
    For each QR contract, accumulate protected volumes onto mdo_vol/mdb_vol arrays.
    PQR: protects MDO (export energy reserved).
    NQR: protects MDB (import energy reserved / headroom reserved).
    During delivery window: QR volume is RELEASED (visible for BM dispatch).
    """
    t_arr = timeline.values  # use native numpy datetime arrays instead of casting to int64
    for c in contracts:
        pre_s = c.protection_start.to_datetime64()
        del_s = c.delivery_start.to_datetime64()
        del_e = c.delivery_end.to_datetime64()
        post_e = c.protection_end.to_datetime64()

        # Active delivery window
        mask_delivery = (t_arr >= del_s) & (t_arr < del_e)
        qr_mw_active[mask_delivery] += c.mw
        qr_mwh_active[mask_delivery] += c.mwh

        # Pre-window OR post-window; delivery window itself is released
        mask = ((t_arr >= pre_s) & (t_arr < del_s)) | ((t_arr >= del_e) & (t_arr < post_e))
        if c.contract_type == "PQR":
            mdo_vol[mask] += c.mwh
        else:
            mdb_vol[mask] += c.mwh


def _apply_dfr_protection(
    timeline: pd.DatetimeIndex,
    contracts: List[DFRContract],
    mdo_vol: np.ndarray,
    mdb_vol: np.ndarray,
    mel_mw: np.ndarray,
    mil_mw: np.ndarray,
    dfr_mw_active: np.ndarray,
    dfr_mwh_active: np.ndarray,
) -> None:
    """
    For each DFR contract, protect energy AND reduce MEL/MIL throughout the full
    protected window (pre + during + post).
    High (export/DCL) → reduces MDO + reduces MEL.
    Low  (import/DCH) → reduces MDB + reduces MIL.
    MEL/MIL reduction applies only during the delivery window.
    """
    t_arr = timeline.values  # use native numpy datetime arrays instead of casting to int64
    for c in contracts:
        pre_s = c.protection_start.to_datetime64()
        post_e = c.protection_end.to_datetime64()
        del_s = c.delivery_start.to_datetime64()
        del_e = c.delivery_end.to_datetime64()

        mask_protection = (t_arr >= pre_s) & (t_arr < post_e)
        mask_delivery   = (t_arr >= del_s) & (t_arr < del_e)

        dfr_mw_active[mask_delivery] += c.mw
        dfr_mwh_active[mask_delivery] += c.protected_mwh

        if c.direction == "Export":  # DCL / export response
            mdo_vol[mask_protection] += c.protected_mwh
            mel_mw[mask_delivery]    += c.mw
        else:                        # Import (DCH) / import response
            mdb_vol[mask_protection] += c.protected_mwh
            mil_mw[mask_delivery]    += c.mw


def _apply_pn_protection(
    timeline: pd.DatetimeIndex,
    pn_segments: List[PNSegment],
    mdo_vol: np.ndarray,
    mdb_vol: np.ndarray,
) -> None:
    """
    As per grid code: PN energy volume must be protected 4 SPs (2 hours) before the PN.
    - Export PN (mw > 0) reduces MDO (energy reserved for discharge).
    - Import PN (mw < 0) reduces MDB (headroom reserved for charge).
    Released during the PN window itself (handled by baseline SoE).
    """
    t_arr = timeline.values  # use native numpy datetime arrays instead of casting to int64
    for seg in pn_segments:
        if seg.mw == 0:
            continue

        duration_hrs = (seg.end_dt - seg.start_dt).total_seconds() / 3600.0
        vol = abs(seg.mw) * duration_hrs

        pre_s = (seg.start_dt - pd.Timedelta(minutes=SP_PRE_WINDOW * MINS_PER_SP)).to_datetime64()
        pn_s  = seg.start_dt.to_datetime64()

        # Protect energy/headroom in the 4 SPs window before the PN starts
        mask = (t_arr >= pre_s) & (t_arr < pn_s)
        if seg.mw > 0:
            mdo_vol[mask] += vol
        else:
            mdb_vol[mask] += vol


# ---------------------------------------------------------------------------
# Main engine function
# ---------------------------------------------------------------------------

def run_engine(
    params: AssetParams,
    pn_segments: List[PNSegment],
    boa_events: List[BOAEvent],
    qr_contracts: List[QRContract],
    dfr_contracts: List[DFRContract],
    start_dt: Optional[pd.Timestamp] = None,
    hours: int = 48,
    end_dt: Optional[pd.Timestamp] = None
) -> pd.DataFrame:
    """
    Run the full GC0166 MDO/MDB/MEL/MIL calculation.

    Returns a DataFrame with 1-minute rows containing:
      Time, SP, SoE_pct, SoE_MWh, PN_MW, BOA_MW,
      MEL_MW, MIL_MW,
      QR_Protected_MDO_MWh, QR_Protected_MDB_MWh,
      DFR_Protected_MDO_MWh, DFR_Protected_MDB_MWh,
      Total_Protected_MDO_MWh, Total_Protected_MDB_MWh,
      MDO_MWh, MDB_MWh
    """
    if start_dt is None:
        start_dt = pd.Timestamp("today").normalize() + pd.Timedelta(hours=11)
    if end_dt is None:
        timeline = build_timeline(start_dt, hours=hours)
    else:
        timeline = pd.date_range(
            start=start_dt - pd.Timedelta(minutes=1),
            end=end_dt,
            freq="1min"
        )
    n = len(timeline)

    # --- SoE baseline ---
    soe_series, pn_mw, boa_mw = compute_soe_baseline(
        params, pn_segments, boa_events, timeline
    )
    soe = soe_series.values
    headroom = params.capacity_mwh - soe

    # --- Accumulator arrays ---
    qr_mdo_vol = np.zeros(n)
    qr_mdb_vol = np.zeros(n)
    qr_mw_active = np.zeros(n)
    qr_mwh_active = np.zeros(n)
    dfr_mdo_vol = np.zeros(n)
    dfr_mdb_vol = np.zeros(n)
    dfr_mw_active = np.zeros(n)
    dfr_mwh_active = np.zeros(n)
    pn_mdo_vol = np.zeros(n)      # PN specific MDO protection
    pn_mdb_vol = np.zeros(n)      # PN specific MDB protection
    mel_reduction = np.zeros(n)   # MW being removed from MEL (DFR High)
    mil_reduction = np.zeros(n)   # MW being removed from |MIL| (DFR Low)

    # --- Apply protection windows ---
    # Unpack multi-SP QR contracts into individual 30-min contracts
    unpacked_qr = []
    for c in qr_contracts:
        if c.duration_sps > 1:
            for i in range(c.duration_sps):
                new_start = c.delivery_start + pd.Timedelta(minutes=i * MINS_PER_SP)
                unpacked_qr.append(QRContract(
                    delivery_start=new_start,
                    mw=c.mw,
                    mwh=c.mwh,
                    contract_type=c.contract_type,
                    duration_sps=1
                ))
        else:
            unpacked_qr.append(c)

    _apply_qr_protection(timeline, unpacked_qr, qr_mdo_vol, qr_mdb_vol, qr_mw_active, qr_mwh_active)
    _apply_dfr_protection(
        timeline, dfr_contracts, dfr_mdo_vol, dfr_mdb_vol, mel_reduction, mil_reduction, dfr_mw_active, dfr_mwh_active
    )
    _apply_pn_protection(timeline, pn_segments, pn_mdo_vol, pn_mdb_vol)

    total_mdo_vol = qr_mdo_vol + dfr_mdo_vol + pn_mdo_vol
    total_mdb_vol = qr_mdb_vol + dfr_mdb_vol + pn_mdb_vol

    # --- MDO / MDB ---
    mdo = np.maximum(0.0, soe - total_mdo_vol)
    mdb = np.maximum(0.0, headroom - total_mdb_vol)
    mdb_signed = -mdb  # MDB convention is negative (import/charging)

    # --- MEL / MIL ---
    mel = np.maximum(0.0, params.max_power_mw - mel_reduction)
    mil = -np.maximum(0.0, params.max_power_mw - mil_reduction)

    # --- Settlement Period labels ---
    # UK BM: SP1 = 00:00-00:30, SP2 = 00:30-01:00, ... SP48 = 23:30-00:00
    # The day we use is the date of each timestamp
    mins_from_midnight = (timeline.hour * 60 + timeline.minute).values
    sp_numbers = mins_from_midnight // MINS_PER_SP + 1  # 1-indexed

    # --- Build DataFrame ---
    df = pd.DataFrame({
        "Time": timeline,
        "SP": sp_numbers,
        "SoE_pct": np.round(soe / params.capacity_mwh * 100, 4),
        "SoE_MWh": np.round(soe, 4),
        "PN_MW": np.round(pn_mw, 4),
        "PN_MWh": np.round(pn_mw / 60.0, 4),
        "BOA_MW": np.round(boa_mw, 4),
        "BOA_MWh": np.round(boa_mw / 60.0, 4),
        "DFR_MW": np.round(dfr_mw_active, 4),
        "DFR_MWh": np.round(dfr_mwh_active, 4),
        "QR_MW": np.round(qr_mw_active, 4),
        "QR_MWh": np.round(qr_mwh_active, 4),
        "MEL_MW": np.round(mel, 4),
        "MIL_MW": np.round(mil, 4),
        "QR_Protected_MDO_MWh": np.round(qr_mdo_vol, 4),
        "QR_Protected_MDB_MWh": np.round(qr_mdb_vol, 4),
        "DFR_Protected_MDO_MWh": np.round(dfr_mdo_vol, 4),
        "DFR_Protected_MDB_MWh": np.round(dfr_mdb_vol, 4),
        "PN_Protected_MDO_MWh": np.round(pn_mdo_vol, 4),
        "PN_Protected_MDB_MWh": np.round(pn_mdb_vol, 4),
        "Total_Protected_MDO_MWh": np.round(total_mdo_vol, 4),
        "Total_Protected_MDB_MWh": np.round(total_mdb_vol, 4),
        "MDO_MWh": np.round(mdo, 4),
        "MDB_MWh": np.round(mdb_signed, 4),
        "Headroom_MWh": np.round(headroom, 4),  # Physical headroom (Capacity - SoE)
        "Footroom_MWh": np.round(soe, 4),       # Physical footroom (SoE)
        "Total_Protected_MEL_MW": np.round(mel_reduction, 4),
        "Total_Protected_MIL_MW": np.round(mil_reduction, 4),
        "DFR_Protected_MEL_MW": np.round(mel_reduction, 4),
        "DFR_Protected_MIL_MW": np.round(mil_reduction, 4),
    })

    df = df.set_index("Time")
    return df
