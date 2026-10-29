"""
★ 三 · 时间尺度口径声明 —— 任何以「天」为单位的阈值,必须声明是交易日还是自然日。
   缺声明 → ★ 直接 FAIL。

三秒版:「20 天」这三个字有两个意思,差 40%(20 个交易日 ≈ 28 个自然日)。
        谁也不会把这件事写错,大家只是**不写**;不写的时候两个人读成两个意思。

为什么要有这个文件(2026-10-29 真实踩的坑):
  ① 时间止损的 p75 口径 —— 四条规矩(★ 按收盘价、★ 未触达 +1R 的完全排除、
     ★ 只看 N_win 绝对笔数、★ N_win < 25 不可采信)★ 散落在报告里,
     代码里没有任何东西强制它们必须被声明。
     (timestop_p5_1029.py 的 docstring 里写了,★ 但 docstring 不会 FAIL。)
  ② 同一批里还撞了两次「周期口径被偷换」:
     · 状-3:Brooks 的实体占比阈值是**单根 K 线**口径 → 我们套到了 20 根均值上
     · 技-3:Weinstein 的 ≥2 倍放量是**周线**口径 → 我们套到了日线单日上
     后果量化过:同一个「2 倍」,日口径发生率 5.22%、周口径 23.15% —— ★ 差 4.4 倍。

★★ 声明方式(三种任选一种,★ 都在配置文件自己里面,不需要改跑批代码):
   A. 键名自带单位后缀:`time_stop_trading_days` / `*_calendar_days` / `*_bars` / `*_weeks`
   B. 同一个 params 块里放一个 `units` 子块:
        params: { time_stop_days: 20, units: { time_stop_days: trading_days } }
   C. 配置顶层放一个 `time_scale` 块,按**点分路径**声明:
        time_scale:
          exit.params.time_stop_days:
            unit: trading_days          # 我们实际作用在什么周期上
            book_unit: trading_days     # ★ 原著是在什么周期上给这个数的
            note: ...                   # 两者不一致时必须写换算依据
   ★ unit 与 book_unit 不一致而没有 note → 同样 FAIL(这就是状-3 / 技-3 那两次)。

★ 本文件只读配置,不改配置、不改跑批逻辑。
"""

from __future__ import annotations

import glob
import os
import re
from typing import Any, Iterable

try:
    import yaml
except ImportError:                                    # pragma: no cover
    yaml = None

# ────────────────────────────────────────────────────────────────────────
# 一 · 什么算「以天为单位的阈值」
# ────────────────────────────────────────────────────────────────────────

#: 合法的单位名。★ 必须显式,「days」不算 —— 它正是有歧义的那个词。
VALID_UNITS = {
    "trading_days", "calendar_days", "bars", "weeks", "months",
    "交易日", "自然日", "根", "周线", "月线",
}

#: 已经自带单位、无需另外声明的键名后缀。
_SELF_DECLARING = (
    "_trading_days", "_calendar_days", "_bars", "_weeks", "_months",
    "_交易日", "_自然日",
)

#: 需要声明的键名长相 —— ★ 按本代码库实际在用的键名写。
#  教训来自 user_facing_ban:只写英文会在我们自己的中文产物上拦不住东西。
_NEEDS_UNIT = re.compile(
    r"(days?$|_days?_|^days?_|天数?$|_天|"
    r"lookback|look_?back|period|window|holding|hold_|"
    r"min_bars|structure_lookback|time_stop|存活|持有|回看|窗口)",
    re.IGNORECASE,
)

#: 这些键名虽然命中上面的正则,但它们**不是时间阈值** → 不要求声明。
_EXEMPT = re.compile(
    r"(bps|pct|percent|ratio|multiple|thr$|_thr|threshold|"
    r"fraction|weight|slots|count$|比例|倍|阈值)",
    re.IGNORECASE,
)


def _flatten(obj: Any, path: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else str(k)
            yield here, v
            yield from _flatten(v, here)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            here = f"{path}[{i}]"
            yield here, v
            yield from _flatten(v, here)


def needs_unit(key: str) -> bool:
    leaf = key.split(".")[-1].split("[")[0]
    if leaf.endswith(_SELF_DECLARING):
        return False
    if _EXEMPT.search(leaf):
        return False
    return bool(_NEEDS_UNIT.search(leaf))


# ────────────────────────────────────────────────────────────────────────
# 二 · 检查一份配置
# ────────────────────────────────────────────────────────────────────────

def _declared_unit(cfg: dict, full_path: str, parent: Any, leaf: str
                   ) -> tuple[str | None, dict]:
    """按 A / B / C 三种方式找声明。返回 (unit, 声明块)。"""
    # A · 键名自带
    if leaf.endswith(_SELF_DECLARING):
        return leaf.rsplit("_", 1)[-1], {}

    # B · 同级 units 子块
    if isinstance(parent, dict):
        u = parent.get("units")
        if isinstance(u, dict) and leaf in u:
            return str(u[leaf]), {}

    # C · 顶层 time_scale 按点分路径
    ts = cfg.get("time_scale")
    if isinstance(ts, dict):
        for k in (full_path, full_path.split(".", 1)[-1], leaf):
            spec = ts.get(k)
            if isinstance(spec, dict) and spec.get("unit"):
                return str(spec["unit"]), spec
            if isinstance(spec, str):
                return spec, {}
    return None, {}


def check_config(cfg: dict, *, where: str = "<未命名>") -> list[str]:
    problems: list[str] = []
    for path, value in _flatten(cfg):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        leaf = path.split(".")[-1].split("[")[0]
        if not needs_unit(path):
            continue
        parent_path = path.rsplit(".", 1)[0] if "." in path else ""
        parent = cfg
        for part in parent_path.split("."):
            if not part:
                break
            m = re.match(r"([^\[]*)((\[\d+\])*)", part)
            name, idxs = m.group(1), re.findall(r"\[(\d+)\]", m.group(2) or "")
            if isinstance(parent, dict) and name in parent:
                parent = parent[name]
            for i in idxs:
                if isinstance(parent, list) and int(i) < len(parent):
                    parent = parent[int(i)]

        unit, spec = _declared_unit(cfg, path, parent, leaf)
        if unit is None:
            problems.append(
                f"[{where}] ★★ FAIL `{path}` = {value} 是一个以「天 / 根」"
                f"为单位的阈值,★ 但没有声明是**交易日**还是**自然日**(也没声明"
                f"是单根还是 N 根均值 / 周线)。"
                f"★「20 天」这三个字有两个意思,差 40% —— 不声明两个人就读成两个意思。"
                f"★ 修法:三种任选一种(键名加 _trading_days 后缀 / 同级 units 子块 / "
                f"顶层 time_scale 块),见本文件开头。")
            continue
        if unit not in VALID_UNITS:
            problems.append(
                f"[{where}] ★★ FAIL `{path}` 声明的单位是 `{unit}`,不在允许集合里 "
                f"{sorted(VALID_UNITS)} —— ★ 特别是裸 `days`/`天` 不算声明,"
                f"它正是有歧义的那个词。")
            continue
        book = spec.get("book_unit")
        if book and str(book) != unit and not spec.get("note"):
            problems.append(
                f"[{where}] ★★ FAIL `{path}`:我们作用在 `{unit}` 上,"
                f"而原著是在 `{book}` 上给这个数的,★ 两者不一致却没写换算依据(note)。"
                f"★ 这正是状-3(单根 K 线阈值套到 20 根均值)和"
                f"技-3(周线放量套到日线单日,发生率 5.22% vs 23.15%,差 4.4 倍)"
                f"那两次踩的坑。")
    return problems


def check_config_file(path: str) -> list[str]:
    if yaml is None:                                   # pragma: no cover
        return [f"[{path}] ★ 跳过:环境里没有 pyyaml"]
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    return check_config(cfg, where=os.path.basename(path))


def scan_config_dir(dirpath: str) -> dict[str, list[str]]:
    out = {}
    for p in sorted(glob.glob(os.path.join(dirpath, "*.yaml"))):
        got = check_config_file(p)
        if got:
            out[os.path.basename(p)] = got
    return out


# ────────────────────────────────────────────────────────────────────────
# 三 · 时间止损 p75 的四条口径 —— ★ 从报告搬进代码,缺一条就 FAIL
# ────────────────────────────────────────────────────────────────────────

#: 时间止损 p75 必须显式声明的四件事。
#  出处:2026-10-29 专家给的口径,逐条照办;现行只写在
#  timestop_p5_1029.py 的 docstring 和报告里 —— ★ docstring 不会 FAIL。
TIMESTOP_REQUIRED = {
    "触达+1R": r"收盘",            # ★ 必须按收盘价,严禁盘中最高价
    "未触达的笔子": r"排除",        # ★ 完全排除在分子与分母之外
    "统计有效性": r"N_win",         # ★ 只看绝对笔数,N_win < 25 不可采信
    "分环境": r"全周期|严禁分环境",  # ★ 全周期固定一个值
    "天数定义": r"交易日",          # ★ 天数是交易日,不是自然日
}


def check_timestop_spec(spec: Any, *, where: str = "<未命名>") -> list[str]:
    """
    输入时间止损产物里的「★口径」块,缺哪一条就报哪一条。
    """
    problems: list[str] = []
    if not isinstance(spec, dict):
        return [f"[{where}] ★★ FAIL 完全没有「★口径」块 —— "
                f"时间止损的 p75 有四条口径(收盘价 / 未触达全排除 / "
                f"只看 N_win 绝对笔数 / 全周期固定),★ 一条都没声明。"]
    for key, pat in TIMESTOP_REQUIRED.items():
        text = str(spec.get(key, ""))
        if not text:
            problems.append(
                f"[{where}] ★★ FAIL 口径缺声明:`{key}` —— "
                f"这一条只写在报告和 docstring 里,★ 报告读完就放下,代码不会。")
        elif not re.search(pat, text):
            problems.append(
                f"[{where}] ★★ FAIL 口径 `{key}` 声明了但对不上:"
                f"写的是「{text[:40]}」,★ 必须含 /{pat}/。")
    # ★ N_win 的硬线必须出现在声明里,而且必须是 25
    if "25" not in str(spec.get("统计有效性", "")):
        problems.append(
            f"[{where}] ★★ FAIL `统计有效性` 里没写出 N_win < 25 这条硬线 —— "
            f"★ 不写死,下次就会有人给一个 N_win=9 的分位数。")
    return problems


# ────────────────────────────────────────────────────────────────────────
# 四 · 自测 —— ★ 跑在仓库里现成的真实配置与真实产物上
# ────────────────────────────────────────────────────────────────────────

_ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _selftest() -> None:
    import json

    # ── 真实配置:engine/configs/ 全量 ──────────────────────────────────
    bad = scan_config_dir(os.path.join(_ENGINE, "configs"))
    assert bad, "★ 这道闸在真实配置上一条都没拦住 —— 那它是假的"
    n = sum(len(v) for v in bad.values())
    print(f"  ① engine/configs/ 真实配置:{len(bad)} 份文件、共 {n} 处"
          f"「以天为单位但没声明交易日/自然日」→ 全部 FAIL")
    for f in list(bad)[:3]:
        print(f"     · {f}:{len(bad[f])} 处,例 → {bad[f][0].split('★★')[1][:88]} …")

    # 技-10 / 技-13 这两条今天跑过的链必须在清单里
    assert any(k.startswith("技-10") for k in bad), sorted(bad)
    assert any(k.startswith("技-13") for k in bad), sorted(bad)

    # ── 不该误伤:带了后缀 / 带了 units / 带了 time_scale 的写法 ─────────
    ok_a = {"exit": {"params": {"time_stop_trading_days": 20}}}
    assert check_config(ok_a, where="A") == [], check_config(ok_a)
    ok_b = {"exit": {"params": {"time_stop_days": 20,
                                "units": {"time_stop_days": "trading_days"}}}}
    assert check_config(ok_b, where="B") == [], check_config(ok_b)
    ok_c = {"entry": {"rules": [{"params": {"lookback": 20}}]},
            "time_scale": {"entry.rules[0].params.lookback":
                           {"unit": "trading_days"}}}
    assert check_config(ok_c, where="C") == [], check_config(ok_c)
    #   裸 days 不算声明
    bad_d = {"p": {"lookback": 20, "units": {"lookback": "days"}}}
    assert any("不在允许集合里" in g for g in check_config(bad_d, where="D"))
    #   原著口径不一致又没写换算依据 → FAIL(状-3 / 技-3 那两次)
    bad_e = {"entry": {"params": {"vol_lookback": 4}},
             "time_scale": {"entry.params.vol_lookback":
                            {"unit": "trading_days", "book_unit": "weeks"}}}
    got_e = check_config(bad_e, where="E")
    assert any("原著是在" in g for g in got_e), got_e
    print("  ② 三种合法声明都不误伤;裸 `days` 与「原著口径不一致无换算依据」都 FAIL")

    # ── 真实产物:时间止损 p75 的四条口径 ───────────────────────────────
    p = os.path.join(_ENGINE, "results_1029_批五时间止损.json")
    with open(p, encoding="utf-8") as fh:
        ts = json.load(fh)
    got = check_timestop_spec(ts.get("★口径"), where="results_1029_批五时间止损")
    assert got == [], got
    print("  ③ 真实产物 results_1029_批五时间止损.json 的「★口径」块 → 四条齐 → 通过")
    #   ★ 把同一个产物的口径块抽掉一条,必须 FAIL(证明它真的在查,不是摆设)
    stripped = {k: v for k, v in ts["★口径"].items() if k != "天数定义"}
    got2 = check_timestop_spec(stripped, where="抽掉天数定义")
    assert any("天数定义" in g for g in got2), got2
    print(f"     → 抽掉「天数定义」一条后立刻 FAIL:{got2[0][:96]} …")

    print("checks/time_scale_unit 自测通过 —— "
          f"★ 在真实配置上拦下 {n} 处缺声明,并在真实产物上证明口径块会被逐条查")


if __name__ == "__main__":
    _selftest()
