# 锁住差二，同埋追问「完美方差」：两次数学实验回望

吴孟城（Mengcheng Wu）｜2026 年 11 月 24 日

> 当年噶我数学造诣不深，但系我认为我系够资格挑战哩两题噶😏

## 孪生素数：隔几耐生成第二列，最后都要核对差二

吴孟城今日回忆，当时想先生成一列素数，隔一段不定嘅时间再生成第二列，两列配对时将差数锁止为二，再用穷举累积孪生素数嘅例证。

当年 Codex 提交嘅 `twin_prime_pairs(limit)` 生成一列有序素数，同错开一个位置嘅自身逐项比较。例如上限取 13，就会留下 (3, 5)、(5, 7)、(11, 13)。每次命中都可以独立核对。代码入面嘅条件系两个数相差 2，生成时间无参与判断。后续实现容许指定一组偏移量，取 (0, 2) 就同时检查两个位置嘅数系咪素数。[原始配对程序 #14](https://github.com/Guilty-Crown-x-Gintama-Ninjas/bootcamp/pull/14/files) · [偏移量推广 #23](https://github.com/Guilty-Crown-x-Gintama-Ninjas/bootcamp/pull/23/files)

要由呢批例证行到猜想，仲差一句要对任意上限都成立嘅论证：无论畀定几大嘅整数 B，点解一定仲有一个大过 B 嘅素数 p，使得 p + 2 亦系素数？

## 黎曼 ζ 函数：个方差究竟睇得到乜？

吴孟城今日回忆，当时想将收敛函数套喺 ζ 函数上，再引入方差，试吓能否用「完美」嘅方差刻画黎曼猜想。对应嘅两份代码记录咗数值实验嘅前半段。第一份用 Hasse 级数截断求和，近似计算 ζ(s)。第二份固定 s = 1/2 + it，默认喺 13 到 15 之间搜索令 |ζ(s)| 尽量细嘅 t；测试用约 14.134725 嘅首个正虚部零点高度作核对。两份改动都未定义「完美方差」嘅样本同公式。[Hasse 级数实现 #22](https://github.com/Guilty-Crown-x-Gintama-Ninjas/bootcamp/pull/22/files) · [临界线搜索及测试 #25](https://github.com/Guilty-Crown-x-Gintama-Ninjas/bootcamp/pull/25/files)

今日复盘时，可以用一个具体问题检验呢个设想：假如有一个非平凡零点偏离临界线，个统计量会点反映？例如直接收集上述搜索返回嘅实部，每个值都会系程序预先写入嘅 1/2，算出零方差系必然结果。要继续追问，就要讲清楚点样让潜在嘅线外零点进入观察范围，以及点解任何一个偏离都足以令判据失效。

## 欢迎切磋

吴孟城留畀 Alpoge 同其他有兴趣读者嘅话：

> 如果Anthropic过边个Alpoge可以黎睇下我噶思路噶话，我认为大家友好交流系冇问题噶😏

For Alpoge and other interested readers: I’d welcome a friendly discussion of these early experiments. How could a variance criterion detect a hypothetical zero off the critical line? — Mengcheng Wu (English rendering of the invitation and discussion question)
