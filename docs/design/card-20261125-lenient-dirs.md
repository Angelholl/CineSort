# 卡 DIR-01：目录存在性校验宽容降级——修「无效配置下库增删无法落盘」死锁

## 一、根因

config.toml 的 `source_root` 指向不存在目录（实机遗留旧模板 `G:\Media\_incoming`）时，
`load_config` 在 `_require_dir`（app/core/config.py:126-128，调用点 :266-272）硬抛
`ConfigError`；而 `save_config_dict`（:429-438）落盘前用 `load_config` 校验候选文件，
失败即 `os.replace` 永不执行 → 配置页任何编辑（含删库）都写不进磁盘，重载后行复原，
形成鸡生蛋死锁（横幅要求「保存前先修正 source_root」，但保存本身被 source_root 拦）。
历史修复 D-20261112-02 只宽容化了悬空别名条目，路径存在性是另一条未修路径。

## 二、改动文件

- `app/core/config.py`（Modify：`_require_dir` 及其在 load 路径的调用点）
- `tests/test_config.py`（Test：先红后绿，新增 + 原地改写语义变更例）

## 三、改法

与 D-20261112-02 悬空别名宽容降级同一模式（结构错误仍硬拦、事实性错误降 warnings）：

1. load 路径中 `_require_dir`（source_root / fallback_path / 各库目录的存在性检查）
   由抛 `ConfigError` 改为向 `Config.warnings` 追加一条中文告警
   （形如 `"source_root 不存在或不是目录：{path}"`），不再中断加载；
   缺键/类型错/重复库名等**结构性错误保持硬拦不动**。
2. `config_hash` 不含 warnings（同悬空别名先例，计划页不误报漂移）。
3. 首跑生成 `ensure_first_run_config` 与 `config.example.toml` 自洽性不受影响
   （它们本来指向存在的目录）。
4. GUI 零改动：配置页警告横幅橙色分支、`load_config` 的 warnings 透出链路
   已由 D-20261112-02 建好（三分支 error > 橙警告 > 隐藏），本卡只增 warning 来源。
   验收时以测试钉「warnings 非空且文案含路径」即可，不改 config_tab。
5. 测试（先红后绿）：
   - source_root 指向不存在目录 → `load_config` 成功返回、warnings 含该路径文案；
   - 含不存在目录的配置删库后 `save_config_dict` 落盘成功（死锁解除的直钉）；
   - 原地改写既有「硬抛错」断言例（如有）为 warnings 语义（基线只增不减，
     改写例须在提交信息列明）；
   - 重复库名仍抛 `ConfigError`（结构性硬拦不松动的护栏钉）。

## 四、验收命令（以下命令均在项目根目录执行）

```bash
python -m ruff check app/core/config.py tests/test_config.py
python -m pytest tests/test_config.py -q
python -m pytest tests/test_config_tab.py -q     # GUI 链回归
python -m pytest -q                              # 全量，当前基线 352 passed
python -m pytest tests/test_entry.py -q          # 首跑自洽回归
```

## 约束

- 运行时下游（scanner/preflight/jobs）零改动；warnings 不进 config_hash。
- 不改 config_tab/state；不动 example 与 ensure_first_run_config 的生成逻辑。
- 卡面自足；执行中读取大于 4KB 的文件或查看改动，用
  `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的
  pointerize/read_pointer/read_diff_only，禁止整读文件全文。
- 执行者只 commit 不 push；卡外问题即停待裁决。

## 验收补记（2026-11-25 主审）
- 执行改写例涉及 tests/test_flow.py::test_config_save_validate_and_reject 后半段
  （卡面改动文件清单未列该文件），依据即卡面第三节第 5 条「原地改写既有硬抛错
  断言例」授权，验收认定在范围内。
- 执行者实测补充：「至少需要定义一个 [[library]]」为结构性硬拦（卡外规则未动），
  死锁直钉例改为删悬空库、保留合法库，落盘断言等价。
- 主审复核：全量 354 passed（基线 352 +2）、ruff 全仓 0 项；实机死锁场景冒烟
  （source_root/fallback/库路径全不存在）加载不抛错、warnings 三条齐。
