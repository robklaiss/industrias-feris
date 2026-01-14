#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Safe Configuration Loader for SIFEN
Loads all sensitive configuration from environment variables only.
Never hardcodes secrets.
"""

import os
import sys
from typing import Dict, Optional


class SifenConfigError(Exception):
    """Configuration error for missing required variables."""
    pass


class SifenConfig:
    """Safe configuration loader for SIFEN system."""
    
    # Required environment variables
    REQUIRED_VARS = {
        'test': ['SIFEN_IDCSC_TEST', 'SIFEN_CSC_TEST'],
        'prod': ['SIFEN_IDCSC_PROD', 'SIFEN_CSC_PROD'],
    }
    
    # Optional variables with defaults
    OPTIONAL_VARS = {
        'SIFEN_ENV': 'test',
        'SIFEN_TIMEOUT': '30',
        'SIFEN_RETRY_COUNT': '3',
    }
    
    def __init__(self, env: Optional[str] = None):
        """Initialize configuration loader.
        
        Args:
            env: Environment to use ('test' or 'prod'). Defaults to SIFEN_ENV or 'test'.
        """
        self.env = env or os.getenv('SIFEN_ENV', 'test')
        self._validate_env()
        self._load_config()
    
    def _validate_env(self):
        """Validate environment name."""
        if self.env not in ['test', 'prod']:
            raise SifenConfigError(f"Invalid environment: {self.env}. Use 'test' or 'prod'")
    
    def _load_config(self):
        """Load all configuration from environment."""
        # Load optional variables with defaults
        for var, default in self.OPTIONAL_VARS.items():
            setattr(self, var.lower(), os.getenv(var, default))
        
        # Load required variables for the environment
        required = self.REQUIRED_VARS.get(self.env, [])
        missing = []
        
        for var in required:
            value = os.getenv(var)
            if value is None:
                missing.append(var)
            else:
                # Store without environment suffix
                clean_name = var.replace('_TEST', '').replace('_PROD', '')
                setattr(self, clean_name.lower(), value)
        
        if missing:
            raise SifenConfigError(
                f"Missing required environment variables for {self.env}: {', '.join(missing)}\n"
                f"Please set these variables or create a .env file with the required values."
            )
    
    def get_idcsc(self) -> str:
        """Get IdCSC for current environment."""
        return self.sifen_idcsc
    
    def get_csc(self) -> str:
        """Get CSC for current environment (never log this!)."""
        return self.sifen_csc
    
    def is_prod(self) -> bool:
        """Check if running in production."""
        return self.env == 'prod'
    
    def is_test(self) -> bool:
        """Check if running in test."""
        return self.env == 'test'
    
    def mask_csc(self, csc: str = None) -> str:
        """Mask CSC for logging (show only first/last chars)."""
        if csc is None:
            csc = self.get_csc()
        if len(csc) <= 8:
            return '*' * len(csc)
        return csc[:2] + '*' * (len(csc) - 4) + csc[-2:]


# Global config instance
_config = None


def get_config(env: Optional[str] = None) -> SifenConfig:
    """Get global configuration instance.
    
    Args:
        env: Environment to use (only on first call).
        
    Returns:
        SifenConfig instance.
    """
    global _config
    if _config is None:
        _config = SifenConfig(env)
    return _config


def require_config(env: Optional[str] = None) -> SifenConfig:
    """Require configuration to be loaded. Exit if missing.
    
    Args:
        env: Environment to use.
        
    Returns:
        SifenConfig instance.
    """
    try:
        return get_config(env)
    except SifenConfigError as e:
        print(f"❌ Configuration Error: {e}", file=sys.stderr)
        print("\n🔧 To fix:", file=sys.stderr)
        print("1. Copy .env.example to .env", file=sys.stderr)
        print("2. Edit .env with your credentials", file=sys.stderr)
        print("3. Run again", file=sys.stderr)
        sys.exit(1)


# Usage example
if __name__ == "__main__":
    # Test configuration loading
    try:
        config = get_config()
        print(f"✅ Environment: {config.env}")
        print(f"✅ IdCSC: {config.get_idcsc()}")
        print(f"✅ CSC: {config.mask_csc()}")
    except SifenConfigError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
