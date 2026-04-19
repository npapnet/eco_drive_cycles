# processing_config.py
# --------------------
# ProcessingConfig has been migrated to schema.py (Pydantic BaseModel).
# This module re-exports it for backward compatibility and owns DEFAULT_CONFIG.

from drive_cycle_calculator.schema import ProcessingConfig

DEFAULT_CONFIG = ProcessingConfig()

__all__ = ["ProcessingConfig", "DEFAULT_CONFIG"]
