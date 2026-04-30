"""Tests for reviewer.py"""

import pytest

from enjinc.reviewer import MasterReviewer, ReviewComment, ReviewResult


class TestReviewResult:
    def test_default_approved(self):
        result = ReviewResult()
        assert result.approved is True
        assert result.comments == []

    def test_with_comments(self):
        comments = [
            ReviewComment(
                node_key="fn:register",
                severity="warning",
                message="missing guard",
                suggestion="add guard for email uniqueness",
            )
        ]
        result = ReviewResult(comments=comments, approved=False, model_used="test")
        assert result.approved is False
        assert len(result.comments) == 1


class TestMasterReviewerParse:
    def setup_method(self):
        self.reviewer = MasterReviewer(client=None)

    def test_parse_approved_json(self):
        content = '{"approved": true, "comments": []}'
        result = self.reviewer._parse_review_response(content, "test-model")
        assert result.approved is True
        assert result.comments == []
        assert result.model_used == "test-model"

    def test_parse_with_comments(self):
        content = '''{
            "approved": false,
            "comments": [
                {
                    "node_key": "fn:register",
                    "severity": "error",
                    "message": "guard not implemented",
                    "suggestion": "add email uniqueness check"
                }
            ]
        }'''
        result = self.reviewer._parse_review_response(content, "test")
        assert result.approved is False
        assert len(result.comments) == 1
        assert result.comments[0].node_key == "fn:register"
        assert result.comments[0].severity == "error"

    def test_parse_json_with_markdown_fences(self):
        content = '```json\n{"approved": true, "comments": []}\n```'
        result = self.reviewer._parse_review_response(content, "test")
        assert result.approved is True

    def test_parse_invalid_json(self):
        content = "This is not JSON"
        result = self.reviewer._parse_review_response(content, "test")
        assert result.approved is True  # fallback to approved

    def test_parse_partial_json(self):
        content = '{"approved": false}'
        result = self.reviewer._parse_review_response(content, "test")
        assert result.approved is False
        assert result.comments == []

    def test_review_handles_exception(self):
        class FailingClient:
            def generate(self, request):
                raise RuntimeError("API down")

        from enjinc.dependency_graph import DependencyGraph
        from enjinc.code_generator import GenerationResult

        reviewer = MasterReviewer(client=FailingClient())
        graph = DependencyGraph.build(
            __import__("enjinc.ast_nodes", fromlist=["Program"]).Program()
        )
        results = {"fn:test": GenerationResult(
            node_type="fn", node_name="test",
            generated_code="pass", intent_hash="abc", cached=False
        )}
        result = reviewer.review(graph, results)
        assert result.approved is True  # fallback
        assert result.model_used == "fallback"
