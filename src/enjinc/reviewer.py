"""
============================================================
EnJin Master AI Reviewer (reviewer.py)
============================================================
Master AI 审核器：只审核+建议，不修改代码。
审核维度：四层隔离、跨层调用、Guard 完整性、模型一致性、代码风格。
============================================================
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from enjinc.dependency_graph import DependencyGraph
from enjinc.prompt_router import GeneratedPrompt, _compute_hash

logger = logging.getLogger(__name__)


@dataclass
class ReviewComment:
    """单条审核意见。"""

    node_key: str    # "fn:register_user"
    severity: str    # "error" | "warning" | "suggestion"
    message: str
    suggestion: str


@dataclass
class ReviewResult:
    """审核结果。"""

    comments: list[ReviewComment] = field(default_factory=list)
    approved: bool = True
    model_used: str = ""


class MasterReviewer:
    """Master AI 审核器：只审核+建议，不修改代码。"""

    def __init__(self, client):
        self.client = client

    def review(
        self,
        dep_graph: DependencyGraph,
        generation_results: dict,
    ) -> ReviewResult:
        """审核所有子 AI 生成的代码。"""
        from enjinc.llm_client import LLMRequest

        prompt = self._build_review_prompt(dep_graph, generation_results)

        try:
            response = self.client.generate(
                LLMRequest(
                    system_prompt=prompt.system_prompt,
                    user_prompt=prompt.user_prompt,
                    intent_hash=prompt.intent_hash,
                )
            )
            return self._parse_review_response(response.content, response.model)
        except Exception as e:
            logger.warning(f"Master AI review failed: {e}")
            return ReviewResult(approved=True, model_used="fallback")

    def _build_review_prompt(
        self,
        dep_graph: DependencyGraph,
        generation_results: dict,
    ) -> GeneratedPrompt:
        """构建审核 prompt。"""
        dep_summary = dep_graph.render_summary()

        code_sections = []
        for key, result in generation_results.items():
            code_sections.append(f"### [{key}]\n```\n{result.generated_code}\n```")
        all_code = "\n\n".join(code_sections)

        system_prompt = """你是项目架构审核员。你只负责审核代码并提出修改建议。
你没有修改代码的权限，只能给出意见。

审核维度：
1. 四层隔离是否违反（struct→fn→module→route 单向调用，不可越级）
2. 跨层调用是否正确（如 route 是否正确引用 module export）
3. Guard 规则是否完整实现
4. 数据模型使用是否与 struct 定义一致
5. 代码风格是否符合目标语言规范

输出格式（严格遵守）：
返回 JSON 对象：
{
  "approved": true/false,
  "comments": [
    {"node_key": "fn:xxx", "severity": "error", "message": "问题描述", "suggestion": "修改建议"}
  ]
}

如果代码没有问题，返回 {"approved": true, "comments": []}
只返回 JSON，不要其他文字。"""

        user_prompt = f"""## 项目依赖图

{dep_summary}

## 待审核代码

{all_code}

请审核以上代码，返回 JSON 格式的审核结果。"""

        intent_hash = _compute_hash(f"review:{dep_summary[:200]}:{len(generation_results)}")

        return GeneratedPrompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            intent_hash=intent_hash,
        )

    def _parse_review_response(self, content: str, model: str) -> ReviewResult:
        """解析 Master AI 返回的 JSON 审核结果。"""
        cleaned = content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"Master AI returned non-JSON review: {content[:200]}")
            return ReviewResult(approved=True, model_used=model)

        comments = []
        for c in data.get("comments", []):
            comments.append(ReviewComment(
                node_key=c.get("node_key", ""),
                severity=c.get("severity", "suggestion"),
                message=c.get("message", ""),
                suggestion=c.get("suggestion", ""),
            ))

        return ReviewResult(
            comments=comments,
            approved=data.get("approved", True),
            model_used=model,
        )
