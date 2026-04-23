# Grid Code (GC0166) Parameter Calculation Methodology

This document outlines the methodological formulation of the Maximum Delivery Offer (MDO), Maximum Delivery Bid (MDB), Maximum Export Limit (MEL), and Maximum Import Limit (MIL) limits under the GC0166 calculation engine. The engine uses 1-minute granular State of Energy (SoE) tracking combined with fixed structural algorithms to guarantee energy obligations.

## 1. Core Principles & Conventions

1. **Power Convention**: Net export (discharge) is treated as positive (+), net import (charge) is treated as negative (-).
2. **Energy Definition**: 
   * **SoE**: The State of Energy of the battery (footroom).
   * **Headroom**: The physical volume available to charge (`Capacity - SoE`).
   * **MDO (Maximum Delivery Offer)**: Real-time available energy that can be promised for positive dispatch.
   * **MDB (Maximum Delivery Bid)**: Real-time available capacity that can be promised for negative dispatch (charging).
   * **MEL / MIL**: Absolute limit boundaries for real-world continuous multi-minute Power (MW) operation.
3. **Protection Window**: Contractual obligations (QR, DFR) typically lock down volumes. The window starts **4 Settlement Periods (SP-4)** before absolute delivery and runs through to **2 Settlement Periods (SP+2)** after delivery conclusion.

## 2. Base State of Energy (SoE) Calculation

Before any contractual overlays are considered, physical position limits are simulated minute-by-minute based strictly on instructed dispatch (Physical Notifications and BOAs).

**Timeline Initialization**: The engine creates a timeline starting exactly 1 minute before the requested `start_dt`. This "prep minute" (T-1) is used to establish the initial State of Energy (SoE) so that the first minute of the scenario (T=0) has a correctly integrated baseline.

For each minute `t`:
```python
Total_{MW}[t] = PN_{MW}[t] + BOA_{MW}[t]
```
Depending on the sign, the battery either charges or discharges, influenced by storage efficiency (`η`).

* **Discharge (Export, Power > 0)**:
  `SoE[t] = SoE[t-1] - (Total_{MW}[t] / 60)`
* **Charge (Import, Power < 0)**:
  `SoE[t] = SoE[t-1] - (Total_{MW}[t] * η / 60)`

Output boundaries generated from baseline SoE:
* **Footroom**: `SoE[t]`
* **Headroom**: `Capacity_{MWh} - SoE[t]`

---

## 3. Limit Reduction (Protection Windows)

Contracts demand guaranteed energy availability at future timestamps. To fulfill this we restrict BM accessibility *before* those contracts activate and *after* the contaracts finish though the MDO/MDB.

### 3.1 Quick Reserve (QR) Logic
Quick Reserve reserves a stated physical energy volume (in MWh).
* **Positive QR (PQR)** reserves footroom inside the battery (Export). It demands absolute reductions from the standard MDO.
* **Negative QR (NQR)** reserves headroom inside the asset (Import). It demands absolute reductions from the standard MDB.

**QR Protection Cycle**:
1. **Pre-Delivery (SP-4 up until Delivery Start)**: Valid contracted volumes are removed from the available MDO or MDB values.
2. **Post-Delivery (Delivery End until SP+2)**: Valid contracted volumes are removed from the available MDO or MDB values.
3. **During Delivery Window**: QR volumes are intentionally *not* protected against MDO/MDB. They are technically "released" to the BM and visible to NESO's dispatch algorithms for instructed delivery.

### 3.2 Dynamic Frequency Response (DFR) Logic
DFR demands un-instructed continuous power availability. These boundaries alter both Power Boundaries (MEL/MIL) and Energy Boundaries (MDO/MDB). 
Unlike QR, DFR is protected continuously **throughout its delivery window** because it is an automatic un-instructed response.

Volume Requirement: `Contract_{MW} * Service_Duration / 60`
*(DC = 15min, DM = 30min, DR = 60min).*

* **DFR Export (Low Frequency / DCL)**: Demands minimum stored energy out. Reduces **MDO** inside the SP-4 → SP+2 protection envelope. Also reduces the maximum operating **MEL** throughout the defined delivery window.
* **DFR Import (High Frequency / DCH)**: Demands minimum stored headroom. Reduces **MDB** inside the SP-4 → SP+2 protection envelope. Also reduces absolute mathematical **MIL** operating capability over the delivery window.

### 3.3 Physical Notification (PN) Future Protection
To ensure sufficient volume for planned asset PNs, the GC0166 changes explicitly protects PN volumes within the 4 Settlement Periods prior to action.
* If a PN signals future export, the requisite `PN_{MW} * Duration` in energy is withheld from current MDO pools in the preamble timeframes.
* If a PN signals future import, requisite headroom is withheld from current MDB.

*(Note: During the PN window itself, standard SoE tracking accounts for the volume dynamically, thus specific secondary volume protection drops off).*

---

## 4. Final Parameter Computations

After aggregating all the necessary protective reservations onto the timeline array buffers:

#### Energy Offers
The Maximum Delivery bounds guarantee that what goes to nested BM dispatch layers holds sufficient energy to fulfill prior binding commitments:
```python
MDO (MWh) = MAX(0.0, SoE - Total_Protected_MDO)
MDB (MWh) = -MAX(0.0, Headroom - Total_Protected_MDB)
```

#### Power Limits
Absolute operational maximum and minimum limitations guarantee enough buffer to handle DFR automatic swinging. DFR protection is unique as it restricts **both** Power (MW) and Energy (MWh) simultaneously:
```python
MEL (MW) = MAX(0.0, Asset_Max_Power_MW - DFR_High_Protection_MW) 
MIL (MW) = -MAX(0.0, Asset_Max_Power_MW - DFR_Low_Protection_MW) 
```

---

## 5. Event-Driven Redeclaration (Rule 5)

As per Grid Code BC2.5.3.4, MDO and MDB are not static. The engine must be re-run and values redeclared inside the Balancing Mechanism window under specific triggers:

1.  **Unavoidable Events**: Plant breakdown or safety events.
2.  **Receipt of a BOA**: Mandatory immediate recalculation of SoE and limits.
3.  **Ancillary Service Depletion**: Large frequency events that utilize reserved volumes.
4.  **PN Changes**: Updates to future schedules beyond the current window.

## 6. BOA Net Profile Logic

When a Bid-Offer Acceptance (BOA) is received, the engine performs a "Net Profile" calculation:
- The **Expected SoE** trajectory is immediately updated to reflect the energy gain/loss predicted from the BOA instructions.
- MDO decreases (if exporting) and MDB increases (headroom opens) minute-by-minute as the BOA is delivered.
- This ensures that subsequent BM dispatches always operate from the most current projected physical baseline.
## 7. Settlement Period (SP) Aggregation

For 30-minute settlement reporting and benchmarking against NESO ground truth, the 1-minute resolution data is aggregated as follows:

1.  **State & Energy Variables**: Use the **Last** value in the 30-minute bucket. This reflects the "End of Period" state for SoE, MDO, MDB, MEL, and MIL.
2.  **Power Variables**: Use the **Mean** value across the 30-minute bucket. This ensures that the reported `BOA_MW` and `PN_MW` reflect the average intensity of the instruction over the half-hour period, rather than a snapshot.
