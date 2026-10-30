"""
★ 四槽位齐全闸 —— 进场 / 加仓 / 离场 / 止损,一个「空着」都不许有。

三秒版:每一条交易策略的这四格,要么**有值**,要么**明确为无 + 写了出处**。
        第三种状态(空着)一个都不许有 —— 因为「空着」和「我们忘了」长得一样。

判据(三种状态的定义在 engine/addon_slot.py,四格用的是同一把尺子):
    有值     : type/rules/stages/components 里有东西
    明确为无 : type: none  + ★ 有 source
    空着     : 槽位缺失 / type: none 但没 source / 有槽位但里面空的  → ★ FAIL

────────────────────────────────────────────────────────────────────────
★★ 一个坑 —— 两套槽位命名,必须全支持别名
────────────────────────────────────────────────────────────────────────
这个仓库里槽位名**有两套**:
    七个大师配置(trend_following / vcp_momentum / liquidity_sweep / …)
        用  stop_init / stop_trail
    技-* 配置
        用  initial_stop / trailing_stop
★ 只找后者的话,会误报 6 个大师配置「缺止损」—— 这个误报已经真的发生过一次。

★★ 这是今天同一类 bug 的第四次。前三次:
    ① 用户面禁止字段闸第一版全英文键名,而报告用的是中文键
       (见 engine/checks/user_facing_ban.py 的 _ZH_ALIASES 那一段)
    ② `*ledger*.csv` 的 glob 扫不到 —— 因为 ledger 在**目录名**上,不在文件名上
    ③ git quotepath 把中文路径转义了
★ 共同的病根都是**同一样东西有两种写法,而检查只认了一种**。
★ 所以本文件的自测**专门有一项**:在两套命名上各跑一遍,证明两边都认得。

────────────────────────────────────────────────────────────────────────
★ 不该用这把尺子量的
────────────────────────────────────────────────────────────────────────
`模-*`(执行模块)和 `状-*`(状态判定)**不是交易策略** ——
模-1 是凯利仓位、状-4 是威科夫区间结构,它们**没有进场/离场是正常的**。
★ 排除,不要误报。

────────────────────────────────────────────────────────────────────────
★★ 「空着」有两种,必须分开 —— 一种是缺陷,一种是产出
────────────────────────────────────────────────────────────────────────
`技-11-原著.yaml` 的四格全空,★ 而这是**正确的产出**:
手册 v13 六附查实威科夫原著**彻底未给**那三个参数,按三版纪律
原著版就该报「原著未给出可执行阈值」。
★ 所以配置里显式写了 `原著未给出` / `cannot_run` / `runnable: false`
  这类标记的,★ 不算缺陷 —— 它们是「我们查了,原著真没有」的留证。
"""

from __future__ import annotations

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from engine.addon_slot import (                                  # noqa: E402
    ADD_ON_ALIASES, STATE_EXPLICIT_NONE, STATE_HAS_VALUE, STATE_MISSING,
    find_slot, slot_state,
)

_CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs")

# ────────────────────────────────────────────────────────────────────────
# ★★ 四个槽位 × 全部别名 —— 这一段就是那个坑的解药
# ────────────────────────────────────────────────────────────────────────

SLOTS: dict[str, tuple[str, ...]] = {
    "进场": ("entry", "entries", "进场"),
    "加仓": ADD_ON_ALIASES,
    "离场": ("exit", "exits", "离场"),
    # ★ 止损算**一格**,两级任一有值即可(初始止损 / 移动止损)——
    #   判据里「止损」是一个槽位,不是两个。
    "止损": ("initial_stop", "stop_init", "stop_initial", "初始止损",
             "trailing_stop", "stop_trail", "stop_trailing", "移动止损"),
}

#: ★ 止损那一格的两级,分开报出来(报告要看清缺的是初始还是移动)
STOP_LEVELS: dict[str, tuple[str, ...]] = {
    "初始止损": ("initial_stop", "stop_init", "stop_initial", "初始止损"),
    "移动止损": ("trailing_stop", "stop_trail", "stop_trailing", "移动止损"),
}

#: 不是交易策略 → 排除
NON_STRATEGY_PREFIXES = ("模-", "状-")

#: ★★ 已登记的「已知未补」—— 不是豁免,是**台账**。
#  闸照样把它报成缺陷(级别 = FAIL);自测断言缺陷清单**恰好等于**这一份台账,
#  所以新冒出来的任何一条缺陷都会让 run_all.py 挂掉。
#  ★ 为什么不直接在配置里补一行把它消掉:那一行是**出处**,
#    出处只能由人填(硬纪律第 6 条)—— 我们不许自己编一个 source 把闸哄过去。
KNOWN_OPEN: dict[str, str] = {
    "buy_and_hold.yaml":
        "移动止损写了 `type: none` 但**没有 source** → 按判据算「空着」。"
        "★ 它的 initial_stop 的 source 写的是「基线链定义,等价于不设止损」—— "
        "移动止损这一格大概率就是同一句话漏写了,但★ 出处必须由人确认后补,"
        "不许我们自己编一个 source 把闸哄过去。",
}

#: ★ 配置里出现这些标记 = 「空着是正确产出」,不算缺陷
PRODUCT_MARKERS = ("原著未给出", "cannot_run", "runnable", "blocked_reason",
                   "chain", "param_gap", "原著未给出可执行阈值的项")


def is_strategy(name: str) -> bool:
    """这份配置是不是一条交易策略(该用四槽位尺子量)。"""
    base = os.path.basename(name)
    if base.startswith("_TEMPLATE"):
        return False
    return not base.startswith(NON_STRATEGY_PREFIXES)


def empty_is_product(cfg: dict) -> str | None:
    """
    「空着」是不是一个**正确的产出**(我们查了,原著真没给)。
    返回那条标记的说法,或 None。
    ★ 这一条是 技-11-原著 / 技-9 逼出来的 —— 不区分就会把留证当缺陷报。
    """
    mt = cfg.get("meta") or {}
    if not isinstance(mt, dict):
        return None
    if mt.get("cannot_run") is True:
        return f"meta.cannot_run = true({str(mt.get('cannot_run_reason', ''))[:60]})"
    if mt.get("runnable") is False:
        return f"meta.runnable = false({str(mt.get('blocked_reason', ''))[:60]})"
    for k, v in mt.items():
        if "原著未给出" in str(k) or "原著未给出" in str(v):
            return f"meta.{k}(显式写了「原著未给出」)"
    if "chain" in cfg and cfg.get("chain") is None:
        return "chain: null(显式声明不建链)"
    return None


def audit_one(cfg: dict, name: str) -> dict:
    """量一份配置的四格。"""
    res: dict = {"配置": name, "槽位": {}, "空着的": [], "止损两级": {}}
    for slot, aliases in SLOTS.items():
        if slot == "止损":
            # ★ 止损算一格:两级任一有值 / 明确为无 → 这一格就算齐
            states = {}
            for lvl, al in STOP_LEVELS.items():
                key, node = find_slot(cfg, al)
                st, why = slot_state(node) if key else (STATE_MISSING, "槽位缺失")
                states[lvl] = {"键名": key, "状态": st, "说明": why}
            res["止损两级"] = states
            vals = [v["状态"] for v in states.values()]
            if STATE_HAS_VALUE in vals:
                st = STATE_HAS_VALUE
            elif STATE_EXPLICIT_NONE in vals:
                st = STATE_EXPLICIT_NONE
            else:
                st = STATE_MISSING
            res["槽位"][slot] = {
                "键名": "/".join(f"{v['键名']}={v['状态']}"
                                 for v in states.values() if v["键名"]) or None,
                "状态": st,
                "说明": "; ".join(f"{k}:{v['状态']}" for k, v in states.items()),
            }
        else:
            key, node = find_slot(cfg, aliases)
            st, why = slot_state(node) if key else (STATE_MISSING, "槽位缺失")
            res["槽位"][slot] = {"键名": key, "状态": st, "说明": why}
        if res["槽位"][slot]["状态"] == STATE_MISSING:
            res["空着的"].append(slot)

    res["四槽位齐全"] = not res["空着的"]
    # ★★ 严格口径:止损那一格的**两级分别**都要齐(初始 + 移动)。
    #   为什么用严格口径当默认:`buy_and_hold.yaml` 的初始止损有值、
    #   移动止损是「没出处的 none」—— 按「一格里有一级有值就算齐」的宽松读法
    #   它会被放过去,而那正是该报的一条。
    res["止损两级都齐"] = all(
        v["状态"] != STATE_MISSING for v in res["止损两级"].values())
    # 不含加仓的三槽位齐全度(★ 回归断言用这个:加仓这一格现在 48 份全空)
    res["三槽位齐全_不含加仓"] = (
        res["槽位"]["进场"]["状态"] != STATE_MISSING
        and res["槽位"]["离场"]["状态"] != STATE_MISSING
        and res["止损两级都齐"])
    res["空着是产出"] = empty_is_product(cfg)
    return res


def _load(path: str) -> dict:
    import yaml
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def check(config_dir: str | None = None, *, require_add_on: bool = False) -> dict:
    """
    扫一遍 engine/configs/。

    require_add_on=False(默认):只量进场 / 离场 / 止损三格。
        ★ 理由:加仓这一格是**今天**才做进 schema 的 —— 48 份配置里一份都没有,
          因为原来**装不了**。立刻按四格卡会把 43 条策略全判 FAIL,
          那不是检查,那是把闸关死。
    require_add_on=True:按完整四格卡 —— ★ 这是加仓逐条落地之后该打开的开关。
    """
    d = config_dir or _CONFIG_DIR
    paths = sorted(glob.glob(os.path.join(d, "*.yaml")))
    out: dict = {"配置总数": 0, "排除的": [], "策略数": 0,
                 "齐全的": [], "有缺陷的": [], "空着是产出的": [],
                 "明细": [], "话": [], "级别": "OK",
                 "口径": "按四格卡" if require_add_on else "按三格卡(加仓格今天刚做进 schema,48 份全空)"}
    for p in paths:
        name = os.path.basename(p)
        if name.startswith("_TEMPLATE"):
            continue
        out["配置总数"] += 1
        if not is_strategy(name):
            out["排除的"].append(name)
            continue
        out["策略数"] += 1
        r = audit_one(_load(p), name)
        out["明细"].append(r)
        ok = (r["四槽位齐全"] and r["止损两级都齐"]) if require_add_on \
            else r["三槽位齐全_不含加仓"]
        # ★ 三格口径下「加仓」不参与判定 → 也不要出现在「空着的」里
        #   (否则 buy_and_hold 的缺陷会被显示成「空着的格:['加仓']」,
        #    而它真正缺的是移动止损的出处 —— 报错信息指错地方最耽误事)
        if not require_add_on:
            r["空着的"] = [s for s in r["空着的"] if s != "加仓"]
        # 止损那一格宽松读法算齐、严格读法不齐 → 把缺的那一级写进「空着的」
        if not ok and "止损" not in r["空着的"]:
            r["空着的"] += [f"止损·{lvl}" for lvl, v in r["止损两级"].items()
                            if v["状态"] == STATE_MISSING]
        if ok:
            out["齐全的"].append(name)
        elif r["空着是产出"]:
            out["空着是产出的"].append((name, r["空着的"], r["空着是产出"]))
        else:
            why = {k: v["说明"] for k, v in r["槽位"].items()
                   if v["状态"] == STATE_MISSING}
            why.update({f"止损·{lvl}": v["说明"]
                        for lvl, v in r["止损两级"].items()
                        if v["状态"] == STATE_MISSING})
            out["有缺陷的"].append((name, r["空着的"], why))

    n = out["策略数"]
    out["齐全率"] = (len(out["齐全的"]) / n) if n else 0.0
    out["话"].append(
        f"配置总数 {out['配置总数']};排除 {len(out['排除的'])} 条"
        f"({', '.join(sorted(out['排除的']))})→ 交易策略 {n} 条。")
    out["话"].append(
        f"★ {out['口径']}:齐全 {len(out['齐全的'])} 条 = {out['齐全率']:.0%};"
        f"真的空着(缺陷){len(out['有缺陷的'])} 条;"
        f"空着但是**正确产出** {len(out['空着是产出的'])} 条。")
    for nm, miss, why in out["有缺陷的"]:
        out["话"].append(f"   ★ 缺陷 · {nm} —— 空着的格:{miss} / {why}")
    for nm, miss, mark in out["空着是产出的"]:
        out["话"].append(f"   ○ 产出(不算缺陷)· {nm} —— 空着的格:{miss} / {mark}")

    if out["有缺陷的"]:
        out["级别"] = "FAIL"
    return out


# ────────────────────────────────────────────────────────────────────────
# 自测 —— ★ 跑在仓库里现成的真实配置上
# ────────────────────────────────────────────────────────────────────────

def _selftest() -> None:
    r = check()
    for line in r["话"]:
        print("  ", line)

    # ★ 回归断言(Lin 手跑的基线)
    assert r["配置总数"] == 48, r["配置总数"]
    assert set(r["排除的"]) == {"模-1.yaml", "模-5.yaml", "模-6.yaml",
                                "状-4.yaml", "状-6.yaml"}, r["排除的"]
    assert r["策略数"] == 43, r["策略数"]
    # 技-11-原著 / 技-9 的「空」是正确产出,不是缺陷
    prod = {n for n, _, _ in r["空着是产出的"]}
    assert prod == {"技-11-原著.yaml", "技-9.yaml"}, prod

    # ★★ 缺陷清单必须**恰好等于**已登记的台账 —— 多一条就挂,少一条也挂。
    #   多一条 = 新的缺陷冒出来了;少一条 = 有人把台账上的补掉了却没更新台账。
    defects = {n for n, _, _ in r["有缺陷的"]}
    assert defects == set(KNOWN_OPEN), \
        f"缺陷清单和台账不一致:实测 {sorted(defects)} / 台账 {sorted(KNOWN_OPEN)}"
    print(f"\n   ★ 缺陷清单 = 已登记台账 {sorted(KNOWN_OPEN)} —— 没有新缺陷。")
    for n, miss, _ in r["有缺陷的"]:
        print(f"      {n}:空着的格 {miss} —— {KNOWN_OPEN[n][:60]}…")

    # ── ★★ 两套命名各跑一遍 —— 这一项就是为那个坑写的 ────────────────
    tf = _load(os.path.join(_CONFIG_DIR, "trend_following.yaml"))    # stop_init/stop_trail
    j4 = _load(os.path.join(_CONFIG_DIR, "技-4-原著.yaml"))          # initial_stop/trailing_stop
    assert "stop_init" in tf and "initial_stop" not in tf, "样本选错了"
    assert "initial_stop" in j4 and "stop_init" not in j4, "样本选错了"
    a_tf = audit_one(tf, "trend_following.yaml")
    a_j4 = audit_one(j4, "技-4-原著.yaml")
    print(f"\n   ★★ 两套命名各跑一遍(这一项就是为那个误报写的):")
    for a in (a_tf, a_j4):
        print(f"      {a['配置']:24s} 止损格={a['槽位']['止损']['状态']}"
              f"  认到的键={a['槽位']['止损']['键名']}")
    assert a_tf["槽位"]["止损"]["状态"] != STATE_MISSING, \
        "★ stop_init/stop_trail 这套命名没认出来 —— 就是那个误报 6 个大师配置的 bug"
    assert a_j4["槽位"]["止损"]["状态"] != STATE_MISSING, \
        "★ initial_stop/trailing_stop 这套命名没认出来"
    assert "stop_init" in (a_tf["槽位"]["止损"]["键名"] or ""), a_tf["槽位"]["止损"]
    assert "initial_stop" in (a_j4["槽位"]["止损"]["键名"] or ""), a_j4["槽位"]["止损"]
    print("      ✅ 两套命名都认得 —— 没有一边被误报成「缺止损」")

    # ── ★★★ 和手跑基线的对账:同一类 bug 的**第五次** ──────────────────
    #  手跑基线说 liquidity_sweep / trend_following / vcp_momentum 「缺移动止损」。
    #  ★ 实测:这三份的移动止损**都有值** —— 它们写的是第三种形态:
    #    `stop_trail:` 底下只有 `stages:`,**顶层没有 type**。
    #  ★ 只认「顶层 type」的检查会把这三份判成空 → 又是「同一样东西有两种写法、
    #    检查只认了一种」。所以这里把它钉成一条断言,以后谁改回去都会挂。
    for nm in ("liquidity_sweep.yaml", "trend_following.yaml", "vcp_momentum.yaml"):
        a = audit_one(_load(os.path.join(_CONFIG_DIR, nm)), nm)
        lv = a["止损两级"]["移动止损"]
        assert lv["状态"] == STATE_HAS_VALUE, (nm, lv)
        assert lv["键名"] == "stop_trail", (nm, lv)
        cfg = _load(os.path.join(_CONFIG_DIR, nm))
        assert cfg["stop_trail"].get("type") is None, \
            f"{nm} 现在有顶层 type 了,这条对账断言该更新"
        assert cfg["stop_trail"].get("stages"), nm
        print(f"      ★ 对账 · {nm}:移动止损 = {lv['状态']}"
              f"(stop_trail 底下 {len(cfg['stop_trail']['stages'])} 级 stages,"
              f"顶层无 type)—— ★ 手跑基线把它判成「缺移动止损」是**误报**")

    # ── ★ 反向自测一:把真实配置的止损整格拿掉 → 必须判「空着」────────
    import copy
    c = copy.deepcopy(j4)
    for k in ("initial_stop", "trailing_stop"):
        c.pop(k, None)
    a = audit_one(c, "技-4-原著(拿掉止损)")
    assert a["槽位"]["止损"]["状态"] == STATE_MISSING, a["槽位"]["止损"]
    assert "止损" in a["空着的"]
    print(f"   ★ 反向自测:真实配置拿掉止损两格 → 止损格 = {a['槽位']['止损']['状态']} → ★ 闸在工作")

    # ── ★ 反向自测二:type: none 但不写 source → 不许算「明确为无」──────
    c = copy.deepcopy(j4)
    c.pop("trailing_stop", None)
    c["initial_stop"] = {"type": "none"}            # ★ 没有 source
    a = audit_one(c, "技-4-原著(none 无 source)")
    assert a["槽位"]["止损"]["状态"] == STATE_MISSING, a["槽位"]["止损"]
    c["initial_stop"] = {"type": "none", "source": "原著(明确不设止损)"}
    a2 = audit_one(c, "技-4-原著(none 有 source)")
    assert a2["槽位"]["止损"]["状态"] == STATE_EXPLICIT_NONE, a2["槽位"]["止损"]
    print("   ★ 反向自测:type: none 不带 source → 算「空着」;带 source → 算「明确为无」")

    # ── ★ 反向自测三:整库级 —— 往真实配置副本里拿掉一格,check() 必须 FAIL ──
    import shutil
    import tempfile
    import yaml
    with tempfile.TemporaryDirectory() as td:
        for p in glob.glob(os.path.join(_CONFIG_DIR, "*.yaml")):
            shutil.copy(p, td)
        bad = os.path.join(td, "技-5-原著.yaml")
        cfg = _load(bad)
        cfg.pop("exit", None)                        # 把离场整格拿掉
        with open(bad, "w", encoding="utf-8") as fh:
            yaml.safe_dump(cfg, fh, allow_unicode=True)
        r2 = check(td)
        assert r2["级别"] == "FAIL", r2["话"]
        assert any(n == "技-5-原著.yaml" for n, _, _ in r2["有缺陷的"]), r2["有缺陷的"]
        print(f"   ★ 整库反向自测:真实配置副本里拿掉 技-5-原著 的离场格 → "
              f"{r2['级别']}({len(r2['有缺陷的'])} 条缺陷)→ ★ 闸在工作")

    # ── 加仓格的现状:★ 48 份一份都没有(原来装不了)────────────────
    r4 = check(require_add_on=True)
    assert r4["策略数"] == 43
    assert len(r4["齐全的"]) == 0, \
        "★ 居然有配置的加仓格有值?加仓是今天才做进 schema 的,应该一份都没有"
    print(f"\n   ★ 按完整四格卡(含加仓):齐全 {len(r4['齐全的'])}/43 —— "
          f"★★ 加仓这一格 48 份配置**一份都没有**,因为原来 schema 里**没有这一格**。"
          f"这是本次要记住的那个事实,不是一个新发现的缺陷。")

    print("\nchecks/four_slot_complete 自测通过 —— "
          "★★ 两套槽位命名都认得(这是今天同一类 bug 的第四次,专门写了自测);"
          "★ 「空着是缺陷」和「空着是产出」已分开。")


if __name__ == "__main__":
    _selftest()
