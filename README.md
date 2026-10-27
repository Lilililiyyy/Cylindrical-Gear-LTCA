# Cylindrical Gear LTCA

**渐开线圆柱齿轮准静态承载齿面接触分析**

**简体中文** · [English](README.en.md)

基于参数化啮合几何、降阶齿体柔度与单边接触约束的半解析 LTCA 工具。计算修形及给定失准下的载荷分配、Hertz 接触压力、承载静态传递误差（TE）与法向切线啮合刚度，支持多工况修形方案比较。

## 示例预览

以下为同一 28/56 齿直齿轮副在 **80 N·m** 下的确定性计算：模数 2.5 mm、齿宽 25 mm、压力角 20°、钢材 E = 210 GPa、ν = 0.3，采用 64 相位、每条接触线 41 条带。周期包络、TE 与刚度比较三个方案：对中无修形、12 μm 两端法向失准、相同失准叠加 10 μm 齿向鼓形。瞬时斑点另选对中鼓形案例。

### 瞬时接触斑点

![对中齿向鼓形案例的单相位单齿对接触压力重建](docs/assets/contact_pattern.png)

固定啮合相位 **0.375**，只显示一个齿对。该案例无安装失准，齿向鼓形为 10 μm；使用求解得到的线载荷及局部 Hertz 半宽，重建接触带内的压力分布。横轴沿接触线、单位 mm，纵轴为齿面内垂直接触线的距离、单位 μm；为看清微米级半宽，两轴使用不同显示比例。

这是**条带式 Hertz 重建**，尚非完整二维接触求解。形状由条带载荷决定，不强制画成椭圆；未修形直齿轮也可能呈长条形接触。

### 承载静态传递误差

![承载静态传递误差及各方案峰峰值](docs/assets/transmission_error.png)

曲线为原始求解相位的法向接近量，右侧列出 TE 峰峰值。角度 TE 单独保存在输出中，并参考小轮的虚功一致法向力臂换算。

### 法向切线啮合刚度

![法向切线啮合刚度及各方案平均值](docs/assets/mesh_stiffness.png)

刚度由接触平衡的切线求得，单位为 N/μm。曲线保留实际相位采样和承载切换特征。鼓形可能降低失准工况下的峰值压力，同时增大 TE 波动；示例不预设所有指标同时改善。

重建以上图片及原始数据：

```bash
python -B examples/generate_readme_figures.py
```

精选响应数据见 [example_responses.csv](docs/data/example_responses.csv)，完整配置、CSV、NPZ 与可编辑 SVG 输出至 `output/readme_examples/`。云图算法与图像含义见[绘图说明](docs/plotting.md)。

## 快速开始

建议使用 Python 3.10 或 3.11：

```bash
python -m pip install -c constraints.txt -e ".[plots]"
python -m gear_contact examples/spur_case.json --output output/first_case --plots
```

安装后也可使用命令入口：

```bash
gear-ltca examples/spur_case.json --output output/first_case --plots
```

`output/first_case/` 包含输入、计算摘要、收敛诊断、完整数组、周期／接触单元 CSV 和 PNG／SVG 图表。`gear-contact` 保留为兼容命令别名。

- `pyproject.toml`：定义项目所需依赖、兼容版本范围和 `plots`／`dev` 可选依赖组。
- `constraints.txt`：固定已验证的 NumPy、SciPy、Matplotlib 版本，以便复现环境；通过 `pip -c` 使用。

只需计算内核时可用 `python -m pip install -e .`。内部统一使用 **m、N、Pa、rad**，扭矩为 N·m。正修形量表示材料去除、增大初始间隙。

## Python 调用

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

## 分析能力

| 模块 | 支持内容 |
| --- | --- |
| 啮合几何 | 内／外啮合、直／斜齿、变位、有效形径、轴向错位、接触线离散 |
| 修形与误差 | 齿向／齿廓鼓形、坡度、顶根修缘、端修、Bias、一维／二维测量偏差组合 |
| 弹性接触 | 变截面梁、齿宽剪切能耦合、单边接触与载荷平衡、局部压陷、解析切线刚度 |
| LTCA 结果 | 承载区域、载荷分配、Hertz 半宽与压力、法向／角度静态 TE、刚度、TE 阶次 |
| 方案评估 | 参数扫描、多工况最坏值、压力约束、有限候选集 Pareto 筛选 |
| 数据与图表 | JSON／NPZ／CSV，接触云图、TE、刚度、修形曲面及方案对比 PNG／SVG |

在每个相位，根据理论接触线与初始间隙，联合两轮结构柔度及局部接触压陷，求解接触协调、不穿透、非负接触力和总载荷平衡。公式与接口见[模型说明](docs/model.md)和[接口与单位](docs/api.md)。

## 案例与验证

```bash
# 全部案例的快速检查
python -B examples/run_examples.py --output output/quick --quick

# 正式案例：默认 32 相位、21 条带
python -B examples/run_examples.py --output output/full

# 独立检查 16/32/64 相位的采样敏感性
python -B examples/check_phase_resolution.py --output output/phase_resolution

# 运行测试、文档链接和命令入口检查
python -B scripts/check_project.py
```

案例覆盖弹簧／Hertz 解析基准、直齿、组合修形、失准、20–120 N·m 载荷、斜齿、内啮合、合成测量残差、空间离散和多工况设计。细节见[案例说明](docs/examples.md)。

已有数值基线覆盖 24 组配置复算；所测组合修形案例从 21 细化到 41 条带、32 细化到 64 相位时，所列 TE、压力、刚度指标变化均小于 1%。验证范围与历史环境见[验证记录](docs/validation.md)。GitHub Actions 配置在 Linux／Windows、Python 3.10／3.11 上执行测试，并检查案例与分发构建。

## 模型范围

本项目采用小变形、线弹性、无摩擦准静态接触。结构模型为固定齿根变截面梁及齿宽剪切耦合降阶近似，可接入外部结构柔度；局部压陷采用有限参照深度的线接触近似，超出适用域时会报错。

尚未完成完整三维弹性接触或物理实验精度验证。未自动生成实际齿根过渡或判定根切／干涉，未计螺旋轴向力引起的齿／轮体弯曲，不直接预测齿根应力、疲劳、润滑、温升或整机动态噪声。多工况筛选只针对给定工况与候选集。

## 项目结构

```text
cylindrical-gear-ltca/
├── gear_contact/       # 计算内核、数据导出与绘图
├── examples/           # JSON 输入、案例与示例图重建
├── tests/              # 解析、数值、接口及图表验证
├── scripts/            # 仓库检查
├── docs/               # 模型、接口、验证、绘图说明、示例图片及数据
├── .github/            # CI 与问题反馈模板
├── README.md           # 中文说明
├── README.en.md        # English documentation
├── pyproject.toml      # 项目元数据与依赖声明
├── constraints.txt     # 复现环境的依赖版本约束
└── LICENSE
```

运行结果、构建产物和缓存不纳入仓库；`docs/` 仅保留精选示例与验证依据。贡献方式见[贡献说明](CONTRIBUTING.md)，版本变化见[更新记录](CHANGELOG.md)。本项目采用 [MIT 许可](LICENSE)。
