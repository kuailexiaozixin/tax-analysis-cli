# tax-analysis-cli

税务问题分析引擎的命令行项目。项目自带引擎的运行时快照（取数脚本、判据
注册表与输出模板），不读取外部引擎目录；整个目录拷到哪里都能单独运行。

## 依赖与定位

- Python ≥ 3.10；已验证 Python 3.13.14、Typer 0.27.2。
- 运行时依赖 `requests`、`urllib3`、`playwright`（`playwright` 只在税屋
  WAF 挑战那条路用，浏览器本体取本机已装的 Edge/Chrome/Firefox）。
- 运行时不查环境变量、不找同级目录：`engine.ENGINE_ROOT` 固定指向包内的
  `runtime/`。

```bash
cd tax-analysis-cli
PYTHONPATH=src python -m tax_engine_cli --help
```

安装成命令行（可选）：

```bash
python -m pip install -e .
tax-analysis --help
```

## 运行时快照与独立性

- 本包 `src/tax_engine_cli/runtime/` 是引擎的只读快照：24 个取数与判据脚本、
  7 个判据注册表、2 份输出模板与风险框架。引导层只把这一个目录放进
  `sys.path`，不 import 任何外部引擎包。
- `runtime/MANIFEST.json` 记录快照对应的引擎版本与每个文件的 SHA-256；
  `tests/test_cli.py::test_runtime_snapshot_matches_manifest` 逐文件核对，
  缺文件或改一个字节都会报红。
- 本项目另带两份实现：`tax_service.py`（服务契约层：参数边界、错误码、
  结果形状）与 `tax_doc.py`（正文下载解析、官方解读检索）。CLI、API、MCP
  各带一份，三份要求逐字节相同，由
  `tests/test_cli.py::test_vendored_copies_match_fingerprint` 用 SHA-256 钉住。
- 与引擎仓库没有运行时依赖：引擎升级后，本项目的行为不变，直到快照被重新
  同步并更新清单。`test_no_external_engine_lookup` 禁止代码回退到环境变量
  或同级目录查找。

## 命令面

| 主线 | 命令 | 说明 |
|---|---|---|
| — | `health` | 离线健康检查 |
| — | `tax-types` | 33 个税种/专题词表 |
| ① | `classify` | 判型、前提缺口、探针 |
| ② | `coverage` | 依据覆盖率；`--evidence` 不传是「没检」，传 `[]` 是「检了没有」 |
| ③④ | `search` | 六源聚合；只有 `--source npc` 单源支持 `--page` |
| ⑧ | `law info` / `law text` / `law interpretations` | 元数据、正文、官方解读 |
| ⑥ | `analyze plan` / `gather` / `answer` | 计划、取数定级、结构化底稿 |
| — | `calc list` / `calc run` | 参数化算式 |
| — | `cases` | 类案台账 |
| — | `check ledger\|inspect\|intake\|reconcile\|control` | 账套巡检、稽查模拟、合同受理与对账、内控生成 |
| — | `templates list\|show` | 输出模板 |

所有命令支持 `--json` 输出完整结构化结果。复杂命令的人读形态直接复用引擎
已有的 `render()`，不在适配器里重写一套口径。

示例：

```bash
PYTHONPATH=src python -m tax_engine_cli classify "研发费用加计扣除比例是多少"
PYTHONPATH=src python -m tax_engine_cli search "增值税" --source npc --size 5
PYTHONPATH=src python -m tax_engine_cli calc run 从价计征 \
  --params '{"计税依据": 100, "税率": 0.05}'
PYTHONPATH=src python -m tax_engine_cli analyze answer "研发费用加计扣除比例是多少" \
  --no-body --no-check-citations
```

`--evidence`、`--params`、`--diagnosis` 一类 JSON 参数既接受内联 JSON，也接受
`@文件路径`；`check` 的账套/合同参数直接收文件路径。

## 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 适配器内部错误 |
| 2 | 参数不合法、缺参数、多源翻页等请求错误 |
| 3 | 法规或模板不存在 |
| 4 | 上游取数失败 |

错误默认写 stderr；加 `--json` 时输出
`{"error":{"code","message","details"}}`，与 API/MCP 的语义一致。

## 测试

```bash
PYTHONPATH=src python -m pytest -q
```

用例只用离线路径或 monkeypatch 替换服务函数，不联网、不调用付费模型。

## 边界

- 不提供付费模型解读（引擎的 `/api/ai-interpret` 那条路没有暴露）。
- `analyze`、`search`、`law`、`cases` 会访问外部站点；失败会按错误码返回，
  不会把「取数失败」打印成「0 条」。
- 多源聚合没有页码维度，`--page > 1` 直接报错；需要翻页请限定 `--source npc`。
- CLI 是单进程同步工具，不负责并发与重试；重试策略仍归引擎取数层。
