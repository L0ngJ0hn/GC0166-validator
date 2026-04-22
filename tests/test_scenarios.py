import pytest
import pandas as pd
import os
from src.engine import run_engine
from src.scenarios import get_scenario, get_scenario_names

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def _load_ground_truth(scenario_name):
    """
    Loads ground truth from CSV.
    """
    # Map scenario name to filename (e.g. "1.1 No BOA..." -> "1.1.csv")
    prefix = scenario_name.split(" ")[0]
    csv_path = os.path.join(DATA_DIR, f"{prefix}.csv")
    
    if not os.path.exists(csv_path):
        return None
        
    df = pd.read_csv(csv_path)
    
    # Select only the columns we need for comparison
    cols = ["MDO_MWh", "MDB_MWh", "MEL_MW", "MIL_MW", "SoE_MWh"]
    target_data = df[[c for c in cols if c in df.columns]]
    
    return target_data.fillna(0.0)

@pytest.mark.parametrize("scenario_name", get_scenario_names())
def test_scenario_consistency(scenario_name):
    # 1. Load scenario inputs
    asset, pns, boas, qrs, dfrs, start_dt, name, desc = get_scenario(scenario_name)
    
    # Determine simulation length based on scenario name
    prefix = scenario_name.split(".")[0]
    end_dt = (
        pd.Timestamp("2024-04-11 17:30") if prefix != "4"
        else pd.Timestamp("2024-04-11 05:00")
    )

    # 2. Run engine
    results_df = run_engine(
        params=asset,
        pn_segments=pns,
        boa_events=boas,
        qr_contracts=qrs,
        dfr_contracts=dfrs,
        start_dt=start_dt,
        end_dt=end_dt
    )
    
    # Filter out the preparatory minute added by the engine
    results_df = results_df[results_df.index >= start_dt]
    
    # 3. Load ground truth
    gt_df = _load_ground_truth(scenario_name)
    if gt_df is None:
        pytest.skip(f"Ground truth CSV for '{scenario_name}' not found in {DATA_DIR}")

    # 4. Alignment & Comparison
    is_sp_level = any(scenario_name.startswith(f"{i}.") for i in ["1", "2", "3"])
    
    if is_sp_level:
        # Aggregate engine results to SP level (30-min) chronologically.
        # resample("30min").last() aligns with the end-of-period view in the NESO Excel sheets.
        engine_sp = results_df.resample("30min").last().head(len(gt_df))
        
        target_engine = engine_sp[["MDO_MWh", "MDB_MWh", "MEL_MW", "MIL_MW", "SoE_MWh"]]
        target_gt = gt_df.head(len(engine_sp))
    else:
        # 1-min level comparison
        target_engine = results_df[["MDO_MWh", "MDB_MWh", "MEL_MW", "MIL_MW", "SoE_MWh"]].head(len(gt_df))
        target_gt = gt_df.head(len(target_engine))

    # 5. Numerical Assertions
    # Tolerance of 0.01 to allow for rounding in the NESO worked examples
    pd.testing.assert_frame_equal(
        target_engine.reset_index(drop=True), 
        target_gt.reset_index(drop=True),
        atol=0.01,
        check_dtype=False
    )
