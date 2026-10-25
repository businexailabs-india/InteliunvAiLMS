from app.passwords import hash_password, verify_password


def test_password_round_trip() -> None:
    encoded = hash_password("Demo@2025")
    assert verify_password("Demo@2025", encoded)
    assert not verify_password("demo@2025", encoded)
    assert not verify_password("Demo@2025", "not-a-hash")
