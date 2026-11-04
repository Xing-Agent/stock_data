#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★ 流水不入库:把 ledgers_1104/ 压成 .tar.gz 并出一份 SHA-256 清单(2026-11-04)

★★ 存指纹,不存流水 —— 清单入库,.tar.gz 和原始 CSV 都不入库。

跑法:python3 probe/friction_rerun_1104/archive_ledgers_1104.py
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGERS = os.path.join(HERE, "ledgers_1104")
TGZ = os.path.join(HERE, "ledgers_1104.tar.gz")
OUT = os.path.join(HERE, "ledgers_manifest_1104.json")


def _sha(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main() -> int:
    if not os.path.isdir(LEDGERS):
        print(f"★ 没有 {LEDGERS},不归档")
        return 1
    files = sorted(f for f in os.listdir(LEDGERS) if f.endswith(".csv"))
    per = []
    for f in files:
        p = os.path.join(LEDGERS, f)
        per.append({"file": f, "字节": os.path.getsize(p), "sha256": _sha(p)})
    agg = hashlib.sha256()
    for e in per:
        agg.update(f"{e['file']}:{e['sha256']}\n".encode())

    r = subprocess.run(["tar", "-czf", TGZ, "-C", HERE, "ledgers_1104"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("★ 压缩失败:", r.stderr[:500])
        return 2

    man = {
        "这是什么": "★ 摩擦三档重跑(1104)的流水 SHA-256 清单 —— ★★ 存指纹,不存流水",
        "时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "文件数": len(per),
        "汇总指纹": agg.hexdigest(),
        "拼法": "逐份 '<file>:<sha256>\\n' 按文件名排序拼接后 sha256",
        "压缩包": {"路径": os.path.basename(TGZ), "字节": os.path.getsize(TGZ),
                   "sha256": _sha(TGZ), "★入库": False},
        "★入库": "只有这份清单入库;ledgers_1104/ 和 .tar.gz 都在 .gitignore 里",
        "逐份": per,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=1)
    print(f"★ {len(per)} 份流水 → {os.path.basename(TGZ)} "
          f"({os.path.getsize(TGZ)/1e6:.1f} MB) · 汇总指纹 {agg.hexdigest()[:16]}")
    print(f"★ 清单写到 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
