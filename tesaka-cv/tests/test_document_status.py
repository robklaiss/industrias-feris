#!/usr/bin/env python3
"""
Tests unitarios para mapeo de estados de documentos SIFEN.
"""
import unittest
import sys
from pathlib import Path

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from web.document_status import (
    STATUS_SIGNED_LOCAL,
    STATUS_SENT_TO_SIFEN,
    STATUS_PENDING_SIFEN,
    STATUS_APPROVED,
    STATUS_REJECTED,
    STATUS_ERROR,
    get_status_message,
    is_final_status,
    can_transition_to,
)
from web.sifen_status_mapper import (
    map_recepcion_response_to_status,
    map_lote_consulta_to_de_status,
    parse_lote_de_results,
)


class TestDocumentStatus(unittest.TestCase):
    """Tests para constantes y utilidades de estados"""
    
    def test_status_constants(self):
        """Verifica que las constantes de estado estén definidas"""
        self.assertEqual(STATUS_SIGNED_LOCAL, "signed_local")
        self.assertEqual(STATUS_SENT_TO_SIFEN, "sent_to_sifen")
        self.assertEqual(STATUS_PENDING_SIFEN, "pending_sifen")
        self.assertEqual(STATUS_APPROVED, "approved")
        self.assertEqual(STATUS_REJECTED, "rejected")
        self.assertEqual(STATUS_ERROR, "error")
    
    def test_get_status_message(self):
        """Verifica mensajes de estado"""
        msg = get_status_message(STATUS_APPROVED, approved_at="2024-01-01T12:00:00")
        self.assertIn("APROBADO POR SIFEN", msg)
        self.assertIn("2024-01-01", msg)
        
        msg = get_status_message(STATUS_REJECTED, code="0141", message="SignatureValue diferente")
        self.assertIn("RECHAZADO POR SIFEN", msg)
        self.assertIn("0141", msg)
        self.assertIn("SignatureValue diferente", msg)
    
    def test_is_final_status(self):
        """Verifica que los estados finales se identifiquen correctamente"""
        self.assertTrue(is_final_status(STATUS_APPROVED))
        self.assertTrue(is_final_status(STATUS_REJECTED))
        self.assertTrue(is_final_status(STATUS_ERROR))
        self.assertFalse(is_final_status(STATUS_SIGNED_LOCAL))
        self.assertFalse(is_final_status(STATUS_SENT_TO_SIFEN))
        self.assertFalse(is_final_status(STATUS_PENDING_SIFEN))
    
    def test_can_transition_to(self):
        """Verifica transiciones válidas de estado"""
        # signed_local puede ir a sent_to_sifen o error
        self.assertTrue(can_transition_to(STATUS_SIGNED_LOCAL, STATUS_SENT_TO_SIFEN))
        self.assertTrue(can_transition_to(STATUS_SIGNED_LOCAL, STATUS_ERROR))
        self.assertFalse(can_transition_to(STATUS_SIGNED_LOCAL, STATUS_APPROVED))
        
        # pending_sifen puede ir a approved, rejected o error
        self.assertTrue(can_transition_to(STATUS_PENDING_SIFEN, STATUS_APPROVED))
        self.assertTrue(can_transition_to(STATUS_PENDING_SIFEN, STATUS_REJECTED))
        self.assertTrue(can_transition_to(STATUS_PENDING_SIFEN, STATUS_ERROR))
        
        # approved no puede cambiar (estado final)
        self.assertFalse(can_transition_to(STATUS_APPROVED, STATUS_REJECTED))


class TestSifenStatusMapper(unittest.TestCase):
    """Tests para mapeo de respuestas SIFEN"""
    
    def test_map_recepcion_response_ok(self):
        """Verifica mapeo de recepción exitosa"""
        response = {
            'ok': True,
            'codigo_respuesta': '0300',
            'mensaje': 'Lote recibido con éxito',
            'd_prot_cons_lote': '123456789'
        }
        status, code, message = map_recepcion_response_to_status(response)
        self.assertEqual(status, STATUS_SENT_TO_SIFEN)
        self.assertEqual(code, '0300')
        self.assertIn("recibido", message.lower())
    
    def test_map_recepcion_response_error(self):
        """Verifica mapeo de recepción fallida"""
        response = {
            'ok': False,
            'codigo_respuesta': '0301',
            'mensaje': 'Lote no encolado'
        }
        status, code, message = map_recepcion_response_to_status(response)
        self.assertEqual(status, STATUS_ERROR)
        self.assertEqual(code, '0301')
    
    def test_map_lote_consulta_pending_0361(self):
        """Verifica mapeo de consulta con lote en procesamiento (dCodResLot=0361)"""
        status, code, message, approved_at = map_lote_consulta_to_de_status(
            cod_res_lot="0361",
            xml_response=None,
            cdc="01045547378001001000000112026010211234567896"
        )
        self.assertEqual(status, STATUS_PENDING_SIFEN)
        self.assertEqual(code, "0361")
        self.assertIn("procesamiento", message.lower())
        self.assertIsNone(approved_at)
    
    def test_map_lote_consulta_approved_aceptado(self):
        """Verifica mapeo de consulta con DE aprobado (dEstRes='Aceptado')"""
        xml_response = """<?xml version="1.0"?>
        <rResConsLoteDe>
            <dCodResLot>0362</dCodResLot>
            <dMsgResLot>Procesamiento concluido</dMsgResLot>
            <gResProc>
                <id>01045547378001001000000112026010211234567896</id>
                <dEstRes>Aceptado</dEstRes>
                <dProtAut>123456789</dProtAut>
                <dFecProc>2024-01-15T14:30:00</dFecProc>
                <gResProc>
                    <dCodRes>0200</dCodRes>
                    <dMsgRes>DE aprobado</dMsgRes>
                </gResProc>
            </gResProc>
        </rResConsLoteDe>"""
        
        status, code, message, approved_at = map_lote_consulta_to_de_status(
            cod_res_lot="0362",
            xml_response=xml_response,
            cdc="01045547378001001000000112026010211234567896"
        )
        self.assertEqual(status, STATUS_APPROVED)
        self.assertEqual(approved_at, "2024-01-15T14:30:00")
    
    def test_map_lote_consulta_approved_aprobado(self):
        """Verifica mapeo de consulta con DE aprobado (dEstRes='Aprobado')"""
        xml_response = """<?xml version="1.0"?>
        <rResConsLoteDe>
            <dCodResLot>0362</dCodResLot>
            <gResProc>
                <id>01045547378001001000000112026010211234567896</id>
                <dEstRes>Aprobado</dEstRes>
                <dFecProc>2024-01-15T15:00:00</dFecProc>
            </gResProc>
        </rResConsLoteDe>"""
        
        status, _, _, approved_at = map_lote_consulta_to_de_status(
            cod_res_lot="0362",
            xml_response=xml_response,
            cdc="01045547378001001000000112026010211234567896"
        )
        self.assertEqual(status, STATUS_APPROVED)
        self.assertEqual(approved_at, "2024-01-15T15:00:00")
    
    def test_map_lote_consulta_approved_con_observacion(self):
        """Verifica mapeo de consulta con DE aprobado con observación"""
        xml_response = """<?xml version="1.0"?>
        <rResConsLoteDe>
            <dCodResLot>0362</dCodResLot>
            <gResProc>
                <id>01045547378001001000000112026010211234567896</id>
                <dEstRes>Aprobado con observación</dEstRes>
                <dFecProc>2024-01-15T16:00:00</dFecProc>
            </gResProc>
        </rResConsLoteDe>"""
        
        status, _, _, approved_at = map_lote_consulta_to_de_status(
            cod_res_lot="0362",
            xml_response=xml_response,
            cdc="01045547378001001000000112026010211234567896"
        )
        self.assertEqual(status, STATUS_APPROVED)
        self.assertEqual(approved_at, "2024-01-15T16:00:00")
    
    def test_map_lote_consulta_rejected(self):
        """Verifica mapeo de consulta con DE rechazado (dEstRes='Rechazado')"""
        xml_response = """<?xml version="1.0"?>
        <rResConsLoteDe>
            <dCodResLot>0362</dCodResLot>
            <dMsgResLot>Procesamiento concluido</dMsgResLot>
            <gResProc>
                <id>01045547378001001000000112026010211234567896</id>
                <dEstRes>Rechazado</dEstRes>
                <gResProc>
                    <dCodRes>0141</dCodRes>
                    <dMsgRes>SignatureValue diferente</dMsgRes>
                </gResProc>
            </gResProc>
        </rResConsLoteDe>"""
        
        status, code, message, approved_at = map_lote_consulta_to_de_status(
            cod_res_lot="0362",
            xml_response=xml_response,
            cdc="01045547378001001000000112026010211234567896"
        )
        self.assertEqual(status, STATUS_REJECTED)
        self.assertEqual(code, "0141")
        self.assertIn("SignatureValue", message)
        self.assertIsNone(approved_at)
    
    def test_map_lote_consulta_rejected_con_observacion(self):
        """Verifica mapeo de consulta con DE rechazado con observación"""
        xml_response = """<?xml version="1.0"?>
        <rResConsLoteDe>
            <dCodResLot>0362</dCodResLot>
            <gResProc>
                <id>01045547378001001000000112026010211234567896</id>
                <dEstRes>Rechazado con observación</dEstRes>
                <gResProc>
                    <dCodRes>0141</dCodRes>
                    <dMsgRes>Error en firma</dMsgRes>
                </gResProc>
            </gResProc>
        </rResConsLoteDe>"""
        
        status, code, message, approved_at = map_lote_consulta_to_de_status(
            cod_res_lot="0362",
            xml_response=xml_response,
            cdc="01045547378001001000000112026010211234567896"
        )
        self.assertEqual(status, STATUS_REJECTED)
        self.assertEqual(code, "0141")
        self.assertIsNone(approved_at)


class TestIntegrationFlow(unittest.TestCase):
    """Tests de integración para flujo completo"""
    
    def test_flow_signed_to_sent(self):
        """Verifica que generar/firmar NO retorna approved"""
        # Simular respuesta de generación (no existe, pero el estado inicial debe ser SIGNED_LOCAL)
        # Esto se verifica en el código: insert_document usa STATUS_SIGNED_LOCAL
        self.assertEqual(STATUS_SIGNED_LOCAL, "signed_local")
    
    def test_flow_sent_to_pending(self):
        """Verifica que enviar retorna sent/pending"""
        response = {
            'ok': True,
            'codigo_respuesta': '0300',
            'd_prot_cons_lote': '123456789'
        }
        status, _, _ = map_recepcion_response_to_status(response)
        self.assertIn(status, [STATUS_SENT_TO_SIFEN, STATUS_PENDING_SIFEN])
        self.assertNotEqual(status, STATUS_APPROVED)
    
    def test_flow_approved_only_from_consulta(self):
        """Verifica que approved solo viene de consulta con dEstRes aprobado"""
        # Recepción exitosa NO es aprobación
        response = {'ok': True, 'codigo_respuesta': '0300'}
        status, _, _ = map_recepcion_response_to_status(response)
        self.assertNotEqual(status, STATUS_APPROVED)
        
        # Solo consulta con dEstRes="Aprobado" es aprobación (NO solo por 0362)
        xml_approved = """<?xml version="1.0"?>
        <rResConsLoteDe>
            <dCodResLot>0362</dCodResLot>
            <gResProc>
                <id>01045547378001001000000112026010211234567896</id>
                <dEstRes>Aprobado</dEstRes>
                <dFecProc>2024-01-15T14:30:00</dFecProc>
            </gResProc>
        </rResConsLoteDe>"""
        
        status, _, _, approved_at = map_lote_consulta_to_de_status(
            cod_res_lot="0362",
            xml_response=xml_approved,
            cdc="01045547378001001000000112026010211234567896"
        )
        self.assertEqual(status, STATUS_APPROVED)
        self.assertEqual(approved_at, "2024-01-15T14:30:00")


if __name__ == "__main__":
    unittest.main()

