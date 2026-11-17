# Engineering brief / 工程说明
**Independent concept / 独立概念 · v0.1 · 2026-11-17**

All requirements below are proposed requirements for a future engineering programme. None has been validated. This document is not build-ready control software, a homologation specification or a completed safety case.
以下为后续工程项目的候选要求；尚未验证，不是可直接制造的设计或已完成的整车安全论证。

## 1. Baseline / 基线

| ID | Requirement / 要求 | Status / 状态 |
|---|---|---|
| VEH-01 | Approximately 12 m, single deck, battery electric, low-floor urban bus / 约12米、单层、纯电、低地台城市巴士 | Concept target / 概念目标 |
| VEH-02 | Approximately 30 seats and 70 total occupants; wheelchair deployment changes the layout; total capacity requires area, passenger mass, gross mass and axle-load checks / 约30座、总载客约70人；轮椅区展开须调整布置并复核面积、乘客质量、总质量和轴荷 | Uncalculated / 未核算 |
| BAT-01 | Evaluate LFP chemistry, pack protection, service access, low-floor clearance, axle loads and roof mass together / 联合评估磷酸铁锂、电池防护、维修通道、低地台净空、轴荷及车顶质量 | Packaging study pending / 待布置研究 |
| BAT-02 | Determine gross and usable energy separately, including ageing, usable SOC window, route reserve and seasonal auxiliaries / 分别确定总能量与可用能量，计入老化、SOC窗口、线路余量和季节附件负荷 | Capacity TBD / 容量待定 |
| PWR-01 | Size continuous power for full-load grades, ambient temperature and auxiliaries; state peak power separately / 按满载坡道、环境温度和附件负荷选择持续功率，峰值单列 | Power TBD / 功率待定 |
| CHG-01 | Evaluate voltage architecture and depot-compatible charging against connection capacity, duty cycle and battery temperature / 按车厂电力容量、班次、电池温度评估电压平台及充电方案 | Voltage, interface and power TBD / 均待定 |
| CHS-01 | Air suspension, controlled damping and load-aware calibration; qualify bus-specific components / 空气悬挂、可控阻尼、载荷标定；另行验证客车级部件 | Proposed / 拟采用 |
| CHS-02 | Assess rear steering only after swept-path, tail-swing, failure-state and maintenance analysis / 后轮转向须先评估扫掠路径、尾摆、故障状态及维修 | Optional study / 可选研究 |
| ACC-01 | Plan wheelchair access, securement, stroller allocation, priority seats, handholds, stop controls and readable information together / 综合设计轮椅通行固定、婴儿车空间、优先座、扶手、按钮与可读信息 | Layout pending / 待布置 |
| SVC-01 | Replaceable body sections, accessible electrical and cooling modules, isolated service work and documented diagnostics / 外饰分段更换、电气与冷却模块可接近、维修隔离及诊断说明 | Service study pending / 待维修研究 |
| HUM-01 | Driver visibility, seat adjustment, glove-operable physical controls and a full-shift ergonomic study / 司机视野、座椅调节、戴手套实体控制及全班次人因研究 | Unvalidated / 未验证 |
| STYLE-01 | Burgundy/ivory exterior, rounded nose, lamp shoulders, four-point lighting motif, clean sides and warm-grey cabin / 酒红奶白、圆润车头、灯肩、四点式灯光、简洁车侧及暖灰内饰 | Styling intent / 造型意向 |

No numerical range, charging time, energy saving, comfort improvement or operating-cost advantage is claimed. Passenger capacity is a target, not certified capacity. A low floor does not imply an entirely flat floor to the rear; the final accessible path and rear arrangement remain to be resolved.
未宣称续航、充电时长、节能比例、舒适改善幅度或成本优势。低地台也不等于直到车尾完全平整，最终通行路径与后部布置待确定。

## 2. LH-START: fixed author requirement / 左手启动：作者固定要求

> “不管系油系电，一定要左手打火”

**LH-01:** The normal driver start control shall be a physical control to the left of the seated driver. Retain this location for left-hand-drive and right-hand-drive versions. Do not mirror it to the right when adapting the cockpit.  
正常驾驶启动控制必须是位于司机坐姿左侧的实体装置；左右舵版本均保留在左侧，驾驶舱换边时不得顺手镜像至右侧。

**LH-02:** Apply the placement rule to combustion, hybrid and electric derivatives if developed. The first proposal remains battery electric; this does not announce additional programmes.  
如后续开发燃油、混动或纯电衍生型，位置要求一律适用；当前仅提出纯电基线。

**LH-03:** For the electric concept, use a tactile rotary start request with clear labels and visible state feedback. It must be reachable without excessive trunk rotation and assessed against door controls, egress and accidental operation in both driving layouts.  
纯电概念采用有触感的旋转启动请求，具备清楚标识与可视状态反馈；须评估触及范围、躯干扭转、车门控制、疏散与误操作。

**LH-04:** A control turn is a request, not evidence of readiness. Require a deliberate start action and service-brake application; the detailed authorisation and enable logic must be established by vehicle safety engineering.  
旋转只是请求，不证明车辆可行驶；要求主动启动动作及行车制动踏板输入，具体授权和使能逻辑由整车安全工程确定。

**LH-05:** The proposed sequence is OFF → CHECKING → READY or FAULT/NOT READY. READY requires the relevant electrical and control checks to pass. Direction selection and parking-brake release are separate actions. An open door, deployed ramp, connected charger or unresolved enabling fault must inhibit propulsion as defined in the final architecture.  
概念状态顺序为关闭→检查中→就绪或故障/未就绪；方向选择与驻车释放独立。最终架构应对车门开启、坡板展开、充电连接和未解决使能故障设置驱动抑制。

**LH-06:** Power-up must not cause vehicle motion. Following power interruption or fault reset, restored control power must not by itself authorise propulsion. Startup, normal shutdown and emergency functions require distinct engineering definitions; turning the normal start control while moving must not abruptly remove necessary braking or steering support.  
上电不得导致移动，断电恢复或故障复位不得自行授权驱动。启动、正常停机与紧急功能分别定义，行驶中操作正常启动装置不得突然移除必要制动或转向支持。

These are high-level design constraints, not a validated interlock implementation. Servicing and depot preconditioning need separate safe operating modes and do not permit unattended vehicle movement.
以上是高层约束，不是已验证互锁实现；维修及车厂预调温须另定义安全模式，不允许无人车辆自行移动。

## 3. Evaluation matrix / 验证矩阵

Every row currently has status **NOT RUN / 未执行**. Numerical thresholds must be fixed before testing; no pass can be reported without them.

| Test | Conditions / 条件 | Evidence required / 所需证据 |
|---|---|---|
| Left-hand reach | Left/right-hand-drive mock-ups; intended driver anthropometric range; gloves / 左右舵模型、目标司机体型范围、手套 | Reach measurements, task errors, interference and video / 触及数据、误操作、干涉及录像 |
| Startup states | Failed checks, door/ramp/charger states, power interruption and deliberate control use / 检查失败、门/坡板/充电状态、断电及主动操作 | Timestamped state and torque-enable logs; proof of no unintended movement / 状态及使能日志、无意外移动证据 |
| Brake blending | Empty/full load; warm/cold battery; high SOC; reduced regeneration / 空满载、冷暖电池、高SOC、受限回收 | Deceleration, jerk, stopping distance and pedal response / 减速度、加加速度、制动距离及踏板响应 |
| Cabin motion | Front/rear seats and standing areas; bends and uneven surfaces / 前后排与站立区、弯道及不平路面 | Longitudinal/lateral/vertical acceleration, roll/pitch, participant feedback / 三轴加速度、侧倾俯仰及反馈 |
| Thermal endurance | Route grades, full load, climate and repeated door opening / 线路坡道、满载、气候及反复开门 | Motor/battery temperatures, derating, HVAC loads and energy / 温度、降额、空调负荷及耗电 |
| Accessible operation | Representative users and mobility aids, boarding and securement / 代表性使用者与辅助器具、上下车及固定 | Timings, clearances, task completion and user feedback / 时间、净空、完成率与反馈 |
| Maintenance | Typical exterior damage and selected electrical/cooling faults / 常见外饰损坏及选定电气冷却故障 | Safe isolation procedure, repair time, parts and access / 隔离流程、工时、零件与可接近性 |
| Fleet pilot | Only after required approvals; complete seasonal coverage / 获得必要审批后，覆盖完整季节 | Availability definition, cancelled trips, kWh/km, maintenance hours and occupancy / 出勤口径、取消班次、耗电、维修工时与载客率 |

Emergency performance and stability constrain all comfort optimisation. Report measured comfort together with stopping distance and relevant operating conditions. Use safely staged and approved test methods; this document does not authorise trials with standing passengers.

## 4. Feasibility gates / 可行性关口

1. Freeze route and depot assumptions; calculate duty-cycle energy, mass, axle loads, accessible layout and service access.
2. Select experienced partners and components; establish applicable-market approval and safety plans from current official requirements.
3. Validate control concepts in mock-ups and engineering environments; prototype and closed-course work only within an approved programme.
4. Complete necessary approval and service preparations before any passenger-service pilot.
5. Assess a small fleet through winter and summer using declared baselines. Account for electricity, demand charges, depot infrastructure, battery replacement assumptions, labour, downtime, financing and occupancy.

依次明确线路与车厂假设、合作部件及适用要求、人因与工程验证、必要审批，再进行冬夏试点。每客公里成本必须公开载客率及基础设施等成本假设。

Bus manufacturing cooperation, Porsche involvement, fleet size, production dates and budgets are all uncommitted. No regulation or certification compliance is asserted by this document.
