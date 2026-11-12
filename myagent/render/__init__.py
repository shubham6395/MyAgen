from __future__ import annotations

from myagent.render import sections
from myagent.types import Role, Section

RENDERERS = {
    "identity_card": sections.identity_card,
    "tech_stack_table": sections.tech_stack_table,
    "file_tree": sections.file_tree,
    "quickstart_commands": sections.quickstart_commands,
    "doc_index": sections.doc_index,
    "feature_inventory": sections.feature_inventory,
    "module_map": sections.module_map,
    "component_diagram": sections.component_diagram,
    "entrypoints_table": sections.entrypoints_table,
    "pattern_evidence": sections.pattern_evidence,
    "component_inventory": sections.component_inventory,
    "model_tables": sections.model_tables,
    "er_diagram": sections.er_diagram,
    "migrations_table": sections.migrations_table,
    "endpoint_tables": sections.endpoint_tables,
    "schema_details": sections.schema_details,
    "repo_commands": sections.repo_commands,
    "convention_configs": sections.convention_configs,
    "module_inventory": sections.module_inventory,
    "feature_map": sections.feature_map,
    "prerequisites": sections.prerequisites,
    "env_table": sections.env_table,
    "commands_table": sections.commands_table,
    "auth_evidence": sections.auth_evidence,
    "security_deps": sections.security_deps,
    "mcp_inventory": sections.mcp_inventory,
    "integrations_table": sections.integrations_table,
    "tests_inventory": sections.tests_inventory,
    "logging_inventory": sections.logging_inventory,
    "failure_surface": sections.failure_surface,
    "system_context_diagram": sections.system_context_diagram,
    "full_component_diagram": sections.full_component_diagram,
    "request_sequence": sections.request_sequence,
    "endpoint_index": sections.endpoint_index,
    "model_index": sections.model_index,
    "env_integration_inventory": sections.env_integration_inventory,
}


def render_section(section: Section, facts: dict, role: Role) -> str:
    return RENDERERS[section.renderer](facts, role)