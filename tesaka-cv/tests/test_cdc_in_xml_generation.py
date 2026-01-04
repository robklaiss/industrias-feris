#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests para validar que el CDC generado en XML sea siempre válido.

Ejecutar:
    python tests/test_cdc_in_xml_generation.py
"""

import sys
from pathlib import Path
from lxml import etree

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Importar directamente sin pasar por __init__.py
import importlib.util

# Importar cdc_utils
cdc_utils_path = Path(__file__).parent.parent / "app" / "sifen_client" / "cdc_utils.py"
spec = importlib.util.spec_from_file_location("cdc_utils", cdc_utils_path)
cdc_utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdc_utils)
validate_cdc = cdc_utils.validate_cdc

# Importar xml_generator_v150
xml_gen_path = Path(__file__).parent.parent / "app" / "sifen_client" / "xml_generator_v150.py"
spec2 = importlib.util.spec_from_file_location("xml_generator_v150", xml_gen_path)
xml_gen = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(xml_gen)
create_rde_xml_v150 = xml_gen.create_rde_xml_v150

# Importar build_de
build_de_path = Path(__file__).parent.parent / "tools" / "build_de.py"
spec3 = importlib.util.spec_from_file_location("build_de", build_de_path)
build_de_mod = importlib.util.module_from_spec(spec3)
spec3.loader.exec_module(build_de_mod)
build_de_xml = build_de_mod.build_de_xml


def test_create_rde_xml_v150_cdc_valido():
    """Test que create_rde_xml_v150 genera un CDC válido."""
    print("\n=== Test: create_rde_xml_v150 genera CDC válido ===")
    
    xml_str = create_rde_xml_v150(
        ruc="80012345",
        timbrado="12345678",
        establecimiento="001",
        punto_expedicion="001",
        numero_documento="0000001",
        tipo_documento="1",
        fecha="2025-01-01",
        hora="12:00:00"
    )
    
    # Parsear XML
    root = etree.fromstring(xml_str.encode("utf-8"))
    
    # Buscar elemento DE
    ns = {"s": "http://ekuatia.set.gov.py/sifen/xsd"}
    de_elem = root.find(".//s:DE", namespaces=ns)
    if de_elem is None:
        de_elem = root.find(".//*[local-name()='DE']")
    
    assert de_elem is not None, "No se encontró elemento <DE> en el XML generado"
    
    # Extraer Id
    de_id = de_elem.get("Id")
    assert de_id is not None, "El elemento <DE> no tiene atributo 'Id'"
    
    print(f"  DE@Id encontrado: {de_id}")
    
    # Validar formato
    assert len(de_id) == 44, f"Id debe tener 44 caracteres. Recibido: {len(de_id)}"
    assert de_id.isdigit(), f"Id debe contener solo dígitos. Recibido: {de_id!r}"
    
    # Validar DV
    es_valido, dv_orig, dv_calc = validate_cdc(de_id)
    assert es_valido, f"CDC debe ser válido. DV original: {dv_orig}, DV calculado: {dv_calc}"
    
    print(f"  ✅ CDC válido: {de_id}")
    print(f"  ✅ DV correcto: {dv_orig}")


def test_build_de_xml_cdc_valido():
    """Test que build_de_xml genera un CDC válido."""
    print("\n=== Test: build_de_xml genera CDC válido ===")
    
    xml_str = build_de_xml(
        ruc="80012345",
        timbrado="12345678",
        establecimiento="001",
        punto_expedicion="001",
        numero_documento="0000001",
        tipo_documento="1",
        fecha="2025-01-01",
        hora="12:00:00",
        env="test"
    )
    
    # Parsear XML
    root = etree.fromstring(xml_str.encode("utf-8"))
    
    # Buscar elemento DE (puede estar en el root)
    de_elem = None
    if root.tag.endswith("}DE") or root.tag == "DE":
        de_elem = root
    else:
        ns = {"s": "http://ekuatia.set.gov.py/sifen/xsd"}
        de_candidates = root.xpath(".//s:DE", namespaces=ns)
        if not de_candidates:
            de_candidates = root.xpath(".//*[local-name()='DE']")
        if de_candidates:
            de_elem = de_candidates[0]
    
    assert de_elem is not None, "No se encontró elemento <DE> en el XML generado"
    
    # Extraer Id
    de_id = de_elem.get("Id")
    assert de_id is not None, "El elemento <DE> no tiene atributo 'Id'"
    
    print(f"  DE@Id encontrado: {de_id}")
    
    # Validar formato
    assert len(de_id) == 44, f"Id debe tener 44 caracteres. Recibido: {len(de_id)}"
    assert de_id.isdigit(), f"Id debe contener solo dígitos. Recibido: {de_id!r}"
    
    # Validar DV
    es_valido, dv_orig, dv_calc = validate_cdc(de_id)
    assert es_valido, f"CDC debe ser válido. DV original: {dv_orig}, DV calculado: {dv_calc}"
    
    print(f"  ✅ CDC válido: {de_id}")
    print(f"  ✅ DV correcto: {dv_orig}")


def test_check_cdc_detecta_cdc_alfanumerico():
    """Test que check_cdc detecta CDC con caracteres no numéricos."""
    print("\n=== Test: check_cdc detecta CDC alfanumérico ===")
    
    # Crear XML temporal con CDC inválido
    cdc_invalido = "011234567A1747642286537210927750174764228653"
    xml_temp = f"""<?xml version="1.0" encoding="UTF-8"?>
<DE xmlns="http://ekuatia.set.gov.py/sifen/xsd" Id="{cdc_invalido}">
    <dDVId>3</dDVId>
</DE>"""
    
    temp_path = Path("/tmp/test_de_invalido.xml")
    temp_path.write_text(xml_temp, encoding="utf-8")
    
    try:
        # Importar función de check_cdc
        check_cdc_path = Path(__file__).parent.parent / "tools" / "check_cdc.py"
        spec4 = importlib.util.spec_from_file_location("check_cdc", check_cdc_path)
        check_cdc_mod = importlib.util.module_from_spec(spec4)
        spec4.loader.exec_module(check_cdc_mod)
        extract_cdc_from_xml = check_cdc_mod.extract_cdc_from_xml
        
        # Extraer CDC del XML
        cdc_extraido = extract_cdc_from_xml(temp_path)
        assert cdc_extraido == cdc_invalido, f"CDC extraído debe coincidir: {cdc_extraido}"
        
        # Validar que detecta caracteres no numéricos
        assert not cdc_extraido.isdigit(), f"CDC debe contener caracteres no numéricos: {cdc_extraido!r}"
        assert "A" in cdc_extraido, f"CDC debe contener 'A': {cdc_extraido!r}"
        
        print(f"  ✅ CDC alfanumérico detectado: {cdc_extraido}")
        print(f"  ✅ Contiene 'A': {'A' in cdc_extraido}")
    
    finally:
        if temp_path.exists():
            temp_path.unlink()


if __name__ == "__main__":
    print("Ejecutando tests de CDC en generación de XML...\n")
    try:
        test_create_rde_xml_v150_cdc_valido()
        test_build_de_xml_cdc_valido()
        test_check_cdc_detecta_cdc_alfanumerico()
        print("\n✅ Todos los tests pasaron")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Test falló: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

