from lxml import etree

from tools.prevalidate_local_v150 import strip_gcamfufd, SIFEN_NS


def test_strip_gcamfufd_removes_nodes():
    xml_bytes = f"""
    <rDE xmlns="{SIFEN_NS}">
        <gCamFuFD>
            <dCarQR>QRDATA</dCarQR>
        </gCamFuFD>
        <gCamGen>
            <dOrdCompra>123</dOrdCompra>
        </gCamGen>
    </rDE>
    """.encode("utf-8")

    tree = etree.ElementTree(etree.fromstring(xml_bytes))

    assert tree.xpath(".//s:gCamFuFD", namespaces={"s": SIFEN_NS})

    removed = strip_gcamfufd(tree)

    assert removed == 1
    assert not tree.xpath(".//s:gCamFuFD", namespaces={"s": SIFEN_NS})
