from pathlib import Path

from event_lead_ops.config import load_yaml


def test_all_example_yaml_files_parse():
    for path in Path("config").glob("*.example.yaml"):
        assert load_yaml(path)
