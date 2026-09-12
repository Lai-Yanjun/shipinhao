#!/usr/bin/env bash
# 迪亚特洛夫事件配图下载。在你自己的机器上跑（云端出网被拦）。
#
# 只包含我能确认存在的文件。第 2、4、5、7 页没查到授权清楚的候选，
# 需要你打开分类页自己挑：
#   https://commons.wikimedia.org/wiki/Category:Dyatlov_Pass_incident
set -euo pipefail
SLUG="${1:-dyatlov-v4}"
DIR="topics/assets/$SLUG"
mkdir -p "$DIR"

get() {  # get <目标文件> <Commons文件名>
  echo "下载 $1 ← $2"
  curl -fL --retry 3 -o "$DIR/$1" \
    "https://commons.wikimedia.org/wiki/Special:FilePath/$(printf %s "$2" | sed 's/ /%20/g')?width=1600"
}

# 第 3 页 · 1959年2月26日帐篷发现现场
# 授权：PD-RU-exempt，文件页标注 possible wrong license —— 用户已确认接受该风险
get p03.jpg "Dyatlov Pass incident 02.jpg"

# 第 6 页 · 现场位置示意图。CC BY-SA，需署名，作者名记进 assets.yaml
# ?width= 会把 SVG 栅格化成 PNG，直接可用
get p06.jpg "Dyatlov pass incident accurate fancy map 1.svg"

# 第 7 页 · 备选地图（也可换成北乌拉尔风景照）
get p07.jpg "Map of djatlov pass incident 2.svg"

echo
echo "已下载到 $DIR"
echo "还缺第 2、4、5 页 —— 从分类页挑，命名 p02.jpg / p04.jpg / p05.jpg"
echo "然后：git add $DIR && git commit -m 'CASE 01 素材' && git push"
