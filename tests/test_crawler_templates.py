"""
============================================================
EnJin Python Crawler 模板渲染测试 (test_crawler_templates.py)
============================================================
验证 template_renderer.py 能否正确将 I-AST 渲染为 Python 爬虫代码。

测试覆盖:
    1. httpx 爬虫配置和代理池生成
    2. Scrapy Spider 和 Pipeline 生成
    3. Playwright 爬虫配置生成
============================================================
"""

from pathlib import Path

import pytest

from enjinc.parser import parse_file
from enjinc.template_renderer import RenderConfig, render_program


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    output = tmp_path / "output"
    output.mkdir(parents=True, exist_ok=True)
    return output


class TestHttpxCrawlerTemplates:
    """验证 httpx 异步爬虫模板生成。"""

    def test_httpx_config_generated(self, examples_dir: Path, output_dir: Path):
        """config.py 应包含正确的爬虫配置。"""
        program = parse_file(examples_dir / "python_crawler" / "product_crawler.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="python_crawler")
        render_program(program, config)

        config_py = output_dir / "python_crawler" / "httpx" / "config.py"
        assert config_py.exists()

        content = config_py.read_text(encoding="utf-8")
        assert "CRAWLER_NAME" in content
        assert "REQUEST_TIMEOUT" in content
        assert "PROXY_POOL_ENABLED" in content
        assert "RATE_LIMIT_ENABLED" in content

    def test_proxy_pool_generated(self, examples_dir: Path, output_dir: Path):
        """proxy_pool.py 应包含代理池管理器。"""
        program = parse_file(examples_dir / "python_crawler" / "product_crawler.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="python_crawler")
        render_program(program, config)

        proxy_pool = output_dir / "python_crawler" / "httpx" / "proxy_pool.py"
        assert proxy_pool.exists()

        content = proxy_pool.read_text(encoding="utf-8")
        assert "class ProxyPool" in content
        assert "class Proxy" in content
        assert "async def get_proxy" in content
        assert "async def release_proxy" in content

    def test_rate_limiter_generated(self, examples_dir: Path, output_dir: Path):
        """rate_limiter.py 应包含速率限制器。"""
        program = parse_file(examples_dir / "python_crawler" / "product_crawler.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="python_crawler")
        render_program(program, config)

        rate_limiter = output_dir / "python_crawler" / "httpx" / "rate_limiter.py"
        assert rate_limiter.exists()

        content = rate_limiter.read_text(encoding="utf-8")
        assert "class RateLimiter" in content
        assert "class TokenBucket" in content
        assert "async def acquire" in content

    def test_httpx_crawler_generated(self, examples_dir: Path, output_dir: Path):
        """crawler.py 应包含异步爬虫主类。"""
        program = parse_file(examples_dir / "python_crawler" / "product_crawler.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="python_crawler")
        render_program(program, config)

        crawler = output_dir / "python_crawler" / "httpx" / "crawler.py"
        assert crawler.exists()

        content = crawler.read_text(encoding="utf-8")
        assert "class Crawler" in content
        assert "class CrawlerResponse" in content
        assert "async def fetch" in content
        assert "async def crawl" in content


class TestScrapyTemplates:
    """验证 Scrapy 爬虫模板生成。"""

    def test_scrapy_base_spider_generated(self, examples_dir: Path, output_dir: Path):
        """scrapy base spider 应被生成。"""
        program = parse_file(examples_dir / "python_crawler" / "product_crawler.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="python_crawler")
        render_program(program, config)

        base_spider = output_dir / "python_crawler" / "scrapy" / "spiders" / "base.py"
        assert base_spider.exists()

        content = base_spider.read_text(encoding="utf-8")
        assert "class BaseSpider" in content
        assert "start_urls" in content

    def test_scrapy_items_generated(self, examples_dir: Path, output_dir: Path):
        """scrapy items 应被生成。"""
        program = parse_file(examples_dir / "python_crawler" / "product_crawler.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="python_crawler")
        render_program(program, config)

        items = output_dir / "python_crawler" / "scrapy" / "items.py"
        assert items.exists()

        content = items.read_text(encoding="utf-8")
        assert "class ProductItem" in content
        assert "class CategoryItem" in content
        assert "class ReviewItem" in content

    def test_scrapy_pipelines_generated(self, examples_dir: Path, output_dir: Path):
        """scrapy pipelines 应被生成。"""
        program = parse_file(examples_dir / "python_crawler" / "product_crawler.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="python_crawler")
        render_program(program, config)

        pipelines = output_dir / "python_crawler" / "scrapy" / "pipelines.py"
        assert pipelines.exists()

        content = pipelines.read_text(encoding="utf-8")
        assert "class MongoDBPipeline" in content
        assert "class DuplicatesPipeline" in content


class TestPlaywrightTemplates:
    """验证 Playwright 爬虫模板生成。"""

    def test_playwright_config_generated(self, examples_dir: Path, output_dir: Path):
        """playwright config 应被生成。"""
        program = parse_file(examples_dir / "python_crawler" / "product_crawler.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="python_crawler")
        render_program(program, config)

        pw_config = output_dir / "python_crawler" / "playwright" / "config.py"
        assert pw_config.exists()

        content = pw_config.read_text(encoding="utf-8")
        assert "PLAYWRIGHT_HEADLESS" in content
        assert "BROWSER_TYPE" in content

    def test_playwright_crawler_generated(self, examples_dir: Path, output_dir: Path):
        """playwright crawler 应被生成。"""
        program = parse_file(examples_dir / "python_crawler" / "product_crawler.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="python_crawler")
        render_program(program, config)

        pw_crawler = output_dir / "python_crawler" / "playwright" / "crawler.py"
        assert pw_crawler.exists()

        content = pw_crawler.read_text(encoding="utf-8")
        assert "class PlaywrightCrawler" in content
        assert "async def fetch" in content
        assert "async def scrape_with_selector" in content


class TestCrawlerIntegration:
    """集成测试。"""

    def test_full_crawler_rendering(self, examples_dir: Path, output_dir: Path):
        """完整渲染所有模板，验证目录结构。"""
        program = parse_file(examples_dir / "python_crawler" / "product_crawler.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="python_crawler")
        render_program(program, config)

        target_dir = output_dir / "python_crawler"

        httpx_dir = target_dir / "httpx"
        assert (httpx_dir / "config.py").exists()
        assert (httpx_dir / "proxy_pool.py").exists()
        assert (httpx_dir / "rate_limiter.py").exists()
        assert (httpx_dir / "crawler.py").exists()

        scrapy_dir = target_dir / "scrapy"
        assert scrapy_dir.exists()

        playwright_dir = target_dir / "playwright"
        assert (playwright_dir / "config.py").exists()
        assert (playwright_dir / "crawler.py").exists()

    def test_struct_count_matches(self, examples_dir: Path, output_dir: Path):
        """渲染后的 items.py 应包含所有 struct。"""
        program = parse_file(examples_dir / "python_crawler" / "product_crawler.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="python_crawler")
        render_program(program, config)

        items = output_dir / "python_crawler" / "scrapy" / "items.py"
        content = items.read_text(encoding="utf-8")

        expected_items = [
            "ProductItem",
            "CategoryItem",
            "ReviewItem",
            "PriceHistoryItem",
        ]
        for item_name in expected_items:
            assert f"class {item_name}" in content, f"Item {item_name} not found"
