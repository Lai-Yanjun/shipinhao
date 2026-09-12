# 极地档案 · 内容工厂

栏目化短视频的自动化生产流水线。做极地、高山、远征中的灾难与未解事件，
形态是竖屏静态档案页翻页视频，配真实历史照片。

一次内容产出三个平台的成品：视频号/抖音的 9:16 翻页视频、小红书图文轮播、公众号纵向长图。

## 为什么是这个技术路线

不做 AI 生图、不做 AI 生视频、不做数字人口播。成片 = 排版模板 + 真实历史照片 + 缓慢推镜。

这样换来三件事：单条边际成本接近零（只有一次 API 调用）、出片稳定（没有画面崩坏和风格漂移）、
画面是真实档案照片而非 AI 假图，可信度与合规压力都低得多。

天花板不高，但下限不亏 —— 你可以一周扔 20 条出去试选题，失败成本近乎为零。
这是这门生意真正能成立的原因。

## 架构：Claude 做判断，代码做管道

内容不由固定提示词生成，由 Claude 会话直接产出 —— 选题不成立就换、素材找不到就重排页面、
钩子平庸就重写，这些是流程分支，不是文本生成，交给固定提示词只会做砸。

| 层 | 谁做 | 为什么 |
|---|---|---|
| 选题、查证、写文案、找图、判断质量 | Claude 会话 | 需要判断与分支 |
| 渲染、合成、编号、归档、校验闸门 | Python 代码 | 必须确定、可重复 |

作业流程写在 `.claude/skills/archive-case/SKILL.md`。任何会话（包括每日定时会话）
按它走完一期，不需要 API Key。

## 快速开始

**建议在本地机器上跑**，不要在云端会话里跑完整流程 —— 云端沙箱的出网策略
拦截了图片站、B 站和发布所需的一切，六个环节里有三个走不通。
原因与取舍见 `docs/local-setup.md`。

```bash
bash scripts/setup.sh          # ffmpeg + Chromium + 思源黑体 + Python 依赖
python cli.py list             # 看选题池
```

让 Claude 做一期：直接说「做一期极地档案」，它会按技能文档走完选题到归档。

手动跑管道部分：

```bash
python cli.py build  --slug <slug>   # 渲染 + 出三平台成品
python cli.py verify --slug <slug>   # 校验闸门，通过才分配 CASE 编号并归档
python cli.py status                 # 看台账
python cli.py publish --slug <slug> --platform 视频号 --url <链接>
```

产物在 `out/<slug>/`：

```
pages/             页面 PNG 序列（中间产物，三个平台都从它派生）
video_9x16.mp4     视频号 / 抖音 / 快手
xiaohongshu/       小红书图文轮播
wechat_longpic.jpg 公众号长图
copy.md            三平台文案、事实核查底稿、合规自检、发布前清单
```

`samples/dyatlov-pass.json` 是一期完整样例，可直接跑通渲染：

```bash
mkdir -p out/dyatlov-pass && cp samples/dyatlov-pass.json out/dyatlov-pass/script.json
python cli.py build --slug dyatlov-pass --case-no 1
```

## 校验闸门为什么不能自动化掉

`verify` 是流水线上唯一的人工闸门。它机器检查四项（素材齐备、授权已登记、钩子不含事件学名、
无过薄的过渡页），再把两项机器判断不了的推给你：事实核查与合规自检。

四项检查对应四种不同的翻车方式 —— 事实错误被判造谣、素材无授权要赔钱、合规风险被限流、
钩子用了事件学名则根本没人点。任何一项不过就不分配编号。

`--yes` 能跳过人工确认，但台账会记成 `auto`。不要用。

## 目录结构

```
.claude/skills/archive-case/   作业流程：Claude 按它走完一期
styles/                        风格锚定语料，蒸馏出的写作规则
config.yaml                    栏目身份与视觉/节奏参数，改这里就能整体换皮
topics/backlog.yaml            选题池，带风险分级与素材线索
topics/assets/<slug>/          每期素材与授权登记
archive/index.yaml             台账：编号、校验状态、发布记录
pipeline/
  models.py                    script.json 的数据结构
  render.py                    HTML → Playwright → PNG 序列
  video.py                     PNG → 翻页视频（xfade + 缓慢推镜）
  package.py                   三平台成品包
  verify.py                    发布前校验的四项检查
  archive.py                   编号分配与台账
  assets_search.py             本地素材下载助手（需能访问 Commons）
  templates/base.css           视觉系统：封面暗黑做旧 / 内页白底极简
docs/playbook.md               内容方法论：六段式、钩子写法、发布节奏
docs/compliance.md             合规红线、素材授权规范、AI 标识要求
```

## 三件必须知道的事

1. **不要在云端自动发布视频号。** 登录态绑定设备与网络环境，云端 IP 异常极易触发风控。
   云端只负责生产，发布在你自己的设备上做。详见 `docs/compliance.md`。
2. **AI 标识不是可选项。** 模板已固定渲染标识，发布时还需在平台侧勾选声明。
3. **素材授权是唯一会让你真正赔钱的环节。** 限流只是白干，图片侵权要赔。
   每张图都要在 `assets.yaml` 里登记来源。

## 关于配图的环境限制

云端会话能搜到图和授权信息，但**下载不了文件** —— 环境的出网策略拦截了外部站点。
所以云端产出的是「配图任务单」（`out/<slug>/assets_todo.md`，含准确 URL 与授权核验结果），
由你照单下载，每期约两分钟。

想全自动下载有两条路：放开该云端环境的网络策略，或把整条流水线放到本地机器上跑。

## 现状

- 已跑通：渲染 → 翻页视频 → 三平台成品包 → 校验闸门 → 编号归档 → 发布记录回填
- 待办：风格语料蒸馏（等素材）、本地发布助手（阶段二）、发布数据回收
