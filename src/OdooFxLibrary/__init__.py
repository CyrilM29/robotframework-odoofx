"""
ODOOFX - Odoo test automation for Robot Framework.

ORM, RPC/XML-RPC, UI web (Playwright), workflows.
"""

__version__ = "0.1.0"
__author__ = "Cyril Montiel"
__email__ = "cyril@montiel.me"
__license__ = "Apache-2.0"

# Core library exports will go here
from .odoo_library import OdooFxLibrary

__all__ = ["OdooFxLibrary", "__version__"]
