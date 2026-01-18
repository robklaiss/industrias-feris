#!/usr/bin/env python3
"""Test if SIFEN accepts formatted XML"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.sifen_client.soap_client import SoapClient

# Read the formatted XML zip
with open("xDE_test.b64", "r") as f:
    xde_b64 = f.read().strip()

# Create SOAP client
client = SoapClient(env="test")

# Send the request
try:
    response = client.siRecepLoteDE(xde_b64)
    print(f"dCodRes: {response.get('dCodRes')}")
    print(f"dMsgRes: {response.get('dMsgRes')}")
except Exception as e:
    print(f"Error: {e}")
