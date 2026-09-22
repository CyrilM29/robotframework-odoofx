# ODOOFX

**Automatisation des tests Odoo pour Robot Framework** : cycle plan → générer
→ réparer sur instances Odoo en direct (Community et Enterprise, versions 14
à 18).

**[English version](README.md)**

## Démarrage rapide

```bash
git clone https://github.com/CyrilM29/robotframework-odoofx.git
cd robotframework-odoofx

python -m venv venv
source venv/bin/activate  # ou venv\Scripts\activate sur Windows

pip install -e ".[all]"
rfbrowser init  # navigateurs Playwright, canal web seulement

pytest tests/                                       # tests unitaires, sans Odoo
robot -v PASSWORD:<secret> specs/odoo_smoke.robot   # smoke test sur un Odoo en direct
```

Les identifiants ne vivent jamais dans une suite : ils passent par la ligne de
commande (`-v`) ou par l'environnement.

## Canaux

- **UI Web** : interface web Odoo via Playwright (bibliothèque Browser)
- **RPC** : APIs XML-RPC et JSON-RPC pour les tests d'intégration directe
- **ORM** : introspection des modèles, champs et enregistrements via RPC
- **Mobile** : application mobile Odoo via Appium (prévu)

## Agents

Cinq agents de test (plan → générer → réparer → istqb + vérifier) :

- `odoo-planner` : décomposer les fonctionnalités Odoo en specs testables
- `odoo-generator` : écrire les suites Robot Framework à partir des specs
- `odoo-healer` : réparer les tests qui échouent sur des instances Odoo en direct
- `odoo-istqb` : vérifier la qualité des tests selon les principes ISTQB
- `odoo-verifier` : vérification indépendante en mode lecture seule

Les agents sont pilotés par le serveur MCP **odoofx-mcp** (gestion des
sessions, exécution des étapes, introspection ORM, état des workflows). Les
définitions des agents et le serveur MCP vivent dans le dépôt studio privé :
ce dépôt livre la bibliothèque, les specs et les tests dont ils dépendent.

## Cibles

- **Toutes les versions d'Odoo** : Community et Enterprise, 14 à 18
- **Instances en direct** : n'importe quelle URL Odoo avec identifiants valides
- **Docker** : instances de test isolées (prévu)

## Structure du dépôt

- `src/OdooFxLibrary/` : bibliothèque Robot Framework (ORM + RPC + web)
- `specs/` : specs Robot Framework et tests de smoke
- `tests/` : tests unitaires, exécutés sans Odoo
- `resources/` : page objects et keywords métier, exemples pour une instance
  à adapter à la vôtre (à venir)
- `scripts/` : gardes exécutées en CI (règles de rédaction, conventions)
- `docs/` : documentation complète (à venir)

## Distribution

- **PyPI** : `robotframework-odoofx` (bibliothèque, specs, tests ; sans agents)
- **Ce dépôt** : `CyrilM29/robotframework-odoofx`, où les issues et pull
  requests sont bienvenues
- **Studio** (privé) : agents, serveur MCP et outillage interne ; chaque
  release en est exportée, son historique est donc indépendant de celui-ci
- **Pack** : ZIP Windows avec le toolkit complet (agents, MCP, libs, scripts),
  prévu

## Licence

Apache 2.0. Voir [LICENSE](LICENSE) pour les détails. Le code upstream
vendorisé est crédité dans [NOTICE](NOTICE).

---

**État** (2026-09-22) : phase de bootstrap. Squelette de bibliothèque, gardes
et tests unitaires en place ; agents et serveur MCP en cours dans le studio.
Toutes les versions d'Odoo ciblées dès le jour 1.
