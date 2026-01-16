#!/usr/bin/env python3
"""Valida un XML rDE contra los XSD SIFEN v150 y opcionalmente elimina la firma."""

import argparse
import sys
from pathlib import Path
from typing import Tuple, Optional

from lxml import etree

DEFAULT_XML = Path("~/Desktop/sifen_de_firmado_test.xml").expanduser()
DEFAULT_OUT_STRIPPED = Path("~/Desktop/sifen_de_prevalidador.xml").expanduser()
DEFAULT_XSD_DIR = Path("./xsd")
DEFAULT_MAIN_XSD = "siRecepDE_v150.xsd"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"

REMOTE_PREFIXES = (
    "https://ekuatia.set.gov.py/sifen/xsd/",
    "http://ekuatia.set.gov.py/sifen/xsd/",
)


class LocalXSDResolver(etree.Resolver):
    """Resuelve imports/includes solo desde el directorio local."""

    def __init__(self, base_dir: Path):
        super().__init__()
        self.base_dir = base_dir

    def _resolve_candidate(self, candidate: Path, context):
        if candidate.exists():
            print(f"↪ include/import: usando {candidate}")
            return self.resolve_filename(str(candidate), context)
        # Intentar variante .local.xsd
        if candidate.suffix == ".xsd":
            local_variant = candidate.with_suffix(".local.xsd")
            if local_variant.exists():
                print(f"↪ include/import: usando {local_variant}")
                return self.resolve_filename(str(local_variant), context)
        return None

    def resolve(self, system_url, public_id, context):  # type: ignore[override]
        url = system_url or ""

        def handle_local_path(path_str: str):
            candidate = Path(path_str)
            if not candidate.is_absolute():
                candidate = self.base_dir / candidate
            result = self._resolve_candidate(candidate, context)
            if result is None:
                raise SystemExit(
                    f"❌ No se encontró XSD local para {path_str}. "
                    f"Buscado en {candidate} y variante .local.xsd."
                )
            return result

        for prefix in REMOTE_PREFIXES:
            if url.startswith(prefix):
                basename = url.split("/")[-1].split("?")[0]
                candidate = self.base_dir / basename
                result = self._resolve_candidate(candidate, context)
                if result is None:
                    raise SystemExit(
                        f"❌ No existe '{basename}' ni '.local.xsd' en {self.base_dir}. "
                        f"Se intentó resolver {url}"
                    )
                return result

        if "://" not in url:
            return handle_local_path(url)

        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida un XML rDE local contra los XSD SIFEN v150.",
    )
    parser.add_argument(
        "xml_path",
        nargs="?",
        default=str(DEFAULT_XML),
        help=f"Ruta al XML firmado (default: {DEFAULT_XML})",
    )
    parser.add_argument(
        "--xsd-dir",
        default=str(DEFAULT_XSD_DIR),
        help="Directorio donde residen los XSD (default: ./xsd)",
    )
    parser.add_argument(
        "--main-xsd",
        default=DEFAULT_MAIN_XSD,
        help="Archivo XSD principal (default: siRecepDE_v150.xsd)",
    )
    parser.add_argument(
        "--schema",
        choices=["recep", "preval"],
        default=None,
        help="Esquema a usar: recep (siRecepDE_v150.xsd, requiere Signature) o preval (rDE_prevalidador_v150.xsd, Signature opcional)",
    )
    parser.add_argument(
        "--strip-signature",
        action="store_true",
        help="Elimina nodos ds:Signature antes de validar y guarda copia opcional.",
    )
    parser.add_argument(
        "--strip-gcamfufd",
        dest="strip_gcamfufd",
        action="store_true",
        help="Elimina nodos gCamFuFD (útil para rDE_prevalidador_v150.xsd).",
    )
    parser.add_argument(
        "--no-strip-gcamfufd",
        dest="strip_gcamfufd",
        action="store_false",
        help="No eliminar gCamFuFD incluso si se valida contra schema preval.",
    )
    parser.set_defaults(strip_gcamfufd=None)
    parser.add_argument(
        "--out",
        dest="output",
        help="Archivo donde guardar el XML (necesario para strip si querés ruta distinta).",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Escribir XML de salida con pretty print.",
    )
    return parser.parse_args()


def load_xml(xml_path: Path) -> etree._ElementTree:
    if not xml_path.exists():
        raise FileNotFoundError(f"No se encontró el XML: {xml_path}")
    parser = etree.XMLParser(remove_blank_text=False)
    return etree.parse(str(xml_path), parser)


def strip_signature(tree: etree._ElementTree) -> int:
    signature_nodes = tree.xpath(
        '//*[local-name()="Signature" and namespace-uri()=$ns]',
        ns=DS_NS,
    )
    removed = 0
    for node in signature_nodes:
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)
            removed += 1
    return removed


def wrap_rde_as_siRecepDE(tree: etree._ElementTree) -> etree._ElementTree:
    """Envuelve el rDE en siRecepDE para validación contra siRecepDE_v150.xsd."""
    rde_root = tree.getroot()
    siRecepDE = etree.Element(
        "{http://ekuatia.set.gov.py/sifen/xsd}siRecepDE",
        nsmap={"sifen": "http://ekuatia.set.gov.py/sifen/xsd"},
    )
    siRecepDE.append(rde_root)
    return etree.ElementTree(siRecepDE)


def strip_gcamfufd(tree: etree._ElementTree) -> Tuple[int, bool]:
    """Elimina nodos gCamFuFD (QR) y retorna (cantidad_removida, tenia_signature)."""
    ns = {"s": SIFEN_NS, "ds": DS_NS}
    nodes = tree.xpath(".//s:gCamFuFD", namespaces=ns)
    removed = 0
    for node in nodes:
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)
            removed += 1
    has_signature = bool(tree.xpath('//ds:Signature', namespaces=ns))
    return removed, has_signature


def build_schema(xsd_dir: Path, main_xsd: str) -> etree.XMLSchema:
    xsd_dir = xsd_dir.resolve()
    main_path = xsd_dir / main_xsd
    if not main_path.exists():
        raise FileNotFoundError(f"XSD principal no encontrado: {main_path}")
    parser = etree.XMLParser(load_dtd=False, no_network=True, huge_tree=True)
    parser.resolvers.add(LocalXSDResolver(xsd_dir))
    print("✓ XSD resolver activo (no_network=True).")
    schema_doc = etree.parse(str(main_path), parser)
    return etree.XMLSchema(schema_doc)


def save_tree(tree: etree._ElementTree, out_path: Path, pretty: bool) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(
        str(out_path),
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=pretty,
    )


def print_error_log(schema: etree.XMLSchema) -> None:
    for entry in schema.error_log:
        message = entry.message.strip()
        print(f"  line {entry.line}, column {entry.column}: {message}")


def print_commands(xml_path: Path, stripped_path: Path, allow_upload: bool = True) -> None:
    print()
    print("Comandos sugeridos:")
    print("  1) Validar firmado:")
    print(
        f"     .venv/bin/python tools/prevalidate_local_v150.py {xml_path}"
    )
    print("  2) Generar sin firma y validar:")
    print(
        "     .venv/bin/python tools/prevalidate_local_v150.py "
        f"{xml_path} --strip-signature --out {stripped_path}"
    )
    if allow_upload:
        print("  3) Subir al prevalidador:")
        print(
            "     Subir el archivo: "
            f"{stripped_path}"
            " a https://ekuatia.set.gov.py/prevalidador/validacion"
        )
    else:
        print("  ⚠️  Para subir al prevalidador web, generá el XML con:")
        print("     .venv/bin/python tools/smoketest.py --target preval ...")
        print("     (No hagas strip de gCamFuFD sobre un XML ya firmado).")


def main() -> None:
    args = parse_args()
    xml_path = Path(args.xml_path).expanduser()
    stripped_target: Optional[Path] = None
    stripped_signature_warning = False
    exit_code = 0
    main_xsd_arg = args.main_xsd
    user_overrode_xsd = any(
        arg.startswith("--main-xsd") for arg in sys.argv[1:]
    )
    
    schema_selected = args.schema
    # Lógica de selección de XSD
    if not user_overrode_xsd:
        if args.schema:
            # Si el usuario especificó --schema, usarlo
            if args.schema == "recep":
                main_xsd_arg = "siRecepDE_v150.xsd"
                schema_selected = "recep"
            elif args.schema == "preval":
                main_xsd_arg = "rDE_prevalidador_v150.xsd"
                schema_selected = "preval"
        else:
            # Comportamiento por defecto: auto-detectar según presencia de Signature
            tree = load_xml(xml_path)
            signatures = tree.xpath(
                '//*[local-name()="Signature" and namespace-uri()="http://www.w3.org/2000/09/xmldsig#"]'
            )
            if signatures:
                main_xsd_arg = "siRecepDE_v150.xsd"
                print("🔍 Detectado ds:Signature en XML, usando schema: recep")
                schema_selected = "recep"
            else:
                main_xsd_arg = "rDE_prevalidador_v150.xsd"
                print("🔍 No se detectó ds:Signature en XML, usando schema: preval")
                schema_selected = "preval"
    else:
        print(f"ℹ️  Usando XSD especificado por usuario: {main_xsd_arg}")
        schema_selected = None
    
    try:
        print("=== SIFEN v150 Local Validator ===")
        print(f"XML: {xml_path}")
        
        # Cargar XML solo si no lo cargamos antes
        if 'tree' not in locals():
            tree = load_xml(xml_path)

        forced_preval_due_to_strip_signature = False
        if args.strip_signature and not args.schema and not user_overrode_xsd:
            main_xsd_arg = "rDE_prevalidador_v150.xsd"
            schema_selected = "preval"
            forced_preval_due_to_strip_signature = True

        strip_gcamfufd_setting = args.strip_gcamfufd
        if strip_gcamfufd_setting is None:
            strip_gcamfufd_setting = (main_xsd_arg == "rDE_prevalidador_v150.xsd")

        if strip_gcamfufd_setting:
            removed, had_signature = strip_gcamfufd(tree)
            if removed == 0:
                print("ℹ️  No se encontraron nodos gCamFuFD para eliminar.")
            else:
                print(f"✅ Eliminados {removed} nodo(s) gCamFuFD para compatibilidad con el prevalidador.")
                if had_signature:
                    stripped_signature_warning = True
                    print("⚠️  Atención: se removió gCamFuFD de un XML ya firmado. "
                          "Esto invalida la firma para PKI. Generá la variante con "
                          "`tools/smoketest.py --target preval` para subir al prevalidador web.")

        if args.strip_signature:
            removed = strip_signature(tree)
            if removed == 0:
                print("⚠️  No se encontraron nodos ds:Signature para eliminar.")
            else:
                print(f"✅ Eliminadas {removed} firmas ds:Signature.")
            stripped_target = Path(args.output).expanduser() if args.output else DEFAULT_OUT_STRIPPED
            save_tree(tree, stripped_target, args.pretty)
            print(f"XML sin firma guardado en: {stripped_target}")

            # Si se eliminó la firma y no se especificó schema, usar preval
            if forced_preval_due_to_strip_signature:
                print("🔄 Firma eliminada, cambiando a schema: preval")

        elif args.output:
            # Si se pidió out sin strip, guardar copia literal
            stripped_target = Path(args.output).expanduser()
            save_tree(tree, stripped_target, args.pretty)
            print(f"XML copiado en: {stripped_target}")

        xsd_dir = Path(args.xsd_dir).expanduser()
        print(f"Usando XSD principal: {main_xsd_arg}")
        schema = build_schema(xsd_dir, main_xsd_arg)
        print(f"Validando contra XSD: {xsd_dir / main_xsd_arg}")

        if schema.validate(tree):
            print("VALID")
            exit_code = 0
        else:
            print("INVALID")
            print_error_log(schema)
            exit_code = 2

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        stripped_path = stripped_target or DEFAULT_OUT_STRIPPED
        allow_upload = not stripped_signature_warning
        print_commands(xml_path, stripped_path, allow_upload=allow_upload)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
