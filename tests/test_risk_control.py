"""
============================================================
EnJin 风控系统测试 (test_risk_control.py)
============================================================
验证风控系统的解析、模板渲染和代码生成功能。
包含对生成代码的逻辑验证。
============================================================
"""

import pytest
import tempfile
import re
import subprocess
import sys
from pathlib import Path

from enjinc.parser import parse
from enjinc.template_renderer import RenderConfig, render_risk_control


@pytest.fixture(scope="class")
def risk_control_output_dir():
    """渲染风控系统并返回输出目录（类级别共享）。"""
    risk_ej_path = (
        Path(__file__).parent.parent / "examples" / "java_ecommerce" / "risk_control.ej"
    )
    if not risk_ej_path.exists():
        pytest.skip("risk_control.ej not found")

    content = risk_ej_path.read_text(encoding="utf-8")
    program = parse(content)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "output"
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
        yield output_dir


class TestRiskControlParsing:
    """测试风控系统 .ej 文件解析。"""

    def test_parse_risk_control_ej(self):
        """验证 risk_control.ej 可以被正确解析。"""
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

        assert program is not None
        assert len(program.structs) >= 8  # RiskRule, RiskEvent, RiskProfile, etc.
        assert len(program.functions) >= 15  # Multiple risk evaluation functions

    def test_risk_structs_exist(self):
        """验证风控相关 Struct 都存在。"""
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

        struct_names = {s.name for s in program.structs}
        expected_structs = [
            "RiskRule",
            "RiskEvent",
            "RiskProfile",
            "RiskBlacklist",
            "RiskWhitelist",
            "RiskAlert",
            "DeviceFingerprint",
            "RiskOperationLog",
        ]

        for expected in expected_structs:
            assert expected in struct_names, f"Missing struct: {expected}"

    def test_risk_functions_exist(self):
        """验证风控相关 Function 都存在。"""
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

        fn_names = {f.name for f in program.functions}
        expected_functions = [
            "evaluate_user_register_risk",
            "evaluate_user_login_risk",
            "evaluate_order_risk",
            "evaluate_payment_risk",
            "check_blacklist",
            "add_to_blacklist",
            "get_risk_profile",
            "trigger_risk_alert",
            "make_risk_decision",
        ]

        for expected in expected_functions:
            assert expected in fn_names, f"Missing function: {expected}"

    def test_risk_module_exists(self):
        """验证 RiskControlManager Module 存在。"""
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

        module_names = {m.name for m in program.modules}
        assert "RiskControlManager" in module_names

    def test_risk_route_exists(self):
        """验证 RiskControlService Route 存在。"""
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

        route_names = {r.name for r in program.routes}
        assert "RiskControlService" in route_names


class TestRiskControlTemplateRendering:
    """测试风控系统模板渲染。"""

    def _get_risk_program(self):
        """获取风控系统的解析结果。"""
        risk_ej_path = (
            Path(__file__).parent.parent
            / "examples"
            / "java_ecommerce"
            / "risk_control.ej"
        )
        if not risk_ej_path.exists():
            pytest.skip("risk_control.ej not found")

        content = risk_ej_path.read_text(encoding="utf-8")
        return parse(content)

    def test_render_risk_entities(self):
        """验证风控实体可以正确渲染。"""
        program = self._get_risk_program()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
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

            entity_file = (
                output_dir / "src/main/java/risk_core/domain/entity/RiskEntity.java"
            )
            assert entity_file.exists(), f"RiskEntity.java not generated"

            content = entity_file.read_text(encoding="utf-8")
            assert "class RiskRule" in content
            assert "class RiskEvent" in content
            assert "class RiskProfile" in content
            assert "class RiskBlacklist" in content

    def test_render_risk_service(self):
        """验证风控服务可以正确渲染。"""
        program = self._get_risk_program()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
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

            service_file = (
                output_dir
                / "src/main/java/risk_core/application/service/RiskControlService.java"
            )
            assert service_file.exists(), f"RiskControlService.java not generated"

            content = service_file.read_text(encoding="utf-8")
            assert "class RiskControlService" in content
            assert "evaluateUserRegisterRisk" in content
            assert "evaluateOrderRisk" in content
            assert "checkBlacklist" in content
            assert "makeRiskDecision" in content

    def test_render_risk_controller(self):
        """验证风控控制器可以正确渲染。"""
        program = self._get_risk_program()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
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

            controller_file = (
                output_dir
                / "src/main/java/risk_core/web/controller/RiskControlController.java"
            )
            assert controller_file.exists(), f"RiskControlController.java not generated"

            content = controller_file.read_text(encoding="utf-8")
            assert "class RiskControlController" in content
            assert '@RequestMapping("/api/v1/risk")' in content
            assert "evaluateRegisterRisk" in content
            assert "evaluateOrderRisk" in content
            assert "checkBlacklist" in content

    def test_render_risk_migration(self):
        """验证风控数据库迁移脚本可以正确渲染。"""
        program = self._get_risk_program()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
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

            migration_file = (
                output_dir / "src/main/resources/db/migration/V2__init_risk_control.sql"
            )
            assert migration_file.exists(), f"V2__init_risk_control.sql not generated"

            content = migration_file.read_text(encoding="utf-8")
            assert "CREATE TABLE risk_rules" in content
            assert "CREATE TABLE risk_events" in content
            assert "CREATE TABLE risk_profiles" in content
            assert "CREATE TABLE risk_blacklist" in content
            assert "CREATE TABLE risk_alerts" in content

    def test_render_risk_mapper(self):
        """验证风控 Mapper 可以正确渲染。"""
        program = self._get_risk_program()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
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

            mapper_file = (
                output_dir
                / "src/main/java/risk_core/infrastructure/mapper/RiskMapper.java"
            )
            assert mapper_file.exists(), f"RiskMapper.java not generated"

            content = mapper_file.read_text(encoding="utf-8")
            assert "interface RiskBlacklistMapper" in content
            assert "interface RiskWhitelistMapper" in content
            assert "interface RiskAlertMapper" in content


class TestRiskControlIntegration:
    """测试风控系统与主系统的集成。"""

    def test_risk_struct_fields(self):
        """验证风控实体的字段定义正确。"""
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

        risk_rule = next((s for s in program.structs if s.name == "RiskRule"), None)
        assert risk_rule is not None
        field_names = {f.name for f in risk_rule.fields}
        assert "rule_code" in field_names
        assert "rule_name" in field_names
        assert "rule_type" in field_names
        assert "risk_level" in field_names
        assert "condition_expr" in field_names
        assert "action" in field_names

    def test_risk_decision_struct(self):
        """验证 RiskDecision 结构体定义。"""
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

        risk_decision = next(
            (s for s in program.structs if s.name == "RiskDecision"), None
        )
        assert risk_decision is not None
        field_names = {f.name for f in risk_decision.fields}
        assert "decision" in field_names
        assert "risk_level" in field_names
        assert "risk_score" in field_names
        assert "hit_rules" in field_names

    def test_risk_functions_have_expect(self):
        """验证风控函数包含 expect 断言。"""
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

        for fn in program.functions:
            if fn.name.startswith("evaluate_") or fn.name.startswith("check_"):
                assert len(fn.expect) > 0, (
                    f"Function {fn.name} should have expect assertions"
                )

    def test_risk_decision_making_coverage(self):
        """验证风控决策覆盖各个业务场景。"""
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

        fn_names = {f.name for f in program.functions}

        assert "evaluate_user_register_risk" in fn_names
        assert "evaluate_user_login_risk" in fn_names
        assert "evaluate_order_risk" in fn_names
        assert "evaluate_payment_risk" in fn_names
        assert "evaluate_coupon_claim_risk" in fn_names
        assert "evaluate_device_risk" in fn_names


class TestGeneratedRiskCodeLogic:
    """测试生成的 Java 代码的业务逻辑正确性。"""

    def test_risk_service_has_decision_making_logic(self, risk_control_output_dir):
        """验证 RiskControlService 包含正确的决策逻辑。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        assert service_file.exists(), f"RiskControlService.java not generated"

        content = service_file.read_text(encoding="utf-8")

        assert "class RiskControlService" in content
        assert "private final RiskRuleMapper riskRuleMapper" in content
        assert "private final RiskEventMapper riskEventMapper" in content
        assert "private final RiskProfileMapper riskProfileMapper" in content
        assert "private final RiskBlacklistMapper riskBlacklistMapper" in content
        assert "private final RiskWhitelistMapper riskWhitelistMapper" in content
        assert "private final RiskAlertMapper riskAlertMapper" in content

    def test_risk_service_has_user_risk_methods(self, risk_control_output_dir):
        """验证用户风控方法正确实现。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        assert "evaluateUserRegisterRisk" in content
        assert "evaluateUserLoginRisk" in content
        assert 'log.info("评估用户注册风险' in content
        assert 'log.info("评估用户登录风险' in content

    def test_risk_service_has_order_risk_methods(self, risk_control_output_dir):
        """验证订单风控方法正确实现。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        assert "evaluateOrderRisk" in content
        assert "evaluateHighValueOrderRisk" in content
        assert 'log.info("评估订单风险' in content
        assert 'log.info("评估高价值订单风险' in content

    def test_risk_service_has_payment_risk_methods(self, risk_control_output_dir):
        """验证支付风控方法正确实现。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        assert "evaluatePaymentRisk" in content
        assert "detectStolenCard" in content
        assert 'log.info("评估支付风险' in content

    def test_risk_service_has_blacklist_methods(self, risk_control_output_dir):
        """验证黑白名单方法正确实现。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        assert "checkBlacklist" in content
        assert "addToBlacklist" in content
        assert "removeFromBlacklist" in content
        assert "checkWhitelist" in content
        assert "addToWhitelist" in content

    def test_risk_service_has_profile_methods(self, risk_control_output_dir):
        """验证风控档案方法正确实现。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        assert "getRiskProfile" in content
        assert "updateRiskProfile" in content

    def test_risk_service_has_alert_methods(self, risk_control_output_dir):
        """验证预警管理方法正确实现。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        assert "triggerRiskAlert" in content
        assert "getPendingAlerts" in content
        assert "resolveAlert" in content

    def test_risk_service_has_device_fingerprint_methods(self, risk_control_output_dir):
        """验证设备指纹方法正确实现。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        assert "registerDeviceFingerprint" in content
        assert "evaluateDeviceRisk" in content

    def test_risk_service_has_rule_engine_methods(self, risk_control_output_dir):
        """验证规则引擎方法正确实现。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        assert "executeRiskRules" in content
        assert "calculateRiskScore" in content
        assert "makeRiskDecision" in content

    def test_risk_service_has_statistics_methods(self, risk_control_output_dir):
        """验证统计报表方法正确实现。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        assert "getRiskStatistics" in content
        assert "getRiskTrend" in content

    def test_risk_service_has_helper_methods(self, risk_control_output_dir):
        """验证辅助方法正确实现。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        assert "private boolean checkRemoteLogin" in content
        assert "private boolean isAddressAnomaly" in content
        assert "private boolean isDeviceAnomaly" in content
        assert "private boolean isIpAnomaly" in content
        assert "private boolean isEmulator" in content
        assert "private String getRiskLevel" in content
        assert "private String makeDecision" in content
        assert "private String getSuggestion" in content

    def test_risk_service_dto_classes(self, risk_control_output_dir):
        """验证 DTO 类正确生成。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        assert "public static class RiskDecision" in content
        assert "public static class BlacklistResult" in content
        assert "public static class WhitelistResult" in content
        assert "public static class RuleResult" in content
        assert "public static class RiskStatistics" in content
        assert "public static class RiskTrendItem" in content

    def test_risk_decision_has_expected_fields(self, risk_control_output_dir):
        """验证 RiskDecision 有正确的字段。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        risk_decision_match = re.search(
            r"public static class RiskDecision\s*\{([^}]+)\}", content, re.DOTALL
        )
        assert risk_decision_match, "RiskDecision class not found"
        decision_body = risk_decision_match.group(1)

        assert "private String decision" in decision_body
        assert "private String riskLevel" in decision_body
        assert "private Integer riskScore" in decision_body
        assert "private List<String> hitRules" in decision_body
        assert "private String suggestion" in decision_body

    def test_risk_blacklist_result_has_expected_fields(self, risk_control_output_dir):
        """验证 BlacklistResult 有正确的字段。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        bl_result_match = re.search(
            r"public static class BlacklistResult\s*\{([^}]+)\}", content, re.DOTALL
        )
        assert bl_result_match, "BlacklistResult class not found"
        bl_body = bl_result_match.group(1)

        assert "private boolean hit" in bl_body
        assert "private RiskBlacklist record" in bl_body
        assert "private String reason" in bl_body

    def test_risk_controller_has_all_endpoints(self, risk_control_output_dir):
        """验证 RiskController 有所有端点。"""
        controller_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/web/controller/RiskControlController.java"
        )
        content = controller_file.read_text(encoding="utf-8")

        assert '@RequestMapping("/api/v1/risk")' in content
        assert 'PostMapping("/evaluate/register")' in content
        assert 'PostMapping("/evaluate/login")' in content
        assert 'PostMapping("/evaluate/order")' in content
        assert 'PostMapping("/evaluate/high_value_order")' in content
        assert 'PostMapping("/evaluate/payment")' in content
        assert 'PostMapping("/detect/stolen_card")' in content
        assert 'PostMapping("/evaluate/coupon")' in content
        assert 'PostMapping("/blacklist/check")' in content
        assert 'PostMapping("/blacklist/add")' in content
        assert 'PostMapping("/blacklist/remove")' in content
        assert 'PostMapping("/whitelist/check")' in content
        assert 'PostMapping("/whitelist/add")' in content
        assert 'GetMapping("/profile/{userId}")' in content
        assert 'PutMapping("/profile/{userId}")' in content
        assert 'PostMapping("/alert/trigger")' in content
        assert 'GetMapping("/alert/pending")' in content
        assert 'PostMapping("/alert/resolve")' in content
        assert 'PostMapping("/device/register")' in content
        assert 'PostMapping("/device/evaluate")' in content
        assert 'PostMapping("/rules/execute")' in content
        assert 'PostMapping("/score/calculate")' in content
        assert 'PostMapping("/decision")' in content
        assert 'GetMapping("/statistics")' in content
        assert 'GetMapping("/trend")' in content

    def test_risk_controller_request_dtos(self, risk_control_output_dir):
        """验证 RiskController 请求 DTO 正确生成。"""
        controller_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/web/controller/RiskControlController.java"
        )
        content = controller_file.read_text(encoding="utf-8")

        assert "public static class RegisterRiskRequest" in content
        assert "public static class LoginRiskRequest" in content
        assert "public static class OrderRiskRequest" in content
        assert "public static class PaymentRiskRequest" in content
        assert "public static class BlacklistCheckRequest" in content
        assert "public static class AlertTriggerRequest" in content

    def test_risk_entities_have_lombok_annotations(self, risk_control_output_dir):
        """验证生成的实体有 Lombok 注解。"""
        entity_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/domain/entity/RiskEntity.java"
        )
        content = entity_file.read_text(encoding="utf-8")

        assert "@lombok.Data" in content
        assert "@lombok.NoArgsConstructor" in content
        assert "@lombok.AllArgsConstructor" in content
        assert "@lombok.Builder" in content
        assert "@Entity" in content
        assert "@Table" in content

    def test_risk_entities_have_riskrule_fields(self, risk_control_output_dir):
        """验证 RiskRule 实体有正确的字段。"""
        entity_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/domain/entity/RiskEntity.java"
        )
        content = entity_file.read_text(encoding="utf-8")

        risk_rule_match = re.search(
            r"public class RiskRule\s*\{([^}]+)\}", content, re.DOTALL
        )
        assert risk_rule_match, "RiskRule class not found"
        rule_body = risk_rule_match.group(1)

        assert (
            "private String ruleCode" in rule_body
            or "private String rule_code" in rule_body
        )
        assert (
            "private String ruleName" in rule_body
            or "private String rule_name" in rule_body
        )
        assert (
            "private String ruleType" in rule_body
            or "private String rule_type" in rule_body
        )

    def test_risk_migration_creates_all_tables(self, risk_control_output_dir):
        """验证迁移脚本创建所有表。"""
        migration_file = (
            risk_control_output_dir
            / "src/main/resources/db/migration/V2__init_risk_control.sql"
        )
        content = migration_file.read_text(encoding="utf-8")

        assert "CREATE TABLE risk_rules" in content
        assert "CREATE TABLE risk_events" in content
        assert "CREATE TABLE risk_profiles" in content
        assert "CREATE TABLE risk_blacklist" in content
        assert "CREATE TABLE risk_whitelist" in content
        assert "CREATE TABLE risk_alerts" in content
        assert "CREATE TABLE device_fingerprints" in content
        assert "CREATE TABLE risk_operation_logs" in content

    def test_risk_migration_has_indexes(self, risk_control_output_dir):
        """验证迁移脚本创建必要的索引。"""
        migration_file = (
            risk_control_output_dir
            / "src/main/resources/db/migration/V2__init_risk_control.sql"
        )
        content = migration_file.read_text(encoding="utf-8")

        assert "CREATE INDEX idx_risk_rules_type" in content
        assert "CREATE INDEX idx_risk_events_user" in content
        assert "CREATE INDEX idx_risk_events_order" in content
        assert "CREATE INDEX idx_risk_blacklist_type_value" in content

    def test_risk_migration_has_initial_rules(self, risk_control_output_dir):
        """验证迁移脚本包含初始风控规则数据。"""
        migration_file = (
            risk_control_output_dir
            / "src/main/resources/db/migration/V2__init_risk_control.sql"
        )
        content = migration_file.read_text(encoding="utf-8")

        assert "INSERT INTO risk_rules" in content

    def test_risk_service_imports_are_correct(self, risk_control_output_dir):
        """验证 RiskService 导入了正确的类。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        assert "import lombok.RequiredArgsConstructor" in content
        assert "import lombok.extern.slf4j.Slf4j" in content
        assert "import org.springframework.stereotype.Service" in content
        assert "import risk_core.domain.entity" in content
        assert "import risk_core.infrastructure.mapper" in content

    def test_risk_controller_imports_are_correct(self, risk_control_output_dir):
        """验证 RiskController 导入了正确的类。"""
        controller_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/web/controller/RiskControlController.java"
        )
        content = controller_file.read_text(encoding="utf-8")

        assert "import lombok.RequiredArgsConstructor" in content
        assert "import lombok.extern.slf4j.Slf4j" in content
        assert "import org.springframework.web.bind.annotation" in content
        assert "import risk_core.application.service.RiskControlService" in content

    def test_risk_service_method_signatures_correct(self, risk_control_output_dir):
        """验证 Service 方法签名正确。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        assert re.search(
            r"public RiskDecision evaluateUserRegisterRisk\s*\(", content
        ), "evaluateUserRegisterRisk method signature incorrect"
        assert re.search(r"public RiskDecision evaluateOrderRisk\s*\(", content), (
            "evaluateOrderRisk method signature incorrect"
        )
        assert re.search(r"public BlacklistResult checkBlacklist\s*\(", content), (
            "checkBlacklist method signature incorrect"
        )
        assert re.search(r"public RiskProfile getRiskProfile\s*\(", content), (
            "getRiskProfile method signature incorrect"
        )

    def test_risk_controller_method_signatures_correct(self, risk_control_output_dir):
        """验证 Controller 方法签名正确。"""
        controller_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/web/controller/RiskControlController.java"
        )
        content = controller_file.read_text(encoding="utf-8")

        assert re.search(
            r"public ApiResponse<RiskDecision> evaluateRegisterRisk\s*\(", content
        ), "evaluateRegisterRisk method signature incorrect"
        assert re.search(
            r"public ApiResponse<RiskDecision> evaluateOrderRisk\s*\(", content
        ), "evaluateOrderRisk method signature incorrect"
        assert re.search(
            r"public ApiResponse<BlacklistResult> checkBlacklist\s*\(", content
        ), "checkBlacklist method signature incorrect"

    def test_risk_service_returns_correct_decision_types(self, risk_control_output_dir):
        """验证 Service 返回类型正确。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        assert re.search(
            r"public RiskDecision evaluateUserRegisterRisk.*\{", content, re.DOTALL
        ), "evaluateUserRegisterRisk should return RiskDecision"
        assert re.search(
            r"public RiskProfile getRiskProfile.*\{", content, re.DOTALL
        ), "getRiskProfile should return RiskProfile"
        assert re.search(
            r"public List<RiskAlert> getPendingAlerts.*\{", content, re.DOTALL
        ), "getPendingAlerts should return List<RiskAlert>"

    def test_risk_service_uses_mapper_correctly(self, risk_control_output_dir):
        """验证 Service 正确使用 Mapper。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        assert "private final RiskBlacklistMapper riskBlacklistMapper" in content
        assert "private final RiskProfileMapper riskProfileMapper" in content

    def test_generated_code_is_syntactically_valid(self, risk_control_output_dir):
        """验证生成的 Java 代码语法基本有效（无明显语法错误）。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        open_braces = content.count("{")
        close_braces = content.count("}")
        assert open_braces == close_braces, (
            f"Mismatched braces: {open_braces} open, {close_braces} close"
        )

        open_parens = content.count("(")
        close_parens = content.count(")")
        assert open_parens == close_parens, (
            f"Mismatched parentheses: {open_parens} open, {close_parens} close"
        )

        open_brackets = content.count("[")
        close_brackets = content.count("]")
        assert open_brackets == close_brackets, (
            f"Mismatched brackets: {open_brackets} open, {close_brackets} close"
        )

    def test_risk_service_builder_pattern_usage(self, risk_control_output_dir):
        """验证代码正确使用 Builder 模式。"""
        service_file = (
            risk_control_output_dir
            / "src/main/java/risk_core/application/service/RiskControlService.java"
        )
        content = service_file.read_text(encoding="utf-8")

        assert "RiskDecision.builder()" in content
        assert ".decision(" in content
        assert ".riskLevel(" in content
        assert ".riskScore(" in content
        assert ".hitRules(" in content
        assert ".suggestion(" in content
        assert ".build()" in content
