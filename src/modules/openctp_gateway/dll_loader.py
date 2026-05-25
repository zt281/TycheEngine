"""DLL loader for OpenCTP/TTS API bindings.

Handles:
- Determining correct DLL subdirectory based on gateway_type
- Inserting paths into sys.path for Python import resolution
- Registering DLL directories on Windows for _se.dll loading
- Validating that required files exist
- Returning imported API modules
"""

import importlib
import logging
import os
import platform
import sys
from typing import Tuple

logger = logging.getLogger(__name__)

# Mapping from gateway_type to DLL subdirectory name
_GATEWAY_TYPE_MAP = {
    "futures": "tts-future",
    "stocks": "tts-stock",
}

# Expected module names by gateway type
_MODULE_NAMES = {
    "futures": ("thostmduserapi", "thosttraderapi"),
    "stocks": ("soptthostmduserapi", "soptthosttraderapi"),
}

# Expected DLL file names by gateway type
_DLL_FILES = {
    "futures": ("thostmduserapi_se.dll", "thosttraderapi_se.dll"),
    "stocks": ("soptthostmduserapi_se.dll", "soptthosttraderapi_se.dll"),
}


def _get_dll_dir(gateway_type: str) -> str:
    """Get the absolute path to the DLL directory for the given gateway type."""
    subdir = _GATEWAY_TYPE_MAP.get(gateway_type)
    if subdir is None:
        raise ValueError(
            f"Unknown gateway_type: '{gateway_type}'. "
            f"Must be one of: {list(_GATEWAY_TYPE_MAP.keys())}"
        )
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "dlls", subdir)


def _get_version_subdir() -> str:
    """Get the Python version-specific subdirectory name (e.g. 'py39')."""
    return "py{}{}".format(sys.version_info.major, sys.version_info.minor)


def _validate_files(dll_dir: str, version_dir: str, gateway_type: str) -> None:
    """Validate that required DLL and wrapper files exist.

    Raises FileNotFoundError if critical files are missing.
    """
    md_name, td_name = _MODULE_NAMES[gateway_type]

    # Check SWIG wrapper .py files
    for wrapper in (md_name + ".py", td_name + ".py"):
        wrapper_path = os.path.join(dll_dir, wrapper)
        if not os.path.isfile(wrapper_path):
            raise FileNotFoundError(
                f"SWIG wrapper not found: {wrapper_path}"
            )

    # Check .dll files (Windows only)
    if platform.system() == "Windows":
        dll_files = _DLL_FILES.get(gateway_type, ())
        for dll_file in dll_files:
            dll_path = os.path.join(dll_dir, dll_file)
            if not os.path.isfile(dll_path):
                raise FileNotFoundError(
                    f"DLL file not found: {dll_path}"
                )

    # Check version-specific .pyd files
    if not os.path.isdir(version_dir):
        raise FileNotFoundError(
            f"Python version directory not found: {version_dir}. "
            f"Current Python version: {_get_version_subdir()}"
        )

    for pyd_name in ("_" + md_name + ".pyd", "_" + td_name + ".pyd"):
        pyd_path = os.path.join(version_dir, pyd_name)
        if not os.path.isfile(pyd_path):
            raise FileNotFoundError(
                f"Python extension not found: {pyd_path}"
            )


def load_api(gateway_type: str) -> Tuple:
    """Load and return the CTP API modules for the specified gateway type.

    This function MUST be called before importing any CTP API classes.
    It sets up sys.path and DLL directories, then imports and returns
    the (md_module, td_module) tuple.

    Args:
        gateway_type: "futures" or "stocks"

    Returns:
        Tuple of (md_api_module, td_api_module)

    Raises:
        ValueError: If gateway_type is invalid
        FileNotFoundError: If required DLL files are missing
        ImportError: If API modules cannot be imported
    """
    dll_dir = _get_dll_dir(gateway_type)
    version_subdir = _get_version_subdir()
    version_dir = os.path.join(dll_dir, version_subdir)

    logger.info(
        "Loading %s API from: %s (Python %s)",
        gateway_type, dll_dir, version_subdir,
    )

    # Validate files exist before attempting any path manipulation
    _validate_files(dll_dir, version_dir, gateway_type)

    # Register DLL directory for Windows _se.dll resolution
    if platform.system() == "Windows":
        os.add_dll_directory(dll_dir)
        logger.debug("Added DLL directory: %s", dll_dir)

    # Insert paths at front of sys.path for import priority
    # Version dir first (for .pyd), then dll_dir (for .py wrappers)
    if version_dir not in sys.path:
        sys.path.insert(0, version_dir)
    if dll_dir not in sys.path:
        sys.path.insert(0, dll_dir)

    # Import the API modules
    md_name, td_name = _MODULE_NAMES[gateway_type]

    try:
        md_module = importlib.import_module(md_name)
        td_module = importlib.import_module(td_name)
    except ImportError as e:
        raise ImportError(
            f"Failed to import {gateway_type} API modules from {dll_dir}: {e}"
        ) from e

    logger.info(
        "Successfully loaded API modules: %s, %s", md_name, td_name,
    )

    return md_module, td_module
