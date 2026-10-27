# 接口、单位与数据布局

项目名为Cylindrical Gear LTCA，仓库／分发名为`cylindrical-gear-ltca`；Python导入名保留`gear_contact`。主要命令为`gear-ltca`，`gear-contact`为兼容别名。

## 高层入口

`analyze_pair(pair, *, torque_n_m, material_pinion, material_wheel, modification_pinion, modification_wheel, misalignment_m, phases, strips, elastic_mode, local_contact, local_reference_depths_m, compliance_provider, boundary_gap)`。

常用结构：`Gear`、`GearPair`、`Material`、`SurfaceModification`、`MeasuredCurve`、`MeasuredSurface`和`CompositeModification`。字段及默认值以源码数据类为准。

|物理量|内部单位／定义|
|---|---|
|长度、间隙、修形|m；正修形是材料去除，增大间隙|
|压力、杨氏模量|Pa|
|扭矩|N·m；输入为已选受载面的非负幅值|
|力、线载荷|N、N/m|
|角度|rad；螺旋角带旋向符号|
|结构柔度|m/N；矩阵须对称正定并消除刚体模态|
|法向刚度|N/m；对当前活动接触分支的切线|
|失准|有效重叠齿宽右端减左端的法向间隙m|

内齿圈设置在`wheel`侧，齿数用正整数；外啮合两轮螺旋角等值异号，内啮合同号。实体根／顶圆与有效渐开线根／顶形径分别配置。齿廓坐标以单轮完整有效渐开线范围归一化，齿向坐标以单轮完整齿宽归一化。

## 结果

`AnalysisResult`提供`phase`、`normal_approach_m`、`angular_te_rad`、`mesh_stiffness_n_per_m`、逐相位`rotations`及`summary`。每个相位包含几何单元、间隙、接触力、活动掩码、线载荷、半宽、压力和收敛诊断。

`export_result(result, directory)`保存：

- `input.json`、`summary.json`、`diagnostics.json`及`manifest.json`。
- `arrays.npz`：无pickle的一维数组；`cell_offsets[k]:cell_offsets[k+1]`对应第k个相位的接触单元。
- `cycle.csv`、`contact_cells.csv`：周期结果及全部原离散单元。
- `te_spectrum.json`：相位0起采的周期谱；近零幅值的相位为null。

`analyze_config`读取命名JSON，包括导出的`input.json`。外部Python回调无法仅由JSON复现，读取时会明确要求重新提供回调。

## 绘图接口

从 `gear_contact.plotting` 导入：

- `plot_analysis(result, output_dir)`：单工况周期响应、周期接触包络、单相位单齿对接触斑点、TE 谐波与 CSV。
- `plot_contact_comparison(results, output_dir, *, phase_index=0, tooth_pair_index=None)`：固定相位、单齿对的条带式 Hertz 压力重建。默认选取该相位载荷最大的齿对；对比共用压力色标。原始条带数据保存为 `contact_pattern_source.csv`，展示网格为 `contact_pattern_data.csv`。
- `plot_contact_envelope_comparison(results, output_dir)`：以名称到结果的字典输入，使用共用压力色标比较整个周期的承载包络，导出 `contact_envelope` 图及原始接触点 CSV。
- `plot_comparison(results, output_dir)`：方案综合对比、独立的 `transmission_error` 和 `mesh_stiffness` 图，以及包含法向接近量与切线刚度的 `comparison_curves.csv`。
- `plot_surface(modification, output_dir)`：修形去除量云图、截线和 CSV。

图表输出 PNG／SVG。`contact_pattern` 专指瞬时斑点，`contact_envelope` 专指周期扫掠包络；原始周期单元仍保存于 `plot_contact_data.csv`。`plot_analysis` 默认使用最接近前八分之三周期的下取整相位下标，可通过单独调用绘图接口选择任意已有相位和齿对。重建方法见[绘图说明](plotting.md)。

## 修形方案评估与扩展

`compare_designs`、`sweep_parameter`、`robust_design_search`使用同一内核；多工况由`OperatingPoint(name, torque_n_m, misalignment_m)`定义。筛选目标为给定工况集合内的最坏TE峰峰值和最大压力，可明确指定压力上限，不内置许用应力或隐藏权重。

外部结构柔度通过`compliance_provider(pair, grid)`提供，不能与局部压陷重复计入接触变形；额外法向间隙通过`boundary_gap(phase, grid)`提供。模型公式与限制见[model.md](model.md)。
