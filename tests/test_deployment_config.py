from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_production_workflow_passes_aura_user_and_database() -> None:
    workflow = (
        REPO_ROOT / ".github" / "workflows" / "deploy-gcp.yml"
    ).read_text(encoding="utf-8")

    assert "NEO4J_USER: ${{ vars.NEO4J_USER || 'neo4j' }}" in workflow
    assert (
        "NEO4J_DATABASE: ${{ vars.NEO4J_DATABASE || 'neo4j' }}"
        in workflow
    )
    assert "Neo4jUser = $env:NEO4J_USER" in workflow
    assert "Neo4jDatabase = $env:NEO4J_DATABASE" in workflow


def test_manual_deploy_defaults_match_the_aura_instance() -> None:
    script = (
        REPO_ROOT / "scripts" / "gcp" / "deploy.ps1"
    ).read_text(encoding="utf-8")

    assert '[string]$Neo4jUser = "neo4j"' in script
    assert '[string]$Neo4jDatabase = "neo4j"' in script
