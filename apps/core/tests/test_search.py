"""DuckDuckGo parse is regex-sensitive; lock it down."""

from __future__ import annotations

from forge_core.backends.search import DuckDuckGoSearchBackend
from forge_core.config import load

SAMPLE = """
<div class="result results_links results_links_deep web-result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fopencode.ai%2Fdocs%2F&rut=abc">opencode docs</a>
  <a class="result__snippet" href="//duckduckgo.com/l/?uddg=x">The opencode agent <strong>docs</strong></a>
</div>
<div class="result results_links results_links_deep web-result">
  <a class="result__a" href="https://github.com/opencode">second result</a>
</div>
"""


def test_parse_html_results():
    backend = DuckDuckGoSearchBackend(load())
    results = backend._parse(SAMPLE, 8)
    assert len(results) == 2
    assert results[0]["title"] == "opencode docs"
    assert results[0]["url"] == "https://opencode.ai/docs/"
    assert "agent" in results[0]["snippet"]


def test_parse_respects_limit():
    backend = DuckDuckGoSearchBackend(load())
    assert len(backend._parse(SAMPLE, 1)) == 1