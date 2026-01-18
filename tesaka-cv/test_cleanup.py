#!/usr/bin/env python3
"""Prueba de cleanup_namespaces"""

import lxml.etree as etree

SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
SOAP_NS = "http://www.w3.org/2003/05/soap-envelope"

# Crear SOAP con namespace por defecto
env = etree.Element(f"{{{SOAP_NS}}}Envelope", nsmap={"env": SOAP_NS, None: SIFEN_NS})
etree.SubElement(env, f"{{{SOAP_NS}}}Header")
body = etree.SubElement(env, f"{{{SOAP_NS}}}Body")
r_envio = etree.SubElement(body, "rEnvioLote")
etree.SubElement(r_envio, "dId").text = "123"
etree.SubElement(r_envio, "xDE").text = "DATA"

print("Antes de cleanup_namespaces:")
xml_before = etree.tostring(env, xml_declaration=True, encoding="UTF-8").decode("utf-8")
print(xml_before)
xmlns_check = f'xmlns="{SIFEN_NS}"'
print(f'xmlns="{SIFEN_NS}" presente: {xmlns_check in xml_before}')
print()

# Aplicar cleanup_namespaces
etree.cleanup_namespaces(env, top_nsmap={"env": SOAP_NS, None: SIFEN_NS})

print("Después de cleanup_namespaces:")
xml_after = etree.tostring(env, xml_declaration=True, encoding="UTF-8").decode("utf-8")
print(xml_after)
print(f'xmlns="{SIFEN_NS}" presente: {xmlns_check in xml_after}')
print()

# Probar sin cleanup_namespaces
env2 = etree.Element(f"{{{SOAP_NS}}}Envelope", nsmap={"env": SOAP_NS, None: SIFEN_NS})
etree.SubElement(env2, f"{{{SOAP_NS}}}Header")
body2 = etree.SubElement(env2, f"{{{SOAP_NS}}}Body")
r_envio2 = etree.SubElement(body2, "rEnvioLote")
etree.SubElement(r_envio2, "dId").text = "123"
etree.SubElement(r_envio2, "xDE").text = "DATA"

print("Sin cleanup_namespaces:")
xml_no_cleanup = etree.tostring(env2, xml_declaration=True, encoding="UTF-8").decode("utf-8")
print(xml_no_cleanup)
print(f'xmlns="{SIFEN_NS}" presente: {xmlns_check in xml_no_cleanup}')
