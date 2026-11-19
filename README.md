# ODOOFX: Odoo library for Robot Framework

**[Version française](README.fr.md)**

[![PyPI](https://img.shields.io/pypi/v/robotframework-odoofx)](https://pypi.org/project/robotframework-odoofx/)
[![Python](https://img.shields.io/pypi/pyversions/robotframework-odoofx)](https://pypi.org/project/robotframework-odoofx/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](https://github.com/CyrilM29/robotframework-odoofx/blob/main/LICENSE)

```bash
pip install robotframework-odoofx
```

`OdooFxLibrary` brings Odoo test automation to Robot Framework through **two
channels under one keyword vocabulary**: the Odoo web client, driven through
the [Browser](https://robotframework-browser.org/) library, and Odoo's
external API (XML-RPC up to Odoo 18, JSON-2 from Odoo 19). A suite can cross
them: prepare or check data over the API, drive the screen for what you
actually test. It targets Odoo Community and Enterprise, and is **proven live
on Odoo 16 and Odoo 19 Community** (it is designed for Odoo 14 and later; 14,
15, 17 and 18 are not measured yet).

> **Status: alpha.** Both channels work and are proven live on Odoo 16 and 19,
> with an HTTP channel (the keywords of RequestsLibrary, absorbed) and the report
> PDFs Odoo prints. Not covered yet: the kanban, calendar, pivot and graph views,
> the chatter, the mass actions of a list, Odoo's legacy `/jsonrpc` route.
> Signatures may still change before 1.0.

## Install

Requirements: Python 3.10 or later, Robot Framework 7.4 or later, and an Odoo
instance reachable over HTTP. The RPC channel needs nothing more. The `web`
extra (`pip install "robotframework-odoofx[web]"`, then `rfbrowser init` once
for the Playwright browsers) brings the Browser library the web channel is
built on; the `pdf` extra (`pypdf`) reads the text of a report; `all` installs every extra.

Keyword documentation:
[cyrilm29.github.io/robotframework-odoofx](https://cyrilm29.github.io/robotframework-odoofx/).

## Quick start

Over the API, reading a quotation's state:

```robotframework
*** Settings ***
Library    OdooFxLibrary

*** Test Cases ***
Read A Quotation State
    Connect To Odoo    http://localhost:8069    my_database    admin    ${PASSWORD}    channel=xmlrpc
    Assert Quotation Status Is    sale    S00004
    [Teardown]    Disconnect From Odoo
```

On screen, entering a contact in the web client and reading it back
independently:

```robotframework
*** Settings ***
Library     Browser
Library     OdooFxLibrary

*** Test Cases ***
Enter A Company Contact
    ${marker}=    New Odoo Run Marker    prefix=DEMO
    New Browser    chromium    headless=${TRUE}
    New Page    about:blank
    Log In To Odoo Web Client    http://localhost:8069    my_database    admin    ${PASSWORD}
    ...    expected_series=19    allow_write=${TRUE}
    Navigate To Menu    contacts.menu_contacts
    Open New Odoo Web Form
    Fill Odoo Web Field    company_type    company
    Fill Odoo Web Field    name    ${marker} Company
    ${contact_id}=    Save Odoo Web Record
    ${found}=    Search Read Odoo Records Through Web Session    res.partner
    ...    ${{[["id", "=", $contact_id]]}}    fields=${{["name"]}}
    Should Be Equal    ${found}[0][name]    ${marker} Company
    [Teardown]    Run Keywords    Run Keyword And Ignore Error    Discard Odoo Web Changes
    ...    AND    Close Browser
```

Credentials never live in a suite: pass them on the command line
(`robot -v "PASSWORD: Secret:..." suite.robot`, the Robot Framework 7.4 typed
variable keeps them out of the logs) or through the environment.

## How it behaves

- **The target is proven first.** `Get Odoo Server Version` needs no session;
  `Connect To Odoo` and `Log In To Odoo Web Client` check the database and the
  Odoo series, and `expected_series` refuses another Odoo version before
  anything happens (two Odoo versions often run side by side).
- **Technical names and codes, never labels.** Labels are translated and change
  between versions. Menus are opened by external id (`sale.sale_menu_root`),
  fields are named by technical name, a radio or selection option is given by
  its code (`one`, not its label), states are compared by code (`draft`,
  `sent`, `sale`, `cancel`). A label fails an assertion as "not a state code".
- **Writes are off unless you opt in** (`allow_write`), on both channels, and
  every write is journaled with its phase: `planned`, `done`, `failed` or
  `unknown`. An `unknown` write (the answer was lost) is read back and
  reconciled, never sent again.
- **A value is read back as it is typed.** A field the web client did not take
  fails the keyword at once. Relational values are picked among the client's
  proposals, never through Create or Search more, which would write or open a
  dialog.
- **A form left half-typed is never saved by accident.** Odoo saves a form it
  leaves, so `Navigate To Menu`, `Go Back Through Odoo Web Breadcrumb` and
  `Log Out Of Odoo Web Client` refuse to leave one with unsaved changes (save
  or discard first): a failed test never writes what it left behind.

## Keywords

**Connection, reads and state codes** (RPC channel):

| Keyword | Purpose |
| --- | --- |
| `Connect To Odoo` | Prove the target (URL, database, version) and open the RPC connection; `channel=auto` picks JSON-2 from Odoo 19, XML-RPC before; `allow_write` opts in to writes, `expected_series` refuses another Odoo version |
| `Get Odoo Connection Info` | The proven target of the current connection, never the secret |
| `Count Odoo Records` | Count the records of a model matching a domain |
| `Search Read Odoo Records` | Read the records of a model matching a domain |
| `Get Odoo Record` | One identified record, whole or by fields |
| `Odoo Record Exists` | Whether a record exists (archived ones count) |
| `Odoo Record Should Exist`, `Odoo Record Should Not Exist` | Prove a presence or a removal on the identified record |
| `Get Field Selection Values` | The technical codes of a selection field |
| `Count Odoo Records By State` | Record count per state code |
| `Get Odoo Record State` | The state code of one identified record |
| `Odoo Record State Should Be` | Fail unless the identified record is in the expected state code |
| `Assert Quotation Status Is` | Check a quotation's state code, by order reference or id |
| `Get Odoo Config Parameter` | A system parameter such as `web.base.url` (administrator) |
| `Odoo User Should Be In Group`, `Odoo User Should Not Be In Group` | Group membership of a user, the group named by its external id |
| `Resolve Odoo External Id` | The database id behind an external id such as `product.product_product_1`, proved to be of the expected model |
| `Get Odoo Server Time` | The server's clock (UTC, one second), to bracket what a run created |
| `New Odoo Run Marker` | A unique label to put in a free-text field of the records a run creates, to find them again |
| `Disconnect From Odoo` | Close the connection |

**Writes and their journal** (both channels journal):

| Keyword | Purpose |
| --- | --- |
| `Create Odoo Record`, `Update Odoo Record`, `Delete Odoo Record` | Write a record (needs `allow_write`) |
| `Call Odoo Record Method` | Call a model method such as `action_confirm` or `action_cancel` (needs `allow_write`) |
| `Get Odoo Write Journal` | Every write (after entry `since`) with its phase: `planned`, `done`, `failed` or `unknown` (to read back, never to resend) |
| `Odoo Write Journal Should Hold No Unknown Outcome`, `Odoo Last Write Should Be` | Assert on the journal: no write of unknown effect, the last write in a given phase |
| `Reconcile Odoo Write` | Settle a `planned` or `unknown` journal entry after reading the record back |

**Structure of the database** (RPC channel):

| Keyword | Purpose |
| --- | --- |
| `Get Odoo Model Fields`, `Get Odoo Field Definition`, `Odoo Field Exists` | The fields of a model with their type, relation and inverse; one field, or whether it exists (fields come and go between versions) |
| `Get Odoo Model Relations` | The many2one, one2many and many2many fields of a model, with the model they point at |
| `Search Odoo Models` | The models whose technical name contains a text, wizards told apart |
| `Get Odoo Module State`, `Odoo Module Should Be Installed` | The state code of a module; fail unless installed |
| `Call Odoo Model Method` | Call a method that needs no record (`name_search`, `search_count`...); a method that may write needs `allow_write` and is journaled |

**Session context** (RPC channel: Odoo applies no preference of the user to an RPC call):

| Keyword | Purpose |
| --- | --- |
| `Set Odoo Session Context` | A language, time zone or companies sent with every RPC call of the connection, under the context a keyword passes; an inactive language, an unknown time zone or a company the user does not have is refused at once |
| `Get Odoo Session Context`, `Clear Odoo Session Context` | Read or empty the session context (a new connection starts empty) |
| `Get Odoo User Context` | The preferences of the connected user as Odoo gives them (`lang`, `tz`) |

**HTTP** (the session and request keywords of RequestsLibrary, absorbed under their names and arguments, the secrets they recognize masked in the log):

| Keyword | Purpose |
| --- | --- |
| `Create Session`, `Update Session`, `Session Exists`, `Delete All Sessions` | Open an HTTP session towards a server under an alias, merge headers or cookies into it, find it, close them all |
| `Create Custom Session`, `Create Digest Session`, `Create Client Cert Session`, `Create Ntlm Session` | Open a session authenticated by any requests authentication, HTTP Digest, a client certificate, or NTLM (optional extra `ntlm`) |
| `GET On Session`, `POST On Session`, `PUT On Session`, `PATCH On Session`, `DELETE On Session`, `HEAD On Session`, `OPTIONS On Session` | Send a request on a session; without `expected_status` a 4xx or 5xx fails, as in RequestsLibrary; HEAD does not follow a redirect, the other verbs do |
| `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS` | Send a request to a full URL without a session; unlike RequestsLibrary, no cookie nor timeout of another session goes with it |
| `Status Should Be`, `Request Should Be Successful`, `Get File For Streaming Upload` | Assert the status of the response given, or of the last one (a failed response given is judged, unlike RequestsLibrary); open a file to stream as a request body |
| `Create Odoo Http Session` | An authenticated Odoo web session on the proven target, proven by its database, series and user, for the routes a logged user reaches (a report PDF) |

A write on Odoo through these keywords (a call of its RPC routes or a website form whose method is not a read) is refused before it is sent unless `Connect To Odoo` proved that target and opened it with `allow_write=${TRUE}`; it then enters the write journal and is sent once.

Coming from RequestsLibrary? The [migration guide](docs/migrating-from-requestslibrary.md) gives each deliberate change, its effect on a suite and its remedy.

**Reports** (the PDF Odoo prints, through a web session of `Create Odoo Http Session`; its text needs the `pdf` extra):

| Keyword | Purpose |
| --- | --- |
| `Get Odoo Report Pdf` | The PDF of a report action on records, by Odoo's report route without following a redirect, a redirect, another status or another type named; refused before any request when the action would save the PDF as an attachment, unless accepted on a writing connection |
| `Get Pdf Text`, `Pdf Should Contain`, `Pdf Should Not Contain` | The text of the PDF, normalized on both sides (Unicode spaces, line breaks, a reference the template wrapped at its hyphen), and a value asserted in it or absent from it; a PDF without a text layer fails saying so |
| `Get Odoo Formatted Amount` | An amount as Odoo writes it in a document of a language and a currency, read from `res.lang` and `res.currency` |

**Web client: session, navigation and reads** (built on the Browser library,
which opens the browser, the context and the page):

| Keyword | Purpose |
| --- | --- |
| `Get Odoo Server Version` | The server's version and series, without session nor secret: the proof a suite opens with |
| `Log In To Odoo Web Client` | Log in through the login page of a named database; `expected_series` refuses another Odoo version before the page opens; the session's database and series are proven, the secret is never logged; `allow_write` opts in to screen writes |
| `Get Odoo Web Session Info`, `Odoo Web Session Is Open`, `Odoo Web Client Is Shown` | The target of the open web session; whether the session and the web client are still there |
| `Navigate To Menu` | Open an application, then its menus, by external ids (`sale.sale_menu_root`), never by label; waits for the view that replaces the one shown |
| `Get Odoo Web View`, `Get Odoo Web Current App` | The view shown (model, view type, action, record id) and the application of the menu bar |
| `Count Odoo Web View Records`, `Get Odoo Web Pager Total`, `Count Odoo Web Search Facets` | What the list or kanban shows: records (ghost cards excluded), the pager's total, the search facets |
| `Search Odoo Web View`, `Select Odoo Web Search Filter`, `Remove Odoo Web Search Facet`, `Switch Odoo Web View` | Search a list through its search bar: a text on a field, or a filter, of the search view, named by its technical name (found at its place in the view's arch, the domain the client sends checked against the arch); remove a facet; switch the action's view (list, kanban). Each waits for the list Odoo shows, returns the count it answered, and writes nothing |
| `Open Odoo Web Record`, `Open Odoo Web Record By Id`, `Get Odoo Web List Cell Text`, `Get Odoo Web Breadcrumb Depth`, `Go Back Through Odoo Web Breadcrumb` | Open a shown record in its form (by the cell of a named field), or any record by its model and id (one a suite created over RPC), read a list cell, read and walk back the breadcrumb |
| `Get Odoo Web Statusbar Value`, `Odoo Web Form Should Be Saved` | The technical code of the form's current step; no pending change |
| `Count Odoo Records Through Web Session`, `Search Read Odoo Records Through Web Session` | Reads with the page's session cookie, on the same route from Odoo 16 to 19 |
| `Log Out Of Odoo Web Client` | Log out through the user menu |

**Web client: form entry** (screen writes need `allow_write` at the login and
are journaled):

| Keyword | Purpose |
| --- | --- |
| `Open New Odoo Web Form`, `Select Odoo Web Form Tab` | Open the form of a new record from a list or kanban; show a notebook page by its name |
| `Fill Odoo Web Field`, `Get Odoo Web Field Value` | Enter a value and read it back on the screen at once: text, numbers and dates (given as `2.5` and ISO, typed in the user's format), radio option and selection by code, checkbox, many2one and tags by exact name or by id; read what the form shows, a number field as a number |
| `Save Odoo Web Record`, `Discard Odoo Web Changes`, `Get Odoo Web Invalid Fields`, `Odoo Web Form Is Unsaved` | Save and get the record id, or a refusal naming its cause; drop pending changes; the fields marked invalid; whether the form holds unsaved changes |
| `Add Odoo Web Line`, `Fill Odoo Web Line Field`, `Get Odoo Web Lines`, `Get Odoo Web Line Field Value`, `Delete Odoo Web Line` | Add a line to a one2many field (the lines of a sales order), a section or a note by its `display_type`; fill a field of the line in edition (the text of a section or a note on Odoo 16 and 19 alike); read the lines once shown as stored, with their type; read one field of a line, a number as a number in the user's format; delete a line by its position |
| `Delete Odoo Web Section` | Delete a section of a list of lines with the lines Odoo attaches to it, by its menu as Odoo 19 does (a subsection up to the next section or subsection); refused before any click on Odoo 16, whose delete button of a section removes its row alone |
| `Click Odoo Web Form Button` | Press a button that calls a method of the record (`action_confirm`), by its technical name, waiting until Odoo answered and reloaded the record (needs `allow_write`, journaled); or a button that opens a window action, by the action's external id, without writing |
| `Archive Odoo Web Record`, `Unarchive Odoo Web Record`, `Delete Odoo Web Record`, `Odoo Web Confirmation Is Open` | Archive, unarchive or delete the record of the form through its Actions menu, the entry told by its icon (Odoo 19) or by the place the code of Odoo gives it (Odoo 16), never by its label; Odoo's question accepted, or refused with `confirm=${FALSE}`; journaled, Odoo's refusal reported with the class of its exception; whether a question of Odoo is open |
| `Odoo Web Dialog Is Open`, `Fill Odoo Web Dialog Field`, `Get Odoo Web Dialog Field Value`, `Click Odoo Web Dialog Button`, `Close Odoo Web Dialog` | Work in the dialog a button opened (a wizard): whether one is shown, enter and read its fields on the wizard's model, press a button of its footer by its technical name (and its id when several share it; needs `allow_write`, journaled) and get the view it opens, close it without writing |

`Create New Quotation` is a skeleton that only warns: do not rely on it.

## Layout

```text
src/OdooFxLibrary/    the library
```

## Issues

Bug reports and suggestions are welcome as
[GitHub issues](https://github.com/CyrilM29/robotframework-odoofx/issues).

## License

Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Trademarks

Odoo is a trademark of Odoo S.A. Robot Framework is a trademark of the Robot
Framework Foundation. ODOOFX is an independent project, not affiliated with,
sponsored or endorsed by Odoo S.A. or the Robot Framework Foundation.
