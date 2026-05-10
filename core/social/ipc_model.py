"""Interpersonal Circumplex (IPC) model.

Coordinate system:
  X axis = Benevolence (Affiliation):  +1 = friendly,  -1 = hostile
  Y axis = Power (Dominance):          +1 = dominant,  -1 = submissive

Eight octants at 45° intervals on the unit circle (B = cos θ, P = sin θ):

  Label      θ      B       P
  -------  -----  ------  ------
  亲和        0°   +1.000  +0.000
  活跃       45°   +0.707  +0.707
  掌控       90°   +0.000  +1.000
  高傲      135°   -0.707  +0.707
  冷淡      180°   -1.000  +0.000
  孤避      225°   -0.707  -0.707
  顺应      270°   +0.000  -1.000
  谦让      315°   +0.707  -0.707

References:
  Markey, P. M., & Markey, C. N. (2013). Journal of Personality, 81, 465-475.
  DeYoung, C. G., et al. (2013). Journal of Personality, 81(5), 465-475.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain.models import BigFiveVector

_SQRT2 = math.sqrt(2)
_EPS = 1e-9


@dataclass(frozen=True)
class _IPCOctant:
    label: str
    angle_deg: float

    @property
    def centroid_b(self) -> float:
        return math.cos(math.radians(self.angle_deg))

    @property
    def centroid_p(self) -> float:
        return math.sin(math.radians(self.angle_deg))


_OCTANTS: tuple[_IPCOctant, ...] = (
    _IPCOctant("亲和",     0.0),
    _IPCOctant("活跃",    45.0),
    _IPCOctant("掌控",    90.0),
    _IPCOctant("高傲",   135.0),
    _IPCOctant("冷淡",   180.0),
    _IPCOctant("孤避",   225.0),
    _IPCOctant("顺应",   270.0),
    _IPCOctant("谦让",   315.0),
)

_ANGLE_TO_OCTANT: dict[float, _IPCOctant] = {o.angle_deg: o for o in _OCTANTS}


def classify_octant(benevolence: float, power: float) -> str:
    """Return the Chinese IPC label whose centroid is nearest to (B, P)."""
    if abs(benevolence) < _EPS and abs(power) < _EPS:
        return "亲和"  # origin → default to friendly
    angle = math.degrees(math.atan2(power, benevolence)) % 360.0
    # Find the nearest octant centre (centres at 0°, 45°, …, 315°)
    nearest = round(angle / 45.0) % 8
    return _OCTANTS[nearest].label


def affect_intensity(benevolence: float, power: float) -> float:
    """Euclidean distance from origin, normalised to [0, 1].

    Maximum possible value when |B| = |P| = 1 is √2, so we divide by √2.
    Result is clamped to [0, 1] for safety.
    """
    raw = math.sqrt(benevolence ** 2 + power ** 2) / _SQRT2
    return min(1.0, max(0.0, raw))


def r_squared(benevolence: float, power: float) -> float:
    """Octant-belonging confidence: how well the point fits its assigned octant.

    Formula: R² = 1 − d² / (r + ε)²
      d  = Euclidean distance from (B, P) to the assigned octant's unit-circle centroid
      r  = modulus √(B² + P²)
      ε  = small epsilon to avoid division by zero

    R² = 1 means the point lies exactly on the octant centroid (perfect fit).
    R² approaches 0 as the point moves toward the boundary between octants.
    """
    label = classify_octant(benevolence, power)
    octant = next(o for o in _OCTANTS if o.label == label)
    d = math.sqrt((benevolence - octant.centroid_b) ** 2 + (power - octant.centroid_p) ** 2)
    r = math.sqrt(benevolence ** 2 + power ** 2)
    result = 1.0 - (d ** 2) / ((r + _EPS) ** 2)
    return min(1.0, max(0.0, result))


# Approximate rotation coefficients from DeYoung et al. 2013 / Markey & Markey 2013.
# Dominant loadings:
#   Benevolence: Agreeableness (strong), Extraversion (moderate), Neuroticism (negative)
#   Power:       Extraversion (strong), Conscientiousness (moderate), Neuroticism (negative)
# These are approximate — replace with paper's exact matrix values when available.
_BEN_COEFF = (0.70, 0.35, -0.20)   # (A, E, N) → benevolence
_POW_COEFF = (0.70, 0.35, -0.15)   # (E, C, N) → power


def bigfive_to_ipc(bfv: BigFiveVector) -> tuple[float, float]:
    """Rotate Big Five scores to IPC coordinates via Procrustean mapping.

    Returns (benevolence, power), each clamped to [-1, 1].

    Note: coefficients are approximate (see module docstring). Replace with
    exact values from DeYoung 2013 Appendix when consulting the source paper.
    """
    ben = (_BEN_COEFF[0] * bfv.agreeableness
           + _BEN_COEFF[1] * bfv.extraversion
           + _BEN_COEFF[2] * bfv.neuroticism)
    pow_ = (_POW_COEFF[0] * bfv.extraversion
            + _POW_COEFF[1] * bfv.conscientiousness
            + _POW_COEFF[2] * bfv.neuroticism)
    return _clamp(ben), _clamp(pow_)


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def derive_fields(benevolence: float, power: float) -> tuple[str, float, float]:
    """Convenience: return (ipc_orientation, affect_intensity, r_squared) for (B, P)."""
    return (
        classify_octant(benevolence, power),
        affect_intensity(benevolence, power),
        r_squared(benevolence, power),
    )
