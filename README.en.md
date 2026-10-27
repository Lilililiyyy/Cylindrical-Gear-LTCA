# Cylindrical Gear LTCA

**Quasi-static loaded tooth contact analysis for involute cylindrical gears**

[简体中文](README.md) · **English**

A semi-analytical LTCA tool combining parametric meshing geometry, reduced-order tooth compliance and unilateral contact constraints. It computes load distribution, Hertz pressure, loaded static transmission error (TE) and tangent normal mesh stiffness with microgeometry and prescribed misalignment, and compares designs across operating conditions.

## Example gallery

These deterministic examples use the same **28/56 spur gear pair at 80 N·m**: module 2.5 mm, face width 25 mm, pressure angle 20°, steel with E = 210 GPa and ν = 0.3, 64 mesh phases and 41 strips per contact line. Envelope, TE and stiffness comparisons use aligned/unmodified gears, 12 μm end-to-end normal misalignment, and the same misalignment with 10 μm lead crowning. The instantaneous footprint uses a separate aligned, crowned case.

### Instantaneous contact footprint

![Single-phase, single-tooth-pair pressure reconstruction for an aligned crowned gear pair](docs/assets/contact_pattern.png)

The footprint shows **phase 0.375 and one tooth pair**, with 10 μm lead crowning and zero misalignment. Pressure across the narrow contact band is reconstructed from the computed line loads and local Hertz half-widths. The along-line axis uses mm and the transverse, in-surface axis uses μm; the transverse direction is enlarged for visibility.

This is a **strip-wise Hertz reconstruction**, not a full two-dimensional contact solution. The shape follows the strip loads; an ellipse is not imposed. Unmodified spur gears may instead exhibit a long contact strip.

### One-cycle loaded contact envelope

![One-cycle envelopes for aligned, misaligned and lead-crowned cases](docs/assets/contact_envelope.png)

The three maps share one pressure scale and show the **loaded contact envelope swept over one base-pitch cycle**. Continuous contours use linear interpolation inside the sampled convex hull; light grey denotes inactive or unsampled regions. This view tracks contact locations over the tooth surface and differs from the fixed-phase footprint above. Boundary accuracy depends on solver resolution.

### Loaded static transmission error

![Loaded static TE with peak-to-peak values for each case](docs/assets/transmission_error.png)

The curves connect the original normal-approach samples. The sidebar reports peak-to-peak TE. Angular TE is exported separately using the pinion's virtual-work-consistent normal-force lever arm.

### Tangent normal mesh stiffness

![Tangent normal mesh stiffness with mean values for each case](docs/assets/mesh_stiffness.png)

Stiffness follows from the tangent contact equilibrium and is displayed in N/μm. Curves retain the original phase sampling and load-sharing transitions. Lead crowning can reduce peak pressure under misalignment while increasing TE fluctuation; the example does not assume that every metric improves.

Regenerate the figures and source data:

```bash
python -B examples/generate_readme_figures.py
```

Selected response data are available in [example_responses.csv](docs/data/example_responses.csv). Full configurations, CSV, NPZ and editable SVG files are written to `output/readme_examples/`. See the [plotting guide](docs/plotting.md#english) for contour semantics and reconstruction details.

## Quick start

Python 3.10 or 3.11 is recommended:

```bash
python -m pip install -c constraints.txt -e ".[plots]"
python -m gear_contact examples/spur_case.json --output output/first_case --plots
```

After installation, the console entry point is also available:

```bash
gear-ltca examples/spur_case.json --output output/first_case --plots
```

`output/first_case/` contains inputs, summary metrics, convergence diagnostics, full arrays, cycle/contact-cell CSV files and PNG/SVG figures. `gear-contact` remains a compatibility alias.

- `pyproject.toml` declares required packages, compatible version ranges and the optional `plots`/`dev` dependency groups.
- `constraints.txt` pins the validated NumPy, SciPy and Matplotlib versions for reproducibility. Use it with `pip -c`.

For the computational core alone, run `python -m pip install -e .`. Internal units are **m, N, Pa and rad**, with torque in N·m. Positive microgeometry values represent material removal and increase the initial gap.

## Python API

```python
from gear_contact import Gear, GearPair, SurfaceModification, analyze_pair, export_result
from gear_contact.plotting import plot_analysis

pair = GearPair(
    Gear(teeth=28, normal_module_m=0.0025, face_width_m=0.025),
    Gear(teeth=56, normal_module_m=0.0025, face_width_m=0.025),
)
result = analyze_pair(
    pair,
    torque_n_m=80,
    modification_pinion=SurfaceModification(lead_crown_m=8e-6, tip_relief_m=6e-6),
    misalignment_m=12e-6,
    phases=32,
    strips=21,
)
print(result.summary)
export_result(result, "output/my_case")
plot_analysis(result, "output/my_case")
```

## Capabilities

| Module | Supported features |
| --- | --- |
| Meshing geometry | External/internal meshes, spur/helical gears, profile shift, active form diameters, axial offset, contact-line discretization |
| Microgeometry and deviations | Lead/profile crowning, slope, tip/root relief, end relief, bias, explicit combinations of 1D/2D measured deviations |
| Elastic contact | Variable-section beam, face-width shear-energy coupling, unilateral contact, load balance, local indentation, analytical tangent stiffness |
| LTCA outputs | Loaded regions, load distribution, Hertz half-width and pressure, normal/angular static TE, mesh stiffness and TE orders |
| Design studies | Parameter scans, worst-case metrics, pressure constraints, finite-candidate Pareto screening |
| Data and figures | JSON/NPZ/CSV; contact contours, TE, stiffness, microgeometry and design comparisons in PNG/SVG |

At each mesh phase, candidate contact lines and initial gaps are combined with both gears' structural compliance and local indentation to enforce compatibility, nonpenetration, nonnegative forces and total load balance. The detailed [model](docs/model.md) and [API/units](docs/api.md) references are in Chinese.

## Examples and validation

```bash
# Run all examples with a small smoke-test grid
python -B examples/run_examples.py --output output/quick --quick

# Full examples: 32 phases and 21 strips by default
python -B examples/run_examples.py --output output/full

# Separate 16/32/64-phase sensitivity check
python -B examples/check_phase_resolution.py --output output/phase_resolution

# Tests, documentation links and CLI checks
python -B scripts/check_project.py
```

Examples cover analytical spring/Hertz baselines, spur gears, combined microgeometry, misalignment, 20–120 N·m loads, helical gears, internal meshes, synthetic measured residuals, spatial resolution and multi-condition studies. See [examples](docs/examples.md) for details.

The existing numerical baseline includes 24 recalculated configurations. For the tested combined-modification case, refining from 21 to 41 strips and from 32 to 64 phases changed the listed TE, pressure and stiffness metrics by less than 1%. The [validation record](docs/validation.md) describes the scope and historical environment. GitHub Actions is configured for Linux/Windows with Python 3.10/3.11, plus example execution and distribution builds.

## Model scope

The model assumes small deformation, linear elasticity, frictionless quasi-static contact. Structural compliance uses a fixed-root variable-section beam with reduced-order face-width shear coupling; external structural compliance can also be supplied. Local indentation uses a finite-reference-depth line-contact approximation, with checks on its validity domain.

Full 3D elastic-contact accuracy and physical experiments have not been validated. The implementation does not generate the actual root fillet, automatically check undercut/interference, include tooth/wheel bending from helical axial forces, or directly predict root stress, fatigue, lubrication, temperature rise or system-level dynamic noise. Multi-condition screening applies only to the specified conditions and candidate set.

## Repository layout

```text
cylindrical-gear-ltca/
├── gear_contact/       # Solver, data export and plotting
├── examples/           # JSON inputs, examples and gallery regeneration
├── tests/              # Analytical, numerical, API and plotting checks
├── scripts/            # Repository checks
├── docs/               # Model, API, validation, plotting, selected figures/data
├── .github/            # CI and issue templates
├── README.md           # Chinese documentation
├── README.en.md        # English documentation
├── pyproject.toml      # Project metadata and dependency declarations
├── constraints.txt     # Validated dependency pins for reproducibility
└── LICENSE
```

Generated results, builds and caches are ignored; `docs/` keeps selected examples and validation evidence. See [contributing](CONTRIBUTING.md) and the [changelog](CHANGELOG.md). Released under the [MIT license](LICENSE).
