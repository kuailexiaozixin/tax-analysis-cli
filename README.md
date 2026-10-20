# tax-analysis-cli

`tax-analysis-engine` 的命令行项目。与引擎仓库分开存放，通过 `TAX_ENGINE_ROOT`
或同级目录约定找到引擎的 `scripts/`，不复制任何税收判据。

## 依赖与定位

- Python ≥ 3.10；本机实测 Python 3.13.14、Typer 0.27.2。
- 默认查找顺序：环境变量 `TAX_ENGINE_ROOT` → 本项目及当前目录的祖先与同级
  `tax-analysis-engine`。
- 引擎自身的依赖：`requests`、`urllib3`（本项目的 `pyproject.toml` 已声明）。

```bash
unset PYTHONHOME
PY="D:/Python/cpython-3.13.14-windows-x86_64-none/python.exe"
cd tax-analysis-cli
PYTHONPATH=src "$PY" -m tax_engine_cli --help
```

安装成命令行（可选）：

```bash
"$PY" -m pip install -e .
tax-analysis --help
```

## 与引擎的边界

- 税收判据只有一份，在引擎里：税种词表、时效判定、算式骨架、输出模板、
  各源取数脚本。本项目按 `TAX_ENGINE_ROOT` 或同级目录约定找到引擎 `scripts/`
  之后 import，不复制这些判据。
- 本项目自带两份副本：`tax_service.py`（服务契约层：参数边界、错误码、
  结果形状）与 `tax_doc.py`（正文下载解析、官方解读检索）。引擎仓库里没有
  这两个文件；CLI、API、MCP 各带一份，三份要求逐字节相同，由
  `tests/test_cli.py::test_vendored_copies_match_fingerprint` 用 SHA-256 钉住。
- 副本不知道引擎在哪：引导层定位到引擎根后调用
  `tax_service.configure(ENGINE_ROOT)` 注入，副本不再用 `__file__` 猜路径。
- 对引擎目录只读：引导层设 `sys.dont_write_bytecode = True`，import 引擎脚本
  不会往引擎的 `scripts/__pycache__` 落 .pyc。

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
PYTHONPATH=src "$PY" -m tax_engine_cli classify "研发费用加计扣除比例是多少"
PYTHONPATH=src "$PY" -m tax_engine_cli search "增值税" --source npc --size 5
PYTHONPATH=src "$PY" -m tax_engine_cli calc run 从价计征 \
  --params '{"计税依据": 100, "税率": 0.05}'
PYTHONPATH=src "$PY" -m tax_engine_cli analyze answer "研发费用加计扣除比例是多少" \
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
PYTHONPATH=src "$PY" -m pytest -q
```

用例只用离线路径或 monkeypatch 替换服务函数，不联网、不调用付费模型。

## 边界

- 不提供付费模型解读（引擎的 `/api/ai-interpret` 那条路没有暴露）。
- `analyze`、`search`、`law`、`cases` 会访问外部站点；失败会按错误码返回，
  不会把「取数失败」打印成「0 条」。
- 多源聚合没有页码维度，`--page > 1` 直接报错；需要翻页请限定 `--source npc`。
- CLI 是单进程同步工具，不负责并发与重试；重试策略仍归引擎取数层。
