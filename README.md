# ODOOFX

**Odoo test automation for Robot Framework**: plan → generate → heal cycle on
live Odoo instances (Community and Enterprise, versions 14 to 18).

**[Version française](README.fr.md)**

## Quick start

```bash
git clone https://github.com/CyrilM29/robotframework-odoofx.git
cd robotframework-odoofx

python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

pip install -e ".[all]"
rfbrowser init  # Playwright browsers, web channel only

pytest tests/                                       # unit tests, no Odoo needed
robot -v PASSWORD:<secret> specs/odoo_smoke.robot   # smoke test on a live Odoo
```

Credentials never live in a suite: pass them on the command line (`-v`) or
through the environment.

## Channels

- **Web UI**: Odoo web interface via Playwright (Browser library)
- **RPC**: XML-RPC and JSON-RPC APIs for direct integration testing
- **ORM**: model, field and record introspection through RPC
- **Mobile**: Odoo mobile app via Appium (planned)

## Agents

Five test agents (plan → generate → heal → istqb + verify):

- `odoo-planner`: decompose Odoo features into testable specs
- `odoo-generator`: write Robot Framework suites from specs
- `odoo-healer`: repair failing tests on live Odoo instances
- `odoo-istqb`: verify test quality against ISTQB principles
- `odoo-verifier`: independent read-only verification

Agents are driven through the **odoofx-mcp** MCP server (session management,
step execution, ORM inspection, workflow state). Agent definitions and the MCP
server live in the private studio repository: this repository ships the
library, the specs and the tests they rely on.

## Targets

- **All Odoo versions**: Community and Enterprise, 14 to 18
- **Live instances**: any Odoo URL with valid credentials
- **Docker**: isolated test instances (planned)

## Repository structure

- `src/OdooFxLibrary/` : Robot Framework library (ORM + RPC + web)
- `specs/` : Robot Framework specs and smoke tests
- `tests/` : unit tests, run without Odoo
- `resources/` : page objects and business keywords, examples for one
  instance to adapt to yours (coming)
- `scripts/` : guards run in CI (writing rules, conventions)
- `docs/` : full documentation (coming)

## Distribution

- **PyPI**: `robotframework-odoofx` (library, specs, tests; no agents)
- **This repository**: `CyrilM29/robotframework-odoofx`, where issues and pull
  requests are welcome
- **Studio** (private): agents, MCP server and internal tooling; every release
  is exported from it, so its history is independent from this one
- **Pack**: Windows ZIP with the full toolkit (agents, MCP, libs, scripts),
  planned

## License

Apache 2.0. See [LICENSE](LICENSE) for details. Vendored upstream code is
credited in [NOTICE](NOTICE).

---

**Status** (2026-09-22): bootstrap phase. Library skeleton, guards and unit
tests in place; agents and MCP server in progress in the studio. All Odoo
versions targeted from day one.
