import pytest

from tools.auto_fix_0160_loop import (
    LoteStatus,
    is_processing_status,
    should_stop_without_0160,
    status_contains_0160,
)


def _status(
    *,
    lote_cod: str | None = None,
    lote_msg: str | None = None,
    de_cod: str | None = None,
    de_estado: str | None = None,
    de_msg: str | None = None,
) -> LoteStatus:
    return LoteStatus(
        dCodResLot=lote_cod,
        dMsgResLot=lote_msg,
        de_cdc=None,
        de_estado=de_estado,
        de_cod=de_cod,
        de_msg=de_msg,
    )


def test_processing_status_detects_0361_and_keywords():
    st = _status(lote_cod="0361", lote_msg="En procesamiento")
    assert is_processing_status(st)

    st2 = _status(de_cod="0361", de_estado="Processing")
    assert is_processing_status(st2)

    st3 = _status(lote_msg="El lote sigue en procesamiento")
    assert is_processing_status(st3)


def test_should_not_stop_when_processing_without_0160():
    st = _status(lote_cod="0361", lote_msg="En procesamiento", de_cod="")
    assert not should_stop_without_0160(st)


def test_should_stop_when_concluded_without_0160():
    st = _status(lote_cod="0362", de_cod="0301", de_estado="Concluido", de_msg="Sin errores")
    assert should_stop_without_0160(st)


def test_should_not_stop_if_concluded_with_0160_message():
    st = _status(lote_cod="0362", de_cod="0160", de_estado="Concluido", de_msg="Error 0160")
    assert not should_stop_without_0160(st)


def test_status_contains_0160_detects_any_field():
    st = _status(lote_cod="0362", de_cod="", de_msg="0160 en mensaje")
    assert status_contains_0160(st)

    st2 = _status(lote_cod="0160", de_cod="", de_msg="")
    assert status_contains_0160(st2)
