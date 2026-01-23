"""
Pipeline logger - Structured logging for SIFEN operations

Provides consistent, structured logging throughout the pipeline.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from contextlib import contextmanager


class PipelineLogger:
    """Structured logger for SIFEN pipeline operations."""
    
    def __init__(self, name: str, log_dir: Optional[Path] = None):
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler if log_dir provided
        if log_dir:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
            
    def info(self, message: str, **kwargs):
        """Log info message with optional structured data."""
        if kwargs:
            self.logger.info(f"{message} | {json.dumps(kwargs)}")
        else:
            self.logger.info(message)
            
    def error(self, message: str, **kwargs):
        """Log error message with optional structured data."""
        if kwargs:
            self.logger.error(f"{message} | {json.dumps(kwargs)}")
        else:
            self.logger.error(message)
            
    def warning(self, message: str, **kwargs):
        """Log warning message with optional structured data."""
        if kwargs:
            self.logger.warning(f"{message} | {json.dumps(kwargs)}")
        else:
            self.logger.warning(message)
            
    def debug(self, message: str, **kwargs):
        """Log debug message with optional structured data."""
        if kwargs:
            self.logger.debug(f"{message} | {json.dumps(kwargs)}")
        else:
            self.logger.debug(message)
            
    def log_operation(self, operation: str, status: str, **data):
        """Log a pipeline operation with structured data."""
        self.info(
            f"Operation: {operation} - {status}",
            operation=operation,
            status=status,
            timestamp=datetime.now().isoformat(),
            **data
        )
        
    def log_metrics(self, metrics: Dict[str, Any]):
        """Log metrics data."""
        self.info("Metrics recorded", **metrics)
        
    @contextmanager
    def log_context(self, operation: str, **context):
        """Context manager for logging operation start/end."""
        start_time = datetime.now()
        self.log_operation(operation, "START", **context)
        
        try:
            yield
            duration = (datetime.now() - start_time).total_seconds()
            self.log_operation(operation, "SUCCESS", duration=duration, **context)
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            self.error(
                f"Operation failed: {operation}",
                operation=operation,
                error=str(e),
                duration=duration,
                **context
            )
            raise


# Global logger instance
_global_logger: Optional[PipelineLogger] = None


def get_logger(name: str = "sifen_pipeline") -> PipelineLogger:
    """Get or create a pipeline logger."""
    global _global_logger
    if _global_logger is None:
        # Try to get log directory from environment
        log_dir = os.environ.get("SIFEN_LOG_DIR")
        if log_dir:
            log_dir = Path(log_dir)
        else:
            # Default to artifacts/logs if we're in tesaka-cv
            if Path("tesaka-cv").exists():
                log_dir = Path("tesaka-cv/artifacts/logs")
            else:
                log_dir = Path("artifacts/logs")
                
        _global_logger = PipelineLogger(name, log_dir)
    return _global_logger


def log_pipeline_step(step: str, **data):
    """Log a pipeline step using the global logger."""
    logger = get_logger()
    logger.log_operation(step, "RUNNING", **data)
