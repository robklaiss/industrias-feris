import re, base64, pathlib, zipfile

soap_path = pathlib.Path("artifacts/_stage_13_soap_payload.xml")
soap = soap_path.read_text("utf-8", errors="replace")

m = re.search(r"<[^>]*:xDE>(.*?)</[^>]*:xDE>", soap, flags=re.S)
if not m:
    raise SystemExit("No encontré xDE en artifacts/_stage_13_soap_payload.xml")

b64 = re.sub(r"\s+", "", m.group(1))
raw = base64.b64decode(b64)

out = pathlib.Path("artifacts/xde_from_stage13.zip")
out.write_bytes(raw)

print("SOAP_FILE:", soap_path)
print("xDE_zip_bytes:", len(raw))
print("WROTE:", out)

with zipfile.ZipFile(out, "r") as z:
    names = z.namelist()
    print("ZIP_NAMES:", names)
    n0 = names[0]
    info = z.getinfo(n0)
    print(f"- {n0} usize={info.file_size} csize={info.compress_size} comp={'STORED' if info.compress_type == 0 else info.compress_type}")

    data = z.read(n0)
    head = data[:220].decode("utf-8", "replace")
    print("\nHEAD(220) del primer archivo:\n" + head)

ok = head.startswith('<?xml version="1.0" encoding="UTF-8"?><rLoteDE><rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">')
print("\nDOUBLE_WRAPPER_MATCH_TIPS:", ok)
