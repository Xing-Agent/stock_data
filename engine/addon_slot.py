"""
★ 第八个槽位:`add_on`(加仓)—— schema 层。

三秒版:我们的配置原来只有 7 个槽位,**没有「加仓」这一格**。
        所以 67 条策略里一条都不可能有加仓 —— 不是漏装了,是**装不了**。
        这个文件把这一格加上,并且在 schema 层把「向下摊平」直接堵死。

旁证(不是推测,是跑出来的):`engine/evidence_1029.py` 打印过
「unit 字段取值分布 ← 全部标记为同一个 unit」—— 每笔持仓永远只有 1 份。

────────────────────────────────────────────────────────────────────────
★★ 为什么要做进 schema,而不是写进手册 / 挂在某个大师名下
────────────────────────────────────────────────────────────────────────
手册 v13 四附点出的问题:「禁止向下摊平」这条禁令原来是挂在**欧奈尔(技-4)**
名下的。挂一个人名下的后果是 —— 用户换一条策略就以为这条不适用。
做进 schema,它就自动对**所有**策略生效:★ 靠结构,不靠大家记得。

────────────────────────────────────────────────────────────────────────
★★ 三种状态必须能区分开(这一条是关键)
────────────────────────────────────────────────────────────────────────
    有值      : type: <某个值> + params
    明确为无  : type: none  + ★ 必须有 source(比如康纳斯原著明确反对加仓)
    空着      : 槽位缺失(原著没说 / 我们没定)

★ 这个惯例不是本文件发明的,现有配置已经在用:
  `engine/configs/技-12.yaml` 的 `initial_stop: type: none` + `source: 原著(…)`
  就是「明确为无」的样板。本文件照着做。

★ 为什么「明确为无」一定要带 source:不带出处的 none 和「忘了写」长得一模一样。
  `buy_and_hold.yaml` 的 `trailing_stop: type: none` 就**没有 source** ——
  那不是「明确为无」,那是「空着」,四槽位闸会把它报出来。

────────────────────────────────────────────────────────────────────────
★★ 默认只许顺势加仓 —— 逆势加仓在 schema 层**不给这个选项**
────────────────────────────────────────────────────────────────────────
传了就**报错**,不是警告。

理由(策略组拍板):向下摊平让**正在亏**的仓位变大,赌它会回来;
不回来损失翻倍。原著里几乎每位趋势 / 动量作者都明确反对。

★ 这里不只按名字黑名单堵(名字能改)。真正的牙齿是**数**:
  加仓触发价必须在上一笔进场价**之上**(做多),等价于
  `params.min_unrealized_r >= 0`。写一个负数进去 = 数学上就是向下摊平 → 报错。

────────────────────────────────────────────────────────────────────────
★★ 均值回归类策略不给这个槽位
────────────────────────────────────────────────────────────────────────
Connors / 拉什克 / 狄马克 / 布林格 的原著都明确反对加仓。
判定依据 = 配置里**现成的** `benchmark.family == "meanrev"` 字段
(`engine/bench_lines.benchmark_family` 读的就是它)—— 不是我们新猜的一个标记。
★ 实测:48 份配置里 41 份有 family 字段,缺的 7 份是 技-9 / 技-11-原著
  (两条 cannot_run,不建链)+ 模-1/5/6 + 状-4/6(不是交易策略)。
  ★ 也就是说:**所有真正建链的配置都有这个字段**,判定是可靠的,不用猜。

★ 纪律 1:本文件**不改** matrices.py / chain.py / config_adapter.py。
  加槽位走新增。`install()` 用的是 engine/ops_exits_1029.py 已经立过的
  那个运行时挂钩套路(只往 config_adapter.IMPLEMENTED 里加 key,不改它的函数)。
"""

from __future__ import annotations

from typing import Any

# ────────────────────────────────────────────────────────────────────────
# 一 · 槽位名的别名
#
# ★★ 这一段是今天同一类 bug 吃了四次之后写的(见 engine/checks/four_slot_complete.py
#   顶上那张清单)。槽位名在这个仓库里从来不只有一种写法:
#   七个大师配置用 stop_init / stop_trail,技-* 配置用 initial_stop / trailing_stop。
#   ★ 新槽位从第一天就把别名备齐,不要等误报了再补。
# ────────────────────────────────────────────────────────────────────────

ADD_ON_ALIASES: tuple[str, ...] = (
    "add_on", "addon", "add_ons", "addons",
    "pyramid", "pyramiding", "scale_in",
    "加仓", "加仓槽位",
)

#: 槽位的标准名(写进报告 / 别的代码引用时用这个)
ADD_ON_CANONICAL = "add_on"


# ────────────────────────────────────────────────────────────────────────
# 二 · 认得的加仓类型 —— ★ 全部是顺势
# ────────────────────────────────────────────────────────────────────────

IMPLEMENTED_ADD_ON: frozenset[str] = frozenset({
    # 「明确为无」的写法(必须带 source)
    "none",
    # 顺势加仓:价格创出新高就加一份(海龟式)
    "breakout_pyramid",
    # 顺势加仓:每涨 N × ATR 加一份(海龟原著 1/2 N 加仓)
    "atr_step_pyramid",
    # 顺势加仓:每赚满 +1R 加一份
    "r_step_pyramid",
    # 顺势加仓:趋势二次确认(均线重新发散 / 新的高紧形态)后加一份
    "trend_confirm_add",
})

#: ★★ schema 层直接堵死的写法 —— 全部是「向下摊平」的别名。
#  ★ 传了就报错,不是警告。
#  ★ 名字黑名单只是第一道;真正的牙齿是下面 min_unrealized_r 的符号检查。
FORBIDDEN_ADD_ON: dict[str, str] = {
    "average_down":
        "★ 向下摊平 —— schema 层不给这个选项。它让正在亏的仓位变大,"
        "赌它会回来;不回来损失翻倍。原著里几乎每位趋势/动量作者都明确反对。",
    "averaging_down": "同 average_down",
    "scale_in_on_dip": "同 average_down(跌下去加仓 = 向下摊平换了个说法)",
    "add_on_dip": "同 average_down",
    "dca_down": "同 average_down(定投式往下补 = 向下摊平)",
    "martingale": "★ 倍投:亏了就加倍。比向下摊平更坏 —— 破产是数学上的必然,不是概率。",
    "grid_add": "★ 网格往下铺 = 结构化的向下摊平",
    "cost_basis_improve": "★ 「摊低成本」是向下摊平最常见的说法 —— 同样不给",
    "摊平": "同 average_down",
    "向下摊平": "同 average_down",
    "补仓": "同 average_down(「补仓」在中文里默认就是往下补)",
}

#: 均值回归家族 —— ★ 这一族不给 add_on 槽位
MEANREV_FAMILY = "meanrev"

MEANREV_REFUSAL = (
    "★ 均值回归类策略不给 `add_on` 槽位 —— "
    "Connors / 拉什克 / 狄马克 / 布林格 的原著**都明确反对加仓**:"
    "均值回归是在赌「偏离会收回」,偏离越大越该怀疑前提、不是越该加注。"
    "★ 判定依据 = 配置里现成的 benchmark.family == 'meanrev' 字段,不是我们新猜的标记。"
)


# ────────────────────────────────────────────────────────────────────────
# 三 · 三种状态
# ────────────────────────────────────────────────────────────────────────

STATE_HAS_VALUE = "有值"
STATE_EXPLICIT_NONE = "明确为无"
STATE_MISSING = "空着"


def find_slot(cfg: dict, aliases: tuple[str, ...]) -> tuple[str | None, Any]:
    """在一份配置里按别名找一个槽位,返回 (实际用的键名, 槽位内容)。找不到 → (None, None)。"""
    if not isinstance(cfg, dict):
        return None, None
    for k in aliases:
        if k in cfg:
            return k, cfg[k]
    return None, None


def _has_content(node: Any) -> bool:
    """这个槽位里到底有没有东西(type / rules / stages / components 任一非空)。"""
    if not isinstance(node, dict):
        return bool(node)
    if node.get("type") not in (None, ""):
        return True
    for k in ("rules", "stages", "components"):
        if node.get(k):
            return True
    return False


def slot_state(node: Any) -> tuple[str, str]:
    """
    判一个槽位处在三种状态的哪一种,返回 (状态, 说明)。

    ★ 这个函数是通用的 —— 四槽位闸(engine/checks/four_slot_complete.py)
      量进场 / 加仓 / 离场 / 止损用的是同一把尺子,不是四把。
    """
    if node is None:
        return STATE_MISSING, "槽位缺失"
    if not isinstance(node, dict):
        # 极少数配置把槽位写成 null / 标量
        return (STATE_MISSING, f"槽位不是 dict(是 {type(node).__name__})")
    if str(node.get("type")) == "none":
        if node.get("source"):
            return STATE_EXPLICIT_NONE, f"type: none + source: {str(node['source'])[:40]}"
        return (STATE_MISSING,
                "★ type: none 但**没有 source** —— 不带出处的 none 和「忘了写」"
                "长得一模一样,所以按「空着」算")
    if _has_content(node):
        return STATE_HAS_VALUE, f"type={node.get('type')!r} / " \
                                f"rules={len(node.get('rules') or [])} / " \
                                f"stages={len(node.get('stages') or [])} / " \
                                f"components={len(node.get('components') or [])}"
    return STATE_MISSING, "槽位存在但里面是空的"


# ────────────────────────────────────────────────────────────────────────
# 四 · 校验 —— ★ 违规一律抛异常,不许只警告
# ────────────────────────────────────────────────────────────────────────

class AddOnSchemaError(ValueError):
    """add_on 槽位写错了。★ 一律抛,不降级成警告。"""


def _family(cfg: dict) -> str | None:
    b = cfg.get("benchmark")
    if isinstance(b, dict) and b.get("family"):
        return str(b["family"]).strip().lower()
    # meta 里的链型标注(备用口径)
    mt = cfg.get("meta")
    if isinstance(mt, dict):
        for k in ("family", "链型", "chain_family"):
            if mt.get(k):
                return str(mt[k]).strip().lower()
    return None


def validate_add_on(cfg: dict, *, where: str = "<未命名>") -> str:
    """
    校验一份配置的 `add_on` 槽位。返回三种状态之一;违规抛 AddOnSchemaError。

    四条:
      ① 类型必须在 IMPLEMENTED_ADD_ON 里;在 FORBIDDEN_ADD_ON 里 → 报错
      ② type: none 必须带 source(否则就是「空着」伪装成「明确为无」)
      ③ ★ params.min_unrealized_r < 0 → 报错(数学上就是向下摊平)
         params.direction 不是顺势 → 报错
      ④ ★ benchmark.family == meanrev 而配置里写了 add_on → 报错
    """
    key, node = find_slot(cfg, ADD_ON_ALIASES)
    if key is None:
        return STATE_MISSING

    fam = _family(cfg)

    # ④ 均值回归类不给这个槽位 —— ★ 放在最前面:写了就报错,连 none 也不用写
    if fam == MEANREV_FAMILY:
        raise AddOnSchemaError(
            f"[{where}] 配置的 benchmark.family = meanrev,却写了 `{key}` 槽位。\n  "
            + MEANREV_REFUSAL)

    if not isinstance(node, dict):
        raise AddOnSchemaError(
            f"[{where}] `{key}` 必须是 dict(type + params + source),"
            f"给的是 {type(node).__name__}")

    t = node.get("type")
    if t in (None, ""):
        raise AddOnSchemaError(
            f"[{where}] `{key}` 没写 type。★ 三种状态必须能区分开:"
            f"要么给一个类型 + params,要么 type: none + source,"
            f"要么**整个槽位不要写**(= 空着)。半个槽位是最坏的那一种。")
    t = str(t)

    # ① 黑名单 / 白名单
    if t in FORBIDDEN_ADD_ON:
        raise AddOnSchemaError(
            f"[{where}] `{key}.type = {t}` —— {FORBIDDEN_ADD_ON[t]}\n  "
            f"★ 这是 schema 层的硬禁令,不是警告:逆势加仓在本仓库**没有这个选项**。")
    if t not in IMPLEMENTED_ADD_ON:
        raise AddOnSchemaError(
            f"[{where}] `{key}.type = {t}` 不认得。"
            f"认得的只有:{sorted(IMPLEMENTED_ADD_ON)}。"
            f"★ 不认得的类型会悄悄不生效 —— 所以在这里报错,不留给它静默失效。")

    # ② type: none 必须带出处
    if t == "none":
        if not node.get("source"):
            raise AddOnSchemaError(
                f"[{where}] `{key}.type = none` 但**没有 source**。"
                f"★ 「明确为无」必须有出处(样板:engine/configs/技-12.yaml 的 "
                f"initial_stop: type: none + source: 原著(…))—— "
                f"不带出处的 none 和「忘了写」长得一模一样。")
        return STATE_EXPLICIT_NONE

    # 有值的分支:params 必须有,且必须有 source(沿用 chain.validate 的既有规矩)
    p = node.get("params")
    if not isinstance(p, dict) or not p:
        raise AddOnSchemaError(
            f"[{where}] `{key}.type = {t}` 有类型但没有 params —— 不许猜参数。")
    if not node.get("source"):
        raise AddOnSchemaError(
            f"[{where}] `{key}` 有参数但没写 source(硬纪律第 6 条:"
            f"参数只能来自原著或行业惯例,并在配置里标明出处)。")

    # ③ ★★ 真正的牙齿:方向 + 数
    d = str(p.get("direction", "with_trend")).strip().lower()
    if d not in ("with_trend", "顺势"):
        raise AddOnSchemaError(
            f"[{where}] `{key}.params.direction = {d}` —— "
            f"★ 只许 with_trend(顺势)。逆势加仓 = 向下摊平,"
            f"schema 层不给这个选项:{FORBIDDEN_ADD_ON['average_down']}")

    if "min_unrealized_r" not in p:
        raise AddOnSchemaError(
            f"[{where}] `{key}.params` 必须显式写 min_unrealized_r"
            f"(加仓之前这笔至少要赚到几 R)。"
            f"★ 不给默认值:默认值会让「加仓门槛」这件事从配置里消失。")
    try:
        mur = float(p["min_unrealized_r"])
    except (TypeError, ValueError) as exc:
        raise AddOnSchemaError(
            f"[{where}] `{key}.params.min_unrealized_r` 不是个数:{p['min_unrealized_r']!r}"
        ) from exc
    if mur < 0:
        raise AddOnSchemaError(
            f"[{where}] `{key}.params.min_unrealized_r = {mur}` 是**负数** —— "
            f"★ 这在数学上就是向下摊平:仓位正在亏({mur}R)却要加大。"
            f"schema 层不给这个选项。{FORBIDDEN_ADD_ON['average_down']}\n  "
            f"★ 名字可以换,这个数换不掉 —— 所以禁令挂在这个数上,不只挂在类型名上。")

    # 份数上限:没有上限的金字塔在数学上和没有止损一样危险
    mu = p.get("max_units")
    if mu is None:
        raise AddOnSchemaError(
            f"[{where}] `{key}.params` 必须写 max_units(最多加到几份)。"
            f"★ 没有上限的金字塔 = 仓位可以无限放大,一次反向就把前面全部还回去。")
    if int(mu) < 2:
        raise AddOnSchemaError(
            f"[{where}] `{key}.params.max_units = {mu}` —— "
            f"加仓的意思是总份数 ≥ 2;要「不加仓」请写 type: none + source。")

    return STATE_HAS_VALUE


def install() -> None:
    """
    把 add_on 登记进 config_adapter.IMPLEMENTED。

    ★ 纪律 1:**不改** config_adapter.py 的任何现有函数 —— 这里只往那个 dict 里
      加一个 key,套路和 engine/ops_exits_1029.py 已经立过的运行时挂钩完全一样。
    ★ 注意它只是让「add_on 这一步的类型」有地方登记;真正的校验走 validate_add_on,
      因为 config_adapter.adapt() 遍历的步骤名是写死的七步,★ 我们不动它。

    ══════════════════════════════════════════════════════════════════════
    ★★ 为什么**没有**把校验接进 config_adapter.adapt()(2026-10-30,Lin 已拍板)
    ══════════════════════════════════════════════════════════════════════
    接进去只需 1 行(adapt() 末尾 return 之前调一次 validate_add_on(cfg)),
    ★ 但要让 adapt() 真正「看见」这一步,得改它写死的七步 tuple 和 `need` 列表;
    而 `need` 加一项会让 `cfg.setdefault("add_on", {})` 对**每一份**配置生效,
    下游凡是遍历 cfg 键的地方都可能受影响。

    ★ 拍板的理由(两条):
      ① 现在 **0 份**配置有 add_on,这道闸唯一能挡的是
         **将来有人新写一份带 add_on 的配置** —— 而那个人一定会跑 run_all.py,
         engine/checks/addon_schema.py 会在那里拦住他。
      ② 为一个**还没发生**的场景动 config_adapter.py 的 `need` 列表,
         风险大于收益。

    ★★ 所以结论是:**等第一份真实 add_on 配置出现时再评估**。
       ★ 下一个人不用重新推一遍这个判断 —— 到那时再看要不要把这 1 行加上。
    ══════════════════════════════════════════════════════════════════════
    """
    from . import config_adapter
    config_adapter.IMPLEMENTED.setdefault(ADD_ON_CANONICAL, set())
    config_adapter.IMPLEMENTED[ADD_ON_CANONICAL] |= set(IMPLEMENTED_ADD_ON)
    config_adapter.BLOCKED_REASONS.update(
        {k: v for k, v in FORBIDDEN_ADD_ON.items()})


__all__ = [
    "ADD_ON_ALIASES", "ADD_ON_CANONICAL",
    "IMPLEMENTED_ADD_ON", "FORBIDDEN_ADD_ON",
    "STATE_HAS_VALUE", "STATE_EXPLICIT_NONE", "STATE_MISSING",
    "AddOnSchemaError", "validate_add_on", "slot_state", "find_slot", "install",
]
