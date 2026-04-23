# GC0166 Validation Tool

An open-source reference implementation of the NESO GC0166 Grid Code changes for energy storage assets.

The application calculates minute-by-minute base State of Energy (SoE) driven by Physical Notifications (PN) and Bid-Offer Acceptances (BOA). It then applies contractual protection rules (SP-4 to SP+2) for Quick Reserve (QR) and Dynamic Frequency Response (DFR) contracts to compute valid **Maximum Delivery Offer (MDO)**, **Maximum Delivery Bid (MDB)**, **Maximum Export Limit (MEL)**, and **Maximum Import Limit (MIL)** profiles.

This tool is designed to help validate and understand the new parameter requirements under the GC0166 grid code modifications.

## Project Structure

* **`src/`**: Core logic and UI components.
    * **`engine.py`**: High-performance vectorized calculation engine using NumPy/Pandas.
    * **`models.py`**: Pydantic/DataClass models and shared constants (e.g., DFR durations).
    * **`scenarios.py`**: Data loader for 18 benchmark scenarios.
    * **`visualizations.py`**: Plotly-based dashboard charts.
* **`tests/`**: Robust validation suite benchmarking the engine against ground-truth datasets.
* **`app.py`**: The Streamlit user interface and dashboard entry point.

## Installation & Running

1. **Install Dependencies**:
   Ensure you have Python 3.10+ installed. For basic usage:
   ```bash
   pip install -r requirements.txt
   ```
   For development and testing (recommended):
   ```bash
   pip install -r requirements.txt -r requirements-dev.txt
   ```

2. **Run the App**:
   ```bash
   streamlit run app.py
   ```

3. **Run Tests**:
   To verify engine accuracy against all 18 NESO scenarios:
   ```bash
   pytest tests/test_scenarios.py -v
   ```

## Features

1. **Scenario Benchmarking**: Select from 18 preset NESO scenarios (stacked QRs, multi-directional DFR, interlocked BOAs).
2. **Dynamic Vector Engines**: Leverages NumPy broadcasting for near-instantaneous recalculation upon parameter changes.
3. **Data Export**: Extract 1-minute high-fidelity logs or 30-minute Settlement Period (SP) summaries.
4. **Visualisation Dashboard**: Real-time tracking of contractual MW profiles, Energy Limits (MDO/MDB), and State of Energy headroom.

## Methodological Details
Check `METHODOLOGY.md` for the full breakdown of calculations and Grid Code compliance logic.
