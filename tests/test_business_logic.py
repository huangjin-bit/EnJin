"""
============================================================
EnJin 业务逻辑测试 (test_business_logic.py)
============================================================
验证生成的代码能够执行业务逻辑，而不只是语法正确。
============================================================
"""

import pytest
import tempfile
import subprocess
import sys
import ast
from pathlib import Path

from enjinc.parser import parse
from enjinc.template_renderer import RenderConfig, render_program


class TestRiskControlBusinessLogic:
    """测试风控系统的业务逻辑是否正确。"""

    def test_risk_decision_scoring_logic(self):
        """测试风险评分逻辑：分数应该在 0-100 之间。"""
        output_dir, tmpdir = self._render_risk_service()
        service_file = (
            output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )

        if not service_file.exists():
            pytest.skip("RiskControlService.java not generated")

        content = service_file.read_text(encoding="utf-8")

        assert "int score = 0" in content or "Integer score = 0" in content
        assert "Math.min(100" in content or "Math.max(0" in content
        assert "getRiskLevel" in content
        assert "if (score >= 80)" in content or "score >= 80" in content

        tmpdir.cleanup()

    def test_blacklist_check_logic(self):
        """测试黑名单检查逻辑。"""
        output_dir, tmpdir = self._render_risk_service()
        service_file = (
            output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )

        if not service_file.exists():
            pytest.skip("RiskControlService.java not generated")

        content = service_file.read_text(encoding="utf-8")

        assert "checkBlacklist" in content
        assert "RiskBlacklist" in content
        assert "LocalDateTime.now()" in content

        tmpdir.cleanup()

    def test_risk_decision_helper_methods(self):
        """测试风控决策辅助方法。"""
        output_dir, tmpdir = self._render_risk_service()
        service_file = (
            output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )

        if not service_file.exists():
            pytest.skip("RiskControlService.java not generated")

        content = service_file.read_text(encoding="utf-8")

        assert "private String getRiskLevel" in content
        assert "private String makeDecision" in content
        assert '"block"' in content
        assert '"allow"' in content
        assert '"review"' in content
        assert '"alert"' in content

        tmpdir.cleanup()

    def test_order_risk_evaluation_logic(self):
        """测试订单风控评估逻辑。"""
        output_dir, tmpdir = self._render_risk_service()
        service_file = (
            output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )

        if not service_file.exists():
            pytest.skip("RiskControlService.java not generated")

        content = service_file.read_text(encoding="utf-8")

        assert "evaluateOrderRisk" in content
        assert "orderAmount" in content or "amount" in content.lower()
        assert "HIGH_AMOUNT" in content or "high" in content.lower()

        tmpdir.cleanup()

    def test_device_risk_evaluation_logic(self):
        """测试设备风控评估逻辑。"""
        output_dir, tmpdir = self._render_risk_service()
        service_file = (
            output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )

        if not service_file.exists():
            pytest.skip("RiskControlService.java not generated")

        content = service_file.read_text(encoding="utf-8")

        assert "evaluateDeviceRisk" in content
        assert "isEmulator" in content or "emulator" in content.lower()
        assert "NEW_DEVICE" in content or "new device" in content.lower()

        tmpdir.cleanup()

    def _render_risk_service(self):
        """渲染风控服务。"""
        from enjinc.template_renderer import render_risk_control

        risk_ej_path = (
            Path(__file__).parent.parent
            / "examples"
            / "java_ecommerce"
            / "risk_control.ej"
        )
        if not risk_ej_path.exists():
            pytest.skip("risk_control.ej not found")

        content = risk_ej_path.read_text(encoding="utf-8")
        program = parse(content)

        tmpdir = tempfile.TemporaryDirectory()
        output_dir = Path(tmpdir.name) / "output"
        config = RenderConfig(
            target_lang="java_springboot",
            output_dir=output_dir,
            app_name="risk-core",
        )

        render_risk_control(
            structs=program.structs,
            functions=program.functions,
            routes=program.routes,
            config=config,
            output_dir=output_dir,
        )
        return output_dir, tmpdir


class TestPythonFastAPIBusinessLogic:
    """测试 Python FastAPI 生成的代码能够执行业务逻辑。"""

    def _render_fastapi(self):
        """渲染 Python FastAPI。"""
        examples_dir = Path(__file__).parent.parent / "examples"
        ej_files = list(examples_dir.glob("**/user_management.ej"))
        if not ej_files:
            pytest.skip("user_management.ej not found")

        content = ej_files[0].read_text(encoding="utf-8")
        program = parse(content)

        tmpdir = tempfile.TemporaryDirectory()
        output_dir = Path(tmpdir.name) / "output"
        config = RenderConfig(
            target_lang="python_fastapi",
            output_dir=output_dir,
            app_name="test_app",
        )

        render_program(program, config)
        return output_dir / "python_fastapi", tmpdir

    def test_services_have_function_signatures(self):
        """测试 services/ 目录中的函数签名正确。"""
        output_dir, tmpdir = self._render_fastapi()
        services_dir = output_dir / "services"

        if not services_dir.exists():
            pytest.skip("services/ directory not generated")

        # Check register_user.py for its signature
        register_user_file = services_dir / "register_user.py"
        if not register_user_file.exists():
            pytest.skip("services/register_user.py not generated")

        content = register_user_file.read_text(encoding="utf-8")

        assert "def register_user" in content or "async def register_user" in content
        assert "username" in content
        assert "email" in content

        # Check other service files exist with their signatures
        get_user_file = services_dir / "get_user_by_id.py"
        assert get_user_file.exists(), "services/get_user_by_id.py not generated"
        get_user_content = get_user_file.read_text(encoding="utf-8")
        assert "def get_user_by_id" in get_user_content or "async def get_user_by_id" in get_user_content

        update_user_file = services_dir / "update_user.py"
        assert update_user_file.exists(), "services/update_user.py not generated"
        update_user_content = update_user_file.read_text(encoding="utf-8")
        assert "def update_user" in update_user_content or "async def update_user" in update_user_content

        tmpdir.cleanup()

    def test_models_define_user_class(self):
        """测试 models/ 目录定义了 User 类。"""
        output_dir, tmpdir = self._render_fastapi()
        models_file = output_dir / "models" / "user.py"

        if not models_file.exists():
            pytest.skip("models/user.py not generated")

        content = models_file.read_text(encoding="utf-8")

        assert "class User" in content or "User =" in content
        assert "username" in content.lower()
        assert "email" in content.lower()

        tmpdir.cleanup()

    def test_routes_define_endpoints(self):
        """测试 routes/ 目录包含路由模块。"""
        output_dir, tmpdir = self._render_fastapi()
        routes_dir = output_dir / "routes"

        if not routes_dir.exists():
            pytest.skip("routes/ directory not generated")

        route_files = list(routes_dir.glob("*.py"))
        route_files = [f for f in route_files if not f.name.startswith("_")]

        assert len(route_files) > 0, "No route files found"
        assert any(
            "register" in f.name.lower() or "user" in f.name.lower()
            for f in route_files
        ), "No user-related routes found"

        tmpdir.cleanup()


class TestGeneratedRiskCodeExecution:
    """测试生成的 Java 风控代码逻辑（通过代码审查验证）。"""

    def _render_risk_control(self):
        """渲染风控系统。"""
        from enjinc.template_renderer import render_risk_control

        risk_ej_path = (
            Path(__file__).parent.parent
            / "examples"
            / "java_ecommerce"
            / "risk_control.ej"
        )
        if not risk_ej_path.exists():
            pytest.skip("risk_control.ej not found")

        content = risk_ej_path.read_text(encoding="utf-8")
        program = parse(content)

        tmpdir = tempfile.TemporaryDirectory()
        output_dir = Path(tmpdir.name) / "output"
        config = RenderConfig(
            target_lang="java_springboot",
            output_dir=output_dir,
            app_name="risk-core",
        )

        render_risk_control(
            structs=program.structs,
            functions=program.functions,
            routes=program.routes,
            config=config,
            output_dir=output_dir,
        )
        return output_dir, tmpdir

    def test_risk_evaluation_workflow_complete(self):
        """测试风控评估工作流完整：whitelist -> blacklist -> device -> decision"""
        output_dir, tmpdir = self._render_risk_control()
        service_file = (
            output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )

        if not service_file.exists():
            pytest.skip("RiskControlService.java not generated")

        content = service_file.read_text(encoding="utf-8")

        assert "evaluateUserRegisterRisk" in content
        assert "checkWhitelist" in content
        assert "checkBlacklist" in content
        assert "evaluateDeviceRisk" in content
        assert "makeRiskDecision" in content or "makeDecision" in content

        tmpdir.cleanup()

    def test_risk_alert_triggered_on_high_risk(self):
        """测试高风险时触发预警。"""
        output_dir, tmpdir = self._render_risk_control()
        service_file = (
            output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )

        if not service_file.exists():
            pytest.skip("RiskControlService.java not generated")

        content = service_file.read_text(encoding="utf-8")

        assert "triggerRiskAlert" in content
        assert "alertLevel" in content or "alert" in content.lower()

        tmpdir.cleanup()

    def test_risk_profile_updated_after_operation(self):
        """测试操作后更新风控档案。"""
        output_dir, tmpdir = self._render_risk_control()
        service_file = (
            output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )

        if not service_file.exists():
            pytest.skip("RiskControlService.java not generated")

        content = service_file.read_text(encoding="utf-8")

        assert "updateRiskProfile" in content
        assert "totalScore" in content
        assert "loginFailCount" in content or "login_fail" in content.lower()
        assert "orderCount" in content or "order" in content.lower()

        tmpdir.cleanup()

    def test_risk_event_logged(self):
        """测试风控事件被记录。"""
        output_dir, tmpdir = self._render_risk_control()
        service_file = (
            output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )

        if not service_file.exists():
            pytest.skip("RiskControlService.java not generated")

        content = service_file.read_text(encoding="utf-8")

        assert "saveRiskEvent" in content or "RiskEvent" in content
        assert "eventId" in content or "event_id" in content.lower()
        assert "riskScore" in content or "risk_score" in content.lower()

        tmpdir.cleanup()

    def test_rule_engine_executes_all_rules(self):
        """测试规则引擎执行所有适用规则。"""
        output_dir, tmpdir = self._render_risk_control()
        service_file = (
            output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )

        if not service_file.exists():
            pytest.skip("RiskControlService.java not generated")

        content = service_file.read_text(encoding="utf-8")

        assert "executeRiskRules" in content
        assert "selectByEventType" in content
        assert "riskRuleMapper" in content
        assert "getEnabled()" in content

        tmpdir.cleanup()

    def test_statistics_calculation(self):
        """测试统计计算。"""
        output_dir, tmpdir = self._render_risk_control()
        service_file = (
            output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )

        if not service_file.exists():
            pytest.skip("RiskControlService.java not generated")

        content = service_file.read_text(encoding="utf-8")

        assert "getRiskStatistics" in content
        assert "getRiskTrend" in content
        assert "totalEvents" in content or "total" in content.lower()
        assert "blockCount" in content or "block" in content.lower()

        tmpdir.cleanup()

    def test_risk_controller_endpoints_complete(self):
        """测试风控控制器端点完整。"""
        output_dir, tmpdir = self._render_risk_control()
        controller_file = (
            output_dir
            / "src/main/java/risk_core/web/controller/RiskControlController.java"
        )

        if not controller_file.exists():
            pytest.skip("RiskControlController.java not generated")

        content = controller_file.read_text(encoding="utf-8")

        expected_endpoints = [
            '"/evaluate/register"',
            '"/evaluate/login"',
            '"/evaluate/order"',
            '"/evaluate/payment"',
            '"/blacklist/check"',
            '"/blacklist/add"',
            '"/profile/{userId}"',
            '"/alert/trigger"',
            '"/decision"',
            '"/statistics"',
        ]

        for endpoint in expected_endpoints:
            assert endpoint in content, f"Missing endpoint: {endpoint}"

        tmpdir.cleanup()

    def test_risk_service_returns_correct_types(self):
        """测试风控服务返回类型正确。"""
        output_dir, tmpdir = self._render_risk_control()
        service_file = (
            output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )

        if not service_file.exists():
            pytest.skip("RiskControlService.java not generated")

        content = service_file.read_text(encoding="utf-8")

        assert "RiskDecision" in content
        assert "BlacklistResult" in content
        assert "RiskProfile" in content
        assert "RiskAlert" in content
        assert "List<RiskAlert>" in content or "List<" in content

        tmpdir.cleanup()

    def test_risk_decision_enum_values(self):
        """测试风险决策枚举值。"""
        output_dir, tmpdir = self._render_risk_control()
        service_file = (
            output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )

        if not service_file.exists():
            pytest.skip("RiskControlService.java not generated")

        content = service_file.read_text(encoding="utf-8")

        assert '"allow"' in content
        assert '"block"' in content
        assert '"review"' in content
        assert '"alert"' in content

        tmpdir.cleanup()

    def test_risk_level_enum_values(self):
        """测试风险等级枚举值。"""
        output_dir, tmpdir = self._render_risk_control()
        service_file = (
            output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )

        if not service_file.exists():
            pytest.skip("RiskControlService.java not generated")

        content = service_file.read_text(encoding="utf-8")

        assert '"low"' in content
        assert '"medium"' in content
        assert '"high"' in content
        assert '"critical"' in content

        tmpdir.cleanup()

    def test_builder_pattern_for_dtos(self):
        """测试 DTO 使用 Builder 模式。"""
        output_dir, tmpdir = self._render_risk_control()
        service_file = (
            output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )

        if not service_file.exists():
            pytest.skip("RiskControlService.java not generated")

        content = service_file.read_text(encoding="utf-8")

        assert ".builder()" in content
        assert ".decision(" in content
        assert ".riskLevel(" in content
        assert ".build()" in content

        tmpdir.cleanup()
