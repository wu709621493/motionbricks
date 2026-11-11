# 真假刘亦菲：同招不同步

一个用来探索 MotionBricks 双人动作制作流程的原创 CPU 分镜实验。
“刘亦菲”是戏仿角色 A 的舞台标签；“刘亦飞”是虚构角色 B。
两人均为抽象人偶，不代表演员参与、授权或真实言行，也不作身份鉴定。

## 先看效果

在仓库根目录运行，无需安装第三方包、CUDA 或模型：

```sh
python experiments/yifei_double/build.py
```

用浏览器打开 `experiments/yifei_double/output/Yifei_Double_Audition.html`。
文件离线运行，不加载网络资源。点击“开始试镜”播放一次；可拖动时间，
调节右侧角色 0–1 秒的延迟、左右镜像和观看角度。

| 时间 | 分镜 | 台词（原创虚构） |
| --- | --- | --- |
| 0–4 秒 | 同台入场 | 导演：“两位，先走一遍。” |
| 4–8 秒 | 转身回眸 | 导演：“我说回眸，没说回炉。” |
| 8–12 秒 | 持道具亮相 | 刘亦飞：“她负责仙，我负责飞。” |

“真假”的喜剧来自导演给定的同步要求；B 故意慢半拍或镜像，A 作为动画参考。
这不是演员真伪、专业水平或相貌的评价。

## MotionBricks 这次实际出了哪些力

| 层级 | 本实验状态 | 说明 |
| --- | --- | --- |
| 原创动作、双人时间线、前向运动学 | 已实现、CPU 执行 | 12 秒，30 Hz，361 个采样点，30 个关节 |
| MotionBricks SOMA 姿态格式 | 已调用仓库校验器 | 四个 context + 四个 target，局部 XYZ 米 + XYZW 单位四元数，Y 向上 |
| 神经动作生成与补帧 | **NOT_RUN** | 本次环境没有可用 CUDA 驱动、Warp、TensorRT 和已展开的模型权重 |
| SOMA 精确骨架比例、重定向 | **NOT_VALIDATED** | 本实验骨长为原创示意值，不能由格式合格推断模型适配 |
| 双人碰撞、接触、足底约束、布料 | **NOT_SIMULATED** | 图中道具和袖形是绘制元素；动作可能脚滑、穿地、穿插 |
| 真人面部、声音与身份识别 | **NOT_IMPLEMENTED** | 仅使用角色名和抽象人偶 |

浏览器播放的是原创解析动作计算后的关节坐标。坐标之间的线性插值只改善
显示连续性，**不是 MotionBricks 的神经补帧结果**，不保证采样点之间骨长严格不变。
右侧延迟采用端点夹紧，不在开头倒绕到结尾；镜像同时翻转 X 坐标并交换左右关节。

界面的“姿态差”是两人去除各自根位置后的同名关节坐标 RMS，单位 cm；
保留朝向差，不做最佳刚体配准，非骨长误差、真实度评分或生物特征指标。
设定延迟为零、关闭镜像时应为零；加入延迟时只在动作变化区间产生差异。

## 可复核的输入和测试

构建还导出 `output/soma_pose_window.json`。context 时间为 3.9、3.933…、
3.966…、4.0 秒；target 时间为 5.0、5.033…、5.066…、5.1 秒。
当前只导出参考角色 A 的单个格式样本；B 的显示延迟和镜像没有作为模型输入导出。

```sh
python -X warn_default_encoding -W error::EncodingWarning -m unittest discover -s experiments/yifei_double -v
node experiments/yifei_double/test_preview.cjs
python tools/preflight.py --model soma --poses experiments/yifei_double/output/soma_pose_window.json --json
python tools/preflight.py --model soma --require-runtime --json
```

最后一条严格环境检查在本次机器返回失败是预期结果。普通预检退出 0 仅表示
离线检查通过，不等于推理成功。执行证据见本目录 `evidence.json`。

Node 脚本使用模拟 DOM/Canvas 检查交互逻辑，不是浏览器测试。本次本地 Chromium
无法启动，云浏览器策略也不允许本地文件 URL，因此尚未完成画面和手机布局的目视验收。

专用工作流 `Yifei double CPU preview` 在 Ubuntu、Windows、macOS 上使用
Python 3.12 / Node 22 执行构建、6 项 Python 测试、交互逻辑和姿态校验。
覆盖中文 UTF-8 文件读写、镜像时道具随持有手反射，以及拖动进度后的播放按钮文案。
工作流存在不代表某次运行成功，具体结果以对应提交的 Actions 记录为准。

`build.py` 仅使用 Python 标准库；会核对当前 SOMA manifest 关节顺序，并调用
现有 `tools/preflight.py::validate_poses`。渲染数据由这些姿态计算，非另一套手工动画。
本实验没有读取、打包或衍生 NVIDIA sample motion clips；生成文件可由代码重建。

## 接下来让模型真正出力

1. 在受支持 NVIDIA GPU 环境展开 LFS、安装仓库锁定依赖，严格预检通过。
2. 将此处原创动作重定向到实际 SOMA 骨架；检查局部轴、静止姿态和比例。
3. 按 [Runtime API](../../docs/runtime_api.md) 的 context/target 接口分别驱动两个角色；
   为每次生成保存配置、提交 SHA、实际输出与耗时。当前并无这个双人推理适配器。
4. 输出末尾四帧接入下一段 context。模型自主决定生成时长，必须另外做双人时间协调。
5. 对比程序参考和真实模型输出，实测足底滑移、目标误差、关节连续性和双人碰撞。
   最后再增加人物美术、服装、镜头和渲染。

MotionBricks 负责身体动作衔接；双人编舞、人物造型和电影成片仍需应用层完成。
现有实现支持做这套制作流程的前期试镜，不支持宣称已完成数字真人影片。

代码采用 Apache-2.0，与仓库代码许可一致。
