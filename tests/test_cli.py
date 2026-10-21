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
    runtime = engine.ENGINE_ROOT
    manifest = json.loads((runtime / "MANIFEST.json").read_text(encoding="utf-8"))
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


def test_vendored_copies_match_fingerprint():
    """三个项目各带一份副本，指纹相同才算同一份。

    改动任一处都要同步另外两个项目；先在这里报红，而不是等到某个适配器
    的行为跟别人不一样。
    """
    import hashlib

    pins = {
        "tax_service": "aa156a7db79d44a706c4fba9561b27ba7e71fedcfadd717976b54bdf5cb0fde9",
        "tax_doc": "4ae92d52346fddb1b660b85836a7d8d7cadde5961025369535d262519cff35a0",
    }
    got = {
        "tax_service": hashlib.sha256(
            Path(engine.tax_service.__file__).read_bytes()).hexdigest(),
        "tax_doc": hashlib.sha256(
            Path(engine.tax_service.tax_doc.__file__).read_bytes()).hexdigest(),
    }
    assert got == pins, got
