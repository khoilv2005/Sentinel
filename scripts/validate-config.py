#!/usr/bin/env python3
import json
from pathlib import Path

import yaml

root = Path(__file__).resolve().parents[1]
for path in (root / "deploy" / "grafana" / "dashboards").glob("*.json"):
    json.loads(path.read_text(encoding="utf-8"))
for path in (root / "deploy").rglob("*.yml"):
    yaml.safe_load(path.read_text(encoding="utf-8"))
yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
print("SentinelView configuration files parsed successfully")
