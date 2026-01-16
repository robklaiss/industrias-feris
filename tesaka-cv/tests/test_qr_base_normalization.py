import os

import pytest

from app.sifen_client.xmlsec_signer import (
    _normalize_qr_base,
    _get_env_qr_base,
    QR_URL_BASES,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://x/qr?", "https://x/qr"),
        ("https://x/qr/?", "https://x/qr"),
        ("https://x/qr/", "https://x/qr"),
        ("https://x/qr", "https://x/qr"),
    ],
)
def test_normalize_qr_base_variations(raw, expected):
    assert _normalize_qr_base(raw) == expected


def test_qr_url_bases_are_normalized():
    for base in QR_URL_BASES.values():
        assert not base.endswith("?")
        assert not base.endswith("/")


def test_get_env_qr_base_respects_env(monkeypatch):
    monkeypatch.setenv("SIFEN_ENV", "test")
    base_test = _get_env_qr_base()
    assert base_test == QR_URL_BASES["TEST"]
    assert not base_test.endswith("?")
    assert not base_test.endswith("/")

    monkeypatch.setenv("SIFEN_ENV", "prod")
    base_prod = _get_env_qr_base()
    assert base_prod == QR_URL_BASES["PROD"]
    assert not base_prod.endswith("?")
    assert not base_prod.endswith("/")
