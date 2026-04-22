from __future__ import annotations
import pandas as pd
from pydantic import BaseModel, Field, model_validator, ConfigDict
from typing import Literal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MINS_PER_SP = 30          # 1 Settlement Period = 30 minutes
MINS_PER_HOUR = 60
SP_PRE_WINDOW = 4         # SPs before contract start to begin protecting
SP_POST_WINDOW = 2        # SPs after contract end to keep protecting

# DFR service minimum continuous delivery durations (minutes)
DFR_DURATION_MINS = {
    "DC":  15,   # Dynamic Containment
    "DM":  30,   # Dynamic Moderation
    "DR":  60,   # Dynamic Regulation
}

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class AssetParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    capacity_mwh: float = Field(default=100.0, gt=0)    # Maximum energy capacity (MWh)
    max_power_mw: float = Field(default=100.0, gt=0)    # Maximum power export/import (MW)
    efficiency_pct: float = Field(default=100.0, ge=0, le=100.0)  # Round-trip efficiency (%)
    initial_soe_pct: float = Field(default=50.0, ge=0, le=100.0)  # Initial State of Energy (%)

    @property
    def initial_soe_mwh(self) -> float:
        return self.capacity_mwh * self.initial_soe_pct / 100.0

    @property
    def efficiency(self) -> float:
        return self.efficiency_pct / 100.0


class PNSegment(BaseModel):
    """A flat PN level for a time range (MW, positive=export, negative=import)."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    start_dt: pd.Timestamp
    end_dt: pd.Timestamp        # exclusive end (up to but not including)
    mw: float                   # +ve = export, -ve = import

    @model_validator(mode="after")
    def check_dates(self) -> PNSegment:
        if self.start_dt >= self.end_dt:
            raise ValueError(f"PNSegment start ({self.start_dt}) must be before end ({self.end_dt})")
        return self


class BOAEvent(BaseModel):
    """A BOA instruction: unit delivers at this level between start/end."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    start_dt: pd.Timestamp
    end_dt: pd.Timestamp        # exclusive end
    mw: float                   # +ve = export (discharge), -ve = import (charge)

    @model_validator(mode="after")
    def check_dates(self) -> BOAEvent:
        if self.start_dt >= self.end_dt:
            raise ValueError(f"BOAEvent start ({self.start_dt}) must be before end ({self.end_dt})")
        return self


class QRContract(BaseModel):
    """
    Quick Reserve contract (Positive or Negative).
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    delivery_start: pd.Timestamp   # start of the delivery SP
    mw: float                      # contracted power in MW
    mwh: float                     # contracted energy in MWh (= volume to protect)
    contract_type: Literal["PQR", "NQR"] = "PQR"
    duration_sps: int = Field(default=1, ge=1)

    @property
    def delivery_end(self) -> pd.Timestamp:
        return self.delivery_start + pd.Timedelta(minutes=self.duration_sps * MINS_PER_SP)

    @property
    def protection_start(self) -> pd.Timestamp:
        return self.delivery_start - pd.Timedelta(minutes=SP_PRE_WINDOW * MINS_PER_SP)

    @property
    def protection_end(self) -> pd.Timestamp:
        return self.delivery_end + pd.Timedelta(minutes=SP_POST_WINDOW * MINS_PER_SP)


class DFRContract(BaseModel):
    """
    Dynamic Frequency Response contract (DC, DM, or DR; High or Low).
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    delivery_start: pd.Timestamp
    mw: float                     # contracted MW band
    direction: Literal["Export", "Import"]
    service_type: Literal["DC", "DM", "DR"] = "DC"
    duration_sps: int = Field(default=8, ge=1)

    @property
    def service_duration_mins(self) -> int:
        return DFR_DURATION_MINS.get(self.service_type, 15)

    @property
    def protected_mwh(self) -> float:
        """Minimum energy volume that must be protected for this DFR service."""
        return self.mw * self.service_duration_mins / MINS_PER_HOUR

    @property
    def delivery_end(self) -> pd.Timestamp:
        return self.delivery_start + pd.Timedelta(minutes=self.duration_sps * MINS_PER_SP)

    @property
    def protection_start(self) -> pd.Timestamp:
        return self.delivery_start - pd.Timedelta(minutes=SP_PRE_WINDOW * MINS_PER_SP)

    @property
    def protection_end(self) -> pd.Timestamp:
        return self.delivery_end + pd.Timedelta(minutes=SP_POST_WINDOW * MINS_PER_SP)
