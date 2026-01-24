from tools.consulta_lote_de import _parse_consulta_lote_response  # ajusta si el helper se llama distinto

SOAP_RET_ENV = """<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
  <env:Header/>
  <env:Body>
    <ns2:rRetEnviDe xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
      <ns2:rProtDe>
        <ns2:dFecProc>2026-01-24T01:43:05-03:00</ns2:dFecProc>
        <ns2:dEstRes>Rechazado</ns2:dEstRes>
        <ns2:gResProc>
          <ns2:dCodRes>0160</ns2:dCodRes>
          <ns2:dMsgRes>XML Mal Formado.</ns2:dMsgRes>
        </ns2:gResProc>
      </ns2:rProtDe>
    </ns2:rRetEnviDe>
  </env:Body>
</env:Envelope>
"""

def test_parse_rRetEnviDe_maps_to_lote_fields():
    d = _parse_consulta_lote_response(SOAP_RET_ENV)
    assert d.get("dFecProc") == "2026-01-24T01:43:05-03:00"
    assert d.get("dCodResLot") == "0160"
    assert d.get("dMsgResLot") == "XML Mal Formado."
    assert d.get("fallback_shape") == "rRetEnviDe"
