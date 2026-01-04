#!/usr/bin/env python3
"""
Regenera CDC de un rDE/DE cambiando el número de documento.

Soporta múltiples formatos de entrada:
- rDE o DE directo
- rEnviDe con xDE base64 (ZIP)
- rEnviDe con xDE que contiene hijos (rDE/DE embebido)
- rLoteDE / lote.xml directo

Uso:
    python tools/regen_cdc_from_rde.py --in artifacts/sirecepde_rebuild_fixed.xml --out artifacts/sirecepde_rebuild_fixed_NEW.xml --numdoc 2
    python tools/regen_cdc_from_rde.py --in artifacts/sirecepde_rebuild_fixed.xml --out artifacts/sirecepde_rebuild_fixed_NEW.xml --numdoc 3

El script:
1. Parsea el XML de entrada (detecta formato automáticamente)
2. Encuentra el DE (namespace-agnostic, desde cualquier formato)
3. Cambia dNumDoc con el nuevo valor
4. Recalcula CDC y DV usando la misma función que el flujo real
5. Actualiza el atributo Id del DE con el nuevo CDC
6. Guarda el XML modificado conservando el formato original
"""
import sys
import argparse
import re
import base64
import zipfile
from pathlib import Path
from typing import Optional, Tuple
from io import BytesIO

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree
from app.sifen_client.xml_generator_v150 import generate_cdc

# Namespace SIFEN
SIFEN_NS_URI = "http://ekuatia.set.gov.py/sifen/xsd"
NS = {"s": SIFEN_NS_URI}


def _localname(tag: str) -> str:
    """Extrae el localname de un tag (sin namespace)"""
    return tag.split("}", 1)[1] if isinstance(tag, str) and tag.startswith("{") else tag


def find_first_by_localname(root: etree._Element, name: str) -> Optional[etree._Element]:
    """
    Encuentra el primer elemento con local-name() == name.
    Namespace-agnostic usando XPath.
    """
    nodes = root.xpath(f".//*[local-name()='{name}']")
    return nodes[0] if nodes else None


def extract_de_from_tree(tree_root: etree._Element) -> etree._Element:
    """
    Extrae el elemento DE desde cualquier formato de árbol XML.
    
    Raises:
        ValueError: Si no se encuentra DE
    """
    root_ln = _localname(tree_root.tag)
    
    # Caso 1: Root es DE
    if root_ln == "DE":
        return tree_root
    
    # Caso 2: Root es rDE, buscar DE dentro
    if root_ln == "rDE":
        de_elem = find_first_by_localname(tree_root, "DE")
        if de_elem:
            return de_elem
    
    # Caso 3: Buscar DE en cualquier parte del árbol
    de_elem = find_first_by_localname(tree_root, "DE")
    if de_elem:
        return de_elem
    
    # Diagnóstico si no se encuentra
    root_tag = tree_root.tag
    root_nsmap = getattr(tree_root, 'nsmap', {})
    first_30_tags = []
    for i, elem in enumerate(tree_root.iter()):
        if i >= 30:
            break
        first_30_tags.append(_localname(elem.tag))
    
    raise ValueError(
        f"No se encontró elemento DE en el XML.\n"
        f"Root tag: {root_tag}\n"
        f"Root localname: {root_ln}\n"
        f"Root nsmap: {root_nsmap}\n"
        f"Primeros 30 tags (localname): {', '.join(first_30_tags[:30])}"
    )


def extract_cdc_fields(de_elem: etree._Element) -> dict:
    """
    Extrae los campos necesarios para calcular CDC desde un elemento DE.
    
    Returns:
        Dict con: ruc, dv_ruc, timbrado, establecimiento, punto_expedicion,
                  numero_documento, tipo_documento, fecha, monto
    """
    # RUC y DV del emisor
    g_emis = de_elem.find(".//s:gEmis", namespaces=NS)
    if g_emis is None:
        raise ValueError("No se encontró <gEmis> en el DE")
    
    d_ruc = g_emis.find("s:dRucEm", namespaces=NS)
    if d_ruc is None or not d_ruc.text:
        raise ValueError("No se encontró <dRucEm> en <gEmis>")
    ruc = d_ruc.text.strip()
    
    d_dv = g_emis.find("s:dDVEmi", namespaces=NS)
    if d_dv is None or not d_dv.text:
        raise ValueError("No se encontró <dDVEmi> en <gEmis>")
    dv_ruc = d_dv.text.strip()
    
    # Timbrado, establecimiento, punto expedición, número documento
    g_timb = de_elem.find(".//s:gTimb", namespaces=NS)
    if g_timb is None:
        raise ValueError("No se encontró <gTimb> en el DE")
    
    d_timb = g_timb.find("s:dNumTim", namespaces=NS)
    if d_timb is None or not d_timb.text:
        raise ValueError("No se encontró <dNumTim> en <gTimb>")
    timbrado = d_timb.text.strip()
    
    d_est = g_timb.find("s:dEst", namespaces=NS)
    if d_est is None or not d_est.text:
        raise ValueError("No se encontró <dEst> en <gTimb>")
    establecimiento = d_est.text.strip()
    
    d_pun = g_timb.find("s:dPunExp", namespaces=NS)
    if d_pun is None or not d_pun.text:
        raise ValueError("No se encontró <dPunExp> en <gTimb>")
    punto_expedicion = d_pun.text.strip()
    
    d_numdoc = g_timb.find("s:dNumDoc", namespaces=NS)
    if d_numdoc is None or not d_numdoc.text:
        raise ValueError("No se encontró <dNumDoc> en <gTimb>")
    numero_documento = d_numdoc.text.strip()
    
    # Tipo documento
    i_tide = g_timb.find("s:iTiDE", namespaces=NS)
    if i_tide is None or not i_tide.text:
        raise ValueError("No se encontró <iTiDE> en <gTimb>")
    tipo_documento = i_tide.text.strip()
    
    # Fecha emisión
    g_datgral = de_elem.find(".//s:gDatGralOpe", namespaces=NS)
    if g_datgral is None:
        raise ValueError("No se encontró <gDatGralOpe> en el DE")
    
    d_femi = g_datgral.find("s:dFeEmiDE", namespaces=NS)
    if d_femi is None or not d_femi.text:
        raise ValueError("No se encontró <dFeEmiDE> en <gDatGralOpe>")
    fecha_emi = d_femi.text.strip()
    
    # Convertir fecha de YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS a YYYYMMDD
    fecha_ymd = re.sub(r"\D", "", fecha_emi)[:8]
    if len(fecha_ymd) != 8:
        raise ValueError(f"Fecha de emisión inválida para CDC: {fecha_emi!r}")
    
    # Monto total
    g_tot = de_elem.find(".//s:gTotSub", namespaces=NS)
    if g_tot is None:
        raise ValueError("No se encontró <gTotSub> en el DE")
    
    d_tot = g_tot.find("s:dTotalGs", namespaces=NS)
    if d_tot is None or not d_tot.text:
        # Fallback: usar 0 si no hay monto
        monto = "0"
    else:
        monto = d_tot.text.strip()
    
    return {
        "ruc": ruc,
        "dv_ruc": dv_ruc,
        "timbrado": timbrado,
        "establecimiento": establecimiento,
        "punto_expedicion": punto_expedicion,
        "numero_documento": numero_documento,
        "tipo_documento": tipo_documento,
        "fecha": fecha_ymd,
        "monto": monto
    }


def update_de_cdc(de_elem: etree._Element, new_numdoc: str) -> Tuple[str, str, str, str]:
    """
    Actualiza dNumDoc y recalcula CDC para un elemento DE.
    
    Args:
        de_elem: Elemento DE a modificar
        new_numdoc: Nuevo número de documento
        
    Returns:
        Tuple: (old_id, new_id, old_numdoc, new_numdoc)
    """
    # Obtener ID actual
    old_id = de_elem.get("Id") or de_elem.get("id")
    if not old_id:
        raise ValueError("El elemento DE no tiene atributo Id")
    
    # Extraer campos para CDC
    fields = extract_cdc_fields(de_elem)
    old_numdoc = fields["numero_documento"]
    
    # Actualizar número de documento
    d_numdoc = de_elem.find(".//s:gTimb/s:dNumDoc", namespaces=NS)
    if d_numdoc is None:
        raise ValueError("No se encontró <dNumDoc> para actualizar")
    
    # Normalizar nuevo número de documento (zero-fill a 7 dígitos)
    new_numdoc_normalized = str(new_numdoc).zfill(7)[-7:]
    d_numdoc.text = new_numdoc_normalized
    
    # Recalcular CDC con el nuevo número de documento
    # Construir RUC completo con DV para generate_cdc
    ruc_complete = f"{fields['ruc']}-{fields['dv_ruc']}"
    
    new_cdc = generate_cdc(
        ruc=ruc_complete,
        timbrado=fields["timbrado"],
        establecimiento=fields["establecimiento"],
        punto_expedicion=fields["punto_expedicion"],
        numero_documento=new_numdoc_normalized,
        tipo_documento=fields["tipo_documento"],
        fecha=fields["fecha"],
        monto=fields["monto"]
    )
    
    # Actualizar atributo Id del DE
    de_elem.set("Id", new_cdc)
    
    return old_id, new_cdc, old_numdoc, new_numdoc_normalized


def regen_cdc_from_rde(xml_path: Path, output_path: Path, new_numdoc: str) -> dict:
    """
    Regenera CDC cambiando el número de documento.
    Soporta múltiples formatos: rDE/DE, rEnviDe con xDE (base64 o hijos), rLoteDE.
    
    Args:
        xml_path: Path al XML de entrada
        output_path: Path donde guardar el XML modificado
        new_numdoc: Nuevo número de documento (ej: "2", "3", "0000002")
        
    Returns:
        Dict con: old_id, new_id, old_numdoc, new_numdoc
    """
    # Parsear XML
    try:
        tree = etree.parse(str(xml_path))
        root = tree.getroot()
    except Exception as e:
        raise ValueError(f"Error al parsear XML: {e}")
    
    root_ln = _localname(root.tag)
    
    # Caso 1: rDE o DE directo
    if root_ln in ("rDE", "DE"):
        de_elem = extract_de_from_tree(root)
        old_id, new_cdc, old_numdoc, new_numdoc_normalized = update_de_cdc(de_elem, new_numdoc)
        
        # Guardar XML modificado
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tree.write(
            str(output_path),
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=True
        )
        
        return {
            "old_id": old_id,
            "new_id": new_cdc,
            "old_numdoc": old_numdoc,
            "new_numdoc": new_numdoc_normalized
        }
    
    # Caso 2: rEnviDe con xDE
    if root_ln == "rEnviDe":
        xde_elem = find_first_by_localname(root, "xDE")
        if xde_elem is None:
            # Diagnóstico
            root_tag = root.tag
            root_nsmap = getattr(root, 'nsmap', {})
            first_30_tags = []
            for i, elem in enumerate(root.iter()):
                if i >= 30:
                    break
                first_30_tags.append(_localname(elem.tag))
            raise ValueError(
                f"rEnviDe no contiene xDE.\n"
                f"Root tag: {root_tag}\n"
                f"Root nsmap: {root_nsmap}\n"
                f"Primeros 30 tags: {', '.join(first_30_tags[:30])}"
            )
        
        xde_text = (xde_elem.text or "").strip()
        
        # Caso 2a: xDE con texto base64 (ZIP)
        if xde_text:
            try:
                # Decodificar base64
                zip_bytes = base64.b64decode(xde_text)
                
                # Validar que es un ZIP (opcional, pero útil)
                if not zip_bytes.startswith(b'PK'):
                    # Intentar de todas formas
                    pass
                
                # Abrir ZIP
                with zipfile.ZipFile(BytesIO(zip_bytes), 'r') as zf:
                    namelist = zf.namelist()
                    
                    # Elegir lote.xml
                    lote_filename = None
                    if 'lote.xml' in namelist:
                        lote_filename = 'lote.xml'
                    else:
                        xml_files = [f for f in namelist if f.endswith('.xml')]
                        if len(xml_files) == 1:
                            lote_filename = xml_files[0]
                        else:
                            raise ValueError(
                                f"No se pudo determinar archivo XML en ZIP. "
                                f"namelist: {namelist}"
                            )
                    
                    # Leer y parsear lote.xml
                    lote_xml_bytes = zf.read(lote_filename)
                    lote_root = etree.fromstring(lote_xml_bytes)
                    
                    # Extraer DE desde lote.xml
                    de_elem = extract_de_from_tree(lote_root)
                    
                    # Actualizar CDC
                    old_id, new_cdc, old_numdoc, new_numdoc_normalized = update_de_cdc(de_elem, new_numdoc)
                    
                    # Re-serializar lote.xml
                    lote_xml_bytes_new = etree.tostring(
                        lote_root,
                        encoding="utf-8",
                        xml_declaration=True,
                        pretty_print=False
                    )
                    
                    # Re-crear ZIP
                    zip_new = BytesIO()
                    with zipfile.ZipFile(zip_new, 'w', zipfile.ZIP_DEFLATED) as zf_new:
                        zf_new.writestr(lote_filename, lote_xml_bytes_new)
                    zip_new_bytes = zip_new.getvalue()
                    
                    # Actualizar xDE.text con nuevo base64
                    xde_elem.text = base64.b64encode(zip_new_bytes).decode('ascii')
                    
            except Exception as e:
                raise ValueError(
                    f"Error al procesar xDE base64 (ZIP): {e}\n"
                    f"xDE text len: {len(xde_text)}"
                ) from e
        
        # Caso 2b: xDE con hijos (rDE/DE embebido)
        else:
            # Buscar rDE o DE dentro de xDE
            de_elem = find_first_by_localname(xde_elem, "DE")
            if de_elem is None:
                de_elem = find_first_by_localname(xde_elem, "rDE")
                if de_elem:
                    de_elem = find_first_by_localname(de_elem, "DE")
            
            if de_elem is None:
                raise ValueError(
                    "xDE no contiene texto base64 ni hijos DE/rDE.\n"
                    f"xDE children: {[child.tag for child in xde_elem]}"
                )
            
            # Actualizar CDC
            old_id, new_cdc, old_numdoc, new_numdoc_normalized = update_de_cdc(de_elem, new_numdoc)
        
        # Guardar rEnviDe actualizado
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tree.write(
            str(output_path),
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=True
        )
        
        return {
            "old_id": old_id,
            "new_id": new_cdc,
            "old_numdoc": old_numdoc,
            "new_numdoc": new_numdoc_normalized
        }
    
    # Caso 3: rLoteDE / lote.xml directo
    if root_ln in ("rLoteDE", "lote"):
        de_elem = extract_de_from_tree(root)
        old_id, new_cdc, old_numdoc, new_numdoc_normalized = update_de_cdc(de_elem, new_numdoc)
        
        # Guardar XML modificado
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tree.write(
            str(output_path),
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=True
        )
        
        return {
            "old_id": old_id,
            "new_id": new_cdc,
            "old_numdoc": old_numdoc,
            "new_numdoc": new_numdoc_normalized
        }
    
    # Formato no reconocido
    root_tag = root.tag
    root_nsmap = getattr(root, 'nsmap', {})
    first_30_tags = []
    for i, elem in enumerate(root.iter()):
        if i >= 30:
            break
        first_30_tags.append(_localname(elem.tag))
    
    raise ValueError(
        f"Formato de XML no reconocido.\n"
        f"Root tag: {root_tag}\n"
        f"Root localname: {root_ln}\n"
        f"Root nsmap: {root_nsmap}\n"
        f"Primeros 30 tags: {', '.join(first_30_tags[:30])}\n"
        f"Formatos soportados: rDE, DE, rEnviDe, rLoteDE, lote"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Regenera CDC de un rDE/DE cambiando el número de documento",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python tools/regen_cdc_from_rde.py --in artifacts/sirecepde_rebuild_fixed.xml --out artifacts/sirecepde_rebuild_fixed_NEW.xml --numdoc 2
  python tools/regen_cdc_from_rde.py --in artifacts/sirecepde_rebuild_fixed.xml --out artifacts/sirecepde_rebuild_fixed_NEW.xml --numdoc 3
        """
    )
    
    parser.add_argument(
        "--in",
        dest="input_file",
        type=Path,
        required=True,
        help="Path al XML de entrada (rDE, DE, rEnviDe, rLoteDE, lote.xml)"
    )
    
    parser.add_argument(
        "--out",
        dest="output_file",
        type=Path,
        required=True,
        help="Path donde guardar el XML modificado"
    )
    
    parser.add_argument(
        "--numdoc",
        type=str,
        required=True,
        help="Nuevo número de documento (ej: 2, 3, 0000002)"
    )
    
    args = parser.parse_args()
    
    # Validar archivo de entrada
    if not args.input_file.exists():
        print(f"❌ Error: El archivo de entrada no existe: {args.input_file}")
        return 1
    
    try:
        # Regenerar CDC
        result = regen_cdc_from_rde(
            xml_path=args.input_file,
            output_path=args.output_file,
            new_numdoc=args.numdoc
        )
        
        # Imprimir resultados
        print("\n" + "="*60)
        print("✅ CDC regenerado exitosamente")
        print("="*60)
        print(f"old_id:     {result['old_id']}")
        print(f"new_id:     {result['new_id']}")
        print(f"old_numdoc: {result['old_numdoc']}")
        print(f"new_numdoc: {result['new_numdoc']}")
        print(f"\nArchivo guardado en: {args.output_file}")
        print("="*60 + "\n")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

