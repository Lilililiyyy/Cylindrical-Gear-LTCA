# Cylindrical Gear LTCA

[中文](README.md) · **English**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab?logo=python&logoColor=white)](https://www.python.org/) [![License: AGPL-3.0-only](https://img.shields.io/badge/License-AGPL--3.0--only-blue.svg)](LICENSE) [![Library Version](https://img.shields.io/badge/version-0.4.0-blue)](#changelog)

A Python calculation kernel for involute cylindrical gear geometry, strength rating and quasi-static loaded tooth contact analysis (LTCA). MASTA is used only for numerical benchmarking.

## Contents

- [Installation and use](#installation-and-use)
- [Capabilities](#capabilities)
- [Current case and reproduction](#current-case-and-reproduction)
- [Verification](#verification)
- [Scope](#scope)
- [Changelog](#changelog)
- [Roadmap](#roadmap)
- [Repository layout](#repository-layout)

## Installation and use

Python 3.10 or 3.11 is recommended. Run from the repository root:

```bash
python -m pip install -c constraints.txt -e ".[plots]"
python -B examples/run_cylindrical_workflow.py --output output/helical_18_77 --plots
```

For calculations without plots, use `python -m pip install -e .`. The command-line entry point is `gear-ltca`; `gear-contact` remains available as an alias.

```python
import json
from pathlib import Path
from gear_contact import analyze_config, export_result

case = json.loads(Path("examples/helical_18_77_case.json").read_text(encoding="utf-8"))
config = case["analysis"]
nominal = case["loading"]["nominal_pinion_torque_n_m"]
config["torque_n_m"] = nominal * case["loading"]["ltca_torque_multiplier"]
config["iso_settings"]["nominal_pinion_torque_n_m"] = nominal
result = analyze_config(config)
export_result(result, "output/helical_18_77_core")
```

Inputs and results use SI units: m, N, Pa, rad and N·m. Positive modification removes material and increases the initial gap. Helix angles have equal magnitudes and opposite signs for external meshes, and the same sign for internal meshes. Put the internal ring gear in `wheel` and keep tooth counts positive.

## Capabilities

| Module                       | Capabilities                                                                                                                                                                |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Geometry and meshing         | Internal/external and spur/helical meshes, profile shifts, reference and base circles, centre distance, active profile limits, contact ratios and discretized contact lines |
| Microgeometry and boundaries | Lead/profile crowning, slopes, tip/root relief, end relief, bias, combined measured deviations, axial offsets and prescribed misalignment                                   |
| Strength rating              | ISO 6336:2006 contact/root stresses and safety factors, with rating factors supplied by the user                                                                            |
| Elasticity                   | Variable-section tooth beams with local Hertz indentation; optional ISO 6336 total tooth-pair stiffness and Love strip influences                                           |
| Extended contact             | Tooth-tip extension geometry, additional gaps and contact-domain checks                                                                                                     |
| LTCA                         | Contact load sharing, transmission error, mesh stiffness, contact pressure and contact half-width                                                                           |
| Design and data              | Multiple operating conditions, parameter sweeps, Pareto screening, JSON/NPZ/CSV data and PNG/SVG plots                                                                      |

## Current case and reproduction

An 18/77 external helical gear pair is used to compare geometry, strength, LTCA and contact pressure with MASTA.

| Input                 | Value                 |
| --------------------- | ---------------------:|
| Tooth counts          | 18 / 77               |
| Normal module         | 2 mm                  |
| Face width            | 24 mm                 |
| Normal pressure angle | 22.5°                 |
| Helix angle magnitude | 23.5°, opposite hands |
| Profile shifts        | +0.3268 / −0.3268     |
| Centre distance       | 103.5919 mm           |
| Material              | E=207 GPa, ν=0.3      |
| Nominal pinion torque | 1.718873 N·m          |
| LTCA torque           | 2.536165 N·m          |

```bash
python -B examples/run_cylindrical_workflow.py examples/helical_18_77_case.json --reference examples/helical_18_77_reference.json --output output/helical_18_77 --plots
```

The [case input](examples/helical_18_77_case.json) defines geometry, materials, modifications, boundaries, loads and discretization. Nominal torque is used for strength rating; the LTCA torque includes load factors.

**Key geometry and strength**

![Key geometry, stresses and safety factors](examples/results/helical_18_77/en/02_case_benchmarks.png)

The comparison covers reference/base diameters, centre distance, contact/root stresses and safety factors for both gears. The same rating factors and material stress limits are used.

**LTCA cycle response**

![LTCA cycle response: MASTA and this project](examples/results/helical_18_77/en/03_ltca_cycle.png)

This case uses ISO total stiffness, Love strip influences and tooth-tip extension. Both calculations use the same load and working flank, with 32 mesh positions per period and 40 strips per contact line. One steady-state period is displayed over three periods; the statistics below use a single period.

| Cycle metric                   | MASTA      | This project | Relative difference |
| ------------------------------ | ----------:| ------------:| -------------------:|
| Mean normal TE / μm            | 1.106705   | 1.106705     | <0.001%             |
| Peak-to-peak TE / μm           | 0.034134   | 0.034134     | <0.001%             |
| Mean normal stiffness / N/μm   | 220.932698 | 220.932698   | <0.001%             |
| Maximum contact pressure / MPa | 186.674352 | 186.674382   | <0.001%             |

Full values are available in the [comparison table](examples/results/helical_18_77/comparison.csv).

**Contact pressure comparison**

![Contact pressure: MASTA and this project](examples/results/helical_18_77/en/07_native_contact_comparison.png)

MASTA results are shown on the left and this project's results on the right, for the same load and working flank over one tooth passage. The horizontal axis is the face-width coordinate, the vertical axis is pinion roll distance, and colour indicates pressure. Grey denotes uncovered regions.

Separate views are available for the [MASTA contact pressure](examples/results/helical_18_77/07_masta_native_contact.png), [instantaneous pressure bands at the same phase](examples/results/helical_18_77/en/04_contact_pattern.png), and [contact positions and cycle coverage](examples/results/helical_18_77/en/05_contact_coordinates.png). Tooth-passage pressure distributions and instantaneous loaded regions are shown separately.

Plots and data are in the [case results directory](examples/results/helical_18_77/). The case command generates complete contact data and SVG plots. To reproduce the English figures:

```bash
python -B examples/generate_english_figures.py --output output/helical_18_77_en
```

**Misalignment and crowning sensitivity for the same case**

Geometry, material, load, existing modifications and prescribed boundaries are retained. The alternatives add 1 μm of end-to-end misalignment, then an additional 0.5 μm of pinion lead crowning under that misalignment. This analysis is included in the case command above.

![Misalignment and crowning sensitivity for the 18/77 pair](examples/results/helical_18_77/en/06_modification_sensitivity.png)

| Metric                       | Baseline | Additional misalignment | Misalignment + additional crowning |
| ---------------------------- | --------:| -----------------------:| ----------------------------------:|
| Peak-to-peak TE / μm         | 0.034134 | 0.038338                | 0.076337                           |
| Mean stiffness / N/μm        | 220.933  | 213.019                 | 202.738                            |
| Endpoint peak pressure / MPa | 186.674  | 192.671                 | 201.673                            |

All three alternatives are calculated by this project. Additional crowning increases both TE variation and peak pressure in this operating condition; modification selection depends on load, misalignment and existing microgeometry.

## Verification

0.3.0 增加固定版本响应回归及空间／相位收敛矩阵，调用方法、状态边界和压力指标见[第一轮验证说明](docs/first_round_validation.md)。

```bash
python -B examples/run_examples.py --output output/full
python -B examples/validate_cases.py --output output/case_validation
python -B examples/check_phase_resolution.py --output output/phase_resolution
python -B examples/run_benchmarks.py --output output/masta --plots --require-common-match
python -B -m unittest discover -s tests -v
```

Verification covers internal/external and spur/helical meshes, combined modifications, dissimilar materials, load changes, mirrored misalignment, zero load and similarity laws. See the [verification data](examples/results/validation/).

## Scope

接触分析采用小变形、线弹性、无摩擦、准静态假设。内置齿梁模式可选用阶梯轴与线性轴承耦合，适用于刚性轮体和刚性箱体。润滑、温升、疲劳寿命和动态噪声超出当前计算范围。

Strength ratings and local LTCA contact pressure are assessed separately. Validation currently relies on numerical comparisons; experimental accuracy has not been established.

Equations and assumptions are described in the [model documentation](docs/model.md). Functions, units and array layouts are described in the [interface documentation](docs/api.md). These detailed documents are currently in Chinese.

## Changelog

- **0.4.0 · 2026-11-13**：新增齿轮、阶梯轴与线性轴承准静态耦合，轴系变形反馈至各相位的齿面载荷分配。输出轴节点位移、转角、轴承反力及条带法向位移，支持导出 JSON 后复算。简支梁解析解、刚性极限和原有 10 案响应回归通过。[模型与算例](docs/shaft_bearing_coupling.md)
- **0.3.0 · 2026-11-12**：新增固定响应回归及空间、相位收敛矩阵。方案比较支持中心或独立端点压力，统一用于压力约束、Pareto 筛选和图表。[验证说明](docs/first_round_validation.md)
- **0.2.1 · 2026-11-02**：统一通用工况与对标案例的接触图，修正实际啮合范围和中心条带的显示边界。增加统一色标的方案比较和原结果重绘。
- **0.2.0 · 2026-10-30**：增加 ISO 综合刚度、Love 条带模型、齿顶延伸及 ISO 6336:2006 显式因子强度计算。补充 18/77 工况的 MASTA 对标、三周期曲线、接触压力图和失准／鼓形敏感性结果。该版本于 2026-10-31 改用 AGPL-3.0-only。
- **0.1.0 · 2026-10-27**：建立渐开线圆柱齿轮几何、齿面修形、齿梁弹性、Hertz 接触、准静态承载接触求解及多工况方案比较。

## Roadmap

- **Near-term plans**: More internal-mesh and edge-contact cases, mesh and phase convergence studies, and independent 3D contact and experimental validation.

- **后续扩展**：有限齿体与轮体柔度、非线性轴承和箱体柔度，更完整的标准评级因子与材料寿命链，以及参数化修形优化。

## Repository layout

This project is licensed under [AGPL-3.0-only](LICENSE). For proprietary or closed-source integration, [contact the author](https://github.com/Lilililiyyy) to discuss a commercial license.

`gear_contact/` contains the calculation and post-processing modules; `examples/` contains inputs and runnable workflows, with selected results in `examples/results/`; `docs/` contains model and interface documentation; `tests/` and `.github/` run verification. 
