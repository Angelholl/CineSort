# 卡 LIB-01：添加库时库名同步预填为关键词

## 一、根因/需求

新用户添加库时（config_tab.py:408-412 `_add_library`），库名已自动填文件夹名
（`Path(chosen).name`），但关键词列留空——摘要预判对无关键词的库不参与
（config_tab.py:180 tooltip 明示），新手漏配导致摘要预判失效。owner 拍板：
库名同步预填为关键词（加权词仍留空）。

## 二、改动文件

- `app/ui/config_tab.py`（Modify：:412 一行）
- `tests/test_config_tab.py`（Test：追加回归）

## 三、改法

1. config_tab.py:412 `self._add_library_row([Path(chosen).name, str(chosen), "", ""])`
   改为 `self._add_library_row([Path(chosen).name, str(chosen), Path(chosen).name, ""])`
   （关键词列 = 库名；加权词仍空）。
2. `tests/test_config_tab.py` 追加回归：monkeypatch `QFileDialog.getExistingDirectory`
   返回临时目录路径，触发 `btn_add.click()`，断言新行四列
   `[文件夹名, 路径, 文件夹名, ""]`。先红后绿。
3. 添加库按钮 tooltip（如有）与 :180-181 tooltip 文案不动；用户仍可手动清空关键词。

## 四、验收命令（以下命令均在项目根目录执行）

```bash
python -m ruff check app/ui/config_tab.py tests/test_config_tab.py
python -m pytest tests/test_config_tab.py -q
python -m pytest -q                              # 全量，基线只增不减（以开工时 git log 基线为准）
```

## 约束

- 前置：卡 DIR-01（card-20261125-lenient-dirs.md）已合入后才可开工，开工前以
  `git log --oneline -1` 重核基线与 :412 行号。
- 只动 _add_library 的预填值一行；不改 load/save 校验与其它列语义。
- 卡面自足；执行中读取大于 4KB 的文件或查看改动，用
  `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的
  pointerize/read_pointer/read_diff_only，禁止整读文件全文。
- 执行者只 commit 不 push；卡外问题即停待裁决。
