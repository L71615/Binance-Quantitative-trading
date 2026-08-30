from app.crypto_store import save_secret, load_secret, delete_secret, SERVICE_NAME


def _slot() -> str:
    return SERVICE_NAME + ":test"


def test_roundtrip(monkeypatch):
    # Use a unique slug for this test
    slug = "test_roundtrip_xyz"
    assert load_secret(slug) is None
    save_secret(slug, "supersecret")
    assert load_secret(slug) == "supersecret"
    delete_secret(slug)
    assert load_secret(slug) is None
