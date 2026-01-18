#!/usr/bin/env python3
"""Prueba de namespace en lxml"""

import lxml.etree as etree

SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
SOAP_NS = "http://www.w3.org/2003/05/soap-envelope"

# Método 1: Usando nsmap con None
env1 = etree.Element(f"{{{SOAP_NS}}}Envelope", nsmap={"env": SOAP_NS, None: SIFEN_NS})
body1 = etree.SubElement(env1, f"{{{SOAP_NS}}}Body")
r_envio1 = etree.SubElement(body1, "rEnvioLote")
print("Método 1 (nsmap con None):")
print(etree.tostring(env1, encoding="unicode"))
print()

# Método 2: Estableciendo xmlns directamente
env2 = etree.Element(f"{{{SOAP_NS}}}Envelope", nsmap={"env": SOAP_NS})
env2.set("xmlns", SIFEN_NS)  # Establecer xmlns por defecto
body2 = etree.SubElement(env2, f"{{{SOAP_NS}}}Body")
r_envio2 = etree.SubElement(body2, "rEnvioLote")
print("Método 2 (xmlns directo):")
print(etree.tostring(env2, encoding="unicode"))
print()

# Método 3: Crear rEnvioLote con namespace explícito
env3 = etree.Element(f"{{{SOAP_NS}}}Envelope", nsmap={"env": SOAP_NS})
body3 = etree.SubElement(env3, f"{{{SOAP_NS}}}Body")
r_envio3 = etree.SubElement(body3, f"{{{SIFEN_NS}}}rEnvioLote", nsmap={None: SIFEN_NS})
print("Método 3 (namespace explícito en rEnvioLote):")
print(etree.tostring(env3, encoding="unicode"))
