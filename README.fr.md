# ODOOFX : bibliothèque Odoo pour Robot Framework

**[English version](README.md)**

`OdooFxLibrary` apporte l'automatisation des tests Odoo à Robot Framework.
Aujourd'hui elle parle à Odoo par son API externe : XML-RPC jusqu'à Odoo 18,
JSON-2 à partir d'Odoo 19, derrière un même vocabulaire de keywords qui lit les
enregistrements et les codes d'état, et n'écrit que si la connexion l'autorise,
avec un journal de chaque écriture. Elle vise Odoo Community et Enterprise.
L'interface web (bibliothèque Browser) est le prochain canal.

Ce dépôt publie les **sources de la bibliothèque** et, à mesure qu'elles
s'écrivent, la documentation qui la concerne et la référence de ses keywords.

> **État (0.1.0, 2026-10-05) : amorçage.** Le canal RPC fonctionne, en lecture
> et en écriture, éprouvé en vrai sur Odoo 16 (XML-RPC) et Odoo 19.0-20260908
> (XML-RPC et JSON-2). Les écritures sont fermées tant que la connexion ne les
> autorise pas. Le canal web est un squelette qui ne fait qu'avertir. Les
> signatures peuvent encore changer avant la 1.0.

## Installation

```bash
pip install robotframework-odoofx
```

Prérequis : Python 3.10 ou plus, Robot Framework 7.4 ou plus, et une instance
Odoo joignable en HTTP (conçue pour Odoo 14 et suivants, éprouvée sur 16 et
19). L'extra `web`
(`pip install "robotframework-odoofx[web]"`, puis `rfbrowser init` une fois
pour les navigateurs Playwright) apporte la bibliothèque Browser pour le futur
canal web ; `all` installe tous les extras.

Documentation des keywords :
[cyrilm29.github.io/robotframework-odoofx](https://cyrilm29.github.io/robotframework-odoofx/).

## Keywords de la version actuelle

| Keyword | Rôle |
| --- | --- |
| `Connect To Odoo` | Prouver la cible (URL, base, version) et ouvrir la connexion RPC ; `channel=auto` choisit JSON-2 dès Odoo 19, XML-RPC avant ; `allow_write` autorise les écritures, `expected_series` refuse une autre version d'Odoo |
| `Get Odoo Connection Info` | La cible prouvée de la connexion courante, jamais le secret |
| `Count Odoo Records` | Compter les enregistrements d'un modèle qui répondent à un domaine |
| `Search Read Odoo Records` | Lire les enregistrements d'un modèle qui répondent à un domaine |
| `Get Field Selection Values` | Les codes techniques d'un champ de sélection |
| `Count Odoo Records By State` | Nombre d'enregistrements par code d'état |
| `Get Odoo Record State` | Le code d'état d'un enregistrement identifié |
| `Odoo Record State Should Be` | Échouer si l'enregistrement identifié n'est pas dans le code d'état attendu |
| `Assert Quotation Status Is` | Vérifier le code d'état d'un devis, par référence de commande ou identifiant |
| `Create Odoo Record`, `Update Odoo Record`, `Delete Odoo Record` | Écrire un enregistrement (demande `allow_write`) |
| `Call Odoo Record Method` | Appeler une méthode du modèle comme `action_confirm` ou `action_cancel` (demande `allow_write`) |
| `Get Odoo Write Journal` | Les écritures (après l'entrée `since`) avec leur phase : `planned`, `done`, `failed` ou `unknown` (à relire, jamais à renvoyer) |
| `Odoo Write Journal Should Hold No Unknown Outcome`, `Odoo Last Write Should Be` | Assertions sur le journal : aucune écriture d'effet inconnu, la dernière écriture dans une phase donnée |
| `Reconcile Odoo Write` | Solder une entrée `planned` ou `unknown` du journal après relecture de l'enregistrement |
| `Get Odoo Config Parameter` | Un paramètre système comme `web.base.url` (administrateur) |
| `Odoo User Should Be In Group`, `Odoo User Should Not Be In Group` | Appartenance d'un utilisateur à un groupe, désigné par son identifiant externe |
| `New Odoo Run Marker` | Une étiquette unique à mettre dans un champ libre des enregistrements qu'un run crée |
| `Get Odoo Server Time` | L'horloge du serveur (UTC, à la seconde), pour borner ce qu'un run a créé |
| `Resolve Odoo External Id` | L'id en base derrière un identifiant externe comme `product.product_product_1`, prouvé du modèle attendu |
| `Get Odoo Record` | Un enregistrement identifié, en entier ou par champs |
| `Odoo Record Exists` | Si un enregistrement existe (archivés compris) |
| `Odoo Record Should Exist`, `Odoo Record Should Not Exist` | Prouver une présence ou une disparition sur l'enregistrement identifié |
| `Disconnect From Odoo` | Fermer la connexion |
| `Navigate To Menu` | Squelette (canal web), n'avertit que |
| `Create New Quotation` | Squelette, n'avertit que |

```robotframework
*** Settings ***
Library    OdooFxLibrary

*** Test Cases ***
Read A Quotation State
    Connect To Odoo    http://localhost:8069    ma_base    admin    ${PASSWORD}    channel=xmlrpc
    Assert Quotation Status Is    sale    S00004
    [Teardown]    Disconnect From Odoo
```

Les états se comparent par code (`draft`, `sent`, `sale`, `cancel`), jamais par
libellé traduit : un libellé fait échouer l'assertion (« pas un code d'état »).

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

## Marques

Odoo est une marque d'Odoo S.A. Robot Framework est une marque de la Robot
Framework Foundation. ODOOFX est un projet indépendant, sans affiliation,
parrainage ni approbation d'Odoo S.A. ou de la Robot Framework Foundation.
