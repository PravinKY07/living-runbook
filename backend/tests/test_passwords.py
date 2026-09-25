from app.security.passwords import hash_password, verify_password


def test_password_hash_is_not_plaintext():
    password = "correct horse battery staple"

    password_hash = hash_password(password)

    assert password_hash != password
    assert password not in password_hash


def test_correct_password_verifies():
    password = "correct horse battery staple"
    password_hash = hash_password(password)

    assert verify_password(password, password_hash) is True


def test_wrong_password_is_rejected():
    password_hash = hash_password("correct horse battery staple")

    assert verify_password("wrong password", password_hash) is False


def test_invalid_hash_is_rejected():
    assert verify_password("any password", "not-a-valid-argon2-hash") is False
