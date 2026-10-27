# 绘图说明 / Plotting guide

绘图后端为 Python/Matplotlib。图表用于表达近似力学模型内的计算结果与数值验证，不作为试验或实物精度证据。

|图|要支持的判断|证据和完整性要求|
|---|---|---|
|周期响应图|接触状态变化会影响接近量、切线刚度和压力|使用原相位数组，法向位移和角度 TE 分开，明确单位|
|TE谐波图|周期波动可分解为不同啮合阶次|首样本相位为0，保留Nyquist幅值规则，近零幅值不报告相位|
|瞬时接触斑点|固定相位的接触带具有有限半宽和横向压力变化|只取一个相位和一个齿对，按局部 Hertz 半宽展开压力，区分条带式重建与二维接触求解|
|周期接触包络|承载位置和载荷随啮合位置变化|在采样点凸包内线性插值，使用最近求解单元活动状态遮罩未接触区，不向凸包外推|
|方案对比图|减小 TE 和减小局部压力可能需要取舍|相同工况、材料、离散和模型；同时报告多项指标|
|修形曲面图|组合修形在不同齿向位置产生不同的法向间隙|直接评价参数化曲面，正值为材料去除；不冒充实测表面|
|多工况散点图|单一工况下最优的方案未必在工况集合中占优|各工况逐一求解，给出最坏值和 Pareto 候选，保留失败和约束状态|
|网格收敛图|离散改变引起的误差需要独立于物理模型误差检查|保持输入相同，只改变条带数，保存每一级结果；峰值边缘压力单独检查|

图面采用真实物理单位、可编辑文字 SVG 与 220 dpi PNG。瞬时斑点按参考工程云图使用蓝至红的连续色阶，蓝底表示零压力；周期包络采用独立色阶，浅灰色表示未接触或未采样区。每组对比共用量程。TE 和刚度保留原相位数据的分段线性曲线，不用样条美化跳变。定量图附 CSV；完整数组由案例输出 NPZ 保存。数据来自确定性计算，没有重复试验或统计误差条。

## 瞬时接触斑点：contact_pattern

固定一个求解相位和一个齿对，沿接触线坐标为 s，齿面内垂直接触线的局部坐标为 n。由求解器给出的线载荷 q(s)、组合曲率及材料计算 Hertz 半宽 b(s) 和峰值 p0(s)，展开：

```text
p(s,n) = p0(s) sqrt(max(0, 1 - (n/b(s))²))
```

沿线对 q 和曲率作线性插值，保留原条带中心的数值；线端延伸半个积分单元并保持端点值，不人为添加圆滑的端部效应。对于本项目每条接触线的均匀条带，插值后 q 沿线的积分恢复该齿对原载荷；横向半椭圆的压力积分恢复 q。原始条带、展示网格分别保存于 `contact_pattern_source.csv`、`contact_pattern_data.csv`。

横轴使用 mm，纵轴使用 μm，图中明确标注横向放大。纵轴是**齿面内距离**，不是法向压陷量。不同齿对的局部坐标不重叠；选择器默认只显示该相位载荷最大的齿对。

这仍是**条带式 Hertz 压力重建**，不是求解二维半空间压力和自由接触边界。未修形直齿轮可形成长条带；鼓形可能使承载区收缩并呈椭圆状，失准可能导致偏斑或边缘截断。不能用预设椭圆轮廓替代求解结果，也不能把光滑外观当成二维接触精度证据。零载荷保持零压力。

## 周期接触包络：contact_envelope

将一个基节周期内的候选接触线投到同一个小轮齿面坐标，展示**周期扫掠的承载接触包络**及各采样位置的 Hertz 峰值压力。原来的大片横带来自这个周期图，不应把它命名为瞬时斑点，也不是着色试验照片。

二维云图使用线性插值，数值不超出参与插值的采样值范围；最近求解单元为非活动时将展示像素遮罩，避免填满未接触区和内部孔洞。采样凸包外也被遮罩，不补画到齿面边缘。边界是随离散分辨率变化的展示近似，不能从图面反算接触面积或峰值。零载荷不显示接触斑点。峰值、TE 和刚度指标始终由原始数组计算。

输出文件采用描述性 `snake_case`：`contact_pattern`、`contact_envelope`、`transmission_error`、`mesh_stiffness`、`modification_surface` 和 `design_comparison`，每种图同时输出 PNG/SVG。

## 重建 README 示例

```bash
python -B examples/generate_readme_figures.py
```

默认使用 64 相位、41 条带，重新计算三个相同齿轮几何、材料与 80 N·m 载荷的方案：对中无修形、12 μm 失准、失准加 10 μm 齿向鼓形。另算对中、10 μm 齿向鼓形的独立案例，在相位 0.375 绘制单齿对瞬时斑点；此案例不混入原来的三方案 TE 和刚度对比。完整数组、配置、原始接触点及图表保存到 `output/readme_examples/`；精选 PNG 和响应 CSV 更新到 `docs/assets/` 与 `docs/data/example_responses.csv`。命令支持 `--phases`、`--strips`、`--output` 和 `--assets`；降低分辨率仅适合快速预览。

## English

`contact_pattern` is an **instantaneous, single-tooth-pair strip-wise Hertz reconstruction**. At one computed phase, line loads and curvatures are interpolated along the contact line and the pressure is expanded across each local Hertz half-width. Original strip-center pressures and widths are retained. Integration across the band recovers the line load; along-line integration recovers the selected tooth-pair load for the uniform strip grids used here. No artificial end taper is added. Source strips and display samples are exported separately. The transverse, in-surface axis uses μm and is enlarged relative to the along-line mm axis.

This reconstruction does not solve the full two-dimensional pressure field or free contact boundary. Unmodified spur gears can show a long strip, crowning can localize contact, and misalignment can produce a shifted or truncated patch. An ellipse is not imposed. Zero load gives zero pressure.

`contact_envelope` shows the **loaded contact envelope swept over one base-pitch cycle**, with local peak Hertz pressure mapped onto pinion face-width/roll coordinates. It differs from the instantaneous footprint and from experimental marking patterns.

The display uses linear interpolation inside the sampled convex hull. Pixels nearest to inactive solver cells and pixels outside that hull are masked. The resulting boundary is a resolution-dependent display approximation. No interpolation is used to calculate metrics; all peaks, TE and stiffness values come from solver arrays. Unloaded cases show no contact patch. Comparisons share one pressure scale. TE and stiffness curves connect original phase samples without spline smoothing.

Run the command above to regenerate the README gallery and its source data. Figures are exported as 220 dpi PNG and SVG with editable text; full inputs and arrays remain in the output directory.

## 参考 / References

- [COMSOL：圆柱线接触验证与横向 Hertz 压力](https://doc.comsol.com/6.4/doc/com.comsol.help.models.sme.cylinder_roller_contact/cylinder_roller_contact.html)。
- [COMSOL：具有两个有限半轴的椭圆接触示例](https://doc.comsol.com/6.3/doc/com.comsol.help.models.fatigue.linear_guide/linear_guide.html)。

检查包括字体、坐标与单位、图例遮挡、颜色尺度、零载荷行为、接触边界和源数据对应。任何未收敛结果不得作为正常方案排序。
