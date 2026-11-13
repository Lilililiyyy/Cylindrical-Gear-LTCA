# 更新记录

按版本从新到旧记录。每个版本使用 `## [版本号] - YYYY-MM-DD`，在「新增」「变更」「修复」「验证」中选用适用的小节。日期为版本在主分支的登记日期。

## [0.4.0] - 2026-11-13

### 新增

- 在内置齿梁模式下支持齿轮、两根阶梯轴与线性轴承的准静态耦合。刚性箱体上的轴承支承与轴段共同变形，并反馈至每个相位的齿面载荷分配。
- 输出各相位的轴节点位移、转角、轴承反力及条带法向位移，支持从导出的 JSON 复算。[模型与算例](docs/shaft_bearing_coupling.md)

### 验证

- 简支梁解析解、刚性极限及柔性支承下的载荷重分配均通过校核。原有 10 案响应回归通过。[轴系功能提交](https://github.com/Lilililiyyy/Cylindrical-Gear-LTCA/commit/b351154a63d48f49b90fb971aa8f4f7db99e1285)

## [0.3.0] - 2026-11-12

### 新增

- 增加固定版本响应回归和多工况空间／相位收敛矩阵。
- 修形方案比较支持显式选择中心或独立端点压力，并将选择用于压力约束、Pareto 筛选和图表，默认采用中心压力。[验证说明](docs/first_round_validation.md)

## [0.2.1] - 2026-11-02

### 新增

- 增加统一色标的候选方案比较及经哈希校验的原结果重绘。

### 修复

- 统一通用工况与对标案例的接触图实现，按实际啮合范围显示接触，保留中心单元的有限显示支撑。[对应提交](https://github.com/Lilililiyyy/Cylindrical-Gear-LTCA/commit/cb2e1ec8a8d1ac2b6137aa6a9b781b9a797c6a7f)

## [0.2.0] - 2026-10-30

### 新增

- 增加 ISO 综合刚度与 Love 条带模型、齿顶延伸及 ISO 6336:2006 显式因子强度计算。
- 补充 18/77 工况的 MASTA 对标、三周期曲线、接触压力图与失准／鼓形敏感性结果，以及中英文说明。[对应提交](https://github.com/Lilililiyyy/Cylindrical-Gear-LTCA/commit/f8ab9d434fcf475056ca90747fd5abc088ecf5ff)

### 变更

- 项目于 2026-10-31 采用 AGPL-3.0-only。[许可变更提交](https://github.com/Lilililiyyy/Cylindrical-Gear-LTCA/commit/c63030d)

## [0.1.0] - 2026-10-27

### 新增

- 建立渐开线圆柱齿轮几何、齿面修形、齿梁弹性、Hertz 接触、准静态承载接触求解与多工况方案比较。[对应提交](https://github.com/Lilililiyyy/Cylindrical-Gear-LTCA/commit/7f16631b16da0c9ac885f424b6310d48fbcb6925)
