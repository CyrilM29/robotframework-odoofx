# ODOOFX : bibliothèque Odoo pour Robot Framework

**[English version](README.md)**

`OdooFxLibrary` apporte l'automatisation des tests Odoo à Robot Framework :
l'interface web d'Odoo, ses API XML-RPC et JSON-RPC, et l'introspection de
l'ORM (modèles, champs, enregistrements), sous un même vocabulaire de
keywords. Elle vise Odoo Community et Enterprise.

Ce dépôt publie les **sources de la bibliothèque** et, à mesure qu'elles
s'écrivent, la documentation qui la concerne et la référence de ses keywords.

> **État (2026-09-29) : amorçage.** La bibliothèque est un squelette : ses
> keywords sont déclarés et documentés, ils ne pilotent pas encore Odoo (ils
> journalisent ce qu'ils feraient). Ne bâtissez pas de campagne de test sur
> cette version.

## Installation

Depuis un clone de ce dépôt (la bibliothèque n'est pas encore sur PyPI) :

```bash
git clone https://github.com/CyrilM29/robotframework-odoofx.git
cd robotframework-odoofx
pip install -e ".[web]"   # l'extra web apporte la bibliothèque Browser
rfbrowser init            # une fois : navigateurs Playwright, canal web seulement
```

Prérequis : Python 3.10 ou plus, Robot Framework 7.4 ou plus. Extras : `web`
(bibliothèque Browser, Playwright), `visual` (Pillow), `all`.

## Keywords de la version actuelle

| Keyword | Rôle |
| --- | --- |
| `Connect To Odoo` | Ouvrir une session sur une instance Odoo (URL, utilisateur, mot de passe) |
| `Navigate To Menu` | Atteindre un menu par son chemin, par exemple `Sales > Quotations` |
| `Create New Quotation` | Créer un devis de vente |
| `Assert Quotation Status Is` | Vérifier le statut du devis courant |
| `Disconnect From Odoo` | Fermer la session |

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

Les identifiants ne vivent jamais dans une suite : passez-les en ligne de
commande (`robot -v "PASSWORD: Secret:..." suite.robot`, la variable typée de
Robot Framework 7.4 les garde hors des journaux) ou par l'environnement.

## Organisation

```text
src/OdooFxLibrary/    la bibliothèque
```

## Signalements

Les rapports d'anomalie et les suggestions sont les bienvenus en
[issues GitHub](https://github.com/CyrilM29/robotframework-odoofx/issues).

## Licence

Apache 2.0. Voir [LICENSE](LICENSE) et [NOTICE](NOTICE).
