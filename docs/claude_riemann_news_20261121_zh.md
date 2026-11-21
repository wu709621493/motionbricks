# Anthropic老哥怒以25万页代码证明黎曼猜想

2026 年 11 月 21 日 · 时事小记

1859 年，黎曼留下一个问题，一句话就能抄完：黎曼 ζ 函数的每一个非平凡零点，实部是不是都等于 ½？这关系到素数的实际个数能偏离估计值多远。167 年后，在 Anthropic 工作的数学家 Levent Alpöge 发了四页说明，说他相信自己和 Claude 找到了证明。四页，周末读书会完全来得及。然后你点开第一页的脚注，附件从 `part01` 排到了 `part14`。 [克雷数学研究所 · 黎曼猜想](https://www.claymath.org/millennium/riemann-hypothesis/) · [Alpöge 的四页说明及分卷链接](https://alpo.ge/remark.pdf)

标题里的「25 万页」还有个更好笑的出处。公开的附件约有 **1700 万行 Lean 代码**。超过 **25 万页** 的，是 Alpöge 试着让 Claude 展开的文字稿。他在脚注里记下了翻开这部巨著的体验：定理一开头，先提醒读者，一个实数如果不等于 ½，那么它要么大于 ½，要么小于 ½。 [Alpöge 的四页说明及分卷链接](https://alpo.ge/remark.pdf) · [美联社 · 公开代码规模](https://apnews.com/article/anthropic-claude-math-solution-ai-4fe8b69a891f160f9e7f0c85af8c55c8)

读到这里，我第一次对数学教授上课跳过六行板书、只肯讲一句「显然」，产生了真挚的感激。

玩笑归玩笑，真有人把十四个分卷接起来验了。到北京时间 11 月 21 日 18:05，MIT 数学家 Andrew Sutherland 的核验记录显示，**175,187 个模块全部通过 Lean 内核逐一复查**，两套独立编写的检查器也接受了完整的导出证明。最后那条定理用的是公共数学库 Mathlib 原有的黎曼猜想定义。另有检查仍在运行，克雷数学研究所的题目页当天仍标作「未解决」。 [Sutherland 的独立核验记录](https://math.mit.edu/~drew/grh/) · [克雷数学研究所 · 黎曼猜想](https://www.claymath.org/millennium/riemann-hypothesis/)

最让我惦记的是老哥自己。他从学生时代就打算花几十年攻这道题。这回他认出了两条思路该在哪里会合，到了最后一程，照他自己的形容，Claude 已经在终点线旁跳起了舞。他接下来想做的，是把论证想透，再好好写一遍。等那一版出来，我想听他讲的恰好是机器最难替读者回答的一句。 [Alpöge 的四页说明及分卷链接](https://alpo.ge/remark.pdf)

**老哥，几时开始觉得，条路真系行得通㗎？**
