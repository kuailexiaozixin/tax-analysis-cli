"""tax-analysis-engine 的命令行入口。

命令按引擎主线编号组织，不把脚本名直接暴露给用户：
  ① classify  ② coverage  ③④ search  ⑥ analyze  ⑧ law
  以及 calc / cases / check / templates 等离线工具。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Callable

import typer

from . import engine

svc = engine.tax_service
ServiceError = svc.ServiceError

app = typer.Typer(
    no_args_is_help=True,
    help="税收政策分析引擎：判型、覆盖率、检索、法规阅读、分层底稿与离线工具。",
)
law_app = typer.Typer(no_args_is_help=True, help="法规元数据、全文与官方解读。")
analyze_app = typer.Typer(no_args_is_help=True, help="⑥ 分析：计划、取数、分层底稿。")
calc_app = typer.Typer(no_args_is_help=True, help="参数化算式骨架。")
check_app = typer.Typer(no_args_is_help=True, help="账套巡检、稽查模拟、合同受理与内控生成。")
templates_app = typer.Typer(no_args_is_help=True, help="输出模板。")

app.add_typer(law_app, name="law")
app.add_typer(analyze_app, name="analyze")
app.add_typer(calc_app, name="calc")
app.add_typer(check_app, name="check")
app.add_typer(templates_app, name="templates")

_JSON_OPTION = typer.Option("--json", help="输出完整 JSON（适合管道与程序调用）")

_EXIT_CODES = {
    "invalid_parameter": 2,
    "invalid_request": 2,
    "missing_params": 2,
    "unknown_skeleton": 2,
    "unknown_question_type": 2,
    "page_not_supported": 2,
    "not_found": 3,
    "unknown_template": 3,
    "upstream_error": 4,
}


def _exit_code(exc: ServiceError) -> int:
    return _EXIT_CODES.get(exc.code, 1)


def _emit(data: Any, as_json: bool, render: Callable[[Any], str] | None = None):
    if as_json or render is None:
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        typer.echo(render(data))


def _run(fn: Callable[[], Any], as_json: bool = False,
         render: Callable[[Any], str] | None = None):
    try:
        data = fn()
    except ServiceError as exc:
        if as_json:
            typer.echo(json.dumps(exc.as_dict(), ensure_ascii=False, indent=2))
        else:
            typer.echo(f"错误[{exc.code}] {exc.message}", err=True)
        raise typer.Exit(_exit_code(exc)) from None
    except KeyboardInterrupt:
        raise typer.Exit(130) from None
    except Exception as exc:  # 适配器自身的故障，不能让用户看到空清单
        if as_json:
            typer.echo(json.dumps(
                {"error": {"code": "internal_error",
                           "message": f"{type(exc).__name__}: {exc}"}},
                ensure_ascii=False, indent=2))
        else:
            typer.echo(f"内部错误：{type(exc).__name__}: {exc}", err=True)
        raise typer.Exit(1) from None
    _emit(data, as_json, render)


def _json_value(value: str, name: str, default: Any):
    """接受内联 JSON 或 @文件；空串取默认值。"""
    text = (value or "").strip()
    if not text:
        return default
    if text.startswith("@"):
        path = Path(text[1:]).expanduser()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise typer.BadParameter(f"{name} 读不到 {path}：{exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"{name} 不是合法 JSON：{exc}") from exc


def _json_file(path: Path, name: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise typer.BadParameter(f"{name} 读不到 {path}：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"{name} 不是合法 JSON：{exc}") from exc


# ── 渲染 ───────────────────────────────────────────────────────────────────

def _render_health(d: dict) -> str:
    return "\n".join([
        f"引擎：{d['engine_root']}",
        f"税种/专题：{d['tax_types']} 条｜算式骨架：{d['calc_skeletons']} 条"
        f"｜输出模板：{d['template_count']} 个",
        f"检查时间：{d['time']}",
    ])


def _render_tax_types(rows: list[dict]) -> str:
    lines = [f"税种与专题（{len(rows)} 条）"]
    for i, row in enumerate(rows, 1):
        lines.append(
            f"{i:>2}. {row['name']}｜上位法：{row['parent_law'] or '未标'}"
            f"｜权限：{row['authority'] or '未标'}")
        if row.get("aliases"):
            lines.append(f"    别名：{'、'.join(row['aliases'])}")
    return "\n".join(lines)


def _render_classify(d: dict) -> str:
    t = d.get("type") or {}
    ctx = d.get("context") or {}
    lines = [
        f"题型：{t.get('label', '')}（{t.get('type', '')}，把握 {t.get('confidence', '')}）",
        f"判型依据：{t.get('reason', '')}",
    ]
    missing = ctx.get("missing") or []
    if missing:
        lines.append(f"题面未交代：{'、'.join(missing)}")
    probes = d.get("probes") or []
    if probes:
        lines.append("建议先问：")
        for p in probes:
            lines.append(f"  · {p.get('label', '')}：{p.get('probe', '')}")
    lines.append(f"这类题要答到位，需要：{'、'.join(d.get('sources') or [])}")
    lines.append(f"结论应包含：{d.get('must_answer', '')}")
    if d.get("rule_note"):
        lines.append(f"规则陈述边界：{d['rule_note']}")
    for gap in d.get("accounting_gap") or []:
        lines.append(f"会计口径缺口：{gap}")
    return "\n".join(lines)


def _render_coverage(d: dict) -> str:
    pct = d.get("覆盖率")
    shown = f"{pct:.0%}" if isinstance(pct, (int, float)) else str(pct)
    lines = [f"覆盖率：{shown}", f"分母：{d.get('分母说明', '')}"]
    counts = d.get("计数") or {}
    if counts:
        lines.append("计数：" + "｜".join(f"{k} {v}" for k, v in counts.items()))
    for item in d.get("分项") or []:
        line = f"  [{item.get('状态', '')}] {item.get('项', '')}"
        if item.get("判据"):
            line += f"（{item['判据']}）"
        lines.append(line)
    if d.get("补问"):
        lines.append("补问：" + "；".join(d["补问"]))
    if d.get("待办"):
        lines.append("待办：")
        for task in d["待办"]:
            lines.append(f"  · {task}")
    if d.get("边界"):
        lines.append(f"边界：{d['边界']}")
    return "\n".join(lines)


def _render_search(d: dict) -> str:
    meta = d.get("meta") or {}
    lines = [
        f"检索「{d.get('query', '')}」：{d.get('total', 0)} 条"
        f"（第 {d.get('page', 1)} 页，每页 {d.get('page_size', 0)}，"
        f"{'还有下一页' if d.get('has_next') else '没有下一页'}）"
    ]
    summary = meta.get("source_summary") or {}
    if summary:
        lines.append("来源：" + "｜".join(f"{k} {v}" for k, v in summary.items()))
    errors = meta.get("errors") or {}
    if errors:
        lines.append("取数失败（失败不等于该源没有内容）：")
        for source, why in errors.items():
            lines.append(f"  · {source}：{why}")
    for i, item in enumerate(d.get("items") or [], 1):
        source = item.get("_source") or "npc"
        lines.append(f"{i:>2}. [{source}] {item.get('title', '')}")
        bits = []
        date = item.get("publish_date") or item.get("date") or ""
        if date:
            bits.append(f"日期 {date}")
        if item.get("status"):
            bits.append(f"状态 {item['status']}")
        if item.get("issuing_authority"):
            bits.append(item["issuing_authority"])
        if bits:
            lines.append("    " + "｜".join(bits))
        if item.get("url"):
            lines.append("    " + item["url"])
        elif item.get("id"):
            lines.append(f"    id={item['id']}（用 law info 查看元数据）")
    if meta.get("degraded_note"):
        lines.append(f"降级说明：{meta['degraded_note']}")
    if meta.get("date_note"):
        lines.append(f"日期口径：{meta['date_note']}")
    gaps = meta.get("gaps") or []
    for gap in gaps:
        lines.append(f"缺口：{gap}")
    return "\n".join(lines)


def _render_law_info(d: dict) -> str:
    fields = [
        ("id", "ID"), ("title", "标题"), ("category", "类别"),
        ("publish_date", "公布日期"), ("effective_date", "生效日期"),
        ("status", "时效"), ("issuing_authority", "制定机关"),
        ("fetched_at", "抓取时间"),
    ]
    lines = ["法规元数据"]
    for key, label in fields:
        value = d.get(key)
        if value not in (None, ""):
            lines.append(f"{label}：{value}")
    oss = d.get("oss_files") or {}
    if oss:
        lines.append("下载件：" + "｜".join(
            f"{k} {'有' if v else '无'}" for k, v in oss.items()))
    related = d.get("related") or {}
    if related:
        lines.append("关联：" + "｜".join(
            f"{k} {len(v)} 条" for k, v in related.items()))
    content = d.get("content_tree") or []
    if content:
        lines.append(f"正文节点：{len(content)} 个（完整内容用 --json）")
    return "\n".join(lines)


def _render_law_text(d: dict) -> str:
    if not d.get("available"):
        return f"法规 {d.get('law_id', '')} 没取到正文（不是「没有正文」，是这次下载/解析失败）"
    lines = [f"法规 {d['law_id']} 正文：{d['count']} 段"]
    for i, paragraph in enumerate(d.get("paragraphs") or [], 1):
        lines.append(f"{i:>3}. {paragraph}")
    return "\n".join(lines)


def _render_interpretations(d: dict) -> str:
    lines = [f"《{d.get('law_title', '')}》官方解读：{d.get('total', 0)} 条"]
    if d.get("engine_error"):
        lines.append(f"搜索引擎异常：{d['engine_error']}"
                     f"（阻挡 {d.get('queries_blocked', '')} 次查询）")
    for i, item in enumerate(d.get("sources") or [], 1):
        lines.append(f"{i:>2}. [{item.get('source_label') or item.get('source', '')}]"
                     f" {item.get('title', '')}")
        if item.get("date"):
            lines.append(f"    日期 {item['date']}")
        if item.get("url"):
            lines.append(f"    {item['url']}")
        if item.get("snippet"):
            lines.append(f"    {item['snippet'][:120]}")
    return "\n".join(lines)


def _render_plan(d: dict) -> str:
    lines = _render_classify(d).splitlines()
    rounds = d.get("rounds") or []
    if rounds:
        lines.append("检索轮次：")
        for r in rounds:
            lines.append(f"  第 {r.get('round')} 轮 {r.get('goal', '')}")
            lines.append(f"    源：{'/'.join(r.get('sources') or [])}")
            lines.append(f"    调用：{r.get('call', '')}")
    if d.get("overseas_note"):
        lines.append(f"境外辖区边界：{d['overseas_note']}")
    return "\n".join(lines)


def _render_gather(d: dict) -> str:
    lines = _render_plan(d).splitlines()
    evidence = d.get("evidence") or []
    lines.append(f"实际取回：{len(evidence)} 条（观察时点 {d.get('at') or '未指定'}）")
    for item in evidence[:20]:
        lines.append(
            f"  [{item.get('role_label', '')}] "
            f"{item.get('rank_label', '')}/{item.get('validity_label', '')} "
            f"{item.get('title', '')[:60]}")
    if len(evidence) > 20:
        lines.append(f"  … 另有 {len(evidence) - 20} 条（用 --json 取全量）")
    for err in d.get("errors") or []:
        lines.append(f"  ! 取数失败：{err}")
    return "\n".join(lines)


def _render_answer(d: dict) -> str:
    t = d.get("type") or {}
    lines = [f"问题：{d.get('question', '')}",
             f"题型：{t.get('label', '')}（{t.get('type', '')}）"]
    if d.get("cited_note"):
        lines.append(f"点名文件说明：{d['cited_note']}")
    primary = d.get("primary") or {}
    lines.append("【主依据】" + (primary.get("title") or "（本轮没有取到法定文件）"))
    bits = [primary.get(k, "") for k in ("rank_label", "validity_label", "role_label")]
    bits = [b for b in bits if b]
    if bits:
        lines.append("  " + "｜".join(bits))
    if primary.get("why"):
        lines.append(f"  {primary['why']}")
    for key, title in (("supporting", "其余法定依据"),
                       ("practice", "执行口径与实务认定"),
                       ("to_verify", "待核对线索")):
        rows = d.get(key) or []
        lines.append(f"【{title}】{len(rows)} 条")
        for row in rows[:10]:
            lines.append(f"  · {row.get('title', '')[:60]}")
        if len(rows) > 10:
            lines.append(f"  … 另有 {len(rows) - 10} 条（用 --json 取全量）")
    if d.get("repealed"):
        lines.append(f"已废止：{'；'.join(d['repealed'])}")
    if d.get("pending"):
        lines.append(f"待生效：{'；'.join(d['pending'])}")
    if d.get("conditions"):
        lines.append(f"必须写在答案里的前提：{'；'.join(d['conditions'])}")
    if d.get("citation_note"):
        lines.append(f"文号核对：{d['citation_note']}")
    if d.get("fetch_errors"):
        lines.append(f"取数失败：{'；'.join(d['fetch_errors'])}")
    if d.get("fetch_note"):
        lines.append(d["fetch_note"])
    if d.get("evidence_gap"):
        lines.append(d["evidence_gap"])
    if d.get("legislative_note"):
        lines.append(f"立法阶段限制：{d['legislative_note']}")
    if d.get("overseas_note"):
        lines.append(f"境外辖区边界：{d['overseas_note']}")
    counts = d.get("counts") or {}
    if counts:
        lines.append("计数：" + "｜".join(f"{k} {v}" for k, v in counts.items()))
    return "\n".join(lines)


def _render_calc_list(rows: list[dict]) -> str:
    lines = [f"算式骨架（{len(rows)} 条）"]
    for row in rows:
        lines.append(f"· {row['name']}：{row['formula']}")
        lines.append(f"    输入：{'、'.join(row['inputs'])}")
        lines.append(f"    结果：{'、'.join(row['results'])}")
    return "\n".join(lines)


def _render_calc_run(d: dict) -> str:
    lines = [f"骨架：{d.get('骨架', '')}", f"公式：{d.get('公式', '')}"]
    for i, step in enumerate(d.get("步骤") or [], 1):
        lines.append(f"  第 {i} 步 {step.get('名称', '')} = {step.get('算式', '')}")
        if step.get("代入"):
            lines.append(f"    代入：{step['代入']}")
        if step.get("结果") is not None:
            lines.append(f"    结果：{step['结果']}")
        if step.get("分档"):
            lines.append(f"    分档：{step['分档']}")
    results = d.get("结果") or {}
    lines.append("结果：" + "｜".join(f"{k} {v}" for k, v in results.items()))
    return "\n".join(lines)


def _render_templates(rows: list[dict]) -> str:
    return "\n".join(f"{i:>2}. {row['key']}  {row['title']}"
                     for i, row in enumerate(rows, 1))


# ── 基础命令 ───────────────────────────────────────────────────────────────

@app.command()
def health(as_json: Annotated[bool, _JSON_OPTION] = False):
    """不联网的健康检查：引擎根、税种数、骨架数、模板数。"""
    _run(svc.health, as_json, _render_health)


@app.command("tax-types")
def tax_types(as_json: Annotated[bool, _JSON_OPTION] = False):
    """列出税种与专题词表（33 条）。"""
    _run(svc.tax_types, as_json, _render_tax_types)


# ── ① 判型 ─────────────────────────────────────────────────────────────────

@app.command()
def classify(
    question: Annotated[str, typer.Argument(help="用户原话")],
    max_probes: Annotated[int, typer.Option("--max-probes", help="最多给几条追问")] = 3,
    as_json: Annotated[bool, _JSON_OPTION] = False,
):
    """① 判型、前提缺口与探针（离线）。"""
    _run(lambda: svc.classify(question, max_probes=max_probes), as_json, _render_classify)


# ── ② 覆盖率 ───────────────────────────────────────────────────────────────

@app.command()
def coverage(
    qtype: Annotated[str, typer.Argument(help="题型代号，见 coverage 报错里的 allowed")],
    question: Annotated[str, typer.Option("--question", "-q", help="题面，用于判前提轴")] = "",
    evidence: Annotated[str, typer.Option("--evidence", help="依据清单 JSON 或 @文件")] = "",
    skeleton: Annotated[str, typer.Option("--skeleton", help="算式骨架名（可选）")] = "",
    params: Annotated[str, typer.Option("--params", help="算式参数 JSON 或 @文件")] = "",
    as_json: Annotated[bool, _JSON_OPTION] = False,
):
    """② 依据覆盖率：evidence 不传是「没检」，传 [] 是「检了没有」。"""
    _run(
        lambda: svc.coverage(
            qtype,
            question=question,
            evidence=_json_value(evidence, "evidence", None),
            skeleton=skeleton,
            params=_json_value(params, "params", None),
        ),
        as_json,
        _render_coverage,
    )


# ── ③④ 检索 ───────────────────────────────────────────────────────────────

@app.command()
def search(
    query: Annotated[str, typer.Argument(help="检索词")],
    source: Annotated[list[str] | None, typer.Option("--source", "-s", help="可重复；默认六源")] = None,
    size: Annotated[int, typer.Option("--size", help="每源条数 1–50")] = 10,
    page: Annotated[int, typer.Option("--page", help="页码；多源聚合只支持 1")] = 1,
    status: Annotated[int, typer.Option("--status", help="1/2/3/4；3=现行有效")] = 3,
    scope: Annotated[str, typer.Option("--scope", help="title 或 fulltext")] = "title",
    exact: Annotated[bool, typer.Option("--exact", help="精确检索（法名本体时必须开）")] = False,
    sort: Annotated[str, typer.Option("--sort", help="relevance 或 date")] = "relevance",
    date_from: Annotated[str, typer.Option("--date-from", help="YYYY-MM-DD")] = "",
    date_to: Annotated[str, typer.Option("--date-to", help="YYYY-MM-DD")] = "",
    as_json: Annotated[bool, _JSON_OPTION] = False,
):
    """③④ 检索：默认六源聚合；只有 --source npc 单源能翻页。"""
    _run(
        lambda: svc.search(
            query, sources=source, size=size, page=page, status=status,
            scope=scope, exact=exact, sort=sort,
            date_from=date_from, date_to=date_to,
        ),
        as_json,
        _render_search,
    )


# ── ⑧ 法规 ─────────────────────────────────────────────────────────────────

@law_app.command("info")
def law_info(
    law_id: Annotated[str, typer.Argument(help="法规 ID（NPC bbbs）")],
    as_json: Annotated[bool, _JSON_OPTION] = False,
):
    """法规元数据。"""
    _run(lambda: svc.law_info(law_id), as_json, _render_law_info)


@law_app.command("text")
def law_text(
    law_id: Annotated[str, typer.Argument(help="法规 ID（NPC bbbs）")],
    as_json: Annotated[bool, _JSON_OPTION] = False,
):
    """下载并读出法规全文段落。"""
    _run(lambda: svc.law_text(law_id), as_json, _render_law_text)


@law_app.command("interpretations")
def law_interpretations(
    title: Annotated[str, typer.Argument(help="法规标题")],
    keyword: Annotated[str, typer.Option("--keyword", "-k", help="补充检索词")] = "",
    province: Annotated[str, typer.Option("--province", help="省份子域名，如 shanghai")] = "",
    source: Annotated[list[str] | None, typer.Option("--source", "-s", help="可重复的站点域名")] = None,
    as_json: Annotated[bool, _JSON_OPTION] = False,
):
    """只查 .gov.cn 的官方解读。"""
    _run(
        lambda: svc.law_interpretations(title, keyword=keyword,
                                        province=province, sources=source),
        as_json,
        _render_interpretations,
    )


# ── ⑥ 分析 ─────────────────────────────────────────────────────────────────

@analyze_app.command("plan")
def analyze_plan(
    question: Annotated[str, typer.Argument(help="用户原话")],
    as_json: Annotated[bool, _JSON_OPTION] = False,
):
    """⑥ 之前的检索计划（离线）。"""
    _run(lambda: svc.analyze_plan(question), as_json, _render_plan)


@analyze_app.command("gather")
def analyze_gather(
    question: Annotated[str, typer.Argument(help="用户原话")],
    at: Annotated[str, typer.Option("--at", help="观察时点 YYYY-MM-DD")] = "",
    body: Annotated[bool, typer.Option("--body/--no-body", help="是否取税屋正文")] = True,
    citations: Annotated[bool, typer.Option("--check-citations/--no-check-citations",
                                           help="是否回官方库核对文号")] = True,
    max_per_round: Annotated[int | None, typer.Option("--max-per-round", help="每轮每源最多几条")] = None,
    as_json: Annotated[bool, _JSON_OPTION] = False,
):
    """按计划联网检索并定级；部分源失败留在结果里，不当作「没有」。"""
    _run(
        lambda: svc.analyze_gather(
            question, at=at, read_body=body, check_citations=citations,
            max_per_round=max_per_round),
        as_json,
        _render_gather,
    )


@analyze_app.command("answer")
def analyze_answer(
    question: Annotated[str, typer.Argument(help="用户原话")],
    at: Annotated[str, typer.Option("--at", help="观察时点 YYYY-MM-DD")] = "",
    body: Annotated[bool, typer.Option("--body/--no-body", help="是否取税屋正文")] = True,
    citations: Annotated[bool, typer.Option("--check-citations/--no-check-citations",
                                           help="是否回官方库核对文号")] = True,
    as_json: Annotated[bool, _JSON_OPTION] = False,
):
    """一次跑完检索与分层，回结构化底稿；不写最终答案。"""
    _run(
        lambda: svc.analyze_answer(question, at=at, read_body=body,
                                   check_citations=citations),
        as_json,
        _render_answer,
    )


# ── 算式 ───────────────────────────────────────────────────────────────────

@calc_app.command("list")
def calc_list(as_json: Annotated[bool, _JSON_OPTION] = False):
    """列出骨架、公式、输入与结果。"""
    _run(svc.calc_list, as_json, _render_calc_list)


@calc_app.command("run")
def calc_run(
    skeleton: Annotated[str, typer.Argument(help="骨架名")],
    params: Annotated[str, typer.Option("--params", help="参数 JSON 或 @文件")],
    as_json: Annotated[bool, _JSON_OPTION] = False,
):
    """展开一条算式；缺参数与多余参数都会报出来。"""
    _run(lambda: svc.calc_run(skeleton, _json_value(params, "params", {})),
         as_json, _render_calc_run)


# ── 类案 ───────────────────────────────────────────────────────────────────

@app.command()
def cases(
    topic: Annotated[str, typer.Argument(help="主题词")],
    element: Annotated[list[str] | None, typer.Option("--element", help="争议要素，可重复")] = None,
    mode: Annotated[str, typer.Option("--mode", help="exhaustive 或 recent")] = "exhaustive",
    pages: Annotated[int, typer.Option("--pages", help="1–20")] = 1,
    order: Annotated[str, typer.Option("--order", help="relevance、date_desc、category 或 date_asc")] = "relevance",
    limit: Annotated[int, typer.Option("--limit", help="1–100")] = 10,
    as_of: Annotated[str, typer.Option("--as-of", help="截止日期 YYYY-MM-DD")] = "",
    shui5: Annotated[bool, typer.Option("--shui5/--no-shui5", help="是否加税屋那一路")] = False,
    as_json: Annotated[bool, _JSON_OPTION] = False,
):
    """类案台账：税务总局查处通报与曝光典型。"""
    _run(
        lambda: svc.cases(topic, elements=element, mode=mode, pages=pages,
                          order=order, limit=limit, as_of=as_of, shui5=shui5),
        as_json,
        engine.tax_cases.render,
    )


# ── 检查类 ─────────────────────────────────────────────────────────────────

@check_app.command("ledger")
def check_ledger(
    ledger: Annotated[Path, typer.Argument(help="账套 JSON 文件", exists=True, dir_okay=False)],
    params: Annotated[str, typer.Option("--params", help="参数 JSON 或 @文件")] = "",
    codes: Annotated[list[str] | None, typer.Option("--code", help="规则代号，可重复")] = None,
    tolerance: Annotated[float, typer.Option("--tolerance", help="相对容差")] = 0.0,
    as_json: Annotated[bool, _JSON_OPTION] = False,
):
    """账套巡检。"""
    _run(
        lambda: svc.ledger_check(_json_file(ledger, "ledger"),
                                 params=_json_value(params, "params", None),
                                 codes=codes, tolerance=tolerance),
        as_json,
        engine.tax_ledger.render,
    )


@check_app.command("inspect")
def check_inspect(
    answers: Annotated[Path | None, typer.Option("--answers", help="回答 JSON 文件",
                                                  exists=True, dir_okay=False)] = None,
    domains: Annotated[list[str] | None, typer.Option("--domain", help="检查域，可重复")] = None,
    codes: Annotated[list[str] | None, typer.Option("--code", help="要点代号，可重复")] = None,
    scenario: Annotated[str, typer.Option("--scenario", help="场景")] = "",
    signal: Annotated[str, typer.Option("--signal", help="风险指标")] = "",
    tolerance: Annotated[float, typer.Option("--tolerance", help="相对容差")] = 0.0,
    as_json: Annotated[bool, _JSON_OPTION] = False,
):
    """稽查模拟问询：逐问生成六字段单元。"""
    _run(
        lambda: svc.inspection(
            answers=_json_file(answers, "answers") if answers else None,
            domains=domains, codes=codes, scenario=scenario,
            signal=signal, tolerance=tolerance),
        as_json,
        engine.tax_inspect.render,
    )


@check_app.command("intake")
def check_intake(
    document: Annotated[Path, typer.Argument(help="多合同 JSON 文件", exists=True, dir_okay=False)],
    as_json: Annotated[bool, _JSON_OPTION] = False,
):
    """多合同受理：九维度覆盖。"""
    _run(lambda: svc.intake(_json_file(document, "document")),
         as_json, engine.tax_intake.render_intake)


@check_app.command("reconcile")
def check_reconcile(
    document: Annotated[Path, typer.Argument(help="多合同 JSON 文件", exists=True, dir_okay=False)],
    confirmed: Annotated[list[str] | None, typer.Option("--confirmed", help="已确认的替代边，可重复")] = None,
    dims: Annotated[list[str] | None, typer.Option("--dim", help="只比对的维度，可重复")] = None,
    as_json: Annotated[bool, _JSON_OPTION] = False,
):
    """合同条款与履行记录对账。"""
    _run(
        lambda: svc.reconcile(_json_file(document, "document"),
                              confirmed=confirmed, dims=dims),
        as_json,
        engine.tax_intake.render,
    )


@check_app.command("control")
def check_control(
    diagnosis: Annotated[Path | None, typer.Option("--diagnosis", help="稽查模拟输出 JSON 文件",
                                                    exists=True, dir_okay=False)] = None,
    assumption: Annotated[list[str] | None, typer.Option("--assumption", help="假设，可重复")] = None,
    links: Annotated[list[str] | None, typer.Option("--link", help="环节代号或名称，可重复")] = None,
    codes: Annotated[list[str] | None, typer.Option("--code", help="活动代号，可重复")] = None,
    as_json: Annotated[bool, _JSON_OPTION] = False,
):
    """把已确认缺口转成九要素制度文本。"""
    _run(
        lambda: svc.controls(
            diagnosis=_json_file(diagnosis, "diagnosis") if diagnosis else None,
            assumptions=assumption, links=links, codes=codes),
        as_json,
        engine.tax_control.render,
    )


# ── 模板 ───────────────────────────────────────────────────────────────────

@templates_app.command("list")
def templates_list(as_json: Annotated[bool, _JSON_OPTION] = False):
    """列出可用的输出模板。"""
    rows = [{"key": key, "title": heading}
            for key, heading in svc.TEMPLATE_KEYS.items()
            if heading in svc.template_index()]
    _run(lambda: rows, as_json, _render_templates)


@templates_app.command("show")
def templates_show(
    key: Annotated[str, typer.Argument(help="模板键，如 analysis")],
    as_json: Annotated[bool, _JSON_OPTION] = False,
):
    """显示一份输出模板的原文。"""
    heading = svc.TEMPLATE_KEYS.get(key, key)
    _run(
        lambda: {"key": key, "title": heading, "text": svc.template_text(key)},
        as_json,
        lambda d: d["text"],
    )


def main():
    app()


if __name__ == "__main__":
    main()
