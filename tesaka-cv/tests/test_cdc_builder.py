#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests dedicados a la reconstrucción de CDC desde un XML <DE>.
"""
import sys
from pathlib import Path
from datetime import datetime

import pytest

pytest.importorskip("lxml", reason="lxml requerido para pruebas de XML")

from lxml import etree

# Permitir imports directos (sin paquetes instalables)
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Import dinámico de build_cdc_from_de_xml
import importlib.util

cdc_builder_path = REPO_ROOT / "app" / "sifen_client" / "cdc_builder.py"
spec = importlib.util.spec_from_file_location("cdc_builder", cdc_builder_path)
cdc_builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdc_builder)
build_cdc_from_de_xml = cdc_builder.build_cdc_from_de_xml

# Import dinámico de cdc_utils.validate_cdc para validaciones
cdc_utils_path = REPO_ROOT / "app" / "sifen_client" / "cdc_utils.py"
spec_utils = importlib.util.spec_from_file_location("cdc_utils", cdc_utils_path)
cdc_utils = importlib.util.module_from_spec(spec_utils)
spec_utils.loader.exec_module(cdc_utils)
validate_cdc = cdc_utils.validate_cdc

SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
NS = {"s": SIFEN_NS}


def _build_sample_rde(dnumdoc: str, total_gs: str = "100000") -> etree._Element:
    """Genera un rDE de ejemplo en memoria."""
    fecha_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    xml = f"""
    <rDE xmlns="{SIFEN_NS}" xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <dVerFor>150</dVerFor>
        <DE Id="{'0'*44}">
            <dDVId>0</dDVId>
            <dFecFirma>{fecha_iso}</dFecFirma>
            <dSisFact>1</dSisFact>
            <gDatGralOpe>
                <dFeEmiDE>{fecha_iso}</dFeEmiDE>
            </gDatGralOpe>
            <gEmis>
                <dRucEm>4554737</dRucEm>
                <dDVEmi>8</dDVEmi>
                <iTipCont>1</iTipCont>
            </gEmis>
            <gTimb>
                <iTiDE>1</iTiDE>
                <dNumTim>12547896</dNumTim>
                <dEst>001</dEst>
                <dPunExp>001</dPunExp>
                <dNumDoc>{dnumdoc}</dNumDoc>
            </gTimb>
            <gTotSub>
                <dTotalGs>{total_gs}</dTotalGs>
            </gTotSub>
        </DE>
    </rDE>
    """.strip()
    return etree.fromstring(xml.encode("utf-8"))


def test_build_cdc_from_de_xml_varia_con_numdoc():
    """El CDC reconstruido debe cambiar si cambia dNumDoc."""
    root = _build_sample_rde("0000002")

    cdc1, dv1 = build_cdc_from_de_xml(root)
    assert len(cdc1) == 44
    assert cdc1.endswith(dv1)
    assert "0000002" in cdc1, "El CDC debe contener el número de documento actual"
    es_valido, _, _ = validate_cdc(cdc1)
    assert es_valido, "El CDC reconstruido debe ser válido"

    # Mutar dNumDoc y volver a construir
    root.find(".//s:dNumDoc", namespaces=NS).text = "0000003"
    cdc2, dv2 = build_cdc_from_de_xml(root)

    assert cdc2 != cdc1, "El CDC debe variar al cambiar dNumDoc"
    assert "0000003" in cdc2
    assert dv2 == cdc2[-1]
    es_valido_2, _, _ = validate_cdc(cdc2)
    assert es_valido_2


def test_build_cdc_from_de_xml_acepta_gtot_faltante():
    """Si no existe dTotalGs, el builder debe usar 0 y seguir siendo válido."""
    root = _build_sample_rde("0000099")
    gtot = root.find(".//s:gTotSub", namespaces=NS)
    gtot.getparent().remove(gtot)

    cdc, _ = build_cdc_from_de_xml(root)
    es_valido, _, _ = validate_cdc(cdc)
    assert es_valido, "El CDC debe seguir siendo válido aunque falte dTotalGs"
