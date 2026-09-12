"""一期档案的数据结构。

这些模型同时是 Claude 结构化输出的 schema —— 字段描述就是写给模型的指令，
改描述等于改生成规则，所以描述写得比一般注释更具体。
"""
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field

PageKind = Literal["cover", "coordinate", "fact", "contradiction", "official", "cta"]


class Page(BaseModel):
    kind: PageKind = Field(
        description=(
            "页面角色。cover=封面钩子页；coordinate=时间地点坐标页；"
            "fact=反常事实堆叠页；contradiction=逻辑空洞页（堵死常规解释）；"
            "official=官方结论/悬置页；cta=互动引导与下期预告页。"
        )
    )
    headline: str = Field(
        description="该页大标题，6-14 字。cta 页写互动问句，cover 页留空字符串。"
    )
    body_lines: List[str] = Field(
        description=(
            "正文，每个元素是一句话、单独成行，3-6 行。每句 12-24 字，"
            "只陈述可核实的事实，带具体数字/日期/地名/官方用词。禁止形容词堆砌与主观推测。"
        )
    )
    image_caption: str = Field(
        description=(
            "档案图注，格式如『图：1959年2月，调查人员在海拔1079米的营地帐篷现场』。"
            "该页不配图时填空字符串。"
        )
    )
    image_query: str = Field(
        description=(
            "用于到 Wikimedia Commons 等公版图库检索该页配图的英文关键词，"
            "3-8 个词。该页不配图时填空字符串。"
        )
    )


class CaseScript(BaseModel):
    slug: str = Field(description="英文小写短标识，连字符分隔，用作输出目录名，如 dyatlov-pass")
    case_title: str = Field(description="事件学名，如『迪亚特洛夫事件』")
    hook_title: str = Field(
        description=(
            "封面钩子短语，5-8 个汉字，必须是『具体动作 + 反常』，"
            "如『赤脚逃出帐篷』。严禁使用事件学名或人名——观众不认识它就不会点。"
        )
    )
    year: int = Field(description="事件发生年份")
    region: str = Field(description="地点，国家+地区，如『苏联 · 乌拉尔』")
    meta_line: str = Field(description="档案编号行的后半段，如『1959 · 苏联 · 乌拉尔』")
    pages: List[Page] = Field(
        description=(
            "按顺序排列的页面，共 8 页：cover ×1、coordinate ×1、fact ×3、"
            "contradiction ×1、official ×1、cta ×1。"
        )
    )
    feed_caption: str = Field(
        description="视频号/抖音文案区正文，60-120 字，承接钩子并埋一个开放问题，结尾不下结论。"
    )
    xhs_title: str = Field(description="小红书标题，18-20 字，可用一个恰当的符号分隔")
    topics: List[str] = Field(description="话题标签，4-6 个，不带 # 号")
    fact_notes: List[str] = Field(
        description=(
            "事实核查备注：逐条列出文案中每个关键断言及其公开信源方向"
            "（如官方调查报告名称、年份、可检索的机构）。这是防止翻车的底稿。"
        )
    )
    risk_flags: List[str] = Field(
        description=(
            "合规自检结果：列出本期可能触线的点（涉在世当事人、未结案、伤情描写、"
            "素材授权存疑等）。确认无风险时写单个元素『无』。"
        )
    )
