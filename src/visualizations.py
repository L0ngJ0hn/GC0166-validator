import plotly.graph_objects as go
import pandas as pd
import streamlit as st

def plot_contract_profile(df, qr_list, dfr_list, full_range):
    """
    Renders the stacked MW contract profile chart.
    """
    t = df.index
    c_df = pd.DataFrame(index=t)
    for cat in ["QR", "DC", "DM", "DR"]:
        c_df[f"{cat}_pos"] = 0.0
        c_df[f"{cat}_neg"] = 0.0
    
    # Populate QR
    for q in qr_list:
        s = pd.Timestamp(q["start"])
        e = s + pd.Timedelta(minutes=q["duration_sps"] * 30)
        mw = q["mw"]
        col = "QR_pos" if q["type"] == "PQR" else "QR_neg"
        val = mw if q["type"] == "PQR" else -mw
        c_df.loc[s:e - pd.Timedelta(minutes=1), col] += val
        
    # Populate DFR
    for d in dfr_list:
        s = pd.Timestamp(d["start"])
        e = s + pd.Timedelta(minutes=d["duration_sps"] * 30)
        mw = d["mw"]
        col = f"{d['service_type']}_pos" if d["direction"] == "Export" else f"{d['service_type']}_neg"
        val = mw if d["direction"] == "Export" else -mw
        c_df.loc[s:e - pd.Timedelta(minutes=1), col] += val

    fig = go.Figure()
    colors = {"QR": "#ffa657", "DC": "#a371f7", "DM": "#388bfd", "DR": "#79c0ff"}
    
    for cat in ["QR", "DC", "DM", "DR"]:
        if c_df[f"{cat}_pos"].any():
            fig.add_trace(go.Scatter(x=t, y=c_df[f"{cat}_pos"], name=f"{cat} (Export)", stackgroup='pos', 
                                     line=dict(width=0, color=colors[cat]), fill='tonexty'))
        if c_df[f"{cat}_neg"].any():
            fig.add_trace(go.Scatter(x=t, y=c_df[f"{cat}_neg"], name=f"{cat} (Import)", stackgroup='neg', 
                                     line=dict(width=0, color=colors[cat]), fill='tonexty'))

    fig.update_layout(height=250, paper_bgcolor="#0d1117", plot_bgcolor="#0d1117", font=dict(color="#ffffff"),
                      xaxis=dict(range=full_range, autorange=False, type='date'),
                      yaxis=dict(title="Contract MW", zeroline=True, zerolinecolor="#666"),
                      margin=dict(l=100, r=20, t=10, b=10),
                      hovermode="x unified", legend=dict(orientation="h", y=1.2, font=dict(color="#ffffff")))
    st.plotly_chart(fig, width="stretch")

def plot_power_dispatch(df, full_range):
    """
    Renders the power dispatch chart (PN, BOA, MEL, MIL).
    """
    max_mw = max(abs(df["MEL_MW"].max()), abs(df["MIL_MW"].min()), abs(df["PN_MW"].max() + df["BOA_MW"].max()), 10)
    fig = go.Figure()
    t = df.index
    
    fig.add_trace(go.Scatter(x=t, y=df["PN_MW"], name="PN (MW)", stackgroup='p', line=dict(color="#8b949e", width=1.5, dash="dash")))
    fig.add_trace(go.Scatter(x=t, y=df["BOA_MW"], name="BOA PN Line (Aggregate)", stackgroup='p', line=dict(color="#ffa657", width=1.5)))
    fig.add_trace(go.Scatter(x=t, y=df["MEL_MW"], name="MEL (MW)", line=dict(color="#58a6ff", width=2.5)))
    fig.add_trace(go.Scatter(x=t, y=df["MIL_MW"], name="MIL (MW)", line=dict(color="#d29922", width=2.5)))

    fig.update_layout(height=400, paper_bgcolor="#0d1117", plot_bgcolor="#0d1117", font=dict(color="#ffffff"),
                     xaxis=dict(range=full_range, autorange=False, type='date'),
                     yaxis=dict(range=[-max_mw*1.2, max_mw*1.2], title="Power (MW)", zeroline=True, zerolinecolor="#666"),
                     margin=dict(l=100, r=20, t=10, b=10),
                     hovermode="x unified", legend=dict(orientation="h", y=1.1, font=dict(color="#ffffff")))
    st.plotly_chart(fig, width="stretch")

def plot_energy_limits(df, full_range):
    """
    Renders the energy limits chart (MDO, MDB).
    """
    max_mwh = max(df["MDO_MWh"].max(), abs(df["MDB_MWh"].min()), 10)
    fig = go.Figure()
    t = df.index
    
    fig.add_trace(go.Scatter(x=t, y=df["PN_MW"], name="PN (MW Context)", line=dict(color="#8b949e", width=1, dash="dash")))
    fig.add_trace(go.Scatter(x=t, y=df["PN_MW"] + df["BOA_MW"], name="BOA PN line (MW Context)", line=dict(color="#ffa657", width=1)))
    fig.add_trace(go.Scatter(x=t, y=df["MDO_MWh"], name="MDO (MWh)", line=dict(color="#3fb950", width=2.5)))
    fig.add_trace(go.Scatter(x=t, y=df["MDB_MWh"], name="MDB (MWh)", line=dict(color="#f85149", width=2.5)))

    fig.update_layout(height=400, paper_bgcolor="#0d1117", plot_bgcolor="#0d1117", font=dict(color="#ffffff"),
                     xaxis=dict(range=full_range, autorange=False, type='date'),
                     yaxis=dict(range=[-max_mwh*1.2, max_mwh*1.2], title="Energy (MWh)", zeroline=True, zerolinecolor="#666"),
                     margin=dict(l=100, r=20, t=10, b=10),
                     hovermode="x unified", legend=dict(orientation="h", y=1.1, font=dict(color="#ffffff")))
    st.plotly_chart(fig, width="stretch")

def plot_soe_margins(df, capacity_mwh, full_range):
    """
    Renders the SoE and operating margins chart.
    """
    fig = go.Figure()
    t = df.index
    fig.add_trace(go.Scatter(x=t, y=df["SoE_MWh"], name="SoE (MWh)", line=dict(color="#ffffff", width=2.5)))
    fig.add_trace(go.Scatter(x=t, y=df["Footroom_MWh"], name="Footroom (SoE available)", line=dict(color="#3fb950", width=1.5)))
    fig.add_trace(go.Scatter(x=t, y=df["Headroom_MWh"], name="Headroom (Capacity - SoE)", line=dict(color="#f85149", width=1.5)))
    
    fig.update_layout(height=400, paper_bgcolor="#0d1117", plot_bgcolor="#0d1117", font=dict(color="#ffffff"),
                      xaxis=dict(range=full_range, autorange=False, type='date'),
                     yaxis=dict(range=[-0.1, capacity_mwh * 1.05], title="Energy (MWh)"),
                     margin=dict(l=100, r=20, t=10, b=10),
                     hovermode="x unified", legend=dict(orientation="h", y=1.1, font=dict(color="#ffffff")))
    st.plotly_chart(fig, width="stretch")
