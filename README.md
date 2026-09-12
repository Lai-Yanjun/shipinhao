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

## 快速开始

```bash
bash scripts/setup.sh          # ffmpeg + Chromium + 思源黑体 + Python 依赖
cp .env.example .env           # 填入 ANTHROPIC_API_KEY

python cli.py list             # 看选题池
python cli.py write --topic "安德烈北极气球远征" --case-no 2
# ↓ 人工校订 out/<slug>/script.json，核事实、调钩子、删掉任何推测句
# ↓ 把公版配图按 p02.jpg 的命名放进 topics/assets/<slug>/，并登记 assets.yaml
python cli.py build --slug <slug>
```

产物在 `out/<slug>/`：

```
pages/             页面 PNG 序列（中间产物，三个平台都从它派生）
video_9x16.mp4     视频号 / 抖音 / 快手
xiaohongshu/       小红书图文轮播
wechat_longpic.jpg 公众号长图
copy.md            三平台文案、事实核查底稿、合规自检、发布前清单
```

`samples/dyatlov-pass.json` 是一期完整样例，不需要 API Key 就能跑通渲染：

```bash
mkdir -p out/dyatlov-pass && cp samples/dyatlov-pass.json out/dyatlov-pass/script.json
python cli.py build --slug dyatlov-pass --case-no 1
```

## write 与 build 为什么分两步

中间那步人工校订不能省。模型会写出通顺但未经核实的句子，这是这类内容最大的翻车来源。
`script.json` 里的 `fact_notes` 是给你逐条核对用的底稿，`risk_flags` 是模型自己看出的风险点。

## 目录结构

```
config.yaml              栏目身份与视觉/节奏参数，改这里就能整体换皮
topics/backlog.yaml      选题池，带风险分级与素材线索
topics/assets/<slug>/    每期素材与授权登记
pipeline/
  models.py              数据结构，同时是 Claude 的输出 schema
  script_gen.py          文案生成，方法论固化在 SYSTEM 提示里
  render.py              HTML → Playwright → PNG 序列
  video.py               PNG → 翻页视频（xfade + 缓慢推镜）
  package.py             三平台成品包
  templates/base.css     视觉系统：封面暗黑做旧 / 内页白底极简
docs/playbook.md         内容方法论：六段式、钩子写法、发布节奏
docs/compliance.md       合规红线、素材授权规范、AI 标识要求
```

## 三件必须知道的事

1. **不要在云端自动发布视频号。** 登录态绑定设备与网络环境，云端 IP 异常极易触发风控。
   云端只负责生产，发布在你自己的设备上做。详见 `docs/compliance.md`。
2. **AI 标识不是可选项。** 模板已固定渲染标识，发布时还需在平台侧勾选声明。
3. **素材授权是唯一会让你真正赔钱的环节。** 限流只是白干，图片侵权要赔。
   每张图都要在 `assets.yaml` 里登记来源。

## 现状

- 已跑通：选题池 → 文案生成 → 页面渲染 → 翻页视频 → 三平台成品包
- 未做：素材半自动检索（Wikimedia Commons API）、本地发布助手、选题效果回收
