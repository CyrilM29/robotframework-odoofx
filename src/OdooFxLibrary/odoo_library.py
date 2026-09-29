"""
OdooFxLibrary : Core Robot Framework library for Odoo test automation.

Provides keywords for:
- Web UI automation (Browser/Playwright)
- RPC/XML-RPC API calls (direct Odoo backend access)
- ORM introspection (models, fields, records)
- Workflow and state management

Version: 0.1.0 (bootstrap phase)
"""

from robot.api.deco import keyword, library
from robot.libraries.BuiltIn import BuiltIn


@library
class OdooFxLibrary:
    """Odoo test automation library for Robot Framework."""

    ROBOT_LIBRARY_SCOPE = "GLOBAL"
    ROBOT_LIBRARY_VERSION = "0.1.0"

    def __init__(self):
        """Initialize OdooFxLibrary."""
        self.builtin = BuiltIn()
        self._session = None

    @keyword("Connect To Odoo")
    def connect_to_odoo(self, url, email, password):
        """
        Connect to an Odoo instance.

        Args:
            url: Odoo instance URL (e.g., http://localhost:8069)
            email: User email address
            password: User password

        Returns:
            Session ID
        """
        # Stub implementation
        self.builtin.log(f"Connecting to Odoo at {url} as {email}")
        self._session = {"url": url, "email": email, "password": password}
        return self._session

    @keyword("Navigate To Menu")
    def navigate_to_menu(self, menu_path):
        """
        Navigate to a menu in Odoo UI.

        Args:
            menu_path: Menu path (e.g., "Sales > Quotations")
        """
        # Stub implementation
        self.builtin.log(f"Navigating to menu: {menu_path}")

    @keyword("Create New Quotation")
    def create_new_quotation(self):
        """
        Create a new sales quotation.

        Returns:
            Quotation ID
        """
        # Stub implementation
        self.builtin.log("Creating new quotation...")

    @keyword("Assert Quotation Status Is")
    def assert_quotation_status_is(self, expected_status):
        """
        Assert that the current quotation has the expected status.

        Args:
            expected_status: Expected status (e.g., "Sales Order")
        """
        # Stub implementation
        self.builtin.log(f"Asserting quotation status is: {expected_status}")

    @keyword("Disconnect From Odoo")
    def disconnect_from_odoo(self):
        """Disconnect from the Odoo instance."""
        # Stub implementation
        self.builtin.log("Disconnecting from Odoo")
        self._session = None
