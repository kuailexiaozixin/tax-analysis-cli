import hashlib
import json
import sys
from pathlib import Path

from typer.testing import CliRunner

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tax_engine_cli import engine  # noqa: E402
from tax_engine_cli.app import app  # noqa: E402

runner = CliRunner()


def invoke(*args: str):
    return runner.invoke(app, list(args))


def output_json(result):
    return json.loads(result.output)


def test_health_reports_engine_scale():
    result = invoke("health")
    assert result.exit_code == 0, result.output
    assert "税种/专题：33" in result.output
    assert "算式骨架：6" in result.output


def test_tax_types_include_leaf_tobacco():
    result = invoke("tax-types")
    assert result.exit_code == 0, result.output
    assert "烟叶税" in result.output
    assert "税种与专题（33 条）" in result.output


def test_classify_offline():
    result = invoke("classify", "研发费用加计扣除比例是多少")
    assert result.exit_code == 0, result.output
    assert "政策查询" in result.output
    assert "lookup" in result.output


def test_coverage_unknown_type_is_json_error():
    result = invoke("coverage", "不存在的题型", "--json")
    assert result.exit_code == 2
    body = output_json(result)
    assert body["error"]["code"] == "unknown_question_type"
    assert "allowed" in body["error"]["details"]


def test_calc_run_offline():
    result = invoke("calc", "run", "从价计征",
                    "--params", '{"计税依据": 100, "税率": 0.05}')
    assert result.exit_code == 0, result.output
    assert "应纳税额" in result.output
    assert "5" in result.output


def test_calc_missing_params_exit_two():
    result = invoke("calc", "run", "从价计征",
                    "--params", '{"计税依据": 100}')
    assert result.exit_code == 2
    assert "缺少参数" in result.output


def test_search_human_output(monkeypatch):
    def fake_search(query, **kwargs):
        assert query == "增值税"
        assert kwargs["sources"] == ["npc"]
        return {
            "query": query, "page": 1, "page_size": 10, "total": 1,
            "has_next": False,
            "items": [{
                "id": "abc", "title": "中华人民共和国增值税法",
                "publish_date": "2024-12-25", "status": "现行有效",
                "issuing_authority": "全国人大常委会",
            }],
            "meta": {"source_summary": {"npc": 1}, "errors": {},
                     "gaps": [], "searched_at": "2026-10-20 12:00:00"},
        }

    monkeypatch.setattr(engine.tax_service, "search", fake_search)
    result = invoke("search", "增值税", "--source", "npc")
    assert result.exit_code == 0, result.output
    assert "中华人民共和国增值税法" in result.output
    assert "[npc]" in result.output
    assert "id=abc" in result.output


def test_multi_source_page_two_is_rejected_without_network():
    result = invoke("search", "增值税", "--source", "npc",
                    "--source", "chinatax", "--page", "2")
    assert result.exit_code == 2
    assert "page_not_supported" in result.output


def test_search_gov_forwards_filters_and_renders_notes(monkeypatch):
    captured = {}

    def fake_gov(query, **kwargs):
        captured.update(kwargs)
        return {
            "query": query, "source": kwargs["source"], "page": 2,
            "page_size": 10, "total": 25, "has_next": True,
            "items": [{"title": "测试文件", "document_number": "公告2026年第1号",
                       "publish_date": "2026-01-01", "url": "https://example.gov.cn/x"}],
            "meta": {"source": kwargs["source"], "filters": {"xxgkAging": "全文有效"},
                     "total_hits": 99, "pages_scanned": 4, "stopped_early": True,
                     "filter_note": "维度拼窄的说明", "errors": {}},
        }

    monkeypatch.setattr(engine.tax_service, "search_gov", fake_gov)
    result = invoke(
        "search-gov", "增值税", "--source", "chinatax", "--page", "2",
        "--aging", "全文有效", "--date-from", "2026-01-01", "--sort", "date",
        "--tax-type", "增值税",
    )
    assert result.exit_code == 0, result.output
    assert captured["aging"] == "全文有效"
    assert captured["date_from"] == "2026-01-01"
    assert captured["sort"] == "date"
    assert captured["tax_type"] == "增值税"
    assert "税务总局 25 条命中" in result.output
    assert "库内命中 99 条" in result.output
    assert "维度拼窄的说明" in result.output
    assert "公告2026年第1号" in result.output


def test_search_gov_rejects_fgk_page_before_network():
    result = invoke("search-gov", "增值税", "--source", "fgk",
                    "--page", "2", "--json")
    assert result.exit_code == 2
    body = output_json(result)
    assert body["error"]["code"] == "page_not_supported"


def test_search_gov_rejects_body_on_chinatax_before_network():
    result = invoke("search-gov", "增值税", "--source", "chinatax",
                    "--body", "--json")
    assert result.exit_code == 2
    body = output_json(result)
    assert body["error"]["code"] == "invalid_parameter"


def test_analyze_answer_forwards_max_per_round(monkeypatch):
    captured = {}

    def fake_answer(question, **kwargs):
        captured.update(kwargs)
        return {"question": question, "type": {"label": "政策查询", "type": "lookup"},
                "primary": {}, "supporting": [], "practice": [], "to_verify": [],
                "repealed": [], "pending": [], "conditions": [],
                "counts": {"total": 0}}

    monkeypatch.setattr(engine.tax_service, "analyze_answer", fake_answer)
    result = invoke("analyze", "answer", "研发费用加计扣除比例是多少",
                    "--max-per-round", "2")
    assert result.exit_code == 0, result.output
    assert captured["max_per_round"] == 2


def test_law_text_patched(monkeypatch):
    monkeypatch.setattr(
        engine.tax_service, "law_text",
        lambda law_id: {"law_id": law_id, "available": True,
                        "count": 2, "paragraphs": ["第一条", "第二条"]},
    )
    result = invoke("law", "text", "abc")
    assert result.exit_code == 0, result.output
    assert "第一条" in result.output
    assert "2 段" in result.output


def test_law_info_forwards_the_id(monkeypatch):
    captured = {}

    def fake_info(law_id):
        captured["law_id"] = law_id
        return {"id": law_id, "title": "中华人民共和国增值税法",
                "status": "现行有效"}

    monkeypatch.setattr(engine.tax_service, "law_info", fake_info)
    result = invoke("law", "info", "abc")
    assert result.exit_code == 0, result.output
    assert captured["law_id"] == "abc"
    assert "增值税法" in result.output


def test_law_related_forwards_keyword(monkeypatch):
    captured = {}

    def fake_related(law_id, keyword=""):
        captured.update(law_id=law_id, keyword=keyword)
        return {"law_id": law_id, "law_title": "增值税法", "keyword": keyword,
                "total": 1,
                "sources": [{"title": "解读A", "url": "https://a.test/1",
                             "source_label": "税屋"}]}

    monkeypatch.setattr(engine.tax_service, "web_related", fake_related)
    result = invoke("law", "related", "abc", "--keyword", "税率")
    assert result.exit_code == 0, result.output
    assert captured == {"law_id": "abc", "keyword": "税率"}
    assert "解读A" in result.output
    assert "相关网页：1 条" in result.output


def test_intake_blank_round_trips_through_intake(tmp_path):
    blank = invoke("check", "intake-blank")
    assert blank.exit_code == 0, blank.output
    doc = output_json(blank)
    assert [c["代号"] for c in doc["合同"]] == ["CT-1"]
    doc["合同"][0]["名称"] = "采购合同"
    path = tmp_path / "document.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    result = invoke("check", "intake", str(path))
    assert result.exit_code == 0, result.output
    assert "缺 9" in result.output


def test_templates_show_and_unknown_key():
    ok = invoke("templates", "show", "analysis")
    assert ok.exit_code == 0, ok.output
    assert "分析六段式" in ok.output

    for key, marker in (("ledger", "账套巡检条件块"),
                        ("intake", "多合同受理条件块")):
        nested = invoke("templates", "show", key)
        assert nested.exit_code == 0, nested.output
        assert marker in nested.output

    missing = invoke("templates", "show", "no-such-template")
    assert missing.exit_code == 3
    assert "unknown_template" in missing.output


def test_analyze_plan_offline():
    result = invoke("analyze", "plan", "研发费用加计扣除比例是多少")
    assert result.exit_code == 0, result.output
    assert "检索轮次" in result.output
    assert "第 1 轮" in result.output


def test_cases_accepts_engine_order_value(monkeypatch):
    captured = {}

    def fake_cases(topic, **kwargs):
        captured.update(kwargs)
        return {"topic": topic, "items": []}

    monkeypatch.setattr(engine.tax_service, "cases", fake_cases)
    result = invoke("cases", "虚开发票", "--order", "date_desc", "--json")
    assert result.exit_code == 0, result.output
    assert captured["order"] == "date_desc"


def test_cases_reject_unknown_order_before_network():
    result = invoke("cases", "虚开发票", "--order", "date", "--json")
    assert result.exit_code == 2
    body = output_json(result)
    assert body["error"]["code"] == "invalid_parameter"
    assert "date_desc" in body["error"]["details"]["allowed"]


def test_analyze_answer_patched(monkeypatch):
    monkeypatch.setattr(
        engine.tax_service, "analyze_answer",
        lambda *a, **k: {
            "question": "研发费用加计扣除比例是多少",
            "type": {"label": "政策查询", "type": "lookup"},
            "primary": {"title": "财政部 税务总局公告2023年第7号",
                        "rank_label": "部门规范性文件",
                        "validity_label": "现行有效", "role_label": "直接规定",
                        "why": "与题面直接对应"},
            "supporting": [], "practice": [], "to_verify": [],
            "repealed": [], "pending": [], "conditions": ["适用年度"],
            "counts": {"total": 1},
        },
    )
    result = invoke("analyze", "answer", "研发费用加计扣除比例是多少")
    assert result.exit_code == 0, result.output
    assert "【主依据】财政部 税务总局公告2023年第7号" in result.output
    assert "适用年度" in result.output


def test_json_output_is_machine_readable():
    result = invoke("calc", "list", "--json")
    assert result.exit_code == 0, result.output
    body = output_json(result)
    assert isinstance(body, list)
    assert {row["name"] for row in body} >= {"从价计征", "超额累进"}


def test_bad_json_parameter_does_not_reach_engine():
    result = invoke("calc", "run", "从价计征", "--params", "{bad")
    assert result.exit_code != 0
    assert "不是合法 JSON" in result.output


def test_service_layer_lives_here_not_in_engine():
    """服务契约层、文档读取层与运行时快照都住在本项目里。

    引擎目录里出现这两个模块就说明适配器与引擎又缠回去了：适配器会跟着
    引擎的提交一起变，四个项目的独立性就没有了。
    """
    project_root = Path(__file__).resolve().parents[1]
    assert Path(engine.tax_service.__file__).is_relative_to(project_root / "src")
    assert Path(engine.tax_service.tax_doc.__file__).is_relative_to(project_root / "src")
    assert engine.ENGINE_ROOT.is_relative_to(project_root / "src")
    assert (engine.ENGINE_ROOT / "MANIFEST.json").is_file()
    assert not (engine.ENGINE_ROOT / "scripts" / "tax_service.py").exists()
    assert not (engine.ENGINE_ROOT / "scripts" / "tax_doc.py").exists()


def test_runtime_snapshot_matches_manifest():
    """运行时快照逐文件与清单里的 SHA-256 对齐。

    少一个脚本、改一个字节都在这里报红，而不是等某个取数分支到运行时才炸。
    """
    import re

    runtime = engine.ENGINE_ROOT
    project = Path(__file__).resolve().parents[1]
    version = re.search(r'^version = "([^"]+)"',
                        (project / "pyproject.toml").read_text(encoding="utf-8"), re.M)[1]
    assert sys.modules[engine.__package__].__version__ == version
    manifest = json.loads((runtime / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["engine_version"] == "3.60.1"
    listed = manifest["files"]
    actual = {
        path.relative_to(runtime).as_posix()
        for folder in ("scripts", "data", "references")
        for path in (runtime / folder).glob("*")
        if path.is_file()
    }
    assert set(listed) == actual
    bad = [rel for rel, digest in listed.items()
           if hashlib.sha256((runtime / rel).read_bytes()).hexdigest() != digest]
    assert not bad, bad


def test_no_external_engine_lookup():
    """分发出去的项目不能再从环境变量或同级目录找引擎。"""
    project_root = Path(__file__).resolve().parents[1]
    package = project_root / "src" / "tax_engine_cli"
    needles = ("TAX_ENGINE_ROOT", "find_engine_root")
    offenders = []
    for path in package.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        offenders.extend(f"{path.relative_to(project_root).as_posix()}: {needle}"
                         for needle in needles if needle in text)
    assert offenders == []


def test_official_interpretations_query_plan_offline(monkeypatch):
    tax_doc = engine.tax_service.tax_doc
    calls = []

    def fake_source(site, query, n):
        calls.append((site, query, n))
        return [{"url": f"https://{site}/interpretation"}], ""

    monkeypatch.setattr(tax_doc, "_search_one_source", fake_source)
    result = tax_doc.search_interpretations("中华人民共和国增值税法", "增值税")
    expected = [
        ("chinatax.gov.cn", "增值税 官方解读", 100),
        ("mof.gov.cn", "增值税法 政策解读", 100),
        ("www.gov.cn", "增值税法 政策解读", 100),
    ]
    assert sorted(calls) == sorted(expected)
    assert [item["url"] for item in result["sources"]] == [
        f"https://{site}/interpretation" for site, _, _ in expected
    ]

    calls.clear()
    result = tax_doc.search_interpretations("增值税法", sources=[
        "chinatax.gov.cn", "chinatax.gov.cn", "fgk.chinatax.gov.cn",
        "shanghai.chinatax.gov.cn", "fgk.chinatax.gov.cn", "www.gov.cn",
    ])
    expected = [
        ("chinatax.gov.cn", "增值税法 解读", 100),
        ("fgk.chinatax.gov.cn", "增值税法 政策解读", 100),
        ("shanghai.chinatax.gov.cn", "增值税法 政策解读", 100),
        ("www.gov.cn", "增值税法 政策解读", 100),
    ]
    assert sorted(calls) == sorted(expected)
    assert [item["url"] for item in result["sources"]] == [
        f"https://{site}/interpretation" for site, _, _ in expected
    ]

    answer = sys.modules["tax_answer"]
    sogou = sys.modules[tax_doc.sogou_search.__module__]
    draft_calls = []

    def draft_search(query, *, site, size):
        draft_calls.append((query, site, size))
        return {"results": []}

    monkeypatch.setattr(sogou, "sogou_search", draft_search)
    assert answer._legis_round("离线草案", 5) == ([], "")
    assert draft_calls == [("离线草案", "npc.gov.cn", 5)]
    monkeypatch.setattr(answer, "build_plan", lambda question: {
        "type": {"type": "default"},
        "rounds": [{"round": 1, "goal": "草案", "sources": ["legis"],
                    "term_key": "legis"}],
    })
    monkeypatch.setattr(answer, "search_terms", lambda question: {"legis": "离线草案"})
    gathered = answer.gather("离线草案", read_body=False, max_per_round=2,
                             check_citations=False)
    assert gathered["errors"] == []
    assert draft_calls == [("离线草案", "npc.gov.cn", 5),
                           ("离线草案", "npc.gov.cn", 2)]


def test_sogou_mobile_full_page_cache_offline(monkeypatch, tmp_path):
    from urllib.parse import quote

    tax_doc = engine.tax_service.tax_doc
    tax_sogou = sys.modules[tax_doc.sogou_search.__module__]
    tax_cache = sys.modules["tax_cache"]
    for module in (tax_sogou, tax_cache):
        assert Path(module.__file__).is_relative_to(engine.ENGINE_ROOT / "scripts")

    cache = tax_cache.CacheManager(enabled=True, namespace="sogou")
    cache.dir = tmp_path
    monkeypatch.setattr(tax_sogou, "_cache", cache)
    snippet = "增值税政策解读摘要完整保留。" * 30
    assert len(snippet) > 200
    urls = [f"https://chinatax.gov.cn/interpretation-{i}.html" for i in range(12)]
    html = "<html><body>" + "".join(
        f'<div class="vrResult"><h3><a class="resultLink" '
        f'href="https://m.sogou.com/web?url={quote(url, safe="")}">'
        f'增值税政策<em>解读</em>{i}</a></h3>'
        '<div class="citeurl"><span>chinatax.gov.cn</span> '
        '<span class="date">1995-01-27</span></div>'
        f'<div class="txt-summary">{snippet}</div></div>'
        for i, url in enumerate(urls)
    ) + "</body></html>"
    calls = []

    def fake_fetch(query):
        calls.append(query)
        return html, "https://m.sogou.com/web", "", False

    monkeypatch.setattr(tax_sogou, "_fetch", fake_fetch)
    for size, count, from_cache in ((1, 1, False), (5, 5, True), (100, 12, True)):
        result = tax_doc.sogou_search("增值税政策解读", site="chinatax.gov.cn", size=size)
        assert not result.get("_error"), result
        assert len(result["results"]) == count
        assert result["_from_cache"] is from_cache
        assert [item["url"] for item in result["results"]] == urls[:count]
        for i, item in enumerate(result["results"]):
            assert item["title"] == f"增值税政策解读{i}"
            assert item["snippet"] == snippet
            assert item["date"] == "1995-01-27"
    assert calls == ["site:chinatax.gov.cn 增值税政策解读"]
    assert cache.stats()["entries"] == 1


def test_interpretations_cache_expiry_and_retry_boundaries_offline(monkeypatch, tmp_path):
    import threading
    import time
    from unittest.mock import patch

    tax_doc = engine.tax_service.tax_doc
    tax_sogou = sys.modules[tax_doc.sogou_search.__module__]
    cache = sys.modules["tax_cache"].CacheManager(enabled=True, namespace="sogou")
    cache.dir = tmp_path
    monkeypatch.setattr(tax_sogou, "_cache", cache)
    clock = [time.time()]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    calls = []
    caller = threading.get_ident()

    def fetch(query):
        assert threading.get_ident() == caller
        calls.append(query)
        html = ('<div class=vrResult><h3><a class=resultLink '
                'href="/tc?url=https%3A%2F%2Fchinatax.gov.cn%2Farticle.html">'
                f'增值税法官方解读第{len(calls)}版</a></h3></div>')
        return html, "", "", False

    with patch.object(tax_sogou, "_fetch", fetch):
        first = tax_doc.search_interpretations("过期验证", sources=["chinatax.gov.cn"])
        clock[0] += tax_sogou.CACHE_TTL - 1
        cached = tax_doc.search_interpretations("过期验证", sources=["chinatax.gov.cn"])
        assert len(calls) == 1 and first["sources"] == cached["sources"]
        clock[0] += 2
        refreshed = tax_doc.search_interpretations("过期验证", sources=["chinatax.gov.cn"])
        assert len(calls) == 2
        assert refreshed["sources"][0]["title"] == "增值税法官方解读第2版"

    for status, count in ((400, 1), (404, 1), (503, 2)):
        response = type("R", (), {"status_code": status, "url": "",
                                 "headers": {}, "content": b""})()
        with patch.object(tax_sogou, "_get", return_value=response) as hit, \
                patch.object(time, "sleep") as wait:
            _, _, error, blocked = tax_sogou._fetch("离线验证")
        assert hit.call_count == count and wait.call_count == count - 1
        assert f"HTTP {status}" in error and not blocked


def test_interpretations_partial_failure_and_missing_date_offline(monkeypatch):
    tax_doc = engine.tax_service.tax_doc
    calls = []
    success = {"title": "增值税政策官方解读", "url": "https://chinatax.gov.cn/interpretation"}
    returned_error = "合成反爬拦截"
    raised_reason = "合成上游异常"

    def fake_source(site, query, n):
        calls.append((site, query, n))
        if site == "chinatax.gov.cn":
            return [success], ""
        if site == "mof.gov.cn":
            return [], returned_error
        assert site == "www.gov.cn"
        raise RuntimeError(raised_reason)

    with monkeypatch.context() as patch:
        patch.setattr(tax_doc, "_search_one_source", fake_source)
        for _ in range(2):
            result = tax_doc.search_interpretations("增值税法")
            assert result["queries_blocked"] == "2/3"
            assert returned_error in result["engine_error"]
            assert raised_reason in result["engine_error"]
            assert "RuntimeError" in result["engine_error"]
            assert result["sources"] == [success]
            assert result["total"] == 1
    expected = [
        ("chinatax.gov.cn", "增值税法 解读", 100),
        ("mof.gov.cn", "增值税法 政策解读", 100),
        ("www.gov.cn", "增值税法 政策解读", 100),
    ]
    assert sorted(calls) == sorted(expected * 2)

    url = "https://chinatax.gov.cn/20240101/interpretation.html"

    def fake_sogou(query, *, site, size):
        assert (query, site, size) == ("增值税法 解读", "chinatax.gov.cn", 100)
        return {"results": [{"title": "增值税政策官方解读", "url": url,
                             "date": "", "snippet": "合成摘要"}]}

    monkeypatch.setattr(tax_doc, "sogou_search", fake_sogou)
    items, error = tax_doc._search_one_source("chinatax.gov.cn", "增值税法 解读", 100)
    assert error == ""
    assert len(items) == 1
    assert items[0]["url"] == url
    assert items[0]["date"] == ""


def test_vendored_copies_match_fingerprint():
    """三个项目各带一份副本，指纹相同才算同一份。

    改动任一处都要同步另外两个项目；先在这里报红，而不是等到某个适配器
    的行为跟别人不一样。
    """
    import hashlib

    pins = {
        "tax_service": "adf63b15c32df4637d6fe730835e1eb4524e28afe8484c95111557d33a531b42",
        "tax_doc": "01f66bf24739285cf42cc72a2d7ec0cdff9f89e29e896db38365ae9e3176738f",
    }
    got = {
        "tax_service": hashlib.sha256(
            Path(engine.tax_service.__file__).read_bytes()).hexdigest(),
        "tax_doc": hashlib.sha256(
            Path(engine.tax_service.tax_doc.__file__).read_bytes()).hexdigest(),
    }
    assert got == pins, got
