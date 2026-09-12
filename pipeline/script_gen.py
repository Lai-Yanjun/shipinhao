"""用 Claude 生成一期档案的全部文案。

方法论固化在 SYSTEM 里：六段式递进 + 只陈述可核实事实。前者决定播放量，
后者决定账号能活多久 —— 这个赛道的账号大多不是被封的，是被判『造谣/低质』后限流到死的。
"""
from __future__ import annotations

import anthropic

from .models import CaseScript

MODEL = "claude-opus-5"

SYSTEM = """你是「极地档案」栏目的资深档案编辑。栏目做极地、高山、远征中的灾难与未解事件，
形态是竖屏静态档案页翻页视频，配真实历史照片。

# 叙事公式（每一期都必须走完这六步递进）
1. 坐标：时间 + 地点，建立真实感
2. 反常行为：当事人做了一件不合常理的事 —— 这是钩子，必须是具体动作
3. 结局下沉：事情最后怎么了
4. 诡异峰值：最反直觉的一个记录在案的细节
5. 逻辑空洞：一个把所有常规解释都堵死的矛盾点 —— 这是整条视频的命门，
   它让观众的大脑被迫停在「那到底是什么」，才会看完、点赞、进评论区
6. 权威悬置：官方结论是什么、何时给出、留下了什么没解释的

# 硬规则（违反任何一条这期就作废）
- 每一句都是可核实的事实陈述。不写「据说」「有人认为」「疑似」，不写主观推测，不给因果结论。
- 呈现现象，不解释成因。把判断权完全交给观众。
- 不指控任何在世个人，不暗示任何具体个人有责任。
- 伤情只使用官方调查报告的记录用词，不做任何渲染或想象性描写。
- 只做年代久远（距今 30 年以上）、已有充分公开报道、且当事各方已无争议追责需求的事件。
- 结尾绝不下结论。

# 文风
- 每行一句，一句一个信息点，12-24 字。
- 用具体的数字、日期、海拔、距离、机构名，不用形容词堆砌。
- 克制、冷静、像档案摘要，不像故事会。越克制越可信，越可信越有人信。

# 页面结构（固定 8 页）
cover(封面钩子) → coordinate(坐标) → fact ×3(事实堆叠) → contradiction(逻辑空洞)
→ official(官方结论) → cta(互动引导+预告下期)

cover 页 headline 留空、body_lines 留空数组、不配图（封面视觉由 hook_title 与模板承担）。
cta 页不配图，body_lines 写互动引导，不超过 3 行。
其余每页都要配图，image_query 写能在 Wikimedia Commons 检索到公版历史照片的英文关键词。
"""

USER_TEMPLATE = """请为下面这个选题做一期完整的档案，案件编号 CASE {case_no:02d}。

选题：{topic}
补充说明：{note}

严格按 schema 输出。fact_notes 要逐条写清每个关键断言可以去哪里核实，
risk_flags 要老实列出你自己看出的风险点 —— 这两块是给人看的底稿，不是走过场。"""


class RefusalError(RuntimeError):
    """模型出于安全策略拒绝生成 —— 通常意味着选题本身踩线，应换题而不是改提示词。"""


def generate(topic: str, case_no: int, note: str = "无") -> CaseScript:
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        messages=[
            {
                "role": "user",
                "content": USER_TEMPLATE.format(case_no=case_no, topic=topic, note=note),
            }
        ],
        output_format=CaseScript,
    )

    if response.stop_reason == "refusal":
        detail = getattr(response.stop_details, "explanation", "") or ""
        raise RefusalError(f"模型拒绝生成该选题，建议换题。{detail}")

    return response.parsed_output
