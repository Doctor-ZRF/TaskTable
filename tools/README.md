# tools/

| 脚本 | 用途 |
|---|---|
| `patch.py` + `patch-spec.json` | 当**同一构建**的新版本到来时，把本地补丁重放上去（锚点会校验） |
| `three-way-merge.sh` | 当对方**重新构建过**（压缩变量名变了，锚点失效）时用：把 0.1.5 / 本仓库版本 / 对方版本三方合并 |
| `merge-with-upstream.py` | 上面合并之后，把本地补丁按**对方的新标识符**重新装进渲染层，产出可发布目录 |

## 处理「原作者发了新版」的完整流程

```bash
# 1) 解包对方的 app.asar 到两个目录：他这次的新版、以及 0.1.5 基线
# 2) 三方合并（main.cjs / preload.cjs / CSS / 渲染层）
bash tools/three-way-merge.sh
# 3) 渲染层按对方别名重装本地补丁，产出新版本目录
python tools/merge-with-upstream.py
# 4) 启动验证 → 装进本仓库 resources/app → commit → push → 打包发 Release
```

⚠️ 关键教训：`patch.py` 的锚点依赖**压缩后的标识符**，对方重新构建后必然失效（2026-10 实测 9 处里 7 处 MISS）。
所以「对方重新构建过」时不要用 `patch.py`，用三方合并 + `merge-with-upstream.py`。
