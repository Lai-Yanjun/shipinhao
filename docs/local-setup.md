# 本地运行

## 为什么建议全本地

云端会话跑在沙箱里，出网走策略代理，默认白名单只有包管理源、GitHub 和 Anthropic API，
其余一律拦截。实测：

| 站点 | 云端 |
|---|---|
| pypi.org / github.com | 通 |
| upload.wikimedia.org / commons.wikimedia.org | 拦 |
| archive.org / images.pexels.com | 拦 |
| bilibili.com | 拦 |

这不是故障，是有意的安全设计 —— 一个能自主执行的云端 agent 如果有完整网络权限，
就是数据外泄和供应链攻击的口子。

流水线六个环节里有三个撞上这条限制：

| 环节 | 云端 | 本地 |
|---|---|---|
| 选题、写文案 | 可以 | 可以 |
| 查证（WebSearch 走服务端） | 可以 | 可以 |
| **下载配图** | 不行 | 可以 |
| 渲染、合成视频 | 可以 | 可以 |
| **抓取对标语料** | 不行 | 可以 |
| **发布** | 不行（登录态 + 风控） | 可以 |

三个受限环节卡在链路中段和末尾，走云端每期要 git 来回倒两次。全本地跑没有这个问题。

云端唯一不可替代的是「电脑关着也能定时跑」，但本流程每期都要人工过校验闸门、
人工发布，定时的价值不大。

另一条路是放开该云端环境的网络策略（在 claude.ai/code 的环境设置里），
需要放行 `*.wikimedia.org` 等域名。是否接受由你判断。

## 装

```bash
git clone https://github.com/Lai-Yanjun/shipinhao
cd shipinhao
bash scripts/setup.sh
```

- **Linux**：直接跑
- **macOS**：先装 [Homebrew](https://brew.sh)，脚本会用 brew 装 ffmpeg 与思源黑体
- **Windows**：在 WSL 里跑

脚本结尾会自检 ffmpeg、python 依赖、中文字体三项。**中文字体那项必须通过** ——
缺了中文会渲染成豆腐块，而且是渲染完才看得出来。

字体要和云端一致（Noto Sans CJK）。不一致不会报错，但换行位置会变，
校验放行的版面到另一台机器上可能就溢出了。

## 验

```bash
mkdir -p out/demo && cp samples/dyatlov-pass-v4.json out/demo/script.json
python cli.py build --slug demo --case-no 1
```

产出在 `out/demo/`。缺配图会渲染成虚线占位框，属正常。

## 跑一期

```bash
python cli.py list                    # 选题池
# 让 Claude 按 .claude/skills/archive-case/ 做完选题→查证→文案→挑图
python cli.py assets --slug <slug>    # 检索候选配图，出九宫格
python cli.py pick   --slug <slug> --page 3 --choice 12   # 下原图并登记授权
python cli.py build  --slug <slug>
python cli.py verify --slug <slug>    # 校验闸门，通过才分配 CASE 编号
# 发布，然后回填
python cli.py publish --slug <slug> --platform 视频号 --url <链接>
```

## 本地跑之后还需要云端吗

不需要。仓库是同一个，两边都能改，git 同步。

想让云端会话帮忙看规则、改模板、拆语料都没问题 —— 那些不碰网络。
只是别让它做下载和发布。
