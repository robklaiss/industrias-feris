#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de integración para reconstrucción de CDC a partir de un XML rDE real.

Lee artifacts/last_lote_bump2.xml si existe; de lo contrario usa un fixture mínimo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from lxml import etree

pytest.importorskip("lxml", reason="lxml requerido para pruebas de XML")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Importar builder canónico y validador DV
import importlib.util

builder_spec = importlib.util.spec_from_file_location(
    "cdc_builder", REPO_ROOT / "app" / "sifen_client" / "cdc_builder.py"
)
cdc_builder = importlib.util.module_from_spec(builder_spec)
builder_spec.loader.exec_module(cdc_builder)
build_cdc_from_de_xml = cdc_builder.build_cdc_from_de_xml

cdc_utils_spec = importlib.util.spec_from_file_location(
    "cdc_utils", REPO_ROOT / "app" / "sifen_client" / "cdc_utils.py"
)
cdc_utils = importlib.util.module_from_spec(cdc_utils_spec)
cdc_utils_spec.loader.exec_module(cdc_utils)
validate_cdc = cdc_utils.validate_cdc

SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
NS = {"s": SIFEN_NS}


def _find_first(element: etree._Element, localname: str) -> etree._Element:
    """Helper que tolera namespaces mixtos."""
    node = element.find(f".//s:{localname}", namespaces=NS)
    if node is not None:
        return node
    nodes = element.xpath(f".//*[local-name()='{localname}']")
    if not nodes:
        raise AssertionError(f"No se encontró <{localname}> en el XML")
    return nodes[0]


def _load_rde_xml() -> etree._Element:
    artifact = REPO_ROOT / "artifacts" / "last_lote_bump2.xml"
    if artifact.exists():
        xml_bytes = artifact.read_bytes()
    else:
        xml_bytes = """
        <rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
            <dVerFor>150</dVerFor>
            <DE Id="01045547378001001000000112026011210000000010">
                <dDVId>0</dDVId>
                <gDatGralOpe>
                    <dFeEmiDE>2025-12-30T23:32:13</dFeEmiDE>
                </gDatGralOpe>
                <gEmis>
                    <dRucEm>4554737</dRucEm>
                    <dDVEmi>8</dDVEmi>
                </gEmis>
                <gTimb>
                    <iTiDE>1</iTiDE>
                    <dNumTim>12547896</dNumTim>
                    <dEst>001</dEst>
                    <dPunExp>001</dPunExp>
                    <dNumDoc>0000002</dNumDoc>
                </gTimb>
                <gTotSub>
                    <dTotalGs>100000</dTotalGs>
                </gTotSub>
            </DE>
        </rDE>
        """.strip().encode("utf-8")
    parser = etree.XMLParser(remove_blank_text=True)
    return etree.fromstring(xml_bytes, parser=parser)


def test_rebuilt_cdc_contains_numdoc_and_is_valid():
    """Siempre que cambie dNumDoc, el CDC reconstruido debe reflejarlo y ser válido."""
    root = _load_rde_xml()
    de_elem = _find_first(root, "DE")
    dnumdoc_elem = _find_first(root, "dNumDoc")
    current_numdoc = (dnumdoc_elem.text or "").strip()

    cdc, dv = build_cdc_from_de_xml(de_elem)
    assert len(cdc) == 44 and cdc.endswith(dv), "CDC/DV deben tener formato válido"
    assert current_numdoc[-7:] in cdc, "El CDC debe contener el dNumDoc actual"
    es_valido, _, _ = validate_cdc(cdc)
    assert es_valido, "El CDC reconstruido debe pasar validate_cdc"

    # Mutar dNumDoc y volver a reconstruir para asegurar que cambia
    dnumdoc_elem.text = "0000003"
    new_cdc, _ = build_cdc_from_de_xml(de_elem)
    assert new_cdc != cdc, "El CDC debe cambiar si cambia dNumDoc"
    assert "0000003" in new_cdc
    es_valido2, _, _ = validate_cdc(new_cdc)
    assert es_valido2
