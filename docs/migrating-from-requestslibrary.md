# Migrating from RequestsLibrary to OdooFxLibrary

> English | [Français](migrating-from-requestslibrary.fr.md)

OdooFxLibrary absorbs the HTTP keywords of
[robotframework-requests](https://github.com/MarketSquare/robotframework-requests) 0.9.7 (RequestsLibrary,
MIT License, Copyright (c) 2016 Bulkan Evcimen): their code is rewritten in the library, under the same
names and arguments, so that a suite written for RequestsLibrary keeps working on Odoo without importing it.
This page says how to move a suite, what changes on purpose, and what Odoo does that a suite must know.

## The move

Replace the import, and nothing else:

```robotframework
*** Settings ***
Library    OdooFxLibrary
```

The 25 current keywords of RequestsLibrary 0.9.7 keep their names, the order, names and defaults of their
parameters:

| Family | Keywords |
| --- | --- |
| Sessions | `Create Session`, `Create Custom Session`, `Create Digest Session`, `Create Client Cert Session`, `Create Ntlm Session`, `Update Session`, `Session Exists`, `Delete All Sessions` |
| Requests on a session | `GET On Session`, `POST On Session`, `PUT On Session`, `PATCH On Session`, `DELETE On Session`, `HEAD On Session`, `OPTIONS On Session` |
| Requests without a session | `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS` |
| Assertions and utilities | `Status Should Be`, `Request Should Be Successful`, `Get File For Streaming Upload` |

The 8 keywords RequestsLibrary already deprecated are not absorbed: `Get Request`, `Post Request`,
`Put Request`, `Patch Request`, `Delete Request`, `Head Request`, `Options Request` (use the
`... On Session` keyword of the same verb) and `To Json` (use `${response.json()}`).

`Create Ntlm Session` needs an optional extra: `pip install robotframework-odoofx[ntlm]` (it installs
`requests_ntlm`). Without it, the keyword fails before creating anything, with a message that starts as
RequestsLibrary's: `requests_ntlm module not installed`.

## Do not import both libraries

The 25 names exist in both libraries: imported together, an unqualified name is ambiguous for Robot
Framework. Each library also keeps its own sessions and its own last response: a session created by one is
unknown to the other, and `Status Should Be` without a response reads the last response of its own library.
Import OdooFxLibrary alone.

## What changes on purpose, its effect on a migrated suite, and the remedy

| Ref. | Change | Effect on a migrated suite | Remedy |
| --- | --- | --- | --- |
| | A request without a session sends no cookie and no timeout but its own. RequestsLibrary sent those of the last `Create Session`, to any host, with the requests of the other sessions and even after `Delete All Sessions`. | A request that counted on that cookie now reads as an anonymous visitor. On Odoo, a protected route read anonymously, redirect followed, answers **200 with the login page**: a suite that checks the status only would stay green. | Pass `cookies=` to the request, or use the session; assert the content type, the redirect history or the final path, not the status alone. |
| | The timeout and cookies given to `Create Session` belong to that session. RequestsLibrary applied the last session's to every session. | A suite that relied on another session's timeout gets the default. | Give each session its own `timeout=`. |
| | `Update Session` replaces a cookie of the same name, whatever its domain. RequestsLibrary kept the existing one. | Lending a `session_id` to a session that already holds Odoo's anonymous one now works; it was ignored before. | None: the documented behaviour now holds. |
| E1 | A Robot `Secret` is accepted in `json`, `data`, `params`, `headers`, `cookies` and `auth` of a request, in `Update Session`, and in `headers` and the password of `auth` of the session keywords; it is revealed when the request is sent (into the session for a session keyword). | Robot's TRACE log shows `<secret>`. | Pass passwords and tokens as `Secret`. |
| E2 | The log masks the secrets it recognizes by name (an `Authorization` or `Cookie` header, a `password`, `token` or `api_key` key...) and every value revealed from a `Secret`; the URL a failure names (status, connection error, timeout) is masked the same way. RequestsLibrary wrote everything in clear. | A suite that read a secret back from the log no longer finds it. | Read values from the response, never from the log. |
| | `debug` is accepted and changes nothing (the raw exchange it dumped carried every secret in clear); `disable_warnings` quiets requests and urllib3 but no longer Python's root logger. | No raw dump. | Read the request and response log lines. |
| | An expected status may be given as a number (`${404}`); an empty one is refused, with another message than RequestsLibrary's. | None for a correct suite. | |
| E3 | `Request Should Be Successful` judges the response it is given, even a failed one; an empty value given is refused, never replaced by the last response. RequestsLibrary replaced a failed response given by the last response (it tested `if not response`, false for a 4xx or 5xx response): a 404 passed once a 200 had followed. | A suite that passed on a failed response turns red: that is the defect it hid. | Fix the request, or assert the failure with `Status Should Be`. |
| E4 | A request that fails without a response (a connection error, a refusal of the write guard, a missing certificate file) clears the last response. RequestsLibrary kept the former one, so that `Status Should Be` without a response judged a stale response. | An assertion after a failed request fails, saying that there is no response. | Assert the request's own outcome. |
| E5 | `Create Client Cert Session` refuses a missing `client_certs` before registering a session (RequestsLibrary failed after registering it) and keeps the single path of a PEM holding both the certificate and the key as given; the file of a streamed upload is closed even when the request fails. | None for a correct suite. | |
| E6 | `Delete All Sessions` clears the last response too. RequestsLibrary kept it, so that under one library instance shared by several missions (rf-mcp), `Status Should Be` without a response judged a response another target had given. | An assertion without a response after `Delete All Sessions` fails, saying that there is no response. | Send the request the assertion is about. |

## The HTTP write guard

A request that writes on Odoo through its RPC routes (`/web/dataset/call_kw`, `call_button`, `resequence`,
a website form, `/jsonrpc` of the `object` service, `/xmlrpc/2/object`, JSON-2) is a write whatever its
HTTP verb: Odoo runs a call of `call_kw` by POST, PUT, PATCH, DELETE, GET, OPTIONS and HEAD. Such a
request is refused before it is sent unless `Connect To Odoo` proved that target, by the same origin and,
when the call names one, the same database, and opened it with `allow_write=${TRUE}`:

```robotframework
Connect To Odoo    http://127.0.0.1:8016    odoo16    admin    ${PASSWORD}    allow_write=${TRUE}    expected_series=16
```

The refusals are named (`Not connected`, `not the proven target`, `is not the proven database`,
`Writes are off`). An accepted write enters `Get Odoo Write Journal` (channel `http`), is sent once, with no
retry and no redirect followed, and its outcome is read in the answer; a gateway status (502, 503, 504)
leaves it `unknown`, to reconcile by reading, never by sending it again. A write by HEAD, the database
service (all but `list`) and the database manager are never sent. Reads, logins, pages, reports and other
APIs keep RequestsLibrary's behaviour. The guard is a net against an accident (a wrong target, a forgotten
write, a double send), not a security boundary: Odoo's access rights stay the control on the server.

## What Odoo does that a suite must know

- A refused login answers **200**, the error in the JSON-RPC body (`odoo.exceptions.AccessDenied`): a status
  check does not see it. `Create Odoo Http Session` judges the body and proves the session it opens.
- A protected route read anonymously answers 200 with the login page when the redirect is followed.
- A verb a web route does not declare is refused with 400; a JSON route reads the body whatever the verb,
  and refuses a call without a JSON body with 400 on Odoo 16 and 415 on Odoo 19.
- An OPTIONS request redirected by a 303 ends as a GET; HEAD does not follow a redirect.
- Odoo sets an anonymous `session_id` cookie on each HTML answer.
- Odoo issues no HTTP Digest challenge: a Digest session reaches it without authenticating. JSON-2 (Odoo 19)
  answers a request without its key with 401 and `WWW-Authenticate: Bearer`, which a Digest session does not
  answer.

## What is not verified on the lab targets

The lab targets are Odoo over plain HTTP, which uses none of the handshakes (in a deployment, a proxy in front
of Odoo carries them). The Digest handshake is played by a unit test against a double that issues the challenge
and checks the response. For NTLM and a client certificate, the unit tests hold only the part of the library:
the NTLM authentication built from the domain, the user and the password, and the certificate handed to the
transport; no NTLM exchange and no TLS presentation is played anywhere. HTTPS and `verify`, the retries and
`proxies` are not played live either.
