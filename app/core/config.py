"""配置加载、数据模型与校验。

校验规则（决策 D-20261031-03 / 评议条件 C4）：
- source_root、所有库根、兜底库必须是真实存在的目录；
- 库根两两互异、互不嵌套；库根目录名不得为 .nfo-sorter-staging；
- source_root 与任何库根/兜底库互不重叠（双向）；
- staging_dir（若配置）不得位于 source_root 或任何库根内部；
- genre_priority / genre_aliases 引用的库名必须存在。
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import tomllib

STRATEGIES = ("smart", "priority", "genre_only")
CONFLICT_MODES = ("skip", "rename")
STAGING_NAME = ".nfo-sorter-staging"


class ConfigError(ValueError):
    """配置非法。"""


def normcase(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def is_sub_path(child: Path | str, parent: Path | str) -> bool:
    """child 是否等于或位于 parent 之内（Windows 大小写不敏感）。"""
    c, p = normcase(child), normcase(parent)
    if c == p:
        return True
    return c.startswith(p.rstrip("\\/") + os.sep)


@dataclass
class Library:
    name: str
    path: Path
    keywords: list[str] = field(default_factory=list)
    keywords_weighted: dict[str, float] = field(default_factory=dict)

    def describe(self) -> dict:
        return {
            "name": self.name,
            "path": str(self.path),
            "keywords": list(self.keywords),
            "keywords_weighted": dict(self.keywords_weighted),
        }


@dataclass
class PlotOptions:
    enabled: bool = True
    min_score: float = 2.0
    normalize: bool = False


@dataclass
class TitleOptions:
    """标题文本弱评分（特性 D）：独立阈值，不复用 plot.min_score。"""
    enabled: bool = True
    min_score: float = 1.0


@dataclass
class LearningOptions:
    """自学习（D-20261101-03）：改判/确认结果沉淀为题材→库映射。"""
    enabled: bool = True
    min_votes: int = 2


@dataclass
class Config:
    path: Path                       # config.toml 自身路径
    source_root: Path
    libraries: dict[str, Library]    # name -> Library，保持声明顺序
    genre_priority: list[str]
    genre_aliases: dict[str, str]
    fallback_path: Path
    strategy: str = "smart"
    on_conflict: str = "skip"
    plot: PlotOptions = field(default_factory=PlotOptions)
    title: TitleOptions = field(default_factory=TitleOptions)
    learning: LearningOptions = field(default_factory=LearningOptions)
    staging_dir: Path | None = None
    warn_fallback_ratio: float = 0.15
    block_fallback_ratio: float = 0.30
    weak_genre_aliases: dict[str, str] = field(default_factory=dict)

    @property
    def runtime_dir(self) -> Path:
        return self.path.parent / "runtime"

    def library_paths(self) -> list[Path]:
        return [lib.path for lib in self.libraries.values()] + [self.fallback_path]

    def config_hash(self) -> str:
        payload = {
            "source_root": normcase(self.source_root),
            "libraries": [(n, normcase(lib.path)) for n, lib in self.libraries.items()],
            "genre_priority": list(self.genre_priority),
            "genre_aliases": dict(sorted(self.genre_aliases.items())),
            "weak_genre_aliases": dict(sorted(self.weak_genre_aliases.items())),
            "fallback_path": normcase(self.fallback_path),
            "strategy": self.strategy,
            "on_conflict": self.on_conflict,
            "title": {"enabled": self.title.enabled,
                      "min_score": self.title.min_score},
            "plot": {"enabled": self.plot.enabled,
                     "min_score": self.plot.min_score,
                     "normalize": self.plot.normalize},
            "learning": {"enabled": self.learning.enabled,
                         "min_votes": self.learning.min_votes},
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _require_dir(p: Path, what: str) -> None:
    if not p.is_dir():
        raise ConfigError(f"{what}不存在或不是目录：{p}")


def _abs(p: Path | str) -> Path:
    return Path(str(p).strip().strip('"')).expanduser()
    # resolve() 在后续校验时统一做，避免解析到不存在的路径时报错语义混乱


def _check_overlap(a: Path, b: Path, ta: str, tb: str) -> None:
    if a == b:
        raise ConfigError(f"{ta} 与 {tb} 不能是同一个目录：{a}")
    if is_sub_path(a, b):
        raise ConfigError(f"{ta}（{a}）不能位于 {tb}（{b}）内部")
    if is_sub_path(b, a):
        raise ConfigError(f"{tb}（{b}）不能位于 {ta}（{a}）内部")


def check_session_root(output_root: Path | str, cfg: Config) -> str | None:
    """本次输出目录校验（会话级，不进 config.toml）：必须存在，且与
    源根 / 库根 / 兜底库互不嵌套（镜像 _check_overlap 语义）。
    返回错误文案；None = 合法。"""
    p = Path(output_root)
    if not p.is_dir():
        return f"输出目录不存在或不是目录：{p}"
    roots: list[tuple[str, Path]] = [("源目录", cfg.source_root)]
    roots += [(f"媒体库[{name}]", lib.path)
              for name, lib in cfg.libraries.items()]
    roots.append(("兜底库", cfg.fallback_path))
    for name, root in roots:
        if normcase(p) == normcase(root):
            return f"输出目录与{name}不能是同一个目录：{root}"
        if is_sub_path(p, root):
            return f"输出目录（{p}）不能位于{name}（{root}）内部"
        if is_sub_path(root, p):
            return f"{name}（{root}）不能位于输出目录（{p}）内部"
    return None


def load_config(path: Path | str) -> Config:
    cfg_path = Path(path)
    if not cfg_path.is_file():
        raise ConfigError(f"找不到配置文件：{cfg_path}")
    try:
        with open(cfg_path, "rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"config.toml 语法错误：{exc}") from exc

    for key in ("source_root", "fallback_path"):
        if not data.get(key):
            raise ConfigError(f"缺少必填项 {key}")

    strategy = str(data.get("strategy", "smart"))
    if strategy not in STRATEGIES:
        raise ConfigError(f"strategy 只能是 {'/'.join(STRATEGIES)}，当前为 {strategy!r}")
    on_conflict = str(data.get("on_conflict", "skip"))
    if on_conflict not in CONFLICT_MODES:
        raise ConfigError(f"on_conflict 只能是 {'/'.join(CONFLICT_MODES)}，当前为 {on_conflict!r}")

    libraries: dict[str, Library] = {}
    for i, item in enumerate(data.get("library", [])):
        name = str(item.get("name", "")).strip()
        if not name:
            raise ConfigError(f"第 {i + 1} 个 [[library]] 缺少 name")
        if name in libraries:
            raise ConfigError(f"库名重复：{name}")
        if "/" in name or "\\" in name or name == STAGING_NAME:
            raise ConfigError(f"非法库名：{name}")
        lib_path = _abs(item["path"])
        kws = [str(k).strip() for k in item.get("keywords", []) if str(k).strip()]
        kww = {}
        for k, v in (item.get("keywords_weighted") or {}).items():
            kww[str(k).strip()] = float(v)
        libraries[name] = Library(name=name, path=lib_path, keywords=kws, keywords_weighted=kww)
    if not libraries:
        raise ConfigError("至少需要定义一个 [[library]]")

    genre_priority_raw = list(data.get("genre_priority", []))
    genre_priority: list[str] = []
    for name in genre_priority_raw:
        name = str(name).strip()
        if name not in libraries:
            raise ConfigError(f"genre_priority 引用了未定义的库：{name}")
        if name in genre_priority:
            raise ConfigError(f"genre_priority 中库名重复：{name}")
        genre_priority.append(name)

    genre_aliases: dict[str, str] = {}
    for k, v in (data.get("genre_aliases") or {}).items():
        v = str(v).strip()
        if v not in libraries:
            raise ConfigError(f"genre_aliases[{k!r}] 指向未定义的库：{v}")
        genre_aliases[str(k)] = v

    weak_genre_aliases: dict[str, str] = {}
    for k, v in (data.get("weak_genre_aliases") or {}).items():
        v = str(v).strip()
        if v not in libraries:
            raise ConfigError(f"weak_genre_aliases[{k!r}] 指向未定义的库：{v}")
        weak_genre_aliases[str(k)] = v

    plot_data = data.get("plot") or {}
    plot = PlotOptions(
        enabled=bool(plot_data.get("enabled", True)),
        min_score=float(plot_data.get("min_score", 2.0)),
        normalize=bool(plot_data.get("normalize", False)),
    )
    if plot.min_score < 0:
        raise ConfigError("plot.min_score 不能为负数")

    title_data = data.get("title") or {}
    title = TitleOptions(
        enabled=bool(title_data.get("enabled", True)),
        min_score=float(title_data.get("min_score", 1.0)),
    )
    if title.min_score < 0:
        raise ConfigError("title.min_score 不能为负数")

    learning_data = data.get("learning") or {}
    learning = LearningOptions(
        enabled=bool(learning_data.get("enabled", True)),
        min_votes=int(learning_data.get("min_votes", 2)),
    )
    if learning.min_votes < 1:
        raise ConfigError("learning.min_votes 至少为 1")

    warn_ratio = float(data.get("warn_fallback_ratio", 0.15))
    block_ratio = float(data.get("block_fallback_ratio", 0.30))
    if not (0 <= warn_ratio <= block_ratio <= 1):
        raise ConfigError("需满足 0 ≤ warn_fallback_ratio ≤ block_fallback_ratio ≤ 1")

    staging_dir = _abs(data["staging_dir"]) if data.get("staging_dir") else None

    # ---- 路径存在性与重叠校验（C4） ----
    source_root = _abs(data["source_root"]).resolve()
    fallback_path = _abs(data["fallback_path"]).resolve()
    _require_dir(source_root, "source_root")
    _require_dir(fallback_path, "fallback_path")
    for lib in libraries.values():
        lib.path = lib.path.resolve()
        _require_dir(lib.path, f"媒体库[{lib.name}]的 path")

    all_roots = [("source_root", source_root)] + [
        (f"媒体库[{name}]", lib.path) for name, lib in libraries.items()
    ] + [("fallback_path", fallback_path)]
    for i in range(len(all_roots)):
        for j in range(i + 1, len(all_roots)):
            ta, pa = all_roots[i]
            tb, pb = all_roots[j]
            _check_overlap(pa, pb, ta, tb)

    if staging_dir is not None:
        if is_sub_path(staging_dir, source_root):
            raise ConfigError("staging_dir 不能位于 source_root 内部")
        for name, lib in libraries.items():
            if is_sub_path(staging_dir, lib.path):
                raise ConfigError(f"staging_dir 不能位于媒体库[{name}]内部")

    return Config(
        path=cfg_path,
        source_root=source_root,
        libraries=libraries,
        genre_priority=genre_priority,
        genre_aliases=genre_aliases,
        weak_genre_aliases=weak_genre_aliases,
        fallback_path=fallback_path,
        strategy=strategy,
        on_conflict=on_conflict,
        plot=plot,
        title=title,
        learning=learning,
        staging_dir=staging_dir,
        warn_fallback_ratio=warn_ratio,
        block_fallback_ratio=block_ratio,
    )


# ---------------------------------------------------------------- GUI 支撑

def describe(cfg: Config) -> dict:
    return {
        "source_root": str(cfg.source_root),
        "fallback_path": str(cfg.fallback_path),
        "strategy": cfg.strategy,
        "on_conflict": cfg.on_conflict,
        "staging_dir": str(cfg.staging_dir) if cfg.staging_dir else "",
        "warn_fallback_ratio": cfg.warn_fallback_ratio,
        "block_fallback_ratio": cfg.block_fallback_ratio,
        "plot": {
            "enabled": cfg.plot.enabled,
            "min_score": cfg.plot.min_score,
            "normalize": cfg.plot.normalize,
        },
        "title": {
            "enabled": cfg.title.enabled,
            "min_score": cfg.title.min_score,
        },
        "learning": {
            "enabled": cfg.learning.enabled,
            "min_votes": cfg.learning.min_votes,
        },
        "genre_priority": list(cfg.genre_priority),
        "genre_aliases": dict(cfg.genre_aliases),
        "weak_genre_aliases": dict(cfg.weak_genre_aliases),
        "libraries": [lib.describe() for lib in cfg.libraries.values()],
    }


def raw_describe(data: dict) -> dict:
    """把未校验的 toml 字典转成 GUI 可编辑的形状（首跑/配置报错时兜底展示）。"""
    libs = []
    for item in data.get("library", []):
        libs.append({
            "name": str(item.get("name", "")),
            "path": str(item.get("path", "")),
            "keywords": [str(k) for k in item.get("keywords", [])],
            "keywords_weighted": {str(k): float(v) for k, v in (item.get("keywords_weighted") or {}).items()},
        })
    plot_data = data.get("plot") or {}
    title_data = data.get("title") or {}
    learning_data = data.get("learning") or {}
    return {
        "source_root": str(data.get("source_root", "")),
        "fallback_path": str(data.get("fallback_path", "")),
        "strategy": str(data.get("strategy", "smart")),
        "on_conflict": str(data.get("on_conflict", "skip")),
        "staging_dir": str(data.get("staging_dir", "") or ""),
        "warn_fallback_ratio": float(data.get("warn_fallback_ratio", 0.15)),
        "block_fallback_ratio": float(data.get("block_fallback_ratio", 0.30)),
        "plot": {
            "enabled": bool(plot_data.get("enabled", True)),
            "min_score": float(plot_data.get("min_score", 2.0)),
            "normalize": bool(plot_data.get("normalize", False)),
        },
        "title": {
            "enabled": bool(title_data.get("enabled", True)),
            "min_score": float(title_data.get("min_score", 1.0)),
        },
        "learning": {
            "enabled": bool(learning_data.get("enabled", True)),
            "min_votes": int(learning_data.get("min_votes", 2)),
        },
        "genre_priority": [str(x) for x in data.get("genre_priority", [])],
        "genre_aliases": {str(k): str(v) for k, v in (data.get("genre_aliases") or {}).items()},
        "weak_genre_aliases": {str(k): str(v) for k, v in (data.get("weak_genre_aliases") or {}).items()},
        "libraries": libs,
    }


def dump_config_text(d: dict) -> str:
    """把 GUI 编辑后的字典序列化为 TOML 文本。"""
    js = lambda s: json.dumps(str(s), ensure_ascii=False)
    lines: list[str] = ["# 由 GUI 保存的配置（人工修改也可，注意 TOML 语法）", ""]
    lines.append(f"source_root = {js(d['source_root'])}")
    lines.append(f"fallback_path = {js(d['fallback_path'])}")
    lines.append(f"strategy = {js(d.get('strategy', 'smart'))}")
    lines.append(f"on_conflict = {js(d.get('on_conflict', 'skip'))}")
    lines.append(f"warn_fallback_ratio = {float(d.get('warn_fallback_ratio', 0.15))}")
    lines.append(f"block_fallback_ratio = {float(d.get('block_fallback_ratio', 0.30))}")
    if str(d.get("staging_dir", "") or "").strip():
        lines.append(f"staging_dir = {js(d['staging_dir'])}")
    priority = [js(x) for x in d.get("genre_priority", [])]
    lines.append("genre_priority = [" + ", ".join(priority) + "]")
    alias_items = [f"{js(k)} = {js(v)}" for k, v in (d.get("genre_aliases") or {}).items()]
    lines.append("genre_aliases = { " + ", ".join(alias_items) + " }")
    weak_items = [f"{js(k)} = {js(v)}" for k, v in (d.get("weak_genre_aliases") or {}).items()]
    lines.append("weak_genre_aliases = { " + ", ".join(weak_items) + " }")
    lines.append("")
    plot = d.get("plot") or {}
    lines.append("[plot]")
    lines.append(f"enabled = {'true' if plot.get('enabled', True) else 'false'}")
    lines.append(f"min_score = {float(plot.get('min_score', 2.0))}")
    lines.append(f"normalize = {'true' if plot.get('normalize', False) else 'false'}")
    title = d.get("title") or {}
    lines.append("")
    lines.append("[title]")
    lines.append(f"enabled = {'true' if title.get('enabled', True) else 'false'}")
    lines.append(f"min_score = {float(title.get('min_score', 1.0))}")
    learning = d.get("learning") or {}
    lines.append("")
    lines.append("[learning]")
    lines.append(f"enabled = {'true' if learning.get('enabled', True) else 'false'}")
    lines.append(f"min_votes = {max(int(learning.get('min_votes', 2)), 1)}")
    for lib in d.get("libraries", []):
        lines.append("")
        lines.append("[[library]]")
        lines.append(f"name = {js(lib['name'])}")
        lines.append(f"path = {js(lib['path'])}")
        kws = ", ".join(js(k) for k in lib.get("keywords", []))
        lines.append(f"keywords = [{kws}]")
        kww = ", ".join(f"{js(k)} = {float(v)}" for k, v in (lib.get("keywords_weighted") or {}).items())
        lines.append(f"keywords_weighted = {{ {kww} }}")
    return "\n".join(lines) + "\n"


def save_config_dict(cfg_path: Path, d: dict) -> Config:
    """校验并原子保存 GUI 提交的配置；失败时抛 ConfigError，原文件不受影响。"""
    runtime = cfg_path.parent / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    candidate = runtime / "config.candidate.toml"
    candidate.write_text(dump_config_text(d), encoding="utf-8")
    new_cfg = load_config(candidate)          # 校验失败在此抛出
    new_cfg.path = cfg_path
    os.replace(candidate, cfg_path)           # 校验通过才替换
    return new_cfg
