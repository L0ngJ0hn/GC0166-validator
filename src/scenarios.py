"""
scenarios.py – Pure data module for loading GC0166 worked example scenarios.
No UI framework dependencies; uses functools.lru_cache for caching.
"""
import json
import os
from functools import lru_cache
from typing import Dict, List, Tuple

import pandas as pd

from .models import (
    AssetParams,
    BOAEvent,
    DFRContract,
    PNSegment,
    QRContract,
)

# Type alias for a fully-parsed scenario tuple
ScenarioDef = Tuple[
    AssetParams,
    List[PNSegment],
    List[BOAEvent],
    List[QRContract],
    List[DFRContract],
    pd.Timestamp,
    str,   # name / key
    str,   # description
]


def _std_asset() -> AssetParams:
    """Return the standard 100 MWh / 100 MW asset used across all NESO worked examples."""
    return AssetParams(
        capacity_mwh=100.0,
        max_power_mw=100.0,
        efficiency_pct=100.0,
        initial_soe_pct=50.0,
    )


@lru_cache(maxsize=1)
def load_scenarios() -> Dict[str, ScenarioDef]:
    """Load and parse all scenarios from config/scenarios.json. Result is cached in-process."""
    base_dir = os.path.dirname(os.path.dirname(__file__))
    json_path = os.path.join(base_dir, "config", "scenarios.json")
    with open(json_path, "r") as f:
        data = json.load(f)

    scenarios: Dict[str, ScenarioDef] = {}
    for key, val in data.items():
        desc = val.get("desc", "")

        pn_objs = [
            PNSegment(
                start_dt=pd.Timestamp(pn["start"]), 
                end_dt=pd.Timestamp(pn["end"]), 
                mw=float(pn["mw"])
            )
            for pn in val.get("pns", [])
        ]

        boa_objs = [
            BOAEvent(
                start_dt=pd.Timestamp(boa["start"]), 
                end_dt=pd.Timestamp(boa["end"]), 
                mw=float(boa["mw"])
            )
            for boa in val.get("boas", [])
        ]

        qr_objs = [
            QRContract(
                delivery_start=pd.Timestamp(qr["start"]),
                mw=float(qr["mw"]),
                mwh=float(qr["mwh"]),
                contract_type=qr["type"],
                duration_sps=int(qr["duration_sps"]),
            )
            for qr in val.get("qrs", [])
        ]

        dfr_objs = [
            DFRContract(
                delivery_start=pd.Timestamp(dfr["start"]),
                mw=float(dfr["mw"]),
                direction=dfr["direction"],
                service_type=dfr["type"],
                duration_sps=int(dfr["duration_sps"]),
            )
            for dfr in val.get("dfrs", [])
        ]

        start_time = pd.Timestamp(val.get("start_time", ""))
        scenarios[key] = (_std_asset(), pn_objs, boa_objs, qr_objs, dfr_objs, start_time, key, desc)

    return scenarios


def get_scenario_names() -> List[str]:
    return list(load_scenarios().keys())


def get_scenario(name: str) -> ScenarioDef:
    return load_scenarios()[name]
