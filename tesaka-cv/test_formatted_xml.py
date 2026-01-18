#!/usr/bin/env python3
"""Test formatted XML with SIFEN"""

import base64
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from tools.send_sirecepde import send_recibe_lote

# Read the formatted XML
with open("xDE_test.b64", "r") as f:
    xde_b64 = f.read().strip()

# Send to SIFEN
response = send_recibe_lote(
    xde_b64=xde_b64,
    env="test"
)

print(f"Response: {response}")
print(f"dCodRes: {response.get('dCodRes')}")
print(f"dMsgRes: {response.get('dMsgRes')}")
