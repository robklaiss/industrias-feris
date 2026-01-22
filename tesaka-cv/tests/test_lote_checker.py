"""
Tests unitarios para lote_checker
"""
import unittest
from unittest.mock import Mock, patch, MagicMock


class TestLoteChecker(unittest.TestCase):
    """Tests para validación y parsing de lotes"""

    def test_validate_prot_cons_lote_valid(self):
        """Test que valida dProtConsLote válido (solo dígitos)"""
        from app.sifen_client.lote_checker import validate_prot_cons_lote

        self.assertTrue(validate_prot_cons_lote("123456789"))
        self.assertTrue(validate_prot_cons_lote("1"))
        self.assertTrue(validate_prot_cons_lote("9999999999999999999999999999"))

    def test_validate_prot_cons_lote_invalid(self):
        """Test que rechaza dProtConsLote inválido"""
        from app.sifen_client.lote_checker import validate_prot_cons_lote

        self.assertFalse(validate_prot_cons_lote(""))
        self.assertFalse(validate_prot_cons_lote(None))
        self.assertFalse(validate_prot_cons_lote("abc123"))
        self.assertFalse(validate_prot_cons_lote("123-456"))
        self.assertTrue(validate_prot_cons_lote(" 123 "))  # strip() lo hace válido
        self.assertFalse(validate_prot_cons_lote("12.34"))

    def test_parse_lote_response_0361(self):
        """Test parsing de respuesta con código 0361 (processing)"""
        from app.sifen_client.lote_checker import parse_lote_response

        xml = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <rResEnviConsLoteDe xmlns="http://ekuatia.set.gov.py/sifen/xsd">
      <dCodResLot>0361</dCodResLot>
      <dMsgResLot>Lote en procesamiento</dMsgResLot>
    </rResEnviConsLoteDe>
  </soap:Body>
</soap:Envelope>"""

        result = parse_lote_response(xml)

        self.assertTrue(result["ok"])
        self.assertEqual(result["cod_res_lot"], "0361")
        self.assertEqual(result["msg_res_lot"], "Lote en procesamiento")

    def test_parse_lote_response_0362(self):
        """Test parsing de respuesta con código 0362 (done)"""
        from app.sifen_client.lote_checker import parse_lote_response

        xml = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <rResEnviConsLoteDe xmlns="http://ekuatia.set.gov.py/sifen/xsd">
      <dCodResLot>0362</dCodResLot>
      <dMsgResLot>Lote procesado exitosamente</dMsgResLot>
    </rResEnviConsLoteDe>
  </soap:Body>
</soap:Envelope>"""

        result = parse_lote_response(xml)

        self.assertTrue(result["ok"])
        self.assertEqual(result["cod_res_lot"], "0362")
        self.assertEqual(result["msg_res_lot"], "Lote procesado exitosamente")

    def test_parse_lote_response_0364(self):
        """Test parsing de respuesta con código 0364 (expired_window)"""
        from app.sifen_client.lote_checker import parse_lote_response

        xml = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <rResEnviConsLoteDe xmlns="http://ekuatia.set.gov.py/sifen/xsd">
      <dCodResLot>0364</dCodResLot>
      <dMsgResLot>Ventana de 48h expirada. Consultar por CDC individual</dMsgResLot>
    </rResEnviConsLoteDe>
  </soap:Body>
</soap:Envelope>"""

        result = parse_lote_response(xml)

        self.assertTrue(result["ok"])
        self.assertEqual(result["cod_res_lot"], "0364")
        self.assertIn("expirada", result["msg_res_lot"])

    def test_parse_lote_response_empty(self):
        """Test parsing de respuesta vacía o inválida"""
        from app.sifen_client.lote_checker import parse_lote_response

        result = parse_lote_response("")
        self.assertFalse(result["ok"])
        self.assertIsNone(result["cod_res_lot"])

        result = parse_lote_response("<invalid>xml</invalid>")
        # Debe intentar parsear aunque falle
        self.assertIsNotNone(result)

    def test_determine_status_from_cod_res_lot(self):
        """Test determinación de estado desde código de respuesta"""
        from app.sifen_client.lote_checker import determine_status_from_cod_res_lot
        from web.lotes_db import (
            LOTE_STATUS_PROCESSING,
            LOTE_STATUS_DONE,
            LOTE_STATUS_EXPIRED_WINDOW,
            LOTE_STATUS_REQUIRES_CDC,
            LOTE_STATUS_ERROR,
        )

        self.assertEqual(
            determine_status_from_cod_res_lot("0361"), LOTE_STATUS_PROCESSING
        )
        self.assertEqual(determine_status_from_cod_res_lot("0362"), LOTE_STATUS_DONE)
        self.assertEqual(
            determine_status_from_cod_res_lot("0364"), LOTE_STATUS_REQUIRES_CDC
        )
        self.assertEqual(
            determine_status_from_cod_res_lot("9999"), LOTE_STATUS_ERROR
        )
        self.assertEqual(determine_status_from_cod_res_lot(None), LOTE_STATUS_ERROR)
        self.assertEqual(determine_status_from_cod_res_lot(""), LOTE_STATUS_ERROR)


if __name__ == "__main__":
    unittest.main()

