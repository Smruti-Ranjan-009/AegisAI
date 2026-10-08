import json

from aegis_rag_ingestion.cli import main


def test_inspect_command_needs_no_database_or_model(capsys) -> None:
    assert main(["inspect", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["documents"] == 15
    assert output["chunks"] >= 15
    assert "dependency-light" in output["note"]
