#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Basic Auth Middleware for SIFEN Web Interface
Simple authentication for admin access.
"""

import base64
import os
from functools import wraps

from flask import request, Response


def check_auth(username, password):
    """Check if username/password are correct."""
    admin_user = os.getenv('ADMIN_USER')
    admin_pass = os.getenv('ADMIN_PASS')
    
    if not admin_user or not admin_pass:
        return False
    
    return username == admin_user and password == admin_pass


def authenticate():
    """Send 401 response that enables basic auth."""
    return Response(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'})


def requires_auth(f):
    """Decorator to require basic auth."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


def require_admin_credentials():
    """Check if admin credentials are set in environment."""
    admin_user = os.getenv('ADMIN_USER')
    admin_pass = os.getenv('ADMIN_PASS')
    
    if not admin_user or not admin_pass:
        raise RuntimeError(
            "ADMIN_USER and ADMIN_PASS environment variables are required.\n"
            "Please set these variables before starting the web interface."
        )


# Rate limiting (simple in-memory)
from collections import defaultdict, deque
from time import time

RATE_LIMIT = {
    'requests': 10,  # requests per minute
    'window': 60,   # seconds
}

rate_limit_store = defaultdict(deque)


def check_rate_limit(ip):
    """Simple rate limiting per IP."""
    now = time()
    requests = rate_limit_store[ip]
    
    # Remove old requests outside the window
    while requests and requests[0] <= now - RATE_LIMIT['window']:
        requests.popleft()
    
    # Check if exceeded
    if len(requests) >= RATE_LIMIT['requests']:
        return False
    
    # Add current request
    requests.append(now)
    return True


def rate_limited(f):
    """Decorator to apply rate limiting."""
    @wraps(f)
    def decorated(*args, **kwargs):
        ip = request.remote_addr
        if not check_rate_limit(ip):
            return Response('Rate limit exceeded. Try again later.', 429)
        return f(*args, **kwargs)
    return decorated


# Usage example with Flask:
"""
from flask import Flask
from tools.web_auth import requires_auth, rate_limited, require_admin_credentials

app = Flask(__name__)

@app.before_first_request
def check_credentials():
    require_admin_credentials()

@app.route('/')
@rate_limited
@requires_auth
def admin_panel():
    return 'Welcome to admin panel!'
"""
