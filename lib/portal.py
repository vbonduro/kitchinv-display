"""
Captive portal for initial WiFi/server configuration.

Serves an HTTP form via Microdot and runs a DNS redirect server so phones
auto-detect the portal. Blocks until the form is submitted successfully,
then returns a populated Settings object.
"""

import logging

import uasyncio
from microdot import Microdot

from . import dns
from .config import Settings

# Paths iOS and Android use to detect captive portals.
# Returning a redirect (rather than the expected 204/success body) tells the
# OS there is a portal and triggers the "Sign in to network" prompt.
_PROBE_PATHS = {
    "/generate_204",  # Android / Chrome
    "/hotspot-detect.html",  # iOS / macOS
    "/connecttest.txt",  # Windows
    "/ncsi.txt",  # Windows (older)
    "/success.txt",  # Firefox
    "/canonical.html",  # Ubuntu
}

_SUCCESS_HTML = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KitchInv Setup</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif;
         max-width: 480px; margin: 0 auto; padding: 40px 16px;
         background: #f5f5f5; text-align: center; }
</style>
</head>
<body>
<h2>Saved!</h2>
<p>Connecting to WiFi&hellip; you may close this page.</p>
</body>
</html>"""


def _portal_html(networks: list[str]) -> str:
    options = "".join('<option value="{}">'.format(s) for s in networks)
    return """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KitchInv Setup</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif;
          max-width: 480px; margin: 0 auto; padding: 32px 16px;
          background: #f5f5f5; }}
  h2 {{ margin: 0 0 24px; font-size: 1.4em; }}
  label {{ display: block; margin-top: 20px; font-size: 0.9em;
           font-weight: 600; color: #333; }}
  input {{ display: block; width: 100%; margin-top: 6px; padding: 12px;
           font-size: 1em; border: 1px solid #ccc; border-radius: 8px;
           background: white; min-height: 44px; -webkit-appearance: none; }}
  input[type=submit] {{ background: #2563eb; color: white; border: none;
                        cursor: pointer; margin-top: 32px; font-weight: 600;
                        border-radius: 8px; font-size: 1em; }}
  input[type=submit]:active {{ background: #1d4ed8; }}
</style>
</head>
<body>
<h2>KitchInv Setup</h2>
<form method="POST" action="/configure">
  <label>WiFi Network
    <input name="ssid" type="text" required autocomplete="off" list="networks">
    <datalist id="networks">{options}</datalist>
  </label>
  <label>WiFi Password
    <input name="password" type="password" autocomplete="current-password">
  </label>
  <label>KitchInv Server URL
    <input name="kitchinv_url" type="url" required
           placeholder="http://192.168.1.x:8080" autocomplete="url">
  </label>
  <input type="submit" value="Save &amp; Connect">
</form>
</body>
</html>""".format(options=options)


def run(networks: list[str] | None = None) -> Settings:
    """
    Serve the captive portal until valid credentials are submitted.
    networks: list of SSIDs to pre-populate the SSID field.
    Returns a Settings object.
    """
    if networks is None:
        networks = []

    portal_html = _portal_html(networks)
    app = Microdot()
    stop_event = uasyncio.Event()
    result: list[Settings | None] = [None]

    @app.get("/")
    async def index(request) -> tuple[str, int, dict[str, str]]:  # type: ignore[no-untyped-def]
        return portal_html, 200, {"Content-Type": "text/html"}

    @app.post("/configure")
    async def configure(request) -> tuple[str, int, dict[str, str]]:  # type: ignore[no-untyped-def]
        ssid = (request.form.get("ssid") or "").strip()
        password = request.form.get("password") or ""
        kitchinv_url = (request.form.get("kitchinv_url") or "").strip()

        if not ssid or not kitchinv_url:
            return "<h2>SSID and Server URL are required.</h2>", 400, {"Content-Type": "text/html"}

        result[0] = Settings(wifi={"ssid": ssid, "password": password}, kitchinv_url=kitchinv_url)
        stop_event.set()
        return _SUCCESS_HTML, 200, {"Content-Type": "text/html"}

    @app.route("/<path:path>", methods=["GET", "POST", "HEAD"])
    async def catchall(request, path: str) -> tuple[str, int, dict[str, str]]:  # type: ignore[no-untyped-def]
        # iOS, Android, and Windows probe specific paths to detect captive portals.
        # Serving the portal HTML directly (200) is more reliable than a redirect:
        # some iOS versions treat the redirect target as "success" and skip the popup.
        if "/" + path in _PROBE_PATHS:
            return portal_html, 200, {"Content-Type": "text/html"}
        return "", 302, {"Location": "http://192.168.4.1/"}

    async def _shutdown_watcher() -> None:
        await stop_event.wait()
        app.shutdown()

    async def _run() -> None:
        await uasyncio.gather(
            app.start_server(port=80, debug=False),
            dns.run_server(stop_event),
            _shutdown_watcher(),
        )

    uasyncio.run(_run())
    assert result[0] is not None
    logging.info("Portal complete: %r", result[0])
    return result[0]
