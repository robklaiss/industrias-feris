
from lxml import etree
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
import xml.etree.ElementTree as ET
import re
import sys

DEFAULT_XML = Path("artifacts/de_test.xml")


def local(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def norm_name(s: str) -> str:
    # lower y quitar todo excepto a-z0-9
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def is_nonempty_text(x) -> bool:
    if x is None:
        return False
    s = str(x).strip()
    return s != ""


def zfill_digits(value, width: int):
    if value is None:
        return None
    s = re.sub(r"\D", "", str(value))
    if s == "":
        return None
    return s.zfill(width)


def calc_dv_mod11(base: str) -> str:
    weights = [2, 3, 4, 5, 6, 7, 8, 9]
    total = 0
    wi = 0
    for ch in reversed(base):
        total += int(ch) * weights[wi]
        wi += 1
        if wi >= 8:
            wi = 0
    r = total % 11
    dv = 11 - r
    if dv == 11:
        dv = 0
    if dv == 10:
        dv = 1
    return str(dv)


def find_all_texts(root: ET.Element, target_names):
    """
    Devuelve lista de (tag_local, texto) para cualquier ocurrencia cuyo localname
    normalizado coincida con cualquiera de target_names (normalizados).
    """
    want = set()
    for n in target_names:
        want.add(norm_name(n))

    out = []
    for el in root.iter():
        ln = local(el.tag)
        ln_norm = norm_name(ln)
        if ln_norm in want:
            txt = (el.text or "").strip()
            if txt != "":
                out.append((ln, txt))
    return out


def pick_best_by_len(values, expected_len):
    """
    values: lista de strings
    elige uno cuyo largo (solo dígitos) == expected_len, sino el primero no vacío.
    """
    if not values:
        return None

    # Primero: match exacto por largo de dígitos
    for v in values:
        digits = re.sub(r"\D", "", str(v))
        if digits != "" and len(digits) == expected_len:
            return digits

    # Fallback: primer no vacío
    for v in values:
        digits = re.sub(r"\D", "", str(v))
        if digits != "":
            return digits
    return None


def main() -> int:
    xml_path = DEFAULT_XML
    if len(sys.argv) >= 2 and sys.argv[1].strip() != "":
        xml_path = Path(sys.argv[1].strip())

    if not xml_path.exists():
        print("❌ No existe:", xml_path)
        return 2

    xml = xml_path.read_text("utf-8", errors="ignore")
    root = ET.fromstring(xml)

    # localizar DE
    de = None
    if local(root.tag) == "DE":
        de = root
    else:
        for el in root.iter():
            if local(el.tag) == "DE":
                de = el
                break

    if de is None:
        print("❌ No encontré <DE> en", xml_path)
        return 2

    de_id = (de.attrib.get("Id") or "").strip()
    de_id_digits = re.sub(r"\D", "", de_id)

    print("FILE:", xml_path)
    print("DE@Id:", de_id, "| len:", len(de_id_digits))

    if not de_id_digits or len(de_id_digits) < 10:
        print("⚠️  DE@Id vacío o inválido. No puedo segmentar CDC.")
        return 2

    # Check DV interno del DE@Id (base = todo menos último dígito)
    base = de_id_digits[:-1]
    dv_in_id = de_id_digits[-1:]
    dv_calc = calc_dv_mod11(base)
    print("")
    print("--- DV CHECK (sobre DE@Id) ---")
    print("DV en Id  :", dv_in_id)
    print("DV calc   :", dv_calc)
    if dv_in_id != dv_calc:
        print("❌ DV NO coincide. Esto solo ya explica el 1003.")
    else:
        print("✅ DV interno del DE@Id parece correcto.")

    # Extraer candidatos del XML (case-insensitive por norm_name)
    # tipDE (2) - buscar iTiDE (tipo documento) que es el que se usa en el CDC
    tipde_vals = find_all_texts(root, ["dTipDE", "iTipDE", "dTipDe", "iTipDe", "iTiDE", "dTiDE"])
    tipde_xml = pick_best_by_len([v for _k, v in tipde_vals], 2)

    # RUC (8) y DV RUC (1)
    ruc_vals = find_all_texts(root, ["dRucEm", "dRucEmi", "dRuc"])
    ruc_xml = pick_best_by_len([v for _k, v in ruc_vals], 8)  # RUC debe tener 8 dígitos (con zero-fill)
    dv_ruc_vals = find_all_texts(root, ["dDVEmi", "dDV", "dDv"])
    dv_ruc_xml = pick_best_by_len([v for _k, v in dv_ruc_vals], 1)

    # Est/Pun
    est_vals = find_all_texts(root, ["dEst"])
    est_xml = pick_best_by_len([v for _k, v in est_vals], 3)

    pun_vals = find_all_texts(root, ["dPunExp"])
    pun_xml = pick_best_by_len([v for _k, v in pun_vals], 3)

    # NumDoc (puede aparecer varias veces: elegimos el que "calza" con DE@Id más abajo)
    num_vals_raw = find_all_texts(root, ["dNumDoc"])
    num_candidates = []
    for _k, v in num_vals_raw:
        d = re.sub(r"\D", "", str(v))
        if d != "":
            num_candidates.append(d)

    # Fecha
    fec_vals = find_all_texts(root, ["dFeEmiDE", "dFecEmiDE", "dFeEmi"])
    fec_text = None
    if fec_vals:
        fec_text = fec_vals[0][1]

    fec8 = None
    if fec_text:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(fec_text))
        if m:
            fec8 = m.group(1) + m.group(2) + m.group(3)

    # Timbrado (8) y TipEmi (1)
    timb_vals = find_all_texts(root, ["dNumTim", "dTimbr"])
    timb8_xml = pick_best_by_len([v for _k, v in timb_vals], 8)

    tipemi_vals = find_all_texts(root, ["iTipEmi", "dTipEmi"])
    tipemi1_xml = pick_best_by_len([v for _k, v in tipemi_vals], 1)

    # CodSeg (puede venir largo, pero en CDC suele ser 1-2 dígitos; lo inferimos desde Id)
    codseg_vals = find_all_texts(root, ["dCodSeg", "dCodSeguridad"])
    codseg_any = None
    if codseg_vals:
        codseg_any = re.sub(r"\D", "", str(codseg_vals[0][1]))

    print("")
    print("--- CAMPOS (XML) candidatos ---")
    print("tipDE vals :", [v for _k, v in tipde_vals] if tipde_vals else [])
    print("tipDE xml  :", tipde_xml)
    print("ruc vals   :", [v for _k, v in ruc_vals] if ruc_vals else [])
    print("ruc xml    :", ruc_xml)
    print("dv_ruc vals:", [v for _k, v in dv_ruc_vals] if dv_ruc_vals else [])
    print("dv_ruc xml :", dv_ruc_xml)
    print("dEst vals  :", [v for _k, v in est_vals] if est_vals else [])
    print("dEst xml   :", est_xml)
    print("dPun vals  :", [v for _k, v in pun_vals] if pun_vals else [])
    print("dPun xml   :", pun_xml)
    print("dNumDoc vals:", num_candidates)
    print("fec text   :", fec_text)
    print("fec8       :", fec8)
    print("timb vals  :", [v for _k, v in timb_vals] if timb_vals else [])
    print("timb8 xml  :", timb8_xml)
    print("tipEmi vals:", [v for _k, v in tipemi_vals] if tipemi_vals else [])
    print("tipEmi xml :", tipemi1_xml)
    print("codseg raw :", codseg_any)

    # Inferencias desde DE@Id (esto es clave para encontrar el "campo correcto")
    print("")
    print("--- SEGMENTACIÓN (inferida desde DE@Id) ---")

    tipde_id = de_id_digits[0:2]
    ruc_id = de_id_digits[2:10]
    dv_ruc_id = de_id_digits[10:11]
    est_id = de_id_digits[11:14]
    pun_id = de_id_digits[14:17]
    # numDoc es de 7 dígitos (posición 17-24)
    numdoc_id = de_id_digits[17:24] if len(de_id_digits) >= 24 else de_id_digits[17:]
    # tipCont es 1 dígito (posición 24-25)
    tipcont_id = de_id_digits[24:25] if len(de_id_digits) >= 25 else None

    print("tipDE(id) :", tipde_id)
    print("ruc(id)   :", ruc_id)
    print("dv_ruc(id):", dv_ruc_id)
    print("est(id)   :", est_id)
    print("pun(id)   :", pun_id)
    print("numDoc(id):", numdoc_id, "| len:", len(numdoc_id))
    print("tipCont(id):", tipcont_id)

    idx_date = -1
    if fec8:
        idx_date = de_id_digits.find(fec8)

    if idx_date < 0:
        print("⚠️  No pude ubicar fec8 dentro del DE@Id. No puedo inferir tail.")
        # Intentar con posición fija (25 si tipCont está presente)
        if tipcont_id and len(de_id_digits) >= 33:
            idx_date = 25
            fec8_id = de_id_digits[25:33]
            tail = de_id_digits[33:-1]
            print("fec8(id)   :", fec8_id, "| len:", len(fec8_id))
            print("tail(id)   :", tail, "| len:", len(tail))
        else:
            print("⚠️  No puedo inferir estructura completa sin fecha.")
    else:
        # Fecha encontrada en idx_date
        if idx_date < 25:
            print("⚠️  idx_date inconsistente (esperado >= 25):", idx_date)
        else:
            fec8_id = de_id_digits[idx_date:idx_date + 8]
            print("fec8(id)   :", fec8_id, "| len:", len(fec8_id))
            # tail: después de fecha hasta antes del DV final
            tail = de_id_digits[idx_date + 8:-1]
            print("tail(id)   :", tail, "| len:", len(tail))

            # Dentro del tail, buscamos timbrado si lo tenemos
            # Estructura: tipEmi(1) + timb(8) + codseg(último dígito)
            tipemi_id = None
            timb_id = None
            codseg_id = None

            if timb8_xml and tail.find(timb8_xml) >= 0:
                p = tail.find(timb8_xml)
                # lo anterior a timb suele ser tipEmi (1 dígito)
                if p >= 1:
                    tipemi_id = tail[p - 1:p]
                timb_id = tail[p:p + 8]
                # codseg es el último dígito del tail restante
                codseg_id = tail[p + 8:] if len(tail) > p + 8 else None
                if codseg_id:
                    codseg_id = codseg_id[-1] if len(codseg_id) > 0 else None
            else:
                # fallback: asumimos estructura tipEmi(1) + timb(8) + codseg(último dígito)
                if len(tail) >= 9:
                    tipemi_id = tail[0:1]
                    timb_id = tail[1:9]
                    codseg_id = tail[9:][-1] if len(tail) > 9 else None

            print("tipEmi(id) :", tipemi_id)
            print("timb(id)   :", timb_id)
            print("codseg(id) :", codseg_id)

            # Ahora comparamos XML vs ID
            print("")
            print("--- COMPARACIÓN XML vs DE@Id ---")
            # tipDE
            if not tipde_xml:
                print("tipDE: XML no encontrado -> uso id =", tipde_id)
            else:
                print("tipDE: xml =", tipde_xml, "| id =", tipde_id, "| OK?" , ("SI" if tipde_xml == tipde_id else "NO"))

            # ruc/dv/est/pun
            if ruc_xml:
                ruc8_xml = zfill_digits(ruc_xml, 8)
                print("ruc : xml =", ruc8_xml, "| id =", ruc_id, "| OK?" , ("SI" if ruc8_xml == ruc_id else "NO"))
            else:
                print("ruc : XML no encontrado")

            if dv_ruc_xml:
                print("dv_ruc: xml =", dv_ruc_xml, "| id =", dv_ruc_id, "| OK?" , ("SI" if dv_ruc_xml == dv_ruc_id else "NO"))
            else:
                print("dv_ruc: XML no encontrado")

            if est_xml:
                print("est : xml =", est_xml, "| id =", est_id, "| OK?" , ("SI" if est_xml == est_id else "NO"))
            else:
                print("est : XML no encontrado")

            if pun_xml:
                print("pun : xml =", pun_xml, "| id =", pun_id, "| OK?" , ("SI" if pun_xml == pun_id else "NO"))
            else:
                print("pun : XML no encontrado")

            # numDoc: puede haber varios, imprimimos cuál coincide con numdoc_id
            if num_candidates:
                found_match = False
                for cand in num_candidates:
                    # Comparar con zero-fill a 7 dígitos
                    cand7 = zfill_digits(cand, 7)
                    if cand7 and cand7 == numdoc_id:
                        found_match = True
                        break
                print("numDoc: id =", numdoc_id, "| existe en XML candidates? ", ("SI" if found_match else "NO"))
                if not found_match:
                    print("➡️  Esto suele ser la causa del 1003/CDC mismatch: el XML tiene otro dNumDoc o agarraste el equivocado.")
            else:
                print("numDoc: XML no encontrado")
            
            # tipCont
            tipcont_vals = find_all_texts(root, ["iTipCont"])
            tipcont_xml = pick_best_by_len([v for _k, v in tipcont_vals], 1)
            if tipcont_xml and tipcont_id:
                print("tipCont: xml =", tipcont_xml, "| id =", tipcont_id, "| OK?" , ("SI" if tipcont_xml == tipcont_id else "NO"))
            else:
                print("tipCont: xml =", tipcont_xml, "| id =", tipcont_id)

            # tipEmi/timb/codseg
            if tipemi1_xml and tipemi_id:
                print("tipEmi: xml =", tipemi1_xml, "| id =", tipemi_id, "| OK?" , ("SI" if tipemi1_xml == tipemi_id else "NO"))
            else:
                print("tipEmi: xml =", tipemi1_xml, "| id =", tipemi_id)

            if timb8_xml and timb_id:
                print("timb: xml =", timb8_xml, "| id =", timb_id, "| OK?" , ("SI" if timb8_xml == timb_id else "NO"))
            else:
                print("timb: xml =", timb8_xml, "| id =", timb_id)

            # codseg en XML puede ser largo; comparamos "terminación" con el id
            if codseg_any and codseg_id:
                ok = False
                if codseg_any == codseg_id:
                    ok = True
                elif codseg_any.endswith(codseg_id):
                    ok = True
                print("codseg: xml =", codseg_any, "| id =", codseg_id, "| OK?" , ("SI" if ok else "NO"))
            else:
                print("codseg: xml =", codseg_any, "| id =", codseg_id)

    # Si el DV interno ya falló -> return 1
    if dv_in_id != dv_calc:
        return 1

    # Si DV interno OK pero SIFEN igual dice 1003, casi siempre es mismatch de campos vs Id.
    # Este script ya deja marcado qué campo no coincide.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
