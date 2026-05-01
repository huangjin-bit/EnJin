"""EnJin 增量构建模块：只重新渲染变更的节点及其依赖。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from enjinc.ast_nodes import FnDef, ModuleDef, Program, RouteDef, StructDef
from enjinc.dependency_graph import DependencyGraph


@dataclass
class NodeChange:
    """单个节点的变更记录。"""
    node_type: str      # "struct" | "fn" | "module" | "route"
    node_name: str
    change_kind: str    # "added" | "removed" | "modified"
    diff_detail: str    # 人类可读的变更描述

    @property
    def key(self) -> str:
        return f"{self.node_type}:{self.node_name}"


@dataclass
class ChangeSet:
    """两个 Program 之间的完整变更集，含依赖传播。"""
    direct_changes: list[NodeChange]
    affected_nodes: list[NodeChange]   # 传播后受影响的节点
    unchanged_keys: set[str]           # 未变化的节点 key


def _node_key(node_type: str, node_name: str) -> str:
    return f"{node_type}:{node_name}"


def _hash_node(node) -> str:
    """计算节点的 SHA-256 hash。"""
    data = node.to_dict()
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def compute_program_diff(old_program: Program, new_program: Program) -> ChangeSet:
    """对比新旧 Program，计算变更并传播到依赖节点。"""
    changes: list[NodeChange] = []

    # 构建索引
    old_structs = {s.name: s for s in old_program.structs}
    new_structs = {s.name: s for s in new_program.structs}
    old_fns = {f.name: f for f in old_program.functions}
    new_fns = {f.name: f for f in new_program.functions}
    old_modules = {m.name: m for m in old_program.modules}
    new_modules = {m.name: m for m in new_program.modules}
    old_routes = {r.name: r for r in old_program.routes}
    new_routes = {r.name: r for r in new_program.routes}

    # Struct 变更
    _diff_layer(old_structs, new_structs, "struct", changes)
    # Fn 变更
    _diff_layer(old_fns, new_fns, "fn", changes)
    # Module 变更
    _diff_layer(old_modules, new_modules, "module", changes)
    # Route 变更
    _diff_layer(old_routes, new_routes, "route", changes)

    # 依赖传播
    dep_graph = DependencyGraph.build(new_program)
    affected = _propagate_changes(changes, dep_graph)

    # 计算未变更节点
    all_keys = set()
    for s in new_program.structs:
        all_keys.add(_node_key("struct", s.name))
    for f in new_program.functions:
        all_keys.add(_node_key("fn", f.name))
    for m in new_program.modules:
        all_keys.add(_node_key("module", m.name))
    for r in new_program.routes:
        all_keys.add(_node_key("route", r.name))

    changed_keys = {c.key for c in affected}
    unchanged = all_keys - changed_keys

    return ChangeSet(
        direct_changes=changes,
        affected_nodes=affected,
        unchanged_keys=unchanged,
    )


def _diff_layer(
    old_map: dict, new_map: dict, layer_name: str, changes: list[NodeChange],
) -> None:
    """对比单层的变更。"""
    old_names = set(old_map.keys())
    new_names = set(new_map.keys())

    for name in new_names - old_names:
        changes.append(NodeChange(
            node_type=layer_name, node_name=name,
            change_kind="added", diff_detail=f"新增 {layer_name} '{name}'",
        ))

    for name in old_names - new_names:
        changes.append(NodeChange(
            node_type=layer_name, node_name=name,
            change_kind="removed", diff_detail=f"删除 {layer_name} '{name}'",
        ))

    for name in old_names & new_names:
        old_hash = _hash_node(old_map[name])
        new_hash = _hash_node(new_map[name])
        if old_hash != new_hash:
            changes.append(NodeChange(
                node_type=layer_name, node_name=name,
                change_kind="modified", diff_detail=f"{layer_name} '{name}' 内容变更",
            ))


def _propagate_changes(
    direct_changes: list[NodeChange], dep_graph: DependencyGraph,
) -> list[NodeChange]:
    """将直接变更沿依赖图传播到受影响的节点。

    传播规则：
    - struct 变更 → 使用该 struct 的所有 fn
    - fn 变更 → 使用该 fn 的所有 module
    - module 变更 → 使用该 module 的所有 route
    """
    affected_keys: set[str] = set()
    affected_list: list[NodeChange] = list(direct_changes)

    for c in direct_changes:
        affected_keys.add(c.key)

    # 第一轮：struct → fn
    for c in direct_changes:
        if c.node_type == "struct":
            for fn_name, struct_names in dep_graph.fn_to_structs.items():
                if c.node_name in struct_names:
                    key = _node_key("fn", fn_name)
                    if key not in affected_keys:
                        affected_keys.add(key)
                        affected_list.append(NodeChange(
                            node_type="fn", node_name=fn_name,
                            change_kind="modified",
                            diff_detail=f"fn '{fn_name}' 因依赖 struct '{c.node_name}' 变更而需重新渲染",
                        ))

    # 第二轮：fn → module
    for c in list(affected_list):
        if c.node_type == "fn":
            for mod_name, fn_names in dep_graph.module_to_fns.items():
                if c.node_name in fn_names:
                    key = _node_key("module", mod_name)
                    if key not in affected_keys:
                        affected_keys.add(key)
                        affected_list.append(NodeChange(
                            node_type="module", node_name=mod_name,
                            change_kind="modified",
                            diff_detail=f"module '{mod_name}' 因依赖 fn '{c.node_name}' 变更而需重新渲染",
                        ))

    # 第三轮：module → route
    for c in list(affected_list):
        if c.node_type == "module":
            for route_name, mod_names in dep_graph.route_to_modules.items():
                if c.node_name in mod_names:
                    key = _node_key("route", route_name)
                    if key not in affected_keys:
                        affected_keys.add(key)
                        affected_list.append(NodeChange(
                            node_type="route", node_name=route_name,
                            change_kind="modified",
                            diff_detail=f"route '{route_name}' 因依赖 module '{c.node_name}' 变更而需重新渲染",
                        ))

    return affected_list


def compute_render_plan(change_set: ChangeSet) -> list[str]:
    """生成有序渲染清单，按四层顺序：struct → fn → module → route。"""
    order = {"struct": 0, "fn": 1, "module": 2, "route": 3}
    # 去重并按层排序
    seen: set[str] = set()
    nodes: list[NodeChange] = []
    for c in change_set.affected_nodes:
        if c.key not in seen:
            seen.add(c.key)
            nodes.append(c)

    nodes.sort(key=lambda c: order.get(c.node_type, 99))
    return [c.key for c in nodes]


# ============================================================
# Build Manifest（构建清单）
# ============================================================

@dataclass
class BuildManifest:
    """跟踪上次构建状态，用于检测增量变更。

    存储为 .enjinc/manifest.json。
    """
    program_hash: str
    target_lang: str
    node_hashes: dict[str, str] = field(default_factory=dict)
    built_files: dict[str, str] = field(default_factory=dict)

    MANIFEST_DIR = ".enjinc"
    MANIFEST_FILE = "manifest.json"

    @classmethod
    def load(cls, project_dir: Path) -> Optional[BuildManifest]:
        """从项目目录加载 manifest。"""
        path = project_dir / cls.MANIFEST_DIR / cls.MANIFEST_FILE
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            program_hash=data.get("program_hash", ""),
            target_lang=data.get("target_lang", ""),
            node_hashes=data.get("node_hashes", {}),
            built_files=data.get("built_files", {}),
        )

    def save(self, project_dir: Path) -> None:
        """保存 manifest 到项目目录。"""
        dir_path = project_dir / self.MANIFEST_DIR
        dir_path.mkdir(exist_ok=True)
        path = dir_path / self.MANIFEST_FILE
        path.write_text(json.dumps({
            "program_hash": self.program_hash,
            "target_lang": self.target_lang,
            "node_hashes": self.node_hashes,
            "built_files": self.built_files,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def compute_for(
        cls, program: Program, target_lang: str, output_dir: Path,
    ) -> BuildManifest:
        """从当前构建结果生成 manifest。"""
        program_hash = _hash_node(program)

        node_hashes: dict[str, str] = {}
        built_files: dict[str, str] = {}

        for s in program.structs:
            node_hashes[_node_key("struct", s.name)] = _hash_node(s)
        for f in program.functions:
            node_hashes[_node_key("fn", f.name)] = _hash_node(f)
        for m in program.modules:
            node_hashes[_node_key("module", m.name)] = _hash_node(m)
        for r in program.routes:
            node_hashes[_node_key("route", r.name)] = _hash_node(r)

        # 记录输出文件
        if output_dir.exists():
            for p in output_dir.rglob("*"):
                if p.is_file() and not p.name.endswith(('.lock', '.json')):
                    rel = p.relative_to(output_dir)
                    built_files[str(rel)] = _hash_file(p)

        return cls(
            program_hash=program_hash,
            target_lang=target_lang,
            node_hashes=node_hashes,
            built_files=built_files,
        )


def _hash_file(path: Path) -> str:
    """计算文件内容的 hash。"""
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:16]
