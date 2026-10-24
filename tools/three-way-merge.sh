#!/usr/bin/env bash
# 三方合并：current=mine(0.1.6-local)  base=0.1.5  other=his(0.1.6)
set -u
T="C:/Users/16542/AppData/Local/Temp/tt_merge"
cd "$T" || exit 2
TERSER="node node_modules/terser/bin/terser"

echo "=== JS 反压缩 ==="
for f in base mine his; do
  $TERSER "$f.js" -b "beautify=true,indent_level=1" -o "$f.beauty.js" >/dev/null 2>&1
  echo "  $f.js -> $(wc -l < "$f.beauty.js") 行"
done

echo "=== CSS 拆行 ==="
for f in base mine his; do
  sed 's/}/}\n/g' "$f.css" > "$f.css.line"
  echo "  $f.css -> $(wc -l < "$f.css.line") 行"
done

echo "=== 三段三方合并（当前=mine, base=0.1.5, 对方=his）==="
git merge-file -p mine.beauty.js base.beauty.js his.beauty.js > merged.js 2>/dev/null
echo "  JS  冲突块: $(grep -c '^<<<<<<<' merged.js)  行数: $(wc -l < merged.js)"
git merge-file -p mine.css.line base.css.line his.css.line > merged.css.line 2>/dev/null
echo "  CSS 冲突块: $(grep -c '^<<<<<<<' merged.css.line)"
tr -d '\n' < merged.css.line > merged.css
git merge-file -p mine.main.cjs base.main.cjs his.main.cjs > merged.main.cjs 2>/dev/null
echo "  main 冲突块: $(grep -c '^<<<<<<<' merged.main.cjs)  registerHotkeys: $(grep -c registerHotkeys merged.main.cjs)  store-load: $(grep -c 'tt:store-load' merged.main.cjs)"
git merge-file -p mine.preload.cjs base.preload.cjs his.preload.cjs > merged.preload.cjs 2>/dev/null
echo "  preload 冲突块: $(grep -c '^<<<<<<<' merged.preload.cjs)  setHotkeys: $(grep -c setHotkeys merged.preload.cjs)  store-save: $(grep -c 'tt:store-save' merged.preload.cjs)"
echo "DONE"
