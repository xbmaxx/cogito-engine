# KnowledgeBridge 多 Provider 架构设计

> 状态：设计阶段
> 版本：v1.7.0 (计划)
> 关联：`cogito_core/fact_store_provider.py`、`cogito_core/knowledge_base.py`、`adapters/hermes_adapter.py`、`install.py`

---

## 一、问题诊断

### 1.1 FactStoreProvider 写死了 Holographic

```python
# fact_store_provider.py:36 — 当前代码
from plugins.memory.holographic import HologographicMemoryProvider
```

**问题**：`fact_store` 是 Hermes 对所有记忆后端的统一工具名，不是 Holographic 专属。用户用 Hindsight / Holographic-plus / 自定义记忆库时，FactStoreProvider 会因为找不到 Holographic 而返回 `available=False`。

**正确语义**：`fact_store` = Hermes 层的记忆工具抽象。任何已注册的记忆库（Holographic、Holographic-plus、Hindsight、Mem0 等）都通过同一个 `fact_store` 工具名暴露给 agent。Provider 不应绑定具体插件，应查询「fact_store 这个工具是否存在」。

### 1.2 hermes_adapter.py 只接了一个 Provider

```python
# hermes_adapter.py:362 — 当前代码
engine.set_knowledge_provider(
    KnowledgeBaseProvider(db_path=os.path.expanduser("~/.hermes/memory_store.db"))
)
```

只创建了 `KnowledgeBaseProvider`，从未实例化 `FactStoreProvider`。`FactStoreProvider._lazy_init()` 里的探针代码是死代码。

### 1.3 无 fallback 链

单 Provider 失败 = KnowledgeBridge 整条链路静默失效。用户升级后「外部知识库检测不到」——不是因为没接，是因为探针根本没触发。

---

## 二、Provider 分类（按存储类型，不按应用名）

不做穷举模式。所有外部知识源本质上只分三种存储形态：

| 存储形态 | Provider | 覆盖的知识源 |
|:--|:--|:--|
| Hermes 工具 | `HermesToolProvider` | Holographic / Hindsight / 自定义记忆插件 / 任何注册的 tool |
| 本地文件 | `FileSystemProvider` | Obsidian vault / Logseq graph / 飞书导出目录 / 任何 markdown 目录 |
| 数据库 | `SQLiteProvider` | knowledge_base.db / 任何有 schema 的 SQLite 库 |

**不按应用名写新的 Provider**——对接 Obsidian 不需要 `ObsidianProvider`，只需：

```python
FileSystemProvider(path="~/Documents/Obsidian Vault", glob="*.md", label="Obsidian")
```

对接 Logseq 同理——同一个 `FileSystemProvider`，换个 path。

---

## 三、KnowledgeScanner — 全量探针

### 3.1 目标

插件启动时**一次性扫描**用户本地所有可接入的知识源，返回列表。不做选择，只做发现。

### 3.2 扫描维度

```python
class KnowledgeScanner:
    """一次性扫描本地所有可接入的知识源。"""

    def scan(self) -> List[KnowledgeSource]:
        sources = []
        sources.extend(self._probe_hermes_tools())   # Hermes 注册的工具
        sources.extend(self._probe_filesystem())      # 本地 markdown 目录
        sources.extend(self._probe_sqlite())          # 本地 SQLite
        return sources
```

#### 维度 1：Hermes 工具

```python
def _probe_hermes_tools(self) -> List[KnowledgeSource]:
    """扫描 Hermes 已注册的工具，匹配记忆/知识类工具。"""
    results = []
    try:
        from hermes_cli.tools import get_registered_tools
        tools = get_registered_tools()
        # fact_store 是 Hermes 记忆系统的统一工具名
        if "fact_store" in tools:
            results.append(KnowledgeSource(
                provider_type="hermes_tool",
                tool_name="fact_store",
                label="Hermes 记忆库",
                description="已注册的 Hermes 记忆插件",
                priority=10,  # Hermes 原生最高优先级
            ))
        # 预留：其他 Hermes 知识类工具
        for name in ["rag", "vector_store", "doc_search"]:
            if name in tools:
                results.append(KnowledgeSource(
                    provider_type="hermes_tool",
                    tool_name=name,
                    label=f"Hermes {name}",
                    description=f"已注册的 Hermes {name} 工具",
                    priority=9,
                ))
    except Exception:
        pass
    return results
```

#### 维度 2：本地文件系统

```python
def _probe_filesystem(self) -> List[KnowledgeSource]:
    """扫描常见本地知识库目录。"""
    patterns = [
        # (路径模式, label, glob)
        ("~/Documents/Obsidian Vault",  "Obsidian Vault",  "*.md"),
        ("~/Documents/Logseq",          "Logseq Graph",     "*.md"),
        ("~/Documents/Knowledge Base",  "本地知识库",        "*.md"),
    ]
    results = []
    for pattern, label, glob in patterns:
        path = Path(pattern).expanduser()
        if path.exists() and any(path.glob(glob)):
            results.append(KnowledgeSource(
                provider_type="filesystem",
                path=str(path),
                glob=glob,
                label=label,
                description=f"{label}（{path}）",
                priority=5,
            ))
    return results
```

#### 维度 3：本地 SQLite

```python
def _probe_sqlite(self) -> List[KnowledgeSource]:
    """扫描含 facts 表或嵌入向量的 SQLite 库。"""
    patterns = [
        ("~/.hermes/memory/knowledge_base.db", "本地知识库"),
        ("~/.hermes/memory/memory_store.db",   "Hermes 记忆存储"),
    ]
    results = []
    for pattern, label in patterns:
        path = Path(pattern).expanduser()
        if path.exists() and path.stat().st_size > 0:
            # 检查是否有 facts 表
            try:
                import sqlite3
                conn = sqlite3.connect(str(path))
                tables = [r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()]
                conn.close()
                if "facts" in tables:
                    results.append(KnowledgeSource(
                        provider_type="sqlite",
                        path=str(path),
                        label=label,
                        description=f"{label}（{path}，含 facts 表）",
                        priority=3,
                    ))
            except Exception:
                pass
    return results
```

---

## 四、决策引擎 — 用户选择权

### 4.1 规则

```
扫描完成 → List[KnowledgeSource] (按 priority 降序)
│
├─ 0 个源 → 静默降级，KnowledgeBridge 不激活
│
├─ 1 个源 → 自动接入，XML 注入中显示来源名
│
└─ 2+ 个源 → ❌ 不替用户做决定
    └─ 输出提示：「检测到以下外部知识库，您想接入哪一个？」
        │
        ├─ 1. Hermes 记忆库（已注册的 Hermes 记忆插件）
        ├─ 2. Obsidian Vault（~/Documents/Obsidian Vault）
        └─ 3. 本地知识库（~/.hermes/memory/knowledge_base.db）
        
        用户选择 → 设置 active source
```

### 4.2 输出格式

```python
class KnowledgeSource:
    provider_type: str      # "hermes_tool" | "filesystem" | "sqlite"
    label: str              # 中文名："Hermes 记忆库"
    description: str        # 完整描述
    path: str = ""          # 文件系统路径（filesystem/sqlite 用）
    tool_name: str = ""     # Hermes 工具名（hermes_tool 用）
    glob: str = ""          # 文件过滤模式
    priority: int = 0       # 排序优先级
```

### 4.3 运行时切换

用户可通过对话随时切换知识源：

```
用户：「把我的知识库切换到 Obsidian」
引擎：读取 active source 配置 → 重新创建对应 Provider → set_knowledge_provider()
```

切换逻辑在 `MultiProvider` 中新增 `set_active(source)` 方法，不重启网关即可生效。

---

## 五、目标架构（更新）

```
网关启动
│
├─ KnowledgeScanner.scan()
│   ├─ HermesToolDetector   → fact_store / rag / ...
│   ├─ FileSystemDetector   → Obsidian / Logseq / ...
│   └─ SQLiteDetector       → knowledge_base.db / ...
│
├─ Decision Engine
│   ├─ 0 源 → 静默
│   ├─ 1 源 → 自动接入
│   └─ 2+ 源 → 提示「检测到 N 个知识库，选一个？」→ 等待用户
│
├─ MultiProvider.set_active(source)
│   └─ 根据 source.provider_type 创建对应的 Provider 实例
│
└─ engine.set_knowledge_provider(multi)

---

## 三、FactStoreProvider 改造

### 3.1 当前（❌）

```python
def _lazy_init(self):
    # 写死 — 只认 Holographic
    from plugins.memory.holographic import HolographicMemoryProvider
    from hermes_cli.plugins import get_plugin_manager
    pm = get_plugin_manager()
    self._memory = pm.memory_provider or HolographicMemoryProvider()
```

### 3.2 目标（✅）

```python
def __init__(self, ctx=None):
    self._ctx = ctx          # Hermes 插件上下文，通过它查 tool 注册表
    self._memory = None
    self._probed = False

def _lazy_init(self):
    """探测 Hermes fact_store 工具是否存在（不绑定具体插件）。"""
    if self._probed:
        return
    self._probed = True

    # 方式 1：通过 ctx 查询已注册工具
    if self._ctx and hasattr(self._ctx, "tools") and "fact_store" in self._ctx.tools:
        self._memory = self._ctx.tools["fact_store"]
        return

    # 方式 2：通过 Hermes 全局工具注册表
    try:
        from hermes_cli.tools import get_registered_tools
        tools = get_registered_tools()
        if "fact_store" in tools:
            self._memory = tools["fact_store"]
            return
    except Exception:
        pass

    # 方式 3：如果 Hermes 运行时可调用 fact_store 工具
    # （预留：某些 Hermes 版本的工具接口不同）
    self._init_error = "fact_store tool not registered"
```

**关键变化**：
- 不再 `import HolographicMemoryProvider`
- 改为查询 Hermes 工具注册表：`"fact_store"` 这个工具名是否存在
- 只要 Hermes 注册了 memory provider（不管是 Holographic / Hindsight / 自定义），该工具名就是 `"fact_store"`
- 如果 ctx 不传（兼容旧调用），静默降级

### 3.3 search() 调用方式

```python
def search(self, query: str, limit: int = 3) -> List[str]:
    self._lazy_init()
    if self._memory is None:
        return []

    # 通过 Hermes 统一 tool 接口调用（而非直接调 Holographic API）
    try:
        results = self._memory.search(query, limit=limit)
        return [r.get("content", str(r)) for r in results[:limit]]
    except Exception:
        return []
```

---

## 四、MultiProvider 聚合器

新建 `cogito_core/multi_provider.py`：

```python
from .knowledge_provider import KnowledgeProvider
from typing import List

class MultiProvider(KnowledgeProvider):
    """多 Provider 聚合器 — 按注册顺序 fallback。
    
    第一个 available()=True 的 Provider 被激活；
    后续 Provider 不再使用（直到激活的 Provider 变为不可用）。
    """

    def __init__(self, providers: List[KnowledgeProvider]):
        self._providers = providers
        self._active: KnowledgeProvider = None

    def _ensure_active(self):
        if self._active and self._active.available():
            return
        for p in self._providers:
            if p.available():
                self._active = p
                return
        self._active = None

    def search(self, query: str, limit: int = 3) -> List[str]:
        self._ensure_active()
        if self._active is None:
            return []
        return self._active.search(query, limit)

    def name(self) -> str:
        self._ensure_active()
        return self._active.name() if self._active else "none"

    def available(self) -> bool:
        self._ensure_active()
        return self._active is not None
```

---

## 五、hermes_adapter.py 对接

```python
# 替换当前单 Provider 创建

from cogito_core.fact_store_provider import FactStoreProvider
from cogito_core.knowledge_base import KnowledgeBaseProvider
from cogito_core.multi_provider import MultiProvider

# 在 register() 中：
multi = MultiProvider([
    FactStoreProvider(ctx=ctx),                      # ① Hermes native
    KnowledgeBaseProvider(
        db_path=os.path.expanduser("~/.hermes/memory/knowledge_base.db")
    ),                                               # ② 本地 fallback
])
engine.set_knowledge_provider(multi)
```

---

## 六、install.py 引导

`install.py --update` 或首次安装后，检测外部记忆库并与用户交互：

```
检测到 Hermes fact_store 工具已注册:
  ✓ 自动对接成功，无需额外配置

未检测到 fact_store 工具:
  → 提示: 「已安装外部知识库接口。如果你使用了 Holographic / Hindsight 等
    记忆插件，引擎会自动探测并接入。当前未检测到已注册的记忆库。」
  → 不阻塞安装，静默降级
```

实现方式：`install.py` 新增一个 `_probe_fact_store()` 函数，尝试导入 Hermes 插件管理器查询 `fact_store` 工具。

---

## 七、P1 和 P4 补丁

### P1: jieba 安装到 Hermes venv

`install.py` 在 bootstrap 之后追加：

```python
def _install_jieba_to_hermes_venv():
    """确保 jieba 安装到 Hermes 网关使用的 venv 中。"""
    venv_pip = Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "pip"
    if venv_pip.exists():
        subprocess.run([str(venv_pip), "install", "jieba"], check=False)
```

### P4: 旧数据迁移

`install.py --update` 检测 `~/.cogito/*.jsonl` 是否存在，如果对应文件在 `~/.hermes/memory/` 下**不存在或为空**，迁移过去（不覆盖已有数据）：

```python
def _migrate_legacy_data():
    old = Path.home() / ".cogito"
    new = Path.home() / ".hermes" / "memory"
    if not old.exists():
        return
    for f in old.glob("*.jsonl"):
        target = new / f.name
        if not target.exists() or target.stat().st_size == 0:
            shutil.copy2(f, target)
```

---

## 八、兼容性

| 场景 | 行为 |
|:--|:--|
| Hermes 有 fact_store 工具（任意后端） | ① 自动对接，用户无感 |
| Hermes 无记忆插件 | ① 降级 → ② 尝试 knowledge_base.db |
| knowledge_base.db 为空 | ② 降级 → ③ 静默 |
| 老版 Cogito（ctx 不传） | FactStoreProvider 兼容 None ctx，直接降级 |
| 用户有 ~/.cogito/ 旧数据 | P4 迁移到 ~/.hermes/memory/，不覆盖已有数据 |
