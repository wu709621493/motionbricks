# Pigment and calcium research accounting

This opt-in module turns the quantitative portion of Windy Wu's research discussion into checked arithmetic. It uses only the Python standard library and does not initialize Torch, Warp, TensorRT, GPUs, viewers or robot controllers. It shares the repository's independent CPU research-module pattern, not its motion-generation semantics.

The full [evidence and hypothesis discussion](pigment_calcium_research.md) covers enamel-development genes; eumelanin and pheomelanin pathways; astronaut calcium homeostasis; allicin and capsaicin exposure; and age-related epigenetic regulation. It includes source links and distinguishes in vitro effects, human findings and proposed mechanisms. No individual health history or diagnostic interpretation is part of this implementation.

## Run

From the repository root on Python 3.12 or newer:

```sh
python -S -m motionbricks.pigment_calcium
python -S -m unittest discover -s tests/pigment_calcium -v
```

The first command prints deterministic JSON to stdout and writes no files. Its schema version is 1. The existing Ubuntu x86/ARM and macOS ARM Python 3.12/3.13 workflow runs the new tests without site packages.

## Calculations and units

| Function | Inputs | Output and boundary |
| --- | --- | --- |
| `photon_count` | Already absorbed energy in mJ, wavelength in nm | Number of single-photon absorption events, not particles consumed |
| `half_time_s` | First-order rate in s⁻¹, or second-order rate in M⁻¹s⁻¹ plus fixed co-reactant in M | Single-step half-time in seconds, not pathway completion time |
| `gibbs_concentration_kj_mol` | Temperature in K and dimensionless positive Q | RT ln Q in kJ/mol, not total Gibbs energy or ATP cost |
| `transfer_calcium` | Pool inventories and interval transfer amounts, all in mg | New inventories with internal redistribution and external losses separated |

The JSON example uses published local kinetic constants without temperature extrapolation and an explicitly assumed constant 1 μM DQ reservoir. Constants are traceable to the linked primary papers. They must not be added as pathway completion times or used as an in vivo calibration.

## Calcium accounting contract

Three bookkeeping pools represent circulating, bone and pigment-bound calcium. `absorbed_mg` enters the circulating pool; `excreted_mg` leaves it; `pigment_exported_mg` leaves the pigment pool. Resorption, deposition, binding and release transfer mass internally. For every accepted interval:

> Final total = initial total + absorbed − excreted − pigment exported.

All amounts are finite and nonnegative. Every pool's summed outflow must fit its starting inventory; inflow cannot be spent again within the same interval. An invalid interval raises `ValueError` without mutating the input. Reduce or explicitly split intervals when this conservative rule is too restrictive. The example inventories are synthetic, not astronaut compartment estimates. This is a discrete ledger, not an ODE solver or validated kinetic model. Small floating-point conservation residuals are expected.

## Variables whose effects remain unidentified

Allicin intake, capsaicin intake, local plaque exposure, systemic bioavailability, chronological age and tissue-specific epigenetic state must remain separate. There are no fabricated coefficients linking them to calcium demand. In particular:

- Cell-culture concentrations and minimum inhibitory concentrations are not oral dose recommendations.
- Protein S-thioallylation and TRPV1 signaling are not automatically epigenetic changes.
- A common pigmentation-associated variant is not an enamel-disease diagnosis.
- Adult enamel is not a living epigenetic or bone-remodeling compartment.
- A local pigment-calcium effect does not establish a systemic skeletal effect.

Unknown total synthesis energy, synthesis time, pigment particle requirements, dietary requirements and exposure/age coefficients are JSON `null`, never zero or estimated effects. There is no diagnostic score, genotype classifier, dosing output, astronaut-selection rule or automatic actuation. To add a fitted model later, first define its target population, units, measured exposures, causal estimand, uncertainty and independent validation.

## Validation

Tests check known physical values, scaling laws, half-conversion, Gibbs sign/reference, binding-release reversibility, explicit export, 200 seeded feasible mass-balance ledgers, summed-outflow rejection, nonfinite and invalid inputs, and the strict JSON CLI under `python -S`. Passing these checks verifies arithmetic and software contracts only; it does not validate the biological hypotheses.
