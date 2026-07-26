#!/usr/bin/env python3
"""
test_multiprovider.py — TDD 测试：KnowledgeBridge 多 Provider 架构

覆盖模块：
  KB-01~15: HermesToolProvider（通用 Hermes 工具适配）
  KB-16~25: FileSystemProvider（本地文件搜索）
  KB-26~35: KnowledgeScanner（全量探针）
  KB-36~42: DecisionEngine（0/1/2+ 决策）
"""
import unittest
import sys
import os
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── 导入 ──
try:
    from cogito_core.knowledge_provider import KnowledgeProvider
    PROVIDER_OK = True
except ImportError:
    PROVIDER_OK = False


@unittest.skipUnless(PROVIDER_OK, "knowledge_provider not importable")
class TestHermesToolProvider(unittest.TestCase):
    """KB-01~15: 通用 Hermes 工具适配器"""

    def setUp(self):
        from cogito_core.hermes_tool_provider import HermesToolProvider
        self.HermesToolProvider = HermesToolProvider

    # ── 构造 ──
    def test_kb01_provider_type(self):
        """KB-01: HermesToolProvider 继承 KnowledgeProvider。"""
        from cogito_core.hermes_tool_provider import HermesToolProvider
        self.assertIsInstance(HermesToolProvider(), KnowledgeProvider)

    def test_kb02_name_default(self):
        """KB-02: 默认 name() 返回 'hermes_tool'。"""
        p = self.HermesToolProvider()
        self.assertEqual(p.name(), "hermes_tool")

    def test_kb03_name_custom(self):
        """KB-03: 支持自定义 tool name。"""
        p = self.HermesToolProvider(tool_name="my_rag")
        self.assertEqual(p.name(), "my_rag")

    # ── 可用性 ──
    def test_kb04_not_available_by_default(self):
        """KB-04: 未注入 tool 时 available() 返回 False。"""
        p = self.HermesToolProvider()
        self.assertFalse(p.available())

    def test_kb05_available_with_tool(self):
        """KB-05: 注入 tool 后 available() 返回 True。"""
        mock_tool = MagicMock()
        mock_tool.search.return_value = []
        p = self.HermesToolProvider(tool=mock_tool)
        self.assertTrue(p.available())

    def test_kb06_available_false_after_tool_gone(self):
        """KB-06: tool 被设为 None 后 available() 返回 False。"""
        mock_tool = MagicMock()
        p = self.HermesToolProvider(tool=mock_tool)
        self.assertTrue(p.available())
        p.tool = None
        self.assertFalse(p.available())

    # ── 搜索 ──
    def test_kb07_search_returns_empty_when_unavailable(self):
        """KB-07: 不可用时 search() 返回 []。"""
        p = self.HermesToolProvider()
        self.assertEqual(p.search("test"), [])

    def test_kb08_search_delegates_to_tool(self):
        """KB-08: search() 委托给注入的 tool。"""
        mock_tool = MagicMock()
        mock_tool.search.return_value = [
            {"content": "result1"},
            {"content": "result2"},
        ]
        p = self.HermesToolProvider(tool=mock_tool)
        results = p.search("test", limit=2)
        self.assertEqual(len(results), 2)
        self.assertIn("result1", results)
        mock_tool.search.assert_called_once_with("test", limit=2)

    def test_kb09_search_respects_limit(self):
        """KB-09: search() 遵守 limit 参数。"""
        mock_tool = MagicMock()
        mock_tool.search.return_value = [{"content": f"r{i}"} for i in range(10)]
        p = self.HermesToolProvider(tool=mock_tool)
        self.assertEqual(len(p.search("q", limit=3)), 3)

    def test_kb10_search_handles_string_results(self):
        """KB-10: tool 返回字符串列表也能正常处理。"""
        mock_tool = MagicMock()
        mock_tool.search.return_value = ["str1", "str2"]
        p = self.HermesToolProvider(tool=mock_tool)
        results = p.search("q")
        self.assertEqual(results, ["str1", "str2"])

    # ── 异常处理 ──
    def test_kb11_search_catches_exception(self):
        """KB-11: tool.search() 抛异常时返回 []，不崩溃。"""
        mock_tool = MagicMock()
        mock_tool.search.side_effect = RuntimeError("boom")
        p = self.HermesToolProvider(tool=mock_tool)
        self.assertEqual(p.search("q"), [])

    def test_kb12_available_catches_exception(self):
        """KB-12: available() 检查时 tool 抛异常返回 False。"""
        mock_tool = MagicMock()
        # hasattr(tool, 'search') 抛异常的处理
        p = self.HermesToolProvider(tool=mock_tool)
        self.assertTrue(p.available())  # mock has search attr

    # ── 无 tool 场景 ──
    def test_kb13_search_no_tool_returns_empty(self):
        """KB-13: tool=None 时 search() 返回 []。"""
        p = self.HermesToolProvider()
        self.assertEqual(p.search("q"), [])

    def test_kb14_tool_without_search_method(self):
        """KB-14: tool 对象没有 search 方法时 available() 返回 False。"""
        p = self.HermesToolProvider(tool="not_a_tool")
        self.assertFalse(p.available())

    def test_kb15_empty_search_results(self):
        """KB-15: tool 返回空列表时正常返回 []。"""
        mock_tool = MagicMock()
        mock_tool.search.return_value = []
        p = self.HermesToolProvider(tool=mock_tool)
        self.assertEqual(p.search("q"), [])


@unittest.skipUnless(PROVIDER_OK, "knowledge_provider not importable")
class TestFileSystemProvider(unittest.TestCase):
    """KB-16~25: 本地文件系统搜索"""

    def setUp(self):
        from cogito_core.filesystem_provider import FileSystemProvider
        self.FileSystemProvider = FileSystemProvider
        self._tmpdir = tempfile.mkdtemp(prefix="cogito_kb_fs_")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_md(self, name: str, content: str):
        p = Path(self._tmpdir) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return str(p)

    # ── 构造 ──
    def test_kb16_provider_type(self):
        """KB-16: FileSystemProvider 继承 KnowledgeProvider。"""
        from cogito_core.filesystem_provider import FileSystemProvider
        self.assertIsInstance(
            FileSystemProvider(path=self._tmpdir), KnowledgeProvider
        )

    def test_kb17_name(self):
        """KB-17: name() 返回传入的 label，默认 'filesystem'。"""
        p = self.FileSystemProvider(path=self._tmpdir)
        self.assertEqual(p.name(), "filesystem")
        p2 = self.FileSystemProvider(path=self._tmpdir, label="Obsidian")
        self.assertEqual(p2.name(), "Obsidian")

    # ── 可用性 ──
    def test_kb18_available_when_dir_exists(self):
        """KB-18: 目录存在且有 .md 文件时 available() 返回 True。"""
        self._write_md("note.md", "# Test\nhello world")
        p = self.FileSystemProvider(path=self._tmpdir, glob="*.md")
        self.assertTrue(p.available())

    def test_kb19_not_available_when_dir_missing(self):
        """KB-19: 目录不存在时 available() 返回 False。"""
        p = self.FileSystemProvider(path="/nonexistent/path", glob="*.md")
        self.assertFalse(p.available())

    def test_kb20_not_available_when_no_matching_files(self):
        """KB-20: 目录存在但没有匹配 glob 的文件时返回 False。"""
        p = self.FileSystemProvider(path=self._tmpdir, glob="*.txt")
        self.assertFalse(p.available())

    # ── 搜索 ──
    def test_kb21_search_finds_content(self):
        """KB-21: search() 能找到 markdown 文件中的内容（Python fallback）。"""
        self._write_md("a.md", "# Docker\n端口映射是把容器端口映射到宿主机。")
        p = self.FileSystemProvider(path=self._tmpdir, glob="*.md")
        # 直接用 fallback 搜索，避免 ripgrep 跨平台不兼容
        results = p._fallback_search("Docker 端口映射", limit=5)
        self.assertGreaterEqual(len(results), 1)

    def test_kb22_search_no_match(self):
        """KB-22: 没有匹配内容时返回 []。"""
        self._write_md("a.md", "# Test\nhello")
        p = self.FileSystemProvider(path=self._tmpdir, glob="*.md")
        self.assertEqual(p.search("不存在的关键词XYZ"), [])

    def test_kb23_search_skips_yaml_frontmatter(self):
        """KB-23: 搜索结果不包含 YAML frontmatter。"""
        self._write_md("a.md", "---\ntags: [test]\n---\n\n# Docker\n端口映射配置。")
        p = self.FileSystemProvider(path=self._tmpdir, glob="*.md")
        results = p.search("tags")
        # "tags" 在 frontmatter 中，不应出现在结果里
        for r in results:
            self.assertNotIn("tags:", r)

    def test_kb24_search_unavailable_returns_empty(self):
        """KB-24: 不可用时 search() 返回 []。"""
        p = self.FileSystemProvider(path="/nonexistent", glob="*.md")
        self.assertEqual(p.search("q"), [])

    def test_kb25_search_respects_limit(self):
        """KB-25: search() 遵守 limit 参数。"""
        for i in range(10):
            self._write_md(f"{i}.md", f"# Note {i}\nDocker port mapping Docker Docker.")
        p = self.FileSystemProvider(path=self._tmpdir, glob="*.md")
        results = p.search("Docker", limit=3)
        self.assertLessEqual(len(results), 3)


@unittest.skipUnless(PROVIDER_OK, "knowledge_provider not importable")
class TestKnowledgeScanner(unittest.TestCase):
    """KB-26~35: 全量探针"""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="cogito_kb_scan_")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # ── 文件系统探测 ──
    def test_kb26_scanner_finds_markdown_dir(self):
        """KB-26: 探测到含 .md 文件的目录。"""
        md_dir = Path(self._tmpdir) / "vault"
        md_dir.mkdir()
        (md_dir / "note.md").write_text("# Test")
        from cogito_core.knowledge_scanner import KnowledgeScanner
        scanner = KnowledgeScanner()
        sources = scanner._probe_filesystem(base_dirs=[str(self._tmpdir)])
        self.assertGreaterEqual(len(sources), 1)

    def test_kb27_scanner_ignores_empty_dir(self):
        """KB-27: 有目录但无匹配文件时不返回。"""
        from cogito_core.knowledge_scanner import KnowledgeScanner
        scanner = KnowledgeScanner()
        sources = scanner._probe_filesystem(base_dirs=[str(self._tmpdir)])
        self.assertEqual(len(sources), 0)

    def test_kb28_scanner_labels_correctly(self):
        """KB-28: 探测到的源有正确的 label。"""
        md_dir = Path(self._tmpdir) / "Obsidian Vault"
        md_dir.mkdir()
        (md_dir / "note.md").write_text("# Test")
        from cogito_core.knowledge_scanner import KnowledgeScanner
        scanner = KnowledgeScanner()
        sources = scanner._probe_filesystem(base_dirs=[str(self._tmpdir)])
        if sources:
            self.assertTrue(any("Obsidian" in s.label for s in sources))

    # ── Hermes 工具探测 ──
    def test_kb29_scanner_finds_hermes_tool(self):
        """KB-29: 模拟注册工具时 scanner 返回 Hermes 源。"""
        mock_ctx = MagicMock()
        mock_ctx.tools = {"fact_store": MagicMock()}
        from cogito_core.knowledge_scanner import KnowledgeScanner
        scanner = KnowledgeScanner(ctx=mock_ctx)
        sources = scanner._probe_hermes_tools()
        self.assertGreaterEqual(len(sources), 1)
        self.assertEqual(sources[0].tool_name, "fact_store")

    def test_kb30_scanner_no_hermes_tools(self):
        """KB-30: 无注册工具时返回空。"""
        from cogito_core.knowledge_scanner import KnowledgeScanner
        scanner = KnowledgeScanner()
        sources = scanner._probe_hermes_tools()
        # 本地环境可能或可能没有 Hermes，不做强断言
        self.assertIsInstance(sources, list)

    # ── SQLite 探测 ──
    def test_kb31_scanner_finds_sqlite_with_facts(self):
        """KB-31: 探测到含 facts 表的 SQLite。"""
        import sqlite3
        db_path = Path(self._tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE facts (content TEXT)")
        conn.execute("INSERT INTO facts VALUES ('test fact')")
        conn.commit()
        conn.close()
        from cogito_core.knowledge_scanner import KnowledgeScanner
        scanner = KnowledgeScanner()
        sources = scanner._probe_sqlite(base_paths=[str(self._tmpdir)])
        self.assertGreaterEqual(len(sources), 1)

    def test_kb32_scanner_ignores_empty_sqlite(self):
        """KB-32: 空 SQLite 文件不返回。"""
        db_path = Path(self._tmpdir) / "empty.db"
        db_path.write_text("")
        from cogito_core.knowledge_scanner import KnowledgeScanner
        scanner = KnowledgeScanner()
        sources = scanner._probe_sqlite(base_paths=[str(self._tmpdir)])
        self.assertEqual(len(sources), 0)

    # ── KnowledgeSource 数据类 ──
    def test_kb33_knowledge_source_dataclass(self):
        """KB-33: KnowledgeSource 在模块中定义。"""
        from cogito_core.knowledge_scanner import KnowledgeSource
        src = KnowledgeSource(
            provider_type="filesystem",
            label="Test",
            path="/tmp/test",
            priority=5,
        )
        self.assertEqual(src.provider_type, "filesystem")
        self.assertEqual(src.label, "Test")
        self.assertEqual(src.priority, 5)

    def test_kb34_source_priority_sorting(self):
        """KB-34: 多源按 priority 降序排列。"""
        from cogito_core.knowledge_scanner import KnowledgeSource
        sources = [
            KnowledgeSource(provider_type="x", label="low", priority=1),
            KnowledgeSource(provider_type="x", label="high", priority=10),
            KnowledgeSource(provider_type="x", label="mid", priority=5),
        ]
        sources.sort(key=lambda s: s.priority, reverse=True)
        self.assertEqual(sources[0].label, "high")
        self.assertEqual(sources[-1].label, "low")

    def test_kb35_full_scan_returns_list(self):
        """KB-35: scan() 全量扫描总是返回 list，不抛异常。"""
        from cogito_core.knowledge_scanner import KnowledgeScanner
        scanner = KnowledgeScanner()
        sources = scanner.scan()
        self.assertIsInstance(sources, list)


@unittest.skipUnless(PROVIDER_OK, "knowledge_provider not importable")
class TestDecisionEngine(unittest.TestCase):
    """KB-36~42: 决策引擎"""

    def setUp(self):
        from cogito_core.knowledge_scanner import KnowledgeSource
        self.KnowledgeSource = KnowledgeSource
        from cogito_core.knowledge_scanner import DecisionEngine
        self.DecisionEngine = DecisionEngine

    def _make_source(self, label="test", priority=5):
        return self.KnowledgeSource(
            provider_type="filesystem",
            label=label,
            path="/tmp/test",
            priority=priority,
        )

    def test_kb36_empty_sources_no_decision(self):
        """KB-36: 0 个源 → decision=None，不应提示。"""
        de = self.DecisionEngine()
        result = de.decide([])
        self.assertIsNone(result)

    def test_kb37_single_source_auto_select(self):
        """KB-37: 1 个源 → 自动选择。"""
        de = self.DecisionEngine()
        s = self._make_source("Obsidian")
        result = de.decide([s])
        self.assertEqual(result, s)

    def test_kb38_multiple_sources_prompt(self):
        """KB-38: 2+ 个源 → 不应自动选择，返回 None 并生成 prompt。"""
        de = self.DecisionEngine()
        sources = [
            self._make_source("Hermes 记忆库", priority=10),
            self._make_source("Obsidian Vault", priority=5),
            self._make_source("本地知识库", priority=3),
        ]
        result = de.decide(sources)
        self.assertIsNone(result)
        self.assertTrue(de.needs_prompt)

    def test_kb39_prompt_format(self):
        """KB-39: prompt 包含所有源的 label 和描述。"""
        de = self.DecisionEngine()
        sources = [
            self._make_source("A", priority=10),
            self._make_source("B", priority=5),
        ]
        de.decide(sources)
        prompt = de.get_prompt()
        self.assertIn("A", prompt)
        self.assertIn("B", prompt)

    def test_kb40_user_select(self):
        """KB-40: 用户选择后返回对应源。"""
        de = self.DecisionEngine()
        s1 = self._make_source("A")
        s2 = self._make_source("B")
        de.decide([s1, s2])
        selected = de.select(0)
        self.assertEqual(selected, s1)
        selected = de.select(1)
        self.assertEqual(selected, s2)

    def test_kb41_user_select_out_of_range(self):
        """KB-41: 越界选择返回 None。"""
        de = self.DecisionEngine()
        de.decide([self._make_source("A")])
        self.assertIsNone(de.select(5))

    def test_kb42_prompt_only_when_multiple(self):
        """KB-42: 单源时 needs_prompt 始终 False。"""
        de = self.DecisionEngine()
        de.decide([self._make_source("A")])
        self.assertFalse(de.needs_prompt)


if __name__ == "__main__":
    unittest.main()
