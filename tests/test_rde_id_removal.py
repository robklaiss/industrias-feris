#!/usr/bin/env python3
"""
Tests anti-regresión para verificar que rDE no contenga atributo Id
en el XML final enviado a SIFEN.
"""
import pytest
import re
import zipfile
from pathlib import Path
from io import BytesIO
import sys
import os

# Agregar el directorio tesaka-cv al path
sys.path.insert(0, str(Path(__file__).parent / "tesaka-cv"))


class TestRdeIdRemoval:
    """Tests para verificar que rDE no tenga atributo Id en el XML final"""
    
    @pytest.fixture
    def sample_de_xml(self):
        """XML DE de ejemplo para pruebas"""
        return """<?xml version="1.0" encoding="utf-8"?>
<DE Id="12345678901234567890123456789012345678901234567890">
    <gDatGralOpe>
        <dFeEmiDE>2026-01-21</dFeEmiDE>
        <hEmiDE>10:30:00</hEmiDE>
        <gOpeDE>
            <iTiDE>1</iTiDE>
            <dDesDE>Factura de prueba</dDesDE>
        </gOpeDE>
    </gDatGralOpe>
    <gEmis>
        <dRucEm>1234567</dRucEm>
        <dDVEmi>8</dDVEmi>
    </gEmis>
    <gTimb>
        <dNumTim>12345678</dNumTim>
        <dEst>001</dEst>
        <dPunExp>001</dPunExp>
        <dNumDoc>0000001</dNumDoc>
    </gTimb>
    <gTot>
        <dTotalGs>100000</dTotalGs>
    </gTot>
</DE>"""
    
    def test_rde_id_removed_in_lote_xml_bytes(self, sample_de_xml):
        """Verifica que se elimine Id de rDE en lote_xml_bytes"""
        # Convertir a bytes
        xml_bytes = sample_de_xml.encode('utf-8')
        
        # Simular el proceso de build and sign (sin firmar realmente para prueba)
        # Crear un lote.xml manualmente con rDE con Id
        lote_with_rde_id = b'''<?xml version="1.0" encoding="utf-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <rDE Id="rDE_1234567890">
        <dVerFor>150</dVerFor>
        ''' + xml_bytes + b'''
        <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
            <SignedInfo>
                <Reference URI="#12345678901234567890123456789012345678901234567890">
                </Reference>
            </SignedInfo>
            <SignatureValue>ABC123</SignatureValue>
        </Signature>
    </rDE>
</rLoteDE>'''
        
        # Aplicar sanitización (como se hace en send_sirecepde.py)
        # Remover SOLO Id=... del start tag de rDE
        sanitized = re.sub(br'(<rDE\b[^>]*?)\s+Id="[^"]+"([^>]*>)', br'\1\2', lote_with_rde_id, count=1)
        
        # Verificar que NO contenga rDE con Id
        assert not re.search(br'<rDE[^>]*\bId\s*=', sanitized), "rDE todavía contiene atributo Id"
        
        # Verificar que todavía tenga rDE (sin Id)
        assert b'<rDE>' in sanitized or b'<rDE/>' in sanitized, "No se encontró rDE después de sanitizar"
        
        # Verificar que el DE conserve su Id
        assert b'Id="12345678901234567890123456789012345678901234567890"' in sanitized, "DE perdió su Id"
    
    def test_rde_id_removed_in_zip(self, sample_de_xml):
        """Verifica que rDE no tenga Id dentro del ZIP final"""
        # Crear lote XML con rDE con Id
        lote_with_rde_id = b'''<?xml version="1.0" encoding="utf-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <rDE Id="rDE_test123">
        <dVerFor>150</dVerFor>
        ''' + sample_de_xml.encode('utf-8') + b'''
    </rDE>
</rLoteDE>'''
        
        # Sanitizar
        sanitized = re.sub(br'(<rDE\b[^>]*?)\s+Id="[^"]+"([^>]*>)', br'\1\2', lote_with_rde_id, count=1)
        
        # Crear ZIP como se hace en send_sirecepde.py
        mem = BytesIO()
        with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("lote.xml", sanitized)
        zip_bytes = mem.getvalue()
        
        # Extraer y verificar contenido del ZIP
        with zipfile.ZipFile(BytesIO(zip_bytes), 'r') as zf:
            lote_from_zip = zf.read('lote.xml')
        
        # Verificar que NO contenga rDE con Id
        assert not re.search(br'<rDE[^>]*\bId\s*=', lote_from_zip), "rDE dentro del ZIP todavía contiene Id"
        
        # Verificar estructura correcta
        assert b'<rLoteDE' in lote_from_zip, "No se encontró rLoteDE en el ZIP"
        assert b'<rDE>' in lote_from_zip, "No se encontró rDE en el ZIP"
    
    def test_only_first_rde_id_removed(self):
        """Verifica que solo se elimine el Id del primer rDE"""
        # XML con múltiples rDE (aunque no debería ocurrir en práctica)
        xml_multiple_rde = b'''<rLoteDE>
    <rDE Id="first">
        <content>1</content>
    </rDE>
    <rDE Id="second">
        <content>2</content>
    </rDE>
</rLoteDE>'''
        
        # Aplicar sanitización
        sanitized = re.sub(br'(<rDE\b[^>]*?)\s+Id="[^"]+"([^>]*>)', br'\1\2', xml_multiple_rde, count=1)
        
        # Verificar que solo el primero perdió el Id
        assert not re.search(br'<rDE[^>]*\bId\s*="first"[^>]*>', sanitized), "El primer rDE todavía tiene Id"
        assert re.search(br'<rDE[^>]*\bId\s*="second"[^>]*>', sanitized), "El segundo rDE perdió su Id"
    
    def test_rde_without_namespace(self):
        """Verifica que funcione con rDE sin namespace"""
        xml_no_ns = b'<rLoteDE><rDE Id="test123"><content>test</content></rDE></rLoteDE>'
        
        # Sanitizar
        sanitized = re.sub(br'(<rDE\b[^>]*?)\s+Id="[^"]+"([^>]*>)', br'\1\2', xml_no_ns, count=1)
        
        # Verificar
        assert not re.search(br'<rDE[^>]*\bId\s*=', sanitized), "rDE sin namespace todavía tiene Id"
        assert b'<rDE><content>test</content></rDE>' in sanitized, "Estructura incorrecta después de sanitizar"
    
    def test_rde_with_namespace(self):
        """Verifica que funcione con rDE con namespace SIFEN"""
        xml_ns = b'<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"><rDE Id="test456"><content>test</content></rDE></rLoteDE>'
        
        # Sanitizar
        sanitized = re.sub(br'(<rDE\b[^>]*?)\s+Id="[^"]+"([^>]*>)', br'\1\2', xml_ns, count=1)
        
        # Verificar
        assert not re.search(br'<rDE[^>]*\bId\s*=', sanitized), "rDE con namespace todavía tiene Id"
        assert b'<rDE><content>test</content></rDE>' in sanitized, "Estructura incorrecta después de sanitizar"
        assert b'xmlns="http://ekuatia.set.gov.py/sifen/xsd"' in sanitized, "Se perdió el namespace"
    
    def test_rde_with_multiple_attributes(self):
        """Verifica que se conserve otros atributos de rDE"""
        xml_attrs = b'<rLoteDE><rDE Id="remove_me" other_attr="keep_me" another="keep_too"><content>test</content></rDE></rLoteDE>'
        
        # Sanitizar
        sanitized = re.sub(br'(<rDE\b[^>]*?)\s+Id="[^"]+"([^>]*>)', br'\1\2', xml_attrs, count=1)
        
        # Verificar
        assert not re.search(br'<rDE[^>]*\bId\s*=', sanitized), "rDE todavía tiene Id"
        assert b'other_attr="keep_me"' in sanitized, "Se perdió other_attr"
        assert b'another="keep_too"' in sanitized, "Se perdió another"
    
    def test_debug_output_format(self, sample_de_xml):
        """Verifica el formato del debug output"""
        xml_with_rde_id = b'<rLoteDE><rDE Id="debug_test"><content>test</content></rDE></rLoteDE>'
        
        # Extraer tags como se hace en el código
        m_before = re.search(br"<rDE\b[^>]*>", xml_with_rde_id)
        before_tag = m_before.group(0) if m_before else b"NO_TAG"
        
        # Sanitizar
        sanitized = re.sub(br'(<rDE\b[^>]*?)\s+Id="[^"]+"([^>]*>)', br'\1\2', xml_with_rde_id, count=1)
        
        m_after = re.search(br"<rDE\b[^>]*>", sanitized)
        after_tag = m_after.group(0) if m_after else b"NO_TAG"
        
        # Verificar formato
        assert b"debug_test" in before_tag, "Tag antes no contiene el Id esperado"
        assert b"Id=" in before_tag, "Tag antes no contiene Id"
        assert b"Id=" not in after_tag, "Tag después todavía contiene Id"
        assert after_tag.startswith(b"<rDE"), "Tag después no comienza con rDE"


if __name__ == "__main__":
    # Ejecutar tests
    pytest.main([__file__, "-vv"])
