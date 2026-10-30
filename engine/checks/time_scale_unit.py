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
     ★★ 2026-10-30 更正:这里原来写「日口径发生率 5.22%、周口径 23.15%,
        差 4.4 倍」。★ 23.15% 这个数**全仓库没有任何产物支撑**,只出现在本段
        docstring 里,而且复算不出来。实测(300 票 × 2018–2025,口径和
        `pat6_ops.weinstein_weekly_breakout` 逐行一致,见
        probe/weekly_daily_mapping_1030/quantify_results_1030.json):
            日口径 **5.11%**(573,507 格) · 周口径 **4.57%**(125,100 格)
            → 比值 **0.89**,两个口径几乎一样严,★ **不是「差 4.4 倍」**。
        ★ 口径被偷换这件事成立,但「后果有 4.4 倍」这个量级是假的 ——
          一个会被反复引用的、没有出处的数,留在这里比没有更坏。

  ③ 2026-10-30 又撞了一次,而且**这道闸在设计上看不见它**(见下面三条 加 的注释):
     · 技-4 柄长:原著「柄至少 1–2 周」→ 写成 `handle_min_bars: 3`(应为 5)
     · 技-8 整理段:原著「横向整理 3 至 5 周」→ 写成 `flag_min_bars: 3`(应为 15)
     · 技-3 / 状-2:原著「30 周均线」→ 写成 `ma: 150`(30 周实测只有 144.6 个交易日)
     三个漏法各不相同,★ 所以补了三处,不是一处:
       (a) `_bars` 后缀原来算「自带声明」→ 前两条直接免检;
       (b) `ma` / `mas` / `near_ma` 这一族原来**一个都不命中** _NEEDS_UNIT;
       (c) 就算声明了,旧版也只查「有没有写 note」,★★ **不查换算有没有真的做**
           —— 前两条的病根正是「依据写了、倍率是 1」。所以加了 `book_value`
           的算术对账(_check_conversion)。

★★ 声明方式(三种任选一种,★ 都在配置文件自己里面,不需要改跑批代码):
   A. 键名自带单位后缀:`time_stop_trading_days` / `*_calendar_days` / `*_bars` / `*_weeks`
   B. 同一个 params 块里放一个 `units` 子块:
        params: { time_stop_days: 20, units: { time_stop_days: trading_days } }
   C. 配置顶层放一个 `time_scale` 块,按**点分路径**声明:
        time_scale:
          exit.params.time_stop_days:
            unit: trading_days          # 我们实际作用在什么周期上
            book_unit: weeks            # ★ 原著是在什么周期上给这个数的
            book_value: 4               # ★★ 原著原文给的**那个数**(选填但强烈建议)
            note: ...                   # 两者不一致时必须写换算依据
   ★ unit 与 book_unit 不一致而没有 note → 同样 FAIL(这就是状-3 / 技-3 那两次)。
   ★★★ 填了 `book_value` → 本闸会**把换算真的算一遍**:
       4 周 × 5 = 20,写 4 就 FAIL(倍率 1.0×,不在 [4.6, 5.2] 里)。
       ★ 这一条是 2026-10-30 加的,专治「依据写了、换算没做」。

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

#: ★ 键名自带单位、**可以**免另外声明的后缀 —— 只有真正点明了日历单位的才算。
_UNAMBIGUOUS_UNIT = (
    "_trading_days", "_calendar_days", "_weeks", "_months",
    "_交易日", "_自然日",
)

#: ★★ 2026-10-30 加 —— `_bars` **不再**算自带声明。
#  理由(本轮踩的那个坑):`handle_min_bars` / `flag_min_bars` 这两个名字
#  只说了「根」,★ 没说**哪种根**(日线根?周线根?),更没说
#  ★★ **原著当年是在什么周期上给这个数的**。于是「柄至少 1 周」被写成
#  `handle_min_bars: 3`、「整理 3 至 5 周」被写成 `flag_min_bars: 3`,
#  而同一个算子里另外三个 bar 参数都 ×5 换算对了 —— 半边做了半边没做。
#  ★ 旧版把 `_bars` 放进自带声明里,所以这道闸在**设计上就看不见**这一类。
_AMBIGUOUS_BAR = ("_bars", "_bar", "_根")

#: 兼容老名字(外部还有地方 import)。
_SELF_DECLARING = _UNAMBIGUOUS_UNIT

#: 需要声明的键名长相 —— ★ 按本代码库实际在用的键名写。
#  教训来自 user_facing_ban:只写英文会在我们自己的中文产物上拦不住东西。
_NEEDS_UNIT = re.compile(
    r"(days?$|_days?_|^days?_|天数?$|_天|"
    r"lookback|look_?back|period|window|holding|hold_|"
    r"min_bars|structure_lookback|time_stop|存活|持有|回看|窗口|"
    # ★★ 2026-10-30 加 —— 均线周期这一族,旧版**一个都不命中**。
    #   甲类里 7 处 `ma: 150`(原著「30 周均线」)就是这么漏过去的:
    #   `ma` 这两个字母不含 day / period / lookback,正则碰不到它。
    #   ★ 「同一样东西几种写法」:ma · ma_period · mas(列表)· near_ma ·
    #     close_above_ma · atr_slow_ma —— 六种写法,必须一起认。
    r"^mas?$|^ma_|_ma$|_mas$|near_ma|close_above_ma|"
    # ★ `*_bars` 也进来 —— 它不再靠后缀自动过关(见 _AMBIGUOUS_BAR)。
    r"_bars?$|_根$)",
    re.IGNORECASE,
)

#: 这些键名虽然命中上面的正则,但它们**不是时间阈值** → 不要求声明。
#  ★★ 2026-10-30 收窄:这几个词只豁免「**无量纲比值**」。
#  见下面 _EXEMPT_CANCELLED_BY_TIME_UNIT。
_EXEMPT = re.compile(
    r"(bps|pct|percent|ratio|multiple|thr$|_thr|threshold|"
    r"fraction|weight|slots|count$|比例|倍|阈值)",
    re.IGNORECASE,
)

#: ★★★ 2026-10-30 加 —— 豁免的**撤销条件**。
#  规矩:`multiple|ratio|倍|threshold|pct` 这几个词只豁免**无量纲比值**;
#  ★ 凡是键名**以时间单位收尾**的(= 它量的是一段时间的长短,不是一个比值),
#    一律**不豁免**,照样要声明。
#  为什么用「收尾」而不是「出现过就算」:`dryup_day_ratio`(缩量日的量比)和
#  `single_day_drop_pct`(单日跌幅)里的 day 是在**修饰那个比值**,它们是真
#  比值,不是时间长度 —— ★ 「出现过就算」会把这 9 处全报成红的,是误伤。
_EXEMPT_CANCELLED_BY_TIME_UNIT = re.compile(
    r"(bars?|days?|weeks?|months?|根|周|日|天|月)$", re.IGNORECASE)

#: ★★★ 2026-10-30 加 —— 周 / 月 → 交易日 的**换算倍率允许区间**。
#  用区间而不是一个数,因为仓库里两把尺子都在用,两把都该放过:
#    · 手册惯例    1 周 = 5 个交易日
#    · 实测跨度    1 周 = 4.8134 个交易日(627 周里 112 个四天周;
#                  见 probe/weekly_daily_mapping_1030/)
#  ★ 这个闸要拦的不是「5 还是 4.81」这种 3.6% 的分歧,★★ 是**忘了换算**
#    —— 倍率 ≈ 1 的那一类,也就是本轮的 技-4 / 技-8。
_CONVERSION_BAND: dict[tuple[str, str], tuple[float, float, str]] = {
    ("weeks", "trading_days"): (4.6, 5.2, "1 周 ≈ 4.81~5 个交易日"),
    ("weeks", "bars"): (4.6, 5.2, "1 周 ≈ 4.81~5 根日线"),
    ("months", "trading_days"): (19.0, 23.0, "1 个月 ≈ 21 个交易日"),
    ("months", "bars"): (19.0, 23.0, "1 个月 ≈ 21 根日线"),
    ("months", "weeks"): (4.0, 4.6, "1 个月 ≈ 4.33 周"),
}


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
    # ★ 只有真正点明日历单位的后缀才算自带声明;`_bars` 不算(见 _AMBIGUOUS_BAR)
    if leaf.endswith(_UNAMBIGUOUS_UNIT):
        return False
    # ★★ 豁免 → 但以时间单位收尾的撤销豁免
    if _EXEMPT.search(leaf) and not _EXEMPT_CANCELLED_BY_TIME_UNIT.search(leaf):
        return False
    return bool(_NEEDS_UNIT.search(leaf))


# ────────────────────────────────────────────────────────────────────────
# 二 · 检查一份配置
# ────────────────────────────────────────────────────────────────────────

def _declared_unit(cfg: dict, full_path: str, parent: Any, leaf: str
                   ) -> tuple[str | None, dict]:
    """按 A / B / C 三种方式找声明。返回 (unit, 声明块)。"""
    # A · 键名自带 —— ★ 只认点明了日历单位的后缀
    if leaf.endswith(_UNAMBIGUOUS_UNIT):
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
                f"技-3(周线放量套到日线单日)那两次踩的坑。")
            continue
        # ★★★ 2026-10-30 加 —— **把换算真的算一遍**。
        #   上面那一条只查「有没有写换算依据」;★ 本轮(技-4 柄长 3、技-8
        #   整理段 3)那两处的病根是**依据写了、换算没做**,倍率是 1 不是 5。
        #   ★ 光查「有没有 note」拦不住它,必须拿 book_value 算。
        problems += _check_conversion(path, value, unit, book, spec, where=where)
    return problems


def _check_conversion(path: str, value: float, unit: str, book: Any,
                      spec: dict, *, where: str) -> list[str]:
    """
    ★ 声明了 `book_value`(原著原文给的那个数)就把换算算一遍。
    三秒版:原著说「至少 1 周」,我们写了 3 —— 倍率 3.0 不在 [4.6, 5.2] 里 → 拦下。
    """
    bv = spec.get("book_value")
    if bv is None:
        return []
    try:
        bv = float(bv)
    except (TypeError, ValueError):
        return [f"[{where}] ★★ FAIL `{path}`:`book_value` = {spec['book_value']!r} "
                f"不是一个数 —— ★ 它要填**原著原文给的那个数**,不是说明文字。"]
    if bv == 0:
        return [f"[{where}] ★★ FAIL `{path}`:`book_value` = 0,★ 换算倍率算不出来。"]
    bu = str(book) if book else unit
    if bu == unit:                        # 同一个单位 → 数值必须相等
        if abs(float(value) - bv) > 1e-9:
            return [f"[{where}] ★★ FAIL `{path}` = {value},而原著在**同一个单位**"
                    f"(`{unit}`)上给的是 {bv:g} —— ★ 同单位却不等值,"
                    f"要么数抄错了,要么 book_unit 填错了。"]
        return []
    band = _CONVERSION_BAND.get((bu, unit))
    if band is None:
        return [f"[{where}] ★★ FAIL `{path}`:原著单位 `{bu}` → 我们的单位 `{unit}` "
                f"这个换算方向**没有登记过倍率**(已登记:"
                f"{sorted(_CONVERSION_BAND)})。★ 「没查」和「查了没问题」必须分开 —— "
                f"不登记就不许静默放过。"]
    lo, hi, how = band
    ratio = float(value) / bv
    if not (lo <= ratio <= hi):
        return [
            f"[{where}] ★★★ FAIL `{path}` = {value}:原著给的是 **{bv:g} {bu}**,"
            f"我们作用在 `{unit}` 上,★ 实际倍率 **{ratio:.3g}×**,"
            f"不在允许区间 [{lo}, {hi}]×({how})。"
            f"★ 应该是 **{bv * lo:.4g} ~ {bv * hi:.4g}**。"
            + ("  ★★★ 倍率**小于**应有的换算倍率 —— 这是**换算没做(或只做了一半)**"
               "那一类,不是阈值松紧之争。本轮两处都长这样:"
               "技-4 柄长(原著「至少 1–2 周」、写成 3 根,倍率 3×)、"
               "技-8 整理段(原著「3 至 5 周」、写成 3 根,★ 倍率正好 1×)。"
               "★ 典型病根:同一个算子里**上界换算了、下界没换**。"
               if ratio < lo else
               "  ★ 倍率**大于**应有的换算倍率 —— 要么换算做了两遍,"
               "要么 book_value 填的不是原著原文那个数。")]
    return []


def check_config_file(path: str) -> list[str]:
    if yaml is None:                                   # pragma: no cover
        return [f"[{path}] ★ 跳过:环境里没有 pyyaml"]
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    return check_config(cfg, where=os.path.basename(path))


#: ★★ 2026-10-30 加 —— 两桶必须分开报,否则新发现的换算错会淹在存量积压里。
#  存量:全库在今天之前**0 份**配置写过 time_scale / book_unit,所以
#  「缺声明」一开闸就是两百多条。★ 那是积压,不是今天新坏的;
#  而「换算算错了」是**今天就得处理**的。两桶混在一列,没人会看。
def split_problems(problems: Iterable[str]) -> dict[str, list[str]]:
    hot, cold = [], []
    for p in problems:
        (hot if "★★★ FAIL" in p or "同单位却不等值" in p
         or "没有登记过倍率" in p else cold).append(p)
    return {"★★★ 换算算错了(马上处理)": hot, "缺声明(存量积压)": cold}


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
    buckets = split_problems(g for v in bad.values() for g in v)
    print(f"  ① engine/configs/ 真实配置:{len(bad)} 份文件、共 {n} 处 FAIL")
    print(f"     · ★★★ 换算算错了(马上处理):{len(buckets['★★★ 换算算错了(马上处理)'])} 处")
    print(f"     · 缺声明(存量积压,全库今天之前 0 份写过 book_unit):"
          f"{len(buckets['缺声明(存量积压)'])} 处")
    for f in list(bad)[:3]:
        print(f"     · {f}:{len(bad[f])} 处,例 → {bad[f][0].split('★★')[1][:88]} …")

    # ── ★ 本轮新补的三个漏法,逐个证明它现在看得见 ─────────────────────
    #   (不证明「闸能看见」,就只是改了个正则)
    assert needs_unit("handle_min_bars"), "★ (a) `_bars` 后缀还在自动过关"
    assert needs_unit("flag_min_bars"), "★ (a) 同上"
    assert needs_unit("ma"), "★ (b) `ma` 这一族还是一个都不命中"
    for k in ("mas", "ma_period", "near_ma", "close_above_ma", "atr_slow_ma"):
        assert needs_unit(k), f"★ (b) 均线周期的写法 `{k}` 漏了"
    #   ★ 豁免收窄:带时间单位收尾的不豁免,真比值照旧豁免(不许误伤)
    assert needs_unit("ratio_bars"), \
        "★ 以时间单位收尾的,豁免必须被撤销(这就是收窄 _EXEMPT 的那一条)"
    assert needs_unit("volume_multiple") is False, "★ 真·无量纲比值被误伤了"
    assert needs_unit("dryup_day_ratio") is False, \
        "★ `dryup_day_ratio` 是「缩量日的量比」,day 在修饰比值 —— 误伤了"
    assert needs_unit("single_day_drop_pct") is False, "★ 同上,误伤"
    print("  ①b 三个漏法现在都看得见:`_bars` 不再免检 · `ma` 一族 6 种写法全命中 · "
          "豁免只保留无量纲比值(dryup_day_ratio / single_day_drop_pct 不误伤)")

    # ── ★★★ 反向自测:**故意塞一个错的换算**,必须被拦下 ────────────────
    #   用的就是 2026-10-30 之前 技-4 盘上的真实原值(handle_min_bars: 3),
    #   以及它的原著出处(手册v13 六附 6.1 ①:柄部持续时间 至少 1–2 周)。
    POISON = {
        "entry": {"rules": [{"type": "pat6_cup_with_handle",
                             "params": {"handle_min_bars": 3,      # ★ 错的那个值
                                        "handle_max_bars": 25}}]},
        "time_scale": {
            "entry.rules[0].params.handle_min_bars": {
                "unit": "trading_days", "book_unit": "weeks",
                "book_value": 1,
                "note": "原著「柄至少 1–2 周」—— ★ 依据写了,但换算没做"},
            "entry.rules[0].params.handle_max_bars": {
                "unit": "trading_days", "book_unit": "weeks",
                "book_value": 5, "note": "5 周 × 5 = 25 ✓"},
        },
    }
    got_p = check_config(POISON, where="★故意塞错的换算")
    assert len(got_p) == 1, f"★ 应该只拦下那一处(上界 25 是对的):{got_p}"
    assert "换算没做" in got_p[0] and "应该是" in got_p[0], got_p
    print("  ② ★★★ 反向自测通过 —— 故意塞 技-4 的真实原值 "
          "`handle_min_bars: 3`(原著「柄至少 1–2 周」)后被拦下:")
    print(f"     {got_p[0]}")

    #   ★ 第二个毒样本:技-8 的真实原值 —— 倍率正好 1.0×(「3 周」写成「3 根」)
    POISON8 = {
        "entry": {"rules": [{"type": "htf_flag_breakout",
                             "params": {"flag_min_bars": 3, "flag_max_bars": 25}}]},
        "time_scale": {
            "entry.rules[0].params.flag_min_bars": {
                "unit": "trading_days", "book_unit": "weeks", "book_value": 3,
                "note": "原著「随后横向整理 3 至 5 周」(手册v13 六附 6.1 ②)"},
            "entry.rules[0].params.flag_max_bars": {
                "unit": "trading_days", "book_unit": "weeks", "book_value": 5,
                "note": "5 周 × 5 = 25 ✓"},
        },
    }
    got_8 = check_config(POISON8, where="★故意塞错的换算·技-8")
    assert len(got_8) == 1 and "倍率 **1×**" in got_8[0], got_8
    print("     ★ 第二个毒样本(技-8 真实原值 `flag_min_bars: 3`,原著「3 至 5 周」)"
          "—— 倍率正好 1×,同样被拦下:")
    print(f"     {got_8[0]}")
    #   ★ 而正确的换算必须放过(否则这道闸是「一律报红」,不是「查对错」)
    FIXED = {
        "entry": {"rules": [{"type": "pat6_cup_with_handle",
                             "params": {"handle_min_bars": 5,
                                        "handle_max_bars": 25}}]},
        "time_scale": POISON["time_scale"],
    }
    assert check_config(FIXED, where="★改对之后") == [], check_config(FIXED)
    print("     → 同一份配置把 3 改成 5(= 1 周 × 5)后立刻放过 ✓ "
          "★ 证明它查的是**换算对不对**,不是一律报红")
    #   ★ 技-4 那 4 份**真实配置**现在必须一条 ★★★ 都不剩(本轮刚改完)
    for _n in ("技-4-原著.yaml", "技-4-原著-中值.yaml",
               "技-4-原著-宽松端.yaml", "技-4-行业.yaml"):
        _p = os.path.join(_ENGINE, "configs", _n)
        _hot = split_problems(check_config_file(_p))["★★★ 换算算错了(马上处理)"]
        assert _hot == [], (_n, _hot)
    print("     → 技-4 四份真实配置:★★★ 桶里 0 条(2026-10-30 的修正已被闸确认)")

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
