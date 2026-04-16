import os
import sys


def resource_path(*parts: str) -> str:
    """Return an absolute path to a bundled resource.

    Honours PyInstaller's ``sys._MEIPASS`` when running from a frozen build,
    otherwise resolves relative to this package directory.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "gsboard", "resources", *parts)
    return os.path.join(os.path.dirname(__file__), *parts)
