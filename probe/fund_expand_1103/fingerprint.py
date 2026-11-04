#!/usr/bin/env python3
"""基本面库指纹:每个文件的 sha256 + 整库一个总哈希。跑批时把总哈希写进指纹,库一变就看得出来。
用法:python3 fingerprint.py <fundamentals_ext 目录>  → 写 _MANIFEST.sha256,打印总哈希"""
import hashlib, os, sys
root = sys.argv[1]; lines = []
for d in sorted(os.listdir(root)):
    f = os.path.join(root, d, 'fundamentals.json.gz')
    if os.path.isfile(f):
        lines.append(f'{hashlib.sha256(open(f, "rb").read()).hexdigest()}  {d}/fundamentals.json.gz')
body = '\n'.join(lines) + '\n'
open(os.path.join(root, '_MANIFEST.sha256'), 'w').write(body)
print(len(lines), hashlib.sha256(body.encode()).hexdigest())
