#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把「本地补丁」（数据文件化 + 同步/记一件按钮 + 卡片布局 + 进展折叠 + 数据路径行）
重放到任意一份 TaskTable 构建产物上。

用法：
    python patch.py <输入.zip 或 已解压目录>  [-o 输出目录]  [--version 0.1.7-local]

典型流程：
    python patch.py "D:\\Downloads\\TaskTable-0.1.7-win-x64.zip" -o "D:\\Build\\TaskTable-0.1.7-local" --version 0.1.7-local

行为：
  * 输入是 zip → 自动解压到输出目录
  * 发现 resources/app.asar → 自动解包成 resources/app（原 asar 改名备份）
  * 逐处按 patch-spec.json 打补丁，每处都校验锚点命中次数
  * 任何一处锚点失踪/歧义 → 该处记为失败，最后以退出码 1 结束并写报告
  * 已经是补丁版（检测到标记）→ 跳过，不重复打

退出码：0 全部成功；1 有失败项；2 环境/输入问题
"""
import argparse
import json
import os
import re
import shutil
import struct
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_PATH = os.path.join(HERE, 'patch-spec.json')

MARKERS = {
    'main': "ipcMain.handle('tt:store-load'",
    'renderer': 'function __TTLogs(',
    'preload': "store: {",
}


# ---------- asar 解包 ----------
def unpack_asar(asar_path, out_dir):
    with open(asar_path, 'rb') as f:
        _, header_size, _, json_size = struct.unpack('<IIII', f.read(16))
        header = json.loads(f.read(json_size).decode('utf-8'))
        base = 8 + header_size
        count = 0

        def walk(node, prefix=''):
            nonlocal count
            for name, meta in node.get('files', {}).items():
                path = prefix + '/' + name
                if 'files' in meta:
                    walk(meta, path)
                else:
                    dest = os.path.join(out_dir, path.lstrip('/').replace('/', os.sep))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    f.seek(base + int(meta['offset']))
                    with open(dest, 'wb') as g:
                        g.write(f.read(int(meta['size'])))
                    count += 1

        walk(header)
    return count


# ---------- 找 app 根 ----------
def find_app_root(root):
    for dirpath, dirnames, filenames in os.walk(root):
        if os.path.basename(dirpath) == 'resources':
            if 'app.asar' in filenames or os.path.isdir(os.path.join(dirpath, 'app')):
                return dirpath
    return None


# ---------- 打补丁 ----------
def apply_ops(text, ops):
    results = []
    for op in ops:
        anchor = op['anchor']
        n = text.count(anchor)
        label = anchor[:48].replace('\n', ' ')
        if n == 0:
            results.append(('MISS', label, 0))
            continue
        if n > 1:
            results.append(('AMBIG', label, n))
            continue
        if op['op'] == 'insert_after':
            text = text.replace(anchor, anchor + op['text'], 1)
        elif op['op'] == 'insert_before':
            text = text.replace(anchor, op['text'] + anchor, 1)
        elif op['op'] == 'replace':
            text = text.replace(anchor, op['text'], 1)
        else:
            raise ValueError('未知操作: ' + op['op'])
        results.append(('OK', label, 1))
    return text, results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input', help='输入 zip 或已解压目录')
    ap.add_argument('-o', '--out', help='输出目录（默认 <输入名>-local）')
    ap.add_argument('--version', default=None, help='界面左侧显示的版本号，例如 0.1.7-local')
    ap.add_argument('--force', action='store_true', help='即使检测到已打过补丁也再打一遍')
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print('[X] 输入不存在:', args.input); return 2
    if not os.path.exists(SPEC_PATH):
        print('[X] 缺少 patch-spec.json'); return 2
    spec = json.load(open(SPEC_PATH, encoding='utf-8'))

    out = args.out or (os.path.splitext(os.path.abspath(args.input))[0] + '-local')
    if os.path.isdir(out) and os.listdir(out):
        print('[X] 输出目录已存在且非空，换一个 -o 或手动清空:', out); return 2

    # 1) 取出去
    if zipfile.is_zipfile(args.input):
        print('[*] 解压 zip →', out)
        os.makedirs(out, exist_ok=True)
        with zipfile.ZipFile(args.input) as z:
            z.extractall(out)
        # 若 zip 里套了一层文件夹，进到那一层
        entries = [e for e in os.listdir(out)]
        if len(entries) == 1 and os.path.isdir(os.path.join(out, entries[0])):
            inner = os.path.join(out, entries[0])
            for name in os.listdir(inner):
                shutil.move(os.path.join(inner, name), os.path.join(out, name))
            os.rmdir(inner)
    else:
        print('[*] 复制目录 →', out)
        shutil.copytree(args.input, out)

    # 2) 定位 resources
    res = find_app_root(out)
    if not res:
        print('[X] 没找到 resources/app.asar 或 resources/app，确认这是 TaskTable 产物'); return 2

    app_dir = os.path.join(res, 'app')
    asar = os.path.join(res, 'app.asar')
    if os.path.isfile(asar) and not os.path.isdir(app_dir):
        print('[*] 解包 app.asar …')
        n = unpack_asar(asar, app_dir)
        print('    解出', n, '个文件')
        os.rename(asar, asar + '.orig.bak')
        print('    原 asar 已改名备份:', os.path.basename(asar) + '.orig.bak')
    elif os.path.isdir(app_dir):
        print('[*] 已是散开的 resources/app，直接改')
    else:
        print('[X] resources 下既没有 app.asar 也没有 app/'); return 2

    report = []
    ok_all = True

    # 3) renderer bundle（文件名带哈希，按 glob 找）
    assets = os.path.join(app_dir, 'dist', 'assets')
    js_files = [f for f in os.listdir(assets) if re.match(r'index-.*\.js$', f)] if os.path.isdir(assets) else []
    css_files = [f for f in os.listdir(assets) if re.match(r'index-.*\.css$', f)] if os.path.isdir(assets) else []

    if not js_files:
        print('[X] 找不到 dist/assets/index-*.js'); return 2
    js_path = os.path.join(assets, js_files[0])
    text = open(js_path, encoding='utf-8', newline='').read()

    if MARKERS['renderer'] in text and not args.force:
        report.append(('SKIP', '渲染层已是补丁版，跳过'))
        print('[=] 渲染层已是补丁版，跳过')
    else:
        text, res_list = apply_ops(text, spec['renderer'])
        for st, label, cnt in res_list:
            report.append((st, 'JS  ' + label))
            if st != 'OK':
                ok_all = False
                print(f'  [{st}] {label}  命中 {cnt} 次')
        if args.version:
            text, nver = re.subn(spec['version_label_regex'],
                                 'children:["v","%s"]' % args.version, text, count=1)
            report.append(('OK' if nver == 1 else 'MISS', '版本号 → ' + args.version))
            if nver != 1:
                ok_all = False
        open(js_path, 'w', encoding='utf-8', newline='').write(text)
        print('[*] 渲染层打完:', os.path.basename(js_path))

    # 4) CSS 追加
    if css_files:
        css_path = os.path.join(assets, css_files[0])
        css = open(css_path, encoding='utf-8', newline='').read()
        if '0.1.6-local 补丁' in css:
            print('[=] CSS 已追加过，跳过')
        else:
            open(css_path, 'w', encoding='utf-8', newline='').write(css.rstrip('\n') + spec['css_append'])
            print('[*] CSS 追加完成:', os.path.basename(css_path))
            report.append(('OK', 'CSS 追加'))

    # 5) main / preload
    for name, fname in (('main', 'main.cjs'), ('preload', 'preload.cjs')):
        p = os.path.join(app_dir, 'desktop', fname)
        if not os.path.isfile(p):
            report.append(('MISS', f'{fname} 不存在')); ok_all = False; continue
        t = open(p, encoding='utf-8', newline='').read()
        if MARKERS[name] in t and not args.force:
            print(f'[=] {fname} 已是补丁版，跳过')
            continue
        t2 = t.replace('\r\n', '\n')
        t2, rl = apply_ops(t2, spec[name])
        for st, label, cnt in rl:
            report.append((st, f'{name}  ' + label))
            if st != 'OK':
                ok_all = False
                print(f'  [{st}] {name}: {label}  命中 {cnt} 次')
        open(p, 'w', encoding='utf-8', newline='').write(t2)
        print(f'[*] {fname} 打完')

    # 6) 报告
    lines = ['# 补丁报告', '', '输入：`%s`' % args.input, '输出：`%s`' % out,
             '版本：`%s`' % (args.version or '(未指定)'), '',
             '| 状态 | 项目 |', '|---|---|']
    for st, label in report:
        lines.append(f'| {st} | {label} |')
    if not ok_all:
        lines += ['', '## ⚠️ 有失败项', '',
                  '锚点 `MISS` = 对方这一版把那段代码改掉了；`AMBIG` = 锚点出现多次。',
                  '需要人工看一眼，再决定怎么合，**不要直接发布**。']
    open(os.path.join(out, 'PATCH-REPORT.md'), 'w', encoding='utf-8').write('\n'.join(lines))

    print()
    print('=' * 52)
    print('结果:', '✅ 全部成功' if ok_all else '❌ 有失败项（见 PATCH-REPORT.md）')
    print('输出:', out)
    print('=' * 52)
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main())
