"""OpenCTP Gateway module for TycheEngine.

DLL loading must happen before importing gateway classes.
Use dll_loader.load_api() first, then import OpenCtpGateway.
"""

from src.modules.openctp_gateway.config import GatewayConfig

__all__ = ["GatewayConfig"]
