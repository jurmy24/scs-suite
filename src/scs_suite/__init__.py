"""Interactive debugger for Feetech SCSCL servos."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("scs-suite")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
