# ODOOFX : bibliothèque Odoo pour Robot Framework

**[English version](README.md)**

[![PyPI](https://img.shields.io/pypi/v/robotframework-odoofx)](https://pypi.org/project/robotframework-odoofx/)
[![Python](https://img.shields.io/pypi/pyversions/robotframework-odoofx)](https://pypi.org/project/robotframework-odoofx/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](https://github.com/CyrilM29/robotframework-odoofx/blob/main/LICENSE)

```bash
pip install robotframework-odoofx
```

`OdooFxLibrary` apporte l'automatisation des tests Odoo à Robot Framework par
**deux canaux sous un même vocabulaire de keywords** : le client web d'Odoo,
piloté par la bibliothèque [Browser](https://robotframework-browser.org/), et
l'API externe d'Odoo (XML-RPC jusqu'à Odoo 18, JSON-2 à partir d'Odoo 19). Une
suite peut les croiser : préparer ou contrôler les données par l'API, piloter
l'écran pour ce que l'on teste vraiment. Elle vise Odoo Community et
Enterprise, et est **éprouvée en vrai sur Odoo 16 et Odoo 19 Community** (elle
est conçue pour Odoo 14 et suivants ; 14, 15, 17 et 18 ne sont pas encore
mesurés).

> **État : alpha.** Les deux canaux fonctionnent et sont éprouvés en vrai sur
> Odoo 16 et 19, avec un canal HTTP (les keywords de RequestsLibrary, absorbés)
> et les rapports PDF qu'Odoo imprime. Pas encore couverts : les vues kanban,
> calendrier, pivot et graphique, le chatter, les actions de masse d'une liste,
> l'ancienne route `/jsonrpc` d'Odoo. Les signatures peuvent encore changer
> avant la 1.0.

## Installation

Prérequis : Python 3.10 ou plus, Robot Framework 7.4 ou plus, et une instance
Odoo joignable en HTTP. Le canal RPC n'exige rien de plus. L'extra `web`
(`pip install "robotframework-odoofx[web]"`, puis `rfbrowser init` une fois
pour les navigateurs Playwright) apporte la bibliothèque Browser sur laquelle
le canal web est bâti ; l'extra `pdf` (`pypdf`) lit le texte d'un rapport ; `all` installe tous les extras.

Documentation des keywords :
[cyrilm29.github.io/robotframework-odoofx](https://cyrilm29.github.io/robotframework-odoofx/).

## Démarrage rapide

Par l'API, lire l'état d'un devis :

```robotframework
*** Settings ***
Library    OdooFxLibrary

*** Test Cases ***
Read A Quotation State
    Connect To Odoo    http://localhost:8069    my_database    admin    ${PASSWORD}    channel=xmlrpc
    Assert Quotation Status Is    sale    S00004
    [Teardown]    Disconnect From Odoo
```

À l'écran, saisir un contact dans le client web puis le relire indépendamment :

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

Les identifiants ne vivent jamais dans une suite : les passer en ligne de
commande (`robot -v "PASSWORD: Secret:..." suite.robot`, la variable typée de
Robot Framework 7.4 les garde hors des journaux) ou par l'environnement.

## Comportement

- **La cible est prouvée d'abord.** `Get Odoo Server Version` n'exige aucune
  session ; `Connect To Odoo` et `Log In To Odoo Web Client` vérifient la base
  et la série d'Odoo, et `expected_series` refuse une autre version d'Odoo
  avant tout geste (deux versions d'Odoo tournent souvent côte à côte).
- **Des noms techniques et des codes, jamais des libellés.** Les libellés sont
  traduits et changent d'une version à l'autre. Les menus s'ouvrent par
  identifiant externe (`sale.sale_menu_root`), les champs se nomment par leur
  nom technique, une option de radio ou de sélection se donne par son code
  (`one`, pas son libellé), les états se comparent par code (`draft`, `sent`,
  `sale`, `cancel`). Un libellé fait échouer l'assertion : « not a state code ».
- **Les écritures sont fermées tant que vous ne les autorisez pas**
  (`allow_write`), sur les deux canaux, et chacune est journalisée avec sa
  phase : `planned`, `done`, `failed` ou `unknown`. Une écriture `unknown` (la
  réponse s'est perdue) se relit et se réconcilie, elle ne se renvoie jamais.
- **Une valeur est relue telle que saisie.** Un champ que le client web n'a pas
  pris fait échouer le keyword aussitôt. Les valeurs relationnelles se
  choisissent parmi les propositions du client, jamais par Créer ni Recherche
  avancée, qui écriraient ou ouvriraient une boîte de dialogue.
- **Un formulaire laissé à moitié saisi n'est jamais enregistré par accident.**
  Odoo enregistre un formulaire qu'on quitte : `Navigate To Menu`,
  `Go Back Through Odoo Web Breadcrumb` et `Log Out Of Odoo Web Client`
  refusent d'en quitter un qui a des modifications non enregistrées
  (enregistrer ou abandonner d'abord) : un test en échec n'écrit jamais ce
  qu'il a laissé derrière lui.

## Keywords

**Connexion, lectures et codes d'état** (canal RPC) :

| Keyword | Rôle |
| --- | --- |
| `Connect To Odoo` | Prouver la cible (URL, base, version) et ouvrir la connexion RPC ; `channel=auto` choisit JSON-2 à partir d'Odoo 19, XML-RPC avant ; `allow_write` autorise les écritures, `expected_series` refuse une autre version d'Odoo |
| `Get Odoo Connection Info` | La cible prouvée de la connexion courante, jamais le secret |
| `Count Odoo Records` | Compter les enregistrements d'un modèle qui répondent à un domaine |
| `Search Read Odoo Records` | Lire les enregistrements d'un modèle qui répondent à un domaine |
| `Get Odoo Record` | Un enregistrement identifié, en entier ou par champs |
| `Odoo Record Exists` | Si un enregistrement existe (les archivés comptent) |
| `Odoo Record Should Exist`, `Odoo Record Should Not Exist` | Prouver une présence ou une disparition sur l'enregistrement identifié |
| `Get Field Selection Values` | Les codes techniques d'un champ de sélection |
| `Count Odoo Records By State` | Le nombre d'enregistrements par code d'état |
| `Get Odoo Record State` | Le code d'état d'un enregistrement identifié |
| `Odoo Record State Should Be` | Échouer sauf si l'enregistrement identifié est dans le code d'état attendu |
| `Assert Quotation Status Is` | Contrôler le code d'état d'un devis, par référence de commande ou par identifiant |
| `Get Odoo Config Parameter` | Un paramètre système tel que `web.base.url` (administrateur) |
| `Odoo User Should Be In Group`, `Odoo User Should Not Be In Group` | L'appartenance d'un utilisateur à un groupe, le groupe nommé par son identifiant externe |
| `Resolve Odoo External Id` | L'identifiant en base derrière un identifiant externe tel que `product.product_product_1`, prouvé du modèle attendu |
| `Get Odoo Server Time` | L'horloge du serveur (UTC, à la seconde), pour borner ce qu'un run a créé |
| `New Odoo Run Marker` | Un libellé unique à mettre dans un champ texte libre des enregistrements qu'un run crée, pour les retrouver |
| `Disconnect From Odoo` | Fermer la connexion |

**Écritures et leur journal** (les deux canaux journalisent) :

| Keyword | Rôle |
| --- | --- |
| `Create Odoo Record`, `Update Odoo Record`, `Delete Odoo Record` | Écrire un enregistrement (exige `allow_write`) |
| `Call Odoo Record Method` | Appeler une méthode de modèle comme `action_confirm` ou `action_cancel` (exige `allow_write`) |
| `Get Odoo Write Journal` | Chaque écriture (après l'entrée `since`) avec sa phase : `planned`, `done`, `failed` ou `unknown` (à relire, jamais à renvoyer) |
| `Odoo Write Journal Should Hold No Unknown Outcome`, `Odoo Last Write Should Be` | Asserter sur le journal : aucune écriture à l'effet inconnu, la dernière écriture dans une phase donnée |
| `Reconcile Odoo Write` | Solder une entrée `planned` ou `unknown` du journal après relecture de l'enregistrement |

**Structure de la base** (canal RPC) :

| Keyword | Rôle |
| --- | --- |
| `Get Odoo Model Fields`, `Get Odoo Field Definition`, `Odoo Field Exists` | Les champs d'un modèle avec leur type, leur relation et leur inverse ; un champ, ou s'il existe (des champs apparaissent et disparaissent d'une version à l'autre) |
| `Get Odoo Model Relations` | Les champs many2one, one2many et many2many d'un modèle, avec le modèle visé |
| `Search Odoo Models` | Les modèles dont le nom technique contient un texte, assistants distingués |
| `Get Odoo Module State`, `Odoo Module Should Be Installed` | Le code d'état d'un module ; échouer sauf s'il est installé |
| `Call Odoo Model Method` | Appeler une méthode sans enregistrement (`name_search`, `search_count`...) ; une méthode qui peut écrire exige `allow_write` et est journalisée |

**Contexte de session** (canal RPC : Odoo n'applique aucune préférence de l'utilisateur à un appel RPC) :

| Keyword | Rôle |
| --- | --- |
| `Set Odoo Session Context` | Une langue, un fuseau ou des sociétés envoyés avec chaque appel RPC de la connexion, sous le contexte que passe un keyword ; une langue inactive, un fuseau inconnu ou une société que l'utilisateur n'a pas est refusé aussitôt |
| `Get Odoo Session Context`, `Clear Odoo Session Context` | Lire ou vider le contexte de session (une nouvelle connexion part vide) |
| `Get Odoo User Context` | Les préférences de l'utilisateur connecté telles qu'Odoo les donne (`lang`, `tz`) |

**HTTP** (les keywords de session et de requête de RequestsLibrary, absorbés sous leurs noms et arguments, les secrets qu'ils reconnaissent masqués au journal) :

| Keyword | Rôle |
| --- | --- |
| `Create Session`, `Update Session`, `Session Exists`, `Delete All Sessions` | Ouvrir une session HTTP vers un serveur sous un alias, y fusionner en-têtes ou cookies, la retrouver, les fermer toutes |
| `Create Custom Session`, `Create Digest Session`, `Create Client Cert Session`, `Create Ntlm Session` | Ouvrir une session authentifiée par toute authentification de requests, HTTP Digest, un certificat client, ou NTLM (extra optionnel `ntlm`) |
| `GET On Session`, `POST On Session`, `PUT On Session`, `PATCH On Session`, `DELETE On Session`, `HEAD On Session`, `OPTIONS On Session` | Envoyer une requête sur une session ; sans `expected_status`, un 4xx ou un 5xx échoue, comme dans RequestsLibrary ; HEAD ne suit pas une redirection, les autres verbes la suivent |
| `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS` | Envoyer une requête vers une URL complète sans session ; contrairement à RequestsLibrary, aucun cookie ni délai d'une autre session ne part avec elle |
| `Status Should Be`, `Request Should Be Successful`, `Get File For Streaming Upload` | Asserter le statut de la réponse donnée, ou de la dernière (une réponse en échec donnée est jugée, contrairement à RequestsLibrary) ; ouvrir un fichier à envoyer en flux comme corps d'une requête |
| `Create Odoo Http Session` | Une session web d'Odoo authentifiée sur la cible prouvée, prouvée par sa base, sa série et son utilisateur, pour les routes d'un utilisateur connecté (un rapport PDF) |

Une écriture sur Odoo par ces keywords (un appel de ses routes RPC ou un formulaire website dont la méthode n'est pas une lecture) est refusée avant l'envoi tant que `Connect To Odoo` n'a pas prouvé cette cible et ne l'a pas ouverte avec `allow_write=${TRUE}` ; elle entre alors au journal d'écriture et ne part qu'une fois.

Vous venez de RequestsLibrary ? Le [guide de migration](docs/migrating-from-requestslibrary.fr.md) donne chaque écart voulu, son effet sur une suite et son remède.

**Rapports** (le PDF qu'Odoo imprime, par une session web de `Create Odoo Http Session` ; son texte demande l'extra `pdf`) :

| Keyword | Rôle |
| --- | --- |
| `Get Odoo Report Pdf` | Le PDF d'une action de rapport sur des enregistrements, par la route de rapport d'Odoo sans suivre de redirection, une redirection, un autre statut ou un autre type nommés ; refusé avant toute requête quand l'action enregistrerait le PDF en pièce jointe, sauf accord sur une connexion qui écrit |
| `Get Pdf Text`, `Pdf Should Contain`, `Pdf Should Not Contain` | Le texte du PDF, normalisé des deux côtés (espaces Unicode, sauts de ligne, référence coupée par le gabarit à son tiret), et une valeur assertée dedans ou absente ; un PDF sans couche texte échoue en le disant |
| `Get Odoo Formatted Amount` | Un montant tel qu'Odoo l'écrit dans un document d'une langue et d'une devise, lues dans `res.lang` et `res.currency` |

**Client web : session, navigation et lectures** (bâti sur la bibliothèque
Browser, qui ouvre le navigateur, le contexte et la page) :

| Keyword | Rôle |
| --- | --- |
| `Get Odoo Server Version` | La version et la série du serveur, sans session ni secret : la preuve par laquelle s'ouvre une suite |
| `Log In To Odoo Web Client` | Se connecter par la page de connexion d'une base nommée ; `expected_series` refuse une autre version d'Odoo avant même l'ouverture de la page ; la base et la série de la session sont prouvées, le secret n'est jamais journalisé ; `allow_write` autorise les écritures à l'écran |
| `Get Odoo Web Session Info`, `Odoo Web Session Is Open`, `Odoo Web Client Is Shown` | La cible de la session web ouverte ; si la session et le client web sont toujours là |
| `Navigate To Menu` | Ouvrir une application puis ses menus, par identifiants externes (`sale.sale_menu_root`), jamais par libellé ; attend la vue qui remplace celle affichée |
| `Get Odoo Web View`, `Get Odoo Web Current App` | La vue affichée (modèle, type de vue, action, identifiant d'enregistrement) et l'application de la barre de menus |
| `Count Odoo Web View Records`, `Get Odoo Web Pager Total`, `Count Odoo Web Search Facets` | Ce que montre la liste ou le kanban : les enregistrements (cartes fantômes exclues), le total du pager, les facettes de recherche |
| `Search Odoo Web View`, `Select Odoo Web Search Filter`, `Remove Odoo Web Search Facet`, `Switch Odoo Web View` | Chercher dans une liste par sa barre de recherche : un texte sur un champ, ou un filtre, de la vue de recherche, désigné par son nom technique (trouvé à sa place dans l'arch de la vue, le domaine qu'envoie le client contrôlé contre l'arch) ; retirer une facette ; basculer la vue de l'action (liste, kanban). Chacun attend la liste qu'Odoo montre, rend le nombre qu'il a répondu et n'écrit rien |
| `Open Odoo Web Record`, `Open Odoo Web Record By Id`, `Get Odoo Web List Cell Text`, `Get Odoo Web Breadcrumb Depth`, `Go Back Through Odoo Web Breadcrumb` | Ouvrir un enregistrement affiché dans son formulaire (par la cellule d'un champ nommé), ou tout enregistrement par son modèle et son id (celui qu'une suite a créé par RPC), lire une cellule de liste, lire le fil d'Ariane et y revenir |
| `Get Odoo Web Statusbar Value`, `Odoo Web Form Should Be Saved` | Le code technique de l'étape courante du formulaire ; aucune modification en attente |
| `Count Odoo Records Through Web Session`, `Search Read Odoo Records Through Web Session` | Des lectures avec le cookie de session de la page, sur la même route d'Odoo 16 à 19 |
| `Log Out Of Odoo Web Client` | Se déconnecter par le menu utilisateur |

**Client web : saisie de formulaire** (les écritures à l'écran exigent
`allow_write` à la connexion et sont journalisées) :

| Keyword | Rôle |
| --- | --- |
| `Open New Odoo Web Form`, `Select Odoo Web Form Tab` | Ouvrir le formulaire d'un nouvel enregistrement depuis une liste ou un kanban ; afficher une page d'onglets par son nom |
| `Fill Odoo Web Field`, `Get Odoo Web Field Value` | Saisir une valeur et la relire aussitôt à l'écran : texte, nombres et dates (donnés en `2.5` et en ISO, tapés au format de l'utilisateur), option de radio et sélection par code, case à cocher, many2one et étiquettes par nom exact ou par identifiant ; lire ce que montre le formulaire, un champ numérique comme nombre |
| `Save Odoo Web Record`, `Discard Odoo Web Changes`, `Get Odoo Web Invalid Fields`, `Odoo Web Form Is Unsaved` | Enregistrer et obtenir l'identifiant, ou un refus qui nomme sa cause ; abandonner les modifications en attente ; les champs marqués invalides ; si le formulaire a des modifications non enregistrées |
| `Add Odoo Web Line`, `Fill Odoo Web Line Field`, `Get Odoo Web Lines`, `Get Odoo Web Line Field Value`, `Delete Odoo Web Line` | Ajouter une ligne à un champ one2many (les lignes d'une commande), une section ou une note par son `display_type` ; saisir un champ de la ligne en édition (le texte d'une section ou d'une note, sur Odoo 16 comme sur 19) ; lire les lignes une fois affichées telles qu'enregistrées, avec leur type ; lire un champ d'une ligne, un nombre comme nombre au format de l'utilisateur ; supprimer une ligne par sa position |
| `Delete Odoo Web Section` | Supprimer une section d'une liste de lignes avec les lignes qu'Odoo lui rattache, par son menu comme le fait Odoo 19 (une sous-section jusqu'à la section ou sous-section suivante) ; refusé avant tout clic sur Odoo 16, où la corbeille d'une section ne retire que sa rangée |
| `Click Odoo Web Form Button` | Appuyer sur un bouton qui appelle une méthode de l'enregistrement (`action_confirm`), par son nom technique, en attendant qu'Odoo ait répondu et rechargé l'enregistrement (exige `allow_write`, journalisé) ; ou sur un bouton qui ouvre une action de fenêtre, par l'identifiant externe de l'action, sans rien écrire |
| `Archive Odoo Web Record`, `Unarchive Odoo Web Record`, `Delete Odoo Web Record`, `Odoo Web Confirmation Is Open` | Archiver, désarchiver ou supprimer l'enregistrement du formulaire par son menu Actions, l'entrée reconnue à son icône (Odoo 19) ou à la place que lui donne le code d'Odoo (Odoo 16), jamais à son libellé ; la question d'Odoo acceptée, ou refusée avec `confirm=${FALSE}` ; journalisé, le refus d'Odoo rapporté avec la classe de son exception ; savoir si une question d'Odoo est ouverte |
| `Odoo Web Dialog Is Open`, `Fill Odoo Web Dialog Field`, `Get Odoo Web Dialog Field Value`, `Click Odoo Web Dialog Button`, `Close Odoo Web Dialog` | Travailler dans la boîte de dialogue qu'un bouton a ouverte (un assistant) : savoir si elle est affichée, saisir et relire ses champs sur le modèle de l'assistant, appuyer sur un bouton de son pied par son nom technique (et son id quand plusieurs le portent ; exige `allow_write`, journalisé) et obtenir la vue qu'il ouvre, la fermer sans rien écrire |

`Create New Quotation` est un squelette qui se contente d'avertir : ne pas s'y
fier.

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
