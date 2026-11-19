"""The web channel of `OdooFxLibrary`: the web client and its session, records opened by id, forms and their
choices, lines of one2many fields and their sections, action buttons, dialogs, the search bar, the view switcher,
the Actions menu of a form."""

from .web import OdooWebKeywords
from .web_buttons import OdooWebButtonKeywords
from .web_choices import OdooWebChoiceKeywords
from .web_dialog import OdooWebDialogKeywords
from .web_form import OdooWebFormKeywords
from .web_lines import OdooWebLineKeywords
from .web_record_actions import OdooWebRecordActionKeywords
from .web_records import OdooWebRecordKeywords
from .web_search import OdooWebSearchKeywords
from .web_sections import OdooWebSectionKeywords
from .web_views import OdooWebViewKeywords


class OdooWebChannelKeywords(OdooWebKeywords, OdooWebRecordKeywords, OdooWebFormKeywords, OdooWebChoiceKeywords,
                             OdooWebLineKeywords, OdooWebSectionKeywords, OdooWebButtonKeywords,
                             OdooWebDialogKeywords, OdooWebSearchKeywords, OdooWebViewKeywords,
                             OdooWebRecordActionKeywords):
    """The web keywords of `OdooFxLibrary`, mixed into it."""
