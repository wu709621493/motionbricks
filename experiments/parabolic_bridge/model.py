"""Exact static GR source for a parabolic embedding; no formation simulation.

Standard library only. Lengths are metres, stresses are J/m^3 = Pa.
The model prescribes geometry and infers an effective anisotropic stress tensor.
It does not provide a matter action, stability proof or realizable device.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path

C_LIGHT = 299_792_458.0
G_NEWTON = 6.67430e-11
STRESS_FACTOR = C_LIGHT**4 / (8.0 * math.pi * G_NEWTON)


@dataclass(frozen=True)
class ParabolicBridge:
    """a: positive throat radius; f: positive parabolic focal scale."""

    a: float
    f: float

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) and v > 0 for v in (self.a, self.f)):
            raise ValueError("a and f must be finite positive lengths")

    def _radius(self, r: float) -> float:
        if not math.isfinite(r) or r < self.a:
            raise ValueError("r must be finite and at least a")
        return r

    def shape(self, r: float) -> float:
        r = self._radius(r)
        return self.f * r / (self.f + (r - self.a))

    def shape_prime(self, r: float) -> float:
        r = self._radius(r)
        return self.f * (self.f - self.a) / (self.f + (r - self.a))**2

    def stresses(self, r: float) -> tuple[float, float, float]:
        """Return (energy density, radial pressure, transverse pressure)."""
        r = self._radius(r)
        d = self.f + (r - self.a)
        common = STRESS_FACTOR * self.f / (r*r*d*d)
        return (common * (self.f - self.a), -common*d, common*r/2)

    def null_contraction(self, r: float, mu: float) -> float:
        """T_kk / (k^hat0)^2, with mu the radial direction cosine."""
        if not math.isfinite(mu) or abs(mu) > 1:
            raise ValueError("mu must be in [-1, 1]")
        e, pr, pt = self.stresses(r)
        return e + pr*mu*mu + pt*(1-mu*mu)

    def curvatures(self, r: float) -> tuple[float, float]:
        """Independent spatial sectional curvatures (radial, tangential), m^-2."""
        r = self._radius(r)
        d = self.f + (r - self.a)
        return (-self.f/(2*r*d*d), self.f/(r*r*d))

    def kretschmann(self, r: float) -> float:
        kr, kt = self.curvatures(r)
        return 8*kr*kr + 4*kt*kt

    def proper_energy(self, outer_radius: float) -> float:
        """Both ends, a<=r<=outer_radius; matter volume energy, not ADM energy."""
        r = self._radius(outer_radius)
        return 2*C_LIGHT**4/G_NEWTON * (self.f-self.a) * math.sqrt(
            (r-self.a)/(self.f+(r-self.a))
        )

    def sample(self, count: int = 81, outer_ratio: float = 5.0) -> list[dict]:
        if not isinstance(count, int) or not 2 <= count <= 10_001:
            raise ValueError("count must be an integer in [2, 10001]")
        if not math.isfinite(outer_ratio) or not 1 < outer_ratio <= 1000:
            raise ValueError("outer_ratio must be in (1, 1000]")
        q = STRESS_FACTOR/(self.a*self.a)
        rows = []
        for i in range(count):
            r = self.a*(1+(outer_ratio-1)*i/(count-1))
            e, pr, pt = self.stresses(r)
            rows.append({
                "status": "FORMAL_STATIC_GR_SOURCE",
                "a_m": self.a, "f_over_a": self.f/self.a, "r_over_a": r/self.a,
                "epsilon_J_m3": e, "p_radial_Pa": pr, "p_transverse_Pa": pt,
                "epsilon_over_Q": e/q, "p_radial_over_Q": pr/q,
                "p_transverse_over_Q": pt/q,
                "radial_NEC_over_Q": self.null_contraction(r, 1)/q,
                "transverse_NEC_over_Q": self.null_contraction(r, 0)/q,
                "kretschmann_m_minus4": self.kretschmann(r),
            })
        return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [row for ratio in (0.25, 0.5, 1.0, 2.0)
            for row in ParabolicBridge(1.0, ratio).sample()]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} formal-model rows to {args.output}")


if __name__ == "__main__":
    main()
