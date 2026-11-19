"""How an HTTP request and its response are written to the Robot log, secrets masked.

Derived from robotframework-requests 0.9.7 (``RequestsLibrary/log.py``, MIT License, Copyright (c)
2016 Bulkan Evcimen), rewritten: the upstream wrote every header and every body as sent, an
``Authorization`` header, a session cookie or a password in a JSON body included.

A secret is masked where it is recognized: a header whose name says it (``Authorization``, ``Cookie``,
``X-Api-Key``...), a key of a JSON or form body or of a query string that says it (``password``,
``token``...), the password of a URL, the password of Odoo's ``/jsonrpc`` calls (third argument of
``login``, ``authenticate``, ``execute`` and ``execute_kw``) and the master password of its ``db``
service (first argument), a ``name``/``value`` pair whose name says it; a multipart body is summarized,
never written. A secret anywhere else is not recognized, an XML-RPC body (``/xmlrpc/2``) among them,
unless it was given as a Robot ``Secret``: every value the library revealed from one is masked wherever
it appears, whatever the header, key or parameter that carries it.
"""

import json
import re
from typing import Any, Iterable, Mapping, Optional
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlsplit, urlunsplit

MASK = "<redacted>"
LOG_CHAR_LIMIT = 10000
SECRET_HEADERS = frozenset({"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key",
                            "x-openerp-session-id"})
SECRET_KEY = re.compile(r"pass(word|wd)?$|_pwd$|^pwd$|secret|token|api[_-]?key|session[_-]?id", re.IGNORECASE)
ODOO_RPC_SECRET_METHODS = frozenset({"login", "authenticate", "execute", "execute_kw"})


def masked_headers(headers: Optional[Mapping]) -> dict:
    """The headers with the value of every authentication or cookie header replaced by the mask."""
    return {name: MASK if name.lower() in SECRET_HEADERS or SECRET_KEY.search(name) else value
            for name, value in (headers or {}).items()}


def masked_url(url: Optional[str]) -> Optional[str]:
    """``url`` with the password of its user info and the secret keys of its query string masked."""
    if not url:
        return url
    parts = urlsplit(str(url))
    netloc = parts.netloc
    if parts.password is not None:
        netloc = f"{parts.username}:{MASK}@{parts.hostname}" + (f":{parts.port}" if parts.port else "")
    query = parts.query
    if query:
        pairs = parse_qsl(query, keep_blank_values=True)
        query = urlencode([(key, MASK if SECRET_KEY.search(key) else item) for key, item in pairs], safe="<>")
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def path_and_query(url: str) -> str:
    parts = urlsplit(url)
    return parts.path + (f"?{parts.query}" if parts.query else "")


def masked_message(message: str, url: Optional[str]) -> str:
    """``message`` with ``url`` masked as the log masks it, whole or as the path and query a connection error names."""
    if not url:
        return message
    safe = masked_url(url)
    for raw, masked in ((str(url), safe), (path_and_query(str(url)), path_and_query(safe))):
        if raw and raw != masked:
            message = message.replace(raw, masked)
    return message


def masked_secrets(text: Any, secrets: Iterable[str]) -> Any:
    """``text`` with every value of ``secrets`` masked, as written, URL-encoded or JSON-escaped."""
    if not isinstance(text, str):
        return text
    forms = {form for value in secrets if value for form in
             (value, quote(value, safe=""), quote_plus(value), json.dumps(value)[1:-1])}
    for form in sorted(forms, key=len, reverse=True):
        text = text.replace(form, MASK)
    return text


def masked_value(value: Any) -> Any:
    """``value`` with every entry whose key names a secret masked, at any depth."""
    if isinstance(value, Mapping):
        masked = {key: MASK if isinstance(key, str) and SECRET_KEY.search(key) else masked_value(item)
                  for key, item in value.items()}
        args = masked.get("args")
        if masked.get("method") in ODOO_RPC_SECRET_METHODS and isinstance(args, list) and len(args) >= 3:
            masked["args"] = args[:2] + [MASK] + args[3:]
        elif masked.get("service") == "db" and isinstance(args, list) and args:
            masked["args"] = [MASK] + args[1:]
        name = masked.get("name")
        if "value" in masked and isinstance(name, str) and SECRET_KEY.search(name):
            masked["value"] = MASK
        return masked
    if isinstance(value, list):
        return [masked_value(item) for item in value]
    return value


def masked_body(body: Any, secrets: Iterable[str] = ()) -> Optional[str]:
    """A request or response body as text for the log, secrets masked: JSON and form bodies are parsed.

    The values revealed from a Robot ``Secret`` are masked in the raw text first, before any parsing rewrites
    it; an XML body (XML-RPC) is never read as a form. A file being uploaded is named, never read."""
    if body is None or body == b"" or body == "":
        return None
    if hasattr(body, "read"):
        return repr(body)
    text = masked_secrets(body.decode("utf-8", errors="replace") if isinstance(body, bytes) else str(body), secrets)
    if text.lstrip().startswith("<"):
        return text
    try:
        return json.dumps(masked_value(json.loads(text)), ensure_ascii=False)
    except ValueError:
        pass
    if "=" not in text:
        return text
    try:
        pairs = parse_qsl(text, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return text
    return urlencode([(key, MASK if SECRET_KEY.search(key) else item) for key, item in pairs])


def is_text(content_type: Optional[str]) -> bool:
    kind = (content_type or "").split(";")[0].strip().lower()
    return not kind or kind.startswith("text/") or kind.endswith(
        ("json", "xml", "javascript", "x-www-form-urlencoded"))


def truncated(text: Optional[str], limit: int = LOG_CHAR_LIMIT) -> Optional[str]:
    if text is None or len(text) <= limit:
        return text
    return f"{text[:limit]}... ({len(text) - limit} more characters)"


def request_body(request, secrets: Iterable[str] = ()) -> Optional[str]:
    """A request body for the log: a multipart one (an upload) summarized, any other masked and cut."""
    if "multipart/" in (request.headers.get("Content-Type") or "").lower():
        size = len(request.body) if isinstance(request.body, (bytes, str)) else "?"
        return f"<multipart body of {size} bytes>"
    return truncated(masked_body(request.body, secrets))


def request_lines(response, secrets: Iterable[str] = ()) -> str:
    """The request that produced ``response``, as the log shows it (the first request of a redirect)."""
    first = response.history[0].request if response.history else response.request
    redirected = " (redirected)" if response.history else ""
    return (f"{first.method.upper()} Request : url={masked_url(first.url)}{redirected}\n"
            f" headers={masked_headers(first.headers)}\n"
            f" body={request_body(first, secrets)}")


def response_lines(response, secrets: Iterable[str] = ()) -> str:
    return (f"{response.request.method.upper()} Response : url={masked_url(response.url)}\n"
            f" status={response.status_code}, reason={response.reason}\n"
            f" headers={masked_headers(response.headers)}\n"
            f" body={response_body(response, secrets)}")


def response_body(response, secrets: Iterable[str] = ()) -> Optional[str]:
    """The response body for the log: text masked and cut, a binary one (a PDF, an image) named by size."""
    content_type = response.headers.get("Content-Type")
    if not is_text(content_type):
        return f"<{len(response.content)} bytes of {content_type}>"
    return truncated(masked_body(response.content, secrets))
