# 素材目录

每期一个子目录，目录名与 `script.json` 的 `slug` 一致：

```
topics/assets/<slug>/
  p02.jpg        # 文件名对应页码，p02 就是第 2 页的配图
  p03.jpg
  assets.yaml    # 逐张登记来源与授权，见 docs/compliance.md
```

图片文件本身不入版本库（`.gitignore` 已排除），但 `assets.yaml` 必须提交 ——
它是素材合规的唯一凭证。
