# ODOOFX: Odoo library for Robot Framework

**[Version française](README.fr.md)**

`OdooFxLibrary` brings Odoo test automation to Robot Framework: the Odoo web
interface, its XML-RPC and JSON-RPC APIs, and ORM introspection (models,
fields, records), under one keyword vocabulary. It targets Odoo Community and
Enterprise.

This repository publishes the **library sources** and, as they are written,
the documentation that concerns the library and its keyword reference.

> **Status (2026-09-29): bootstrap.** The library is a skeleton: its keywords
> are declared and documented, and they do not drive Odoo yet (they log what
> they would do). Do not build a test campaign on this version.

## Install

From a clone of this repository (the library is not on PyPI yet):

```bash
git clone https://github.com/CyrilM29/robotframework-odoofx.git
cd robotframework-odoofx
pip install -e ".[web]"   # the web extra brings the Browser library
rfbrowser init            # one-time: Playwright browsers, web channel only
```

Requirements: Python 3.10 or later, Robot Framework 7.4 or later. Extras:
`web` (Browser library, Playwright), `visual` (Pillow), `all`.

## Keywords of the current version

| Keyword | Purpose |
| --- | --- |
| `Connect To Odoo` | Open a session on an Odoo instance (URL, user, password) |
| `Navigate To Menu` | Reach a menu by its path, such as `Sales > Quotations` |
| `Create New Quotation` | Create a sales quotation |
| `Assert Quotation Status Is` | Check the status of the current quotation |
| `Disconnect From Odoo` | Close the session |

```robotframework
*** Settings ***
Library    OdooFxLibrary

*** Test Cases ***
Create A Quotation
    Connect To Odoo    http://localhost:8069    admin    ${PASSWORD}
    Navigate To Menu    Sales > Quotations
    Create New Quotation
    Assert Quotation Status Is    Quotation
    [Teardown]    Disconnect From Odoo
```

Credentials never live in a suite: pass them on the command line
(`robot -v "PASSWORD: Secret:..." suite.robot`, the Robot Framework 7.4 typed
variable keeps them out of the logs) or through the environment.

## Layout

```text
src/OdooFxLibrary/    the library
```

## Issues

Bug reports and suggestions are welcome as
[GitHub issues](https://github.com/CyrilM29/robotframework-odoofx/issues).

## License

Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
