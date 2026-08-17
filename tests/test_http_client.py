"""Shared HTTP client tests: reuse, safe close, reset."""

from launcher.meta.manifest import _new_client, reset_http_client


def test_new_client_returns_same_shared_instance() -> None:
    a = _new_client()
    b = _new_client()
    assert a is b
    a.close()  # no-op close keeps the shared pool alive
    assert a is _new_client()


def test_reset_builds_fresh_client() -> None:
    a = _new_client()
    reset_http_client()
    b = _new_client()
    assert b is not a
    reset_http_client()  # restore a clean default for other tests

