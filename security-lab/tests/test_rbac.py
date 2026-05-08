import json
from pathlib import Path

from app.rbac import RBACPolicy


def test_rbac_permissions(tmp_path):
    p = tmp_path / "rbac.json"
    p.write_text(
        json.dumps(
            {
                "roles": {"a": {"permissions": ["chat"]}},
                "default_role": "a",
            }
        ),
        encoding="utf-8",
    )
    pol = RBACPolicy(str(p))
    assert pol.allowed("a", "chat")
    assert not pol.allowed("a", "tools.shell")
