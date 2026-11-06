# -*- coding: utf-8 -*-
"""
★★★ 流水去重 —— 1106 查出的 Bug ①:同一条流水在不同批次里存了多份。

★ 大白话:`probe/friction_rerun_1104/ledgers_1104/` 下有 45 个 `REAL__*.csv`,
   但**按文件内容算哈希只有 32 份是不一样的** —— 有 11 组是一模一样的副本
   (同一条策略在「剔污染」「批五修正」「技术派六条三版」等批次里各存了一份)。
★★ 原来三个脚本(重切_按天拆账 / 环境分档 / 右尾配装单)都是 `glob` 一遍全吃进去,
   所以**同一笔交易被数了两三次** → 笔数、簇数虚高,显著性判断偏乐观。
★★★ 这里把去重逻辑写成一个共用函数,三个脚本都 import 它,**不许静默去重** ——
   每个脚本都要把 `去重报告()` 写进自己 json 的口径节里。

★★ 去重规则(写死、可复现):
   ① 对每个文件读全部字节算 sha256;
   ② 同一个 sha256 的若干文件算同一份内容;
   ③ **只保留文件名(basename)按 Python 默认字符串排序最靠前的那一份**,其余丢掉。
"""
from __future__ import annotations

import glob
import hashlib
import os

__all__ = ["内容哈希", "分组", "去重后的流水文件", "去重报告"]


def 内容哈希(路径: str) -> str:
    """★ 对文件全部字节算 sha256。"""
    h = hashlib.sha256()
    with open(路径, "rb") as fh:
        for 块 in iter(lambda: fh.read(1 << 20), b""):
            h.update(块)
    return h.hexdigest()


def 分组(目录: str, 模式: str = "REAL__*.csv") -> dict[str, list[str]]:
    """★ 返回 {sha256: [完整路径, ...]},每组内部按 basename 排序。"""
    组: dict[str, list[str]] = {}
    for f in sorted(glob.glob(os.path.join(目录, 模式))):
        组.setdefault(内容哈希(f), []).append(f)
    for h in 组:
        组[h] = sorted(组[h], key=lambda p: os.path.basename(p))
    return 组


def 去重后的流水文件(目录: str, 模式: str = "REAL__*.csv") -> list[str]:
    """★★ 去重后要用的文件列表 —— 每组内容只留 basename 排序最靠前的那一份。"""
    保留 = [v[0] for v in 分组(目录, 模式).values()]
    return sorted(保留, key=lambda p: os.path.basename(p))


def 去重报告(目录: str, 模式: str = "REAL__*.csv") -> dict:
    """★★★ 去重的全过程,原样写进 json 的口径节 —— 不许静默去重。"""
    组 = 分组(目录, 模式)
    原始 = sum(len(v) for v in 组.values())
    重复组 = []
    for h, v in 组.items():
        if len(v) > 1:
            重复组.append({
                "sha256前12位": h[:12],
                "这一组有几份": len(v),
                "★保留": os.path.basename(v[0]),
                "丢掉": [os.path.basename(p) for p in v[1:]],
            })
    重复组.sort(key=lambda x: x["★保留"])
    return {
        "★这是什么": "1106 查出的 Bug ①:流水文件有内容完全相同的副本,"
                     "原来三个脚本都把重复的算进了笔数,导致笔数/簇数虚高。",
        "去重规则": "按文件内容 sha256 分组;同一内容只保留 basename 排序最靠前的一份(规则写死、可复现)。",
        "原始份数": 原始,
        "去重后份数": len(组),
        "被丢掉的份数": 原始 - len(组),
        "重复组数": len(重复组),
        "重复明细": 重复组,
    }
