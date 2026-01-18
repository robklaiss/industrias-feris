import os
os.environ["SIFEN_EMISOR_RUC"] = "4554737-8"

import lxml.etree as etree

# Simular el proceso de construcción de SOAP
sifen_ns = "http://ekuatia.set.gov.py/sifen/xsd"
soap_env_ns = "http://www.w3.org/2003/05/soap-envelope"

# Construir SOAP como TIPS (sin prefijos en body)
env = etree.Element(
    f"{{{soap_env_ns}}}Envelope",
    nsmap={"env": soap_env_ns, None: sifen_ns}
)
etree.SubElement(env, f"{{{soap_env_ns}}}Header")
body = etree.SubElement(env, f"{{{soap_env_ns}}}Body")

# Usar namespace por defecto (sin prefijo) como TIPS
r_envio = etree.SubElement(body, "rEnvioLote")
dId_elem = etree.SubElement(r_envio, "dId")
dId_elem.text = "202601181700000"
xDE_elem = etree.SubElement(r_envio, "xDE")
xDE_elem.text = "BASE64_DATA_HERE"

# Serializar
payload_xml = etree.tostring(env, xml_declaration=True, encoding="UTF-8", pretty_print=False).decode("utf-8")
payload_xml = payload_xml.replace("<?xml version='1.0' encoding='UTF-8'?>", '<?xml version="1.0" encoding="UTF-8"?>')

print("SOAP generado (estilo TIPS):")
print(payload_xml[:200] + "...")

# Validar estructura
assert "<rEnvioLote>" in payload_xml, "Debe usar rEnvioLote sin prefijo"
assert "<dId>" in payload_xml, "Debe usar dId sin prefijo"
assert "<xDE>" in payload_xml, "Debe usar xDE sin prefijo"
assert f'xmlns="{sifen_ns}"' in payload_xml, "Debe declarar xmlns por defecto"
assert "xmlns:env" in payload_xml, "Debe usar prefijo env para SOAP"

print("\n✅ Validaciones pasadas: SOAP generado correctamente como TIPS")
