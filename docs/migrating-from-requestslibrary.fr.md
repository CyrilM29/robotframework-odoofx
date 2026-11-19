# Passer de RequestsLibrary à OdooFxLibrary

> [English](migrating-from-requestslibrary.md) | Français

OdooFxLibrary absorbe les keywords HTTP de
[robotframework-requests](https://github.com/MarketSquare/robotframework-requests) 0.9.7 (RequestsLibrary,
licence MIT, Copyright (c) 2016 Bulkan Evcimen) : leur code est réécrit dans la bibliothèque, sous les mêmes
noms et arguments, pour qu'une suite écrite pour RequestsLibrary continue de tourner sur Odoo sans l'importer.
Cette page dit comment déplacer une suite, ce qui change exprès, et ce qu'Odoo fait qu'une suite doit savoir.

## Le geste

Remplacer l'import, et rien d'autre :

```robotframework
*** Settings ***
Library    OdooFxLibrary
```

Les 25 keywords actuels de RequestsLibrary 0.9.7 gardent leurs noms, l'ordre, les noms et les défauts de leurs
paramètres :

| Famille | Keywords |
| --- | --- |
| Sessions | `Create Session`, `Create Custom Session`, `Create Digest Session`, `Create Client Cert Session`, `Create Ntlm Session`, `Update Session`, `Session Exists`, `Delete All Sessions` |
| Requêtes sur une session | `GET On Session`, `POST On Session`, `PUT On Session`, `PATCH On Session`, `DELETE On Session`, `HEAD On Session`, `OPTIONS On Session` |
| Requêtes sans session | `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS` |
| Assertions et utilitaires | `Status Should Be`, `Request Should Be Successful`, `Get File For Streaming Upload` |

Les 8 keywords que RequestsLibrary avait déjà dépréciés ne sont pas absorbés : `Get Request`, `Post Request`,
`Put Request`, `Patch Request`, `Delete Request`, `Head Request`, `Options Request` (prendre le keyword
`... On Session` du même verbe) et `To Json` (prendre `${response.json()}`).

`Create Ntlm Session` demande un extra optionnel : `pip install robotframework-odoofx[ntlm]` (il installe
`requests_ntlm`). Sans lui, le keyword échoue avant de rien créer, avec un message qui commence comme celui de
RequestsLibrary : `requests_ntlm module not installed`.

## Ne pas importer les deux bibliothèques

Les 25 noms existent dans les deux bibliothèques : importées ensemble, un nom non qualifié est ambigu pour Robot
Framework. Chaque bibliothèque garde aussi ses propres sessions et sa propre dernière réponse : une session créée
par l'une est inconnue de l'autre, et `Status Should Be` sans réponse lit la dernière réponse de SA bibliothèque.
Importer OdooFxLibrary seule.

## Ce qui change exprès, son effet sur une suite migrée, et le remède

| Réf. | Changement | Effet sur une suite migrée | Remède |
| --- | --- | --- | --- |
| | Une requête sans session n'envoie aucun cookie ni délai autre que les siens. RequestsLibrary envoyait ceux du dernier `Create Session`, vers tout hôte, avec les requêtes des autres sessions et même après `Delete All Sessions`. | Une requête qui comptait sur ce cookie lit désormais en visiteur anonyme. Sur Odoo, une route protégée lue en anonyme, redirection suivie, répond **200 avec la page de connexion** : une suite qui ne juge que le statut resterait verte. | Passer `cookies=` à la requête, ou passer par la session ; asserter le type de contenu, l'historique de redirection ou le chemin final, pas le seul statut. |
| | Le délai et les cookies donnés à `Create Session` appartiennent à cette session. RequestsLibrary imposait ceux de la dernière session à toutes. | Une suite qui comptait sur le délai d'une autre session reçoit le défaut. | Donner à chaque session son `timeout=`. |
| | `Update Session` remplace un cookie de même nom, quel que soit son domaine. RequestsLibrary gardait l'ancien. | Prêter un `session_id` à une session qui porte déjà l'anonyme d'Odoo fonctionne désormais ; c'était ignoré. | Aucun : le comportement documenté tient désormais. |
| E1 | Un `Secret` de Robot est accepté dans `json`, `data`, `params`, `headers`, `cookies` et `auth` d'une requête, dans `Update Session`, et dans `headers` et le mot de passe d'`auth` des keywords de session ; il est déballé à l'envoi (dans la session pour un keyword de session). | Le journal TRACE de Robot affiche `<secret>`. | Passer mots de passe et jetons en `Secret`. |
| E2 | Le journal masque les secrets qu'il reconnaît par leur nom (un en-tête `Authorization` ou `Cookie`, une clé `password`, `token` ou `api_key`...) et toute valeur déballée d'un `Secret` ; l'URL que nomme un échec (statut, erreur de connexion, délai) est masquée de même. RequestsLibrary écrivait tout en clair. | Une suite qui relisait un secret dans le journal ne l'y trouve plus. | Lire les valeurs dans la réponse, jamais dans le journal. |
| | `debug` est accepté et ne change rien (le vidage brut de l'échange portait tous les secrets en clair) ; `disable_warnings` coupe les journaux de requests et d'urllib3, plus le journal racine de Python. | Plus de vidage brut. | Lire les lignes de journal de la requête et de la réponse. |
| | Un statut attendu peut se donner en nombre (`${404}`) ; un statut vide est refusé, avec un autre message que celui de RequestsLibrary. | Aucun pour une suite correcte. | |
| E3 | `Request Should Be Successful` juge la réponse donnée, même en échec ; une valeur vide donnée est refusée, jamais remplacée par la dernière réponse. RequestsLibrary remplaçait une réponse en échec donnée par la dernière réponse (il testait `if not response`, faux pour une réponse 4xx ou 5xx) : une 404 passait dès qu'une 200 avait suivi. | Une suite qui passait sur une réponse en échec devient rouge : c'est le défaut qu'elle cachait. | Corriger la requête, ou asserter l'échec par `Status Should Be`. |
| E4 | Une requête qui échoue sans réponse (erreur de connexion, refus de la garde d'écriture, fichier de certificat absent) efface la dernière réponse. RequestsLibrary gardait l'ancienne, si bien que `Status Should Be` sans réponse jugeait une réponse périmée. | Une assertion après une requête échouée échoue en disant qu'il n'y a pas de réponse. | Asserter l'issue de la requête elle-même. |
| E5 | `Create Client Cert Session` refuse un `client_certs` absent avant d'enregistrer une session (RequestsLibrary échouait après l'avoir enregistrée) et garde tel quel le chemin unique d'un PEM qui porte le certificat et la clé ; le fichier d'un envoi en flux est fermé même quand la requête échoue. | Aucun pour une suite correcte. | |
| E6 | `Delete All Sessions` efface aussi la dernière réponse. RequestsLibrary la gardait, si bien que sous une seule instance partagée par plusieurs missions (rf-mcp), `Status Should Be` sans réponse jugeait une réponse donnée par une autre cible. | Une assertion sans réponse après `Delete All Sessions` échoue en disant qu'il n'y a pas de réponse. | Envoyer la requête dont l'assertion parle. |

## La garde d'écriture HTTP

Une requête qui écrit sur Odoo par ses routes RPC (`/web/dataset/call_kw`, `call_button`, `resequence`, un
formulaire website, `/jsonrpc` du service `object`, `/xmlrpc/2/object`, JSON-2) est une écriture quel que soit
son verbe HTTP : Odoo exécute un appel de `call_kw` par POST, PUT, PATCH, DELETE, GET, OPTIONS et HEAD. Une telle
requête est refusée avant l'envoi tant que `Connect To Odoo` n'a pas prouvé cette cible, par la même origine et,
quand l'appel en nomme une, la même base, et ne l'a pas ouverte avec `allow_write=${TRUE}` :

```robotframework
Connect To Odoo    http://127.0.0.1:8016    odoo16    admin    ${PASSWORD}    allow_write=${TRUE}    expected_series=16
```

Les refus sont nommés (`Not connected`, `not the proven target`, `is not the proven database`,
`Writes are off`). Une écriture acceptée entre dans `Get Odoo Write Journal` (canal `http`), part une seule
fois, sans reprise ni redirection suivie, et son issue se lit dans la réponse ; un statut de passerelle (502,
503, 504) la laisse `unknown`, à réconcilier par une lecture, jamais par un nouvel envoi. Une écriture par HEAD,
le service `db` (sauf `list`) et le gestionnaire de bases ne partent jamais. Les lectures, les connexions, les
pages, les rapports et les autres API gardent le comportement de RequestsLibrary. La garde est un filet contre
l'accident (mauvaise cible, écriture oubliée, double envoi), pas une frontière de sécurité : les droits d'accès
d'Odoo restent le contrôle côté serveur.

## Ce qu'Odoo fait et qu'une suite doit savoir

- Une connexion refusée répond **200**, l'erreur dans le corps JSON-RPC (`odoo.exceptions.AccessDenied`) : un
  contrôle du statut ne la voit pas. `Create Odoo Http Session` juge le corps et prouve la session qu'il ouvre.
- Une route protégée lue en anonyme répond 200 avec la page de connexion quand la redirection est suivie.
- Un verbe qu'une route web ne déclare pas est refusé en 400 ; une route JSON lit le corps quel que soit le
  verbe, et refuse un appel sans corps JSON en 400 sur Odoo 16 et en 415 sur Odoo 19.
- Une requête OPTIONS redirigée par un 303 finit en GET ; HEAD ne suit pas une redirection.
- Odoo pose un cookie `session_id` anonyme sur chaque réponse HTML.
- Odoo ne lance aucun défi HTTP Digest : une session Digest l'atteint sans s'authentifier. JSON-2 (Odoo 19)
  répond à une requête sans sa clé par 401 et `WWW-Authenticate: Bearer`, auquel une session Digest ne répond
  pas.

## Ce qui n'est pas vérifié sur les cibles du labo

Les cibles du labo sont Odoo en HTTP simple, qui n'utilise aucune de ces poignées de main (dans un déploiement,
un proxy placé devant Odoo les porte). La poignée de main Digest est jouée par un test unitaire face à un double
qui lance le défi et vérifie la réponse. Pour NTLM et un certificat client, les tests unitaires ne tiennent que la
part de la bibliothèque : l'authentification NTLM bâtie du domaine, de l'identifiant et du mot de passe, et le
certificat remis au transport ; aucun échange NTLM ni aucune présentation TLS n'est joué nulle part. HTTPS et
`verify`, les reprises et `proxies` ne sont pas joués en live non plus.
