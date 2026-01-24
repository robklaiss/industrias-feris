import json
from pathlib import Path

import pytest

from tools.follow_lote import parse_consulta_lote_response


FIXTURES_DIR = Path(__file__).with_name("test_follow_lote_parse_fixtures")


@pytest.mark.parametrize(
    "fixture_name",
    [
        "gResProcLote_dict.json",
        "gResProcLote_list.json",
    ],
)
def test_parse_consulta_lote_response_handles_varied_shapes(fixture_name: str):
    payload = json.loads((FIXTURES_DIR / fixture_name).read_text(encoding="utf-8"))

    docs = parse_consulta_lote_response(payload)

    assert len(docs) == 2
    ids = {doc.get("id") or doc.get("cdc") for doc in docs}
    assert ids == {"0101", "0102"}
    for doc in docs:
        assert doc.get("dEstRes") in {"Aprobado", "Rechazado"}
        assert doc.get("dCodRes") in {"0200", "0301"}
        assert doc.get("dMsgRes")
