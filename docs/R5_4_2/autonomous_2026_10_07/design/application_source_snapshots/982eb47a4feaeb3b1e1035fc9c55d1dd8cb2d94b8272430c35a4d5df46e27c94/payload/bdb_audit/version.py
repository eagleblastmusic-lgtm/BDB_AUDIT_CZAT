"""Single authoritative product version identity for BDB Audit v2."""
from __future__ import annotations

APP_VERSION = "2.0.3"
BUILD_ID = f"BDB-V2-STANDALONE-{APP_VERSION}"
__version__ = APP_VERSION

__all__ = ["APP_VERSION", "BUILD_ID", "__version__"]
