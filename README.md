# ODOOFX: Odoo library for Robot Framework

**[Version française](README.fr.md)**

[![PyPI](https://img.shields.io/pypi/v/robotframework-odoofx)](https://pypi.org/project/robotframework-odoofx/)
[![Python](https://img.shields.io/pypi/pyversions/robotframework-odoofx)](https://pypi.org/project/robotframework-odoofx/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](https://github.com/CyrilM29/robotframework-odoofx/blob/main/LICENSE)

`OdooFxLibrary` brings Odoo test automation to Robot Framework. Today it talks
to Odoo through its external API: XML-RPC up to Odoo 18, JSON-2 from Odoo 19,
behind one keyword vocabulary that reads records and state codes, and writes
only when the connection opts in, with a journal of every write. It targets
Odoo Community and Enterprise. The web interface (Browser library) is the next
channel.

This repository publishes the **library sources** and, as they are written,
the documentation that concerns the library and its keyword reference.

> **Status (0.1.0, 2026-10-05): bootstrap.** The RPC channel works, reads and
> writes, proven live on Odoo 16 (XML-RPC) and Odoo 19.0-20260908 (XML-RPC and
> JSON-2). Writes are off unless the connection opts in. The web channel is a
> skeleton that only warns. Signatures may still change before 1.0.

## Install

```bash
pip install robotframework-odoofx
```

Requirements: Python 3.10 or later, Robot Framework 7.4 or later, and an Odoo
instance reachable over HTTP (designed for Odoo 14 and later, proven on 16 and
19). The `web` extra
(`pip install "robotframework-odoofx[web]"`, then `rfbrowser init` once for
the Playwright browsers) brings the Browser library for the coming web channel;
`all` installs every extra.

Keyword documentation:
[cyrilm29.github.io/robotframework-odoofx](https://cyrilm29.github.io/robotframework-odoofx/).

## Keywords of the current version

| Keyword | Purpose |
| --- | --- |
| `Connect To Odoo` | Prove the target (URL, database, version) and open the RPC connection; `channel=auto` picks JSON-2 from Odoo 19, XML-RPC before; `allow_write` opts in to writes, `expected_series` refuses another Odoo version |
| `Get Odoo Connection Info` | The proven target of the current connection, never the secret |
| `Count Odoo Records` | Count the records of a model matching a domain |
| `Search Read Odoo Records` | Read the records of a model matching a domain |
| `Get Field Selection Values` | The technical codes of a selection field |
| `Count Odoo Records By State` | Record count per state code |
| `Get Odoo Record State` | The state code of one identified record |
| `Odoo Record State Should Be` | Fail unless the identified record is in the expected state code |
| `Assert Quotation Status Is` | Check a quotation's state code, by order reference or id |
| `Create Odoo Record`, `Update Odoo Record`, `Delete Odoo Record` | Write a record (needs `allow_write`) |
| `Call Odoo Record Method` | Call a model method such as `action_confirm` or `action_cancel` (needs `allow_write`) |
| `Get Odoo Write Journal` | Every write (after entry `since`) with its phase: `planned`, `done`, `failed` or `unknown` (to read back, never to resend) |
| `Odoo Write Journal Should Hold No Unknown Outcome`, `Odoo Last Write Should Be` | Assert on the journal: no write of unknown effect, the last write in a given phase |
| `Reconcile Odoo Write` | Settle a `planned` or `unknown` journal entry after reading the record back |
| `Get Odoo Config Parameter` | A system parameter such as `web.base.url` (administrator) |
| `Odoo User Should Be In Group`, `Odoo User Should Not Be In Group` | Group membership of a user, the group named by its external id |
| `New Odoo Run Marker` | A unique label to put in a free-text field of the records a run creates |
| `Get Odoo Server Time` | The server's clock (UTC, one second), to bracket what a run created |
| `Resolve Odoo External Id` | The database id behind an external id such as `product.product_product_1`, proved to be of the expected model |
| `Get Odoo Record` | One identified record, whole or by fields |
| `Odoo Record Exists` | Whether a record exists (archived ones count) |
| `Odoo Record Should Exist`, `Odoo Record Should Not Exist` | Prove a presence or a removal on the identified record |
| `Disconnect From Odoo` | Close the connection |
| `Navigate To Menu` | Skeleton (web channel), only warns |
| `Create New Quotation` | Skeleton, only warns |

```robotframework
*** Settings ***
Library    OdooFxLibrary

*** Test Cases ***
Read A Quotation State
    Connect To Odoo    http://localhost:8069    my_database    admin    ${PASSWORD}    channel=xmlrpc
    Assert Quotation Status Is    sale    S00004
    [Teardown]    Disconnect From Odoo
```

States are compared by code (`draft`, `sent`, `sale`, `cancel`), never by the
translated label: a label fails the assertion as "not a state code".

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

## Trademarks

Odoo is a trademark of Odoo S.A. Robot Framework is a trademark of the Robot
Framework Foundation. ODOOFX is an independent project, not affiliated with,
sponsored or endorsed by Odoo S.A. or the Robot Framework Foundation.
