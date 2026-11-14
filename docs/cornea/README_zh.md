# 健康角膜与典型圆锥角膜：合成几何对照 v0.1

按吴孟城 2026-11-14 的要求，在 MotionBricks fork 中搭建一组可复现的角膜模型。
本模块是独立 CPU 几何工具，不调用动作模型权重。

- [离线互动观察页](generated/index.html)：下载后直接在浏览器打开；拖动同步旋转，按钮切换正面、侧面和斜视。
- [健康角膜 OBJ](generated/healthy.obj) / [圆锥角膜 OBJ](generated/keratoconus.obj)：可导入 Blender 等网格工具，单位 mm。
- [模型与参数 JSON](generated/models.json) / [文件 SHA-256 清单](generated/manifest.json)。

## 形态与参数

| 项目 | 健康参考 | 圆锥示意 | 数值身份 |
|---|---|---|---|
| 模型口径 | 直径 10 mm | 相同 | 选定的中央角膜观察窗口，不是全角膜直径 |
| 前表面参考曲率半径 R | 7.8 mm | 同一底面 | 参考正常角膜量级 [S1]，非人群均值拟合 |
| 非球面参数 Q | −0.25 | 相同 | 设计选择 |
| 中央轴向厚度基线 | 550 µm | 同一基线叠加局部减薄 | 设计参考值；非患者数据 |
| 周边增厚 | 120 µm | 相同 | 设计选择 |
| 局部中心 (x,y) | 无突出/减薄 | (0.5, −0.9) mm | 设计选择，表现偏下方形态 |
| 局部宽度 σ | 不起作用 | 1.1 mm | 设计选择 |
| 中心处前移幅度 | 0 | 0.28 mm | 设计选择，不是总高度或独立测得的后表面高度 |
| 中心处减薄幅度 | 0 | 0.20 mm | 设计选择，局部厚度约 355 µm |

“典型”表示演示局部变薄、偏心突出等常见形态特征 [S2]，不表示所有患者都如此，
也不表示临床平均形状、诊断阈值或某一严重程度。网格采样最薄点约 350 µm，
与预设锥中心不必重合；采样最小值不是解析全域最小值。

坐标：x 为横向，+y 为上方，+z 为向前；没有指定左右眼，不能把 +x 解释为鼻侧或颞侧。
两个网格各 3,458 顶点、6,912 三角面，包含前表面、后表面和闭合侧壁。
观察页默认 xyz 相同物理比例；z 轴放大可选 1–3 倍，数值始终明确显示。
截面图单独缩放坐标轴，不能按截图的像素间距测厚。

## 定义与可复现方法

令 a 为口径半径，r²=x²+y²，采用非球面弧高：

`s(r) = r² / [R + sqrt(R² − (1+Q) r²)]`。

局部形变使用平滑高斯乘以边缘衰减项：

`B(x,y) = exp(−[(x−xc)²+(y−yc)²]/(2σ²)) × (1−r²/a²)² / (1−(xc²+yc²)/a²)²`。

因此 B 在预设中心为 1，在边缘为 0 且边缘一阶导为 0。B 的最大值不一定在预设中心，
所以幅度参数不是全域最大位移。前表面与轴向厚度为：

`z_front = s(a) − s(r) + A×B`；

`t_axial = t0 + Δt_edge×r²/a² − D×B`；

`z_back = z_front − t_axial`。

厚度明确指同一 x,y 位置的 z 向间距，**不是法向厚度**。后表面并非独立拟合的另一非球面。
这些公式是一组描述性构造；没有求解力平衡，没有质量守恒或组织生长方程。
局部减薄会改变壳体体积，不代表已经模拟胶原丢失或层板滑移。

```bash
python -S -m motionbricks.cornea --out-dir /tmp/cornea --template docs/cornea/viewer.template.html
python -S -m unittest discover -s tests/cornea -v
node tests/cornea/check_viewer.cjs
# 更新仓内预生成文件：
python -S -m motionbricks.cornea --out-dir docs/cornea/generated --template docs/cornea/viewer.template.html
```

仅使用 Python 标准库；HTML 内嵌数据与脚本，无 fetch、CDN 或外部运行依赖。
OBJ 与 JSON 保留真实 mm 尺寸，视图放大不改变导出数据。

## 与此前机制讨论的关系

胶原生成、纤维组装/交联成熟、长期维护/重塑三条线均可能参与圆锥角膜。
胶原层板取向和分布研究支持层板滑移参与形变的解释 [S3]，但静态形态不能确定起始缺陷。
前述“LOX 异常”也不能简化为所有交联总量下降：直接 LC–MS 研究发现部分交联组分改变，
但总交联密度未显著下降 [S4]。

本版本不把易感基因名、mRNA、交联量或蛋白酶水平直接换算为几何参数。
未实现组织五层分层、胶原微纤维、法向厚度、应力应变、眼压、病程、光学、视力或治疗预测。
若继续推进，需独立引入角膜断层数据、材料本构参数与边界条件，并验证后才能声称生物力学仿真。

## 来源

以下来源用于限定形态与机制解释，不声称这些论文给出了本模型的全部数值。
检索日期：2026-11-14。

- **S1**：*A clinical study of the association between thickness and curvature of the central cornea.*
  正常前表面水平、垂直中心曲率半径均值分别为 7.86、7.66 mm。
  [PubMed 6624411](https://pubmed.ncbi.nlm.nih.gov/6624411/)。
- **S2**：AAO，*Corneal Ectasia Preferred Practice Pattern*（2024）。
  圆锥角膜局部变薄、突出和不规则曲率特征；偏下方只是可能构型之一。
  [指南](https://www.aaojournal.org/article/S0161-6420(24)00010-1/fulltext)。
- **S3**：*A study of corneal thickness, shape and collagen organisation in keratoconus using videokeratography and X-ray scattering techniques.*
  [PubMed 17178118](https://pubmed.ncbi.nlm.nih.gov/17178118/)。
- **S4**：*An Evaluation of Lysyl Oxidase-Derived Cross-Linking in Keratoconus by Liquid Chromatography/Mass Spectrometry.*
  17 个手术病例与 11 个对照角膜；交联组分差异与总密度结果应分开。
  [PubMed 26780316](https://pubmed.ncbi.nlm.nih.gov/26780316/)。

## 验证范围

标准库测试覆盖：健康轴对称、局部幅度和减薄、边界连续、正厚度、封闭且方向一致的网格、
错误网格拒绝、非法参数拒绝、确定性导出、OBJ 数量与 SHA-256。
Node VM 另检查 Python/JavaScript 逐顶点一致性、显示按钮、共享旋转状态、放大标签、
画布绘制坐标有限性与离线依赖。它使用 DOM/canvas 测试替身，不替代真实浏览器。
本次真实 Chromium 启动被环境的 socket 权限限制阻断，因此没有实测浏览器布局、触屏或性能。
几何网格另经静态渲染目视核对。详见 [本次验证记录](validation.json)。本地验证与 GitHub CI 分开；
无患者拟合、临床验证或真实组织实验。
