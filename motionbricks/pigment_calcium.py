"""Dependency-free research accounting; not a physiological predictor or controller."""
from dataclasses import asdict, dataclass
import json
import math

H_J_S = 6.62607015e-34
C_M_S = 299792458.0
R_J_MOL_K = 8.314462618


def _number(name, value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite real number")
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return value


def _finite(value):
    if not math.isfinite(value):
        raise ValueError("calculation exceeds finite numeric range")
    return value


def photon_count(absorbed_energy_mj, wavelength_nm):
    """Absorption events, NOT pigment particles, destruction or synthesis demand."""
    e = _number("absorbed_energy_mj", absorbed_energy_mj)
    w = _number("wavelength_nm", wavelength_nm, positive=True)
    return _finite(e * w * (1e-12 / (H_J_S * C_M_S)))


def half_time_s(rate_constant, coreactant_molar=None):
    """First-order half-time, or conditional pseudo-first-order half-time.

    rate_constant is s^-1 without a co-reactant, M^-1 s^-1 otherwise.
    The latter requires a constant co-reactant reservoir. No temperature
    extrapolation, competing reactions, substrate depletion or pathway sum.
    """
    k = _number("rate_constant", rate_constant, positive=True)
    if coreactant_molar is not None:
        k = _finite(k * _number("coreactant_molar", coreactant_molar, positive=True))
    if k == 0:
        raise ValueError("effective rate underflows numeric range")
    return _finite(math.log(2) / k)


def gibbs_concentration_kj_mol(temperature_k, reaction_quotient):
    """RT ln Q only; Q is dimensionless. Not total reaction or activation energy."""
    t = _number("temperature_k", temperature_k, positive=True)
    q = _number("reaction_quotient", reaction_quotient, positive=True)
    return _finite((R_J_MOL_K / 1000) * t * math.log(q))


@dataclass(frozen=True)
class CalciumPools:
    """Toy accounting inventories in mg, not calibrated human compartment sizes."""
    circulating_mg: float
    bone_mg: float
    pigment_bound_mg: float

    def __post_init__(self):
        for name, value in asdict(self).items():
            _number(name, value)
        _finite(self.total_mg)

    @property
    def total_mg(self):
        return self.circulating_mg + self.bone_mg + self.pigment_bound_mg


@dataclass(frozen=True)
class CalciumTransfers:
    """Amounts transferred over ONE interval, in mg; not rates or dietary doses."""
    absorbed_mg: float = 0.0
    resorbed_mg: float = 0.0
    deposited_mg: float = 0.0
    pigment_bound_mg: float = 0.0
    pigment_released_mg: float = 0.0
    excreted_mg: float = 0.0
    pigment_exported_mg: float = 0.0

    def __post_init__(self):
        for name, value in asdict(self).items():
            _number(name, value)


def transfer_calcium(pools, transfers):
    """Conservative ledger with explicit export, no implicit pigment consumption.

    Outflows must be available in each STARTING pool. Incoming transfers cannot
    be spent again within this interval; split intervals explicitly if needed.
    Returns a new immutable state, rejecting an infeasible ledger atomically.
    """
    if not isinstance(pools, CalciumPools) or not isinstance(transfers, CalciumTransfers):
        raise ValueError("expected CalciumPools and CalciumTransfers")
    p, t = pools, transfers
    circulating_out = _finite(t.deposited_mg + t.pigment_bound_mg + t.excreted_mg)
    pigment_out = _finite(t.pigment_released_mg + t.pigment_exported_mg)
    if circulating_out > p.circulating_mg or t.resorbed_mg > p.bone_mg or pigment_out > p.pigment_bound_mg:
        raise ValueError("outflow exceeds starting inventory; reduce or split the interval")
    return CalciumPools(
        p.circulating_mg - circulating_out + t.absorbed_mg + t.resorbed_mg + t.pigment_released_mg,
        p.bone_mg - t.resorbed_mg + t.deposited_mg,
        p.pigment_bound_mg - pigment_out + t.pigment_bound_mg,
    )


def illustrative_report():
    """Only cited local kinetics and explicitly synthetic mass-balance arithmetic."""
    initial = CalciumPools(10, 100, 2)
    transfers = CalciumTransfers(absorbed_mg=1, resorbed_mg=2, deposited_mg=1,
                                 pigment_bound_mg=.5, pigment_released_mg=.25,
                                 excreted_mg=.75, pigment_exported_mg=.1)
    final = transfer_calcium(initial, transfers)
    return {
        "schema_version": 1,
        "evidence": "ILLUSTRATIVE_ACCOUNTING_NOT_PHYSIOLOGICAL_VALIDATION",
        "absorbed_1mj_photons_at_300nm": photon_count(1, 300),
        "conditional_half_times_s": {
            "dq_cyclization": half_time_s(3.8),
            "cyclodopa_redox_at_fixed_1uM_dq": half_time_s(5.3e6, 1e-6),
            "cysteinyldopa_redox_at_fixed_1uM_dq": half_time_s(8.8e5, 1e-6),
        },
        "kinetics_sources": ["https://pubmed.ncbi.nlm.nih.gov/12950725/",
                             "https://pubmed.ncbi.nlm.nih.gov/10952395/"],
        "rt_ln_q_kj_mol_at_310_15k_q10": gibbs_concentration_kj_mol(310.15, 10),
        "synthetic_calcium_ledger": {
            "initial_mg": asdict(initial), "transfers_mg": asdict(transfers),
            "final_mg": asdict(final),
            "conservation_residual_mg": final.total_mg - initial.total_mg
                - transfers.absorbed_mg + transfers.excreted_mg + transfers.pigment_exported_mg,
        },
        "unidentified_outputs": {
            "pigment_particles_required": None, "total_synthesis_time_s": None,
            "total_synthesis_gibbs_kj_mol": None, "dietary_calcium_requirement_mg": None,
            "allicin_effect_coefficient": None, "capsaicin_effect_coefficient": None,
            "age_epigenetic_effect_coefficient": None,
        },
        "scope": "No dosing, diagnosis, crew selection, motion or robot actuation.",
    }


if __name__ == "__main__":
    print(json.dumps(illustrative_report(), indent=2, allow_nan=False))
