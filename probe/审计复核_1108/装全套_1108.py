# -*- coding: utf-8 -*-
"""★★★★★ 规矩 67 的 `装全套()` —— ★ 第三次该写了，这一次写出来并当场用上。

★★ 它要挡的那个错（#100，1108 一天里犯了**两次**）：
  ★ 跑批侧装了「基准 + 分红」两层覆盖层，出数侧只装了分红 →
  ★★ A 段标普全收益年化印成 **+14.62%**、日数只有 **251 天**（2014 一整年），
  ★★★ 而真值是 **+7.82% / 2,768 天**。★ 两次都是靠《132》那道**跑前写死的对账自证**挡下来的。

★★★ 本模块只做一件事：**把「装哪几层」从每个脚本的记性里搬出来，变成一个函数**。
  ★ 它**不**替代对账自证 —— ★★★ 判法仍然是「少装一层就对不上」，不是「我觉得用不到」。

★★ 两套（按脚本要不要跑引擎分）：
  · `装全套("只读面板")` → 基准 BM + 分红 DV  （★ 算指数 / 出数 / 比基准，不跑回测）
  · `装全套("跑引擎")`   → 上面两层 + 回看期 / 日序列 / 跳过基准一 / panel_meta
    ★★★ 「跑引擎」那一套目前**只登记、不代跑** —— ★ 跑批脚本（跑重测_1107.py）自己有一份
      逐层带自证的装法，本模块**不去动它**（《131》教训：不碰两路共用的跑批脚本）。

★ 用法：
    from 装全套_1108 import 装全套
    自证 = 装全套("只读面板", 需覆盖=sorted(cl.columns))
    # ★★ 自证里必带：基准真的换掉了 · 分红拆股折算生效 · 覆盖率
"""
from __future__ import annotations
import importlib.util, json, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

_层 = {
    "只读面板": ["基准", "分红"],
    "跑引擎": ["基准", "分红", "回看期", "日序列", "跳过基准一", "panel_meta"],
}


def _载(rel: str, name: str):
    p = os.path.join(ROOT, rel)
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    os.chdir(ROOT)                      # ★ 这些模块里有 os.chdir，装完要自己拨回来
    return m


def 装全套(哪一套: str = "只读面板", 需覆盖=None) -> dict:
    if 哪一套 not in _层:
        raise ValueError(f"★★★ 只有这两套：{list(_层)}")
    os.chdir(ROOT)
    sys.path.insert(0, ROOT)
    出 = {"★这一套": 哪一套, "★该装的层": _层[哪一套], "★实装": [], "自证": {}}

    # ① 基准覆盖层（★ #100 漏的就是这一层）
    BM = _载("probe/并池_1107/接新基准_1107.py", "_zqt_bm")
    自证基准 = BM.install()
    assert 自证基准.get("★真的换掉了"), f"★★★ 基准覆盖层没装上 —— 停。{自证基准}"
    出["★实装"].append("基准")
    出["自证"]["基准"] = {"★★★基准自证": 自证基准.get("★★★基准自证"),
                      "★★★自动扫到的数据目录": 自证基准.get("★★★自动扫到的数据目录")}

    # ② 分红覆盖层（★★★ 含 R1 那个拆股折算 —— 1108 之前一次都没执行过）
    DV = _载("probe/并池_1107/分红覆盖层_1107.py", "_zqt_dv")
    自证分红 = DV.install(需覆盖=需覆盖) if 需覆盖 is not None else DV.install()
    assert "0 只被折算过" not in 自证分红.get("★★★拆股折算生效", ""), \
        f"★★★ 分红的拆股折算没生效（R1）—— 停。{自证分红.get('★★★拆股折算生效')}"
    出["★实装"].append("分红")
    出["自证"]["分红"] = {k: v for k, v in 自证分红.items()
                      if k.startswith("★★★") or "覆盖" in k}

    if 哪一套 == "跑引擎":
        raise NotImplementedError(
            "★★★ 「跑引擎」那一套本模块只登记、不代跑 —— ★ 跑批脚本自己那份逐层自证更严，"
            "★★ 要合并得两路一起拍（《135》第五节③ 还挂着）。")

    出["★★★判法"] = ("★ 装没装全**不靠这个函数说了算** —— ★★★ 仍然要在脚本里写死一道对账自证"
                 "（例：标普全收益 A 段必须重算出 +7.82% / 2,768 天）；★★ 少装一层它就对不上。")
    出["★DV"] = "已返回模块句柄，见 装全套_模块()"
    _句柄["BM"], _句柄["DV"] = BM, DV
    return 出


_句柄: dict = {}


def 装全套_模块(name: str):
    """★ 取回 install 过的模块句柄（★★ 例：DV.全收益基准("SPY")）。"""
    if name not in _句柄:
        raise RuntimeError("★★★ 先调 装全套()")
    return _句柄[name]


if __name__ == "__main__":
    print(json.dumps(装全套("只读面板"), ensure_ascii=False, indent=1)[:2000])
