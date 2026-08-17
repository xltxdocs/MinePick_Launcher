import json
import logging

from launcher.auth.models import Account
from launcher.auth.storage import AccountStore


def _offline(id_: str, name: str) -> Account:
    return Account(id=id_, type="offline", username=name, uuid=id_, created_at=1.0)


def test_missing_file_returns_empty(ws_tmp):
    assert AccountStore(ws_tmp / "accounts.json").load() == {}


def test_roundtrip(ws_tmp):
    path = ws_tmp / "accounts.json"
    store = AccountStore(path)
    acc = _offline("uuid-1", "Steve")
    saved = store.save({"uuid-1": acc})
    assert saved == path
    assert AccountStore(path).load() == {"uuid-1": acc}
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["accounts"]["uuid-1"]["username"] == "Steve"


def test_unknown_fields_ignored(ws_tmp):
    path = ws_tmp / "accounts.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "accounts": {
                    "uuid-1": {
                        "id": "uuid-1",
                        "type": "offline",
                        "username": "Steve",
                        "uuid": "uuid-1",
                        "created_at": 1.0,
                        "future_field": 123,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    accounts = AccountStore(path).load()
    assert accounts["uuid-1"].username == "Steve"


def test_corrupt_entry_skipped(ws_tmp, caplog):
    path = ws_tmp / "accounts.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "accounts": {
                    "bad": {"type": "offline"},  # missing required fields
                    "uuid-1": {
                        "id": "uuid-1",
                        "type": "offline",
                        "username": "Steve",
                        "uuid": "uuid-1",
                        "created_at": 1.0,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING):
        accounts = AccountStore(path).load()
    assert list(accounts) == ["uuid-1"]
    assert "bad" in caplog.text
