"""Explicit test connections to localhost or a credential-bound CloudFront demo."""
import base64
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request


def connection(origin, access_file=None):
    url = urllib.parse.urlsplit(origin)
    local = url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1")
    hosted = url.scheme == "https" and re.fullmatch(r"[a-z0-9]+\.cloudfront\.net", url.netloc)
    if url.username or url.password or url.path not in ("", "/") or url.query or url.fragment or not (local or hosted):
        raise ValueError("Test only a local sandbox or an explicit CloudFront HTTPS deployment")
    headers = {}
    if access_file:
        access = json.loads(Path(access_file).read_text())
        if access["origin"].rstrip("/") != origin.rstrip("/"):
            raise ValueError("Access file does not belong to the requested origin")
        basic = (access["username"] + ":" + access["password"]).encode()
        headers["Authorization"] = "Basic " + base64.b64encode(basic).decode()
    elif hosted:
        raise ValueError("Hosted smoke tests require that deployment's access file")

    class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, response_headers, newurl):
            target = urllib.parse.urlsplit(newurl)
            if (target.scheme, target.netloc) != (url.scheme, url.netloc):
                raise ValueError("Refusing a cross-origin redirect with sandbox credentials")
            return super().redirect_request(req, fp, code, msg, response_headers, newurl)

    return headers, urllib.request.build_opener(SameOriginRedirect)
