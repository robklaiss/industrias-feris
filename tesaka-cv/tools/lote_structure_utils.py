#!/usr/bin/env python3
"""
Helpers para inspeccionar la estructura de rLoteDE (conteo de rDE/xDE, namespace, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, List

try:
    import lxml.etree as etree
except ImportError as exc:  # pragma: no cover - fallback amigable en CLI
    raise SystemExit(
        "❌ lxml no está instalado. Instale dependencias con: pip install lxml"
    ) from exc


SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"


def _local_name(tag: str) -> str:
    if isinstance(tag, str) and tag.startswith("{"):
        return tag.split("}", 1)[1]
    return str(tag)


def _namespace(tag: str) -> Optional[str]:
    if isinstance(tag, str) and tag.startswith("{"):
        return tag.split("}", 1)[0][1:]
    return None


@dataclass
class LoteStructureInfo:
    root_local: str
    root_namespace: Optional[str]
    xde_count: int
    rde_total: int
    rde_sifen: int
    direct_rde: int
    errors: List[str]
    first_de_id: Optional[str]


def analyze_lote_bytes(xml_bytes: bytes) -> Tuple[LoteStructureInfo, etree._Element]:
    """
    Parsea lote.xml y retorna métricas estructurales básicas.
    """
    parser = etree.XMLParser(remove_blank_text=False, recover=False)
    root = etree.fromstring(xml_bytes, parser=parser)

    direct_children = list(root)
    xde_children = [c for c in direct_children if _local_name(c.tag) == "xDE"]
    rde_descendants = root.xpath(".//*[local-name()='rDE']")
    rde_sifen = [r for r in rde_descendants if _namespace(r.tag) == SIFEN_NS]
    direct_rde_children = [c for c in direct_children if _local_name(c.tag) == "rDE"]

    first_de_id = None
    for candidate in root.xpath(".//*[local-name()='DE']"):
        first_de_id = candidate.get("Id") or candidate.get("id")
        if first_de_id:
            break

    info = LoteStructureInfo(
        root_local=_local_name(root.tag),
        root_namespace=_namespace(root.tag),
        xde_count=len(xde_children),
        rde_total=len(rde_descendants),
        rde_sifen=len(rde_sifen),
        direct_rde=len(direct_rde_children),
        errors=[],
        first_de_id=first_de_id,
    )

    if info.root_local != "rLoteDE":
        info.errors.append(
            f"root localname debe ser rLoteDE, encontrado: {info.root_local!r}"
        )
    if info.root_namespace != SIFEN_NS:
        info.errors.append(
            f"rLoteDE debe usar namespace {SIFEN_NS}, encontrado: {info.root_namespace or 'VACÍO'}"
        )
    if info.rde_total == 0:
        info.errors.append("No se encontró ningún <rDE> en el lote")
    if info.xde_count == 0:
        info.errors.append("No se encontró ningún <xDE> hijo directo de rLoteDE")
    if info.xde_count != info.rde_total:
        info.errors.append(
            f"xDE count ({info.xde_count}) debe coincidir con rDE count ({info.rde_total})"
        )
    if info.rde_total != info.rde_sifen:
        info.errors.append(
            f"Todos los <rDE> deben estar en namespace SIFEN ({info.rde_sifen}/{info.rde_total} lo están)"
        )

    return info, root


def analyze_xml_file(xml_path: str) -> LoteStructureInfo:
    """
    Helper para analizar un archivo en disco y devolver LoteStructureInfo.
    """
    with open(xml_path, "rb") as handle:
        xml_bytes = handle.read()
    info, _ = analyze_lote_bytes(xml_bytes)
    return info
