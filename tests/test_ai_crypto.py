from app.ai.crypto import decrypt_secret, encrypt_secret


def test_encrypt_then_decrypt_round_trips() -> None:
    ciphertext = encrypt_secret("sk-real-secret-key", "the-deployment-secret")

    assert ciphertext != "sk-real-secret-key"
    assert decrypt_secret(ciphertext, "the-deployment-secret") == "sk-real-secret-key"


def test_decrypt_with_the_wrong_secret_returns_none_instead_of_raising() -> None:
    ciphertext = encrypt_secret("sk-real-secret-key", "secret-a")

    assert decrypt_secret(ciphertext, "secret-b") is None
