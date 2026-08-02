#!/usr/bin/env python3
"""
Koha MCP Server
===============
Exposes the Koha REST API as Model Context Protocol (MCP) tools.

Tasks covered:
  * Catalogue search and retrieval
  * Cataloguing (create/update/delete biblios and items)
  * Circulation (checkout / issue, renew, return)
  * Holds (place, list, cancel)
  * Patron lookup

Run as an MCP stdio server:
    python koha_mcp_server.py

Configuration: config.json (override with env var KOHA_MCP_CONFIG)
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from fastmcp import FastMCP

BASE_DIR = Path(__file__).resolve().parent


def _load_config() -> dict:
    """Locate and load the Koha MCP configuration.

    Resolution order:
      1. KOHA_MCP_CONFIG env var
      2. ./config.json (next to this file)
      3. ~/.koha-mcp/config.json
    """
    candidates = [
        Path(os.environ["KOHA_MCP_CONFIG"]) if os.environ.get("KOHA_MCP_CONFIG") else None,
        BASE_DIR / "config.json",
        Path.home() / ".koha-mcp" / "config.json",
    ]
    for path in candidates:
        if path and path.is_file():
            return json.loads(path.read_text())
    raise SystemExit(
        "No configuration found. Copy config.example.json to config.json "
        "(or ~/.koha-mcp/config.json) and fill in your Koha credentials.\n"
        "You can also point to a config file with the KOHA_MCP_CONFIG env var."
    )


CONFIG = _load_config()

BASE_URL = CONFIG["base_url"].rstrip("/") + "/api/v1"
CLIENT_ID = CONFIG["client_id"]
CLIENT_SECRET = CONFIG["client_secret"]
INSTANCE = CONFIG.get("instance", "library")
BRANCHCODE = CONFIG.get("branchcode", "GVP")
KOHA_USER = CONFIG.get("koha_user", f"{INSTANCE}-koha")
RETURN_HELPER = CONFIG.get("return_helper", "/usr/local/lib/koha-mcp/scripts/koha_return.pl")

mcp = FastMCP("koha")


class KohaAPI:
    """Small OAuth2 client_credentials client for the Koha REST API."""

    def __init__(self) -> None:
        self._client = httpx.Client(timeout=45.0)
        self._token: Optional[str] = None
        self._expires_at: float = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        resp = self._client.post(
            f"{BASE_URL}/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 3600))
        return self._token

    def request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        body: Optional[dict] = None,
        headers: Optional[dict] = None,
        content_type: str = "application/json",
    ) -> Any:
        hdrs = {
            "Authorization": f"Bearer {self._get_token()}",
            "Accept": "application/json",
            "User-Agent": "koha-mcp-server/1.0",
        }
        if headers:
            hdrs.update(headers)
        if body is not None:
            hdrs["Content-Type"] = content_type

        url = f"{BASE_URL}{path}"
        for attempt in range(2):
            resp = self._client.request(
                method, url, params=params, headers=hdrs, json=body
            )
            if resp.status_code == 401 and attempt == 0:
                # Token may have been revoked server-side; refresh once.
                self._token = None
                self._expires_at = 0.0
                hdrs["Authorization"] = f"Bearer {self._get_token()}"
                continue
            break

        if resp.status_code >= 400:
            raise RuntimeError(
                f"Koha API {method} {path} -> HTTP {resp.status_code}: {resp.text[:1000]}"
            )
        if not resp.content:
            return {}
        try:
            return resp.json()
        except Exception:
            return resp.text


api = KohaAPI()


def _parse_json(value: str, what: str) -> dict:
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for {what}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{what} must be a JSON object")
    return data


# ---------------------------------------------------------------- catalogue --


@mcp.tool()
def search_catalogue(
    query: str,
    field: str = "title",
    page: int = 1,
    per_page: int = 20,
) -> str:
    """Search the catalogue (bibliographic records) for a term.

    Performs a substring match on the chosen field using the Koha query filter.
    Useful fields: title, author, publisher, isbn, publicationdate, subject,
    abstract, notes.

    Returns a JSON list of matching biblios with their biblio_id and title.
    """
    term = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    q = json.dumps({field: {"-like": f"%{term}%"}})
    result = api.request(
        "GET", "/biblios", params={"q": q, "_page": page, "_per_page": per_page}
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def search_catalogue_raw(
    filters_json: str,
    page: int = 1,
    per_page: int = 20,
) -> str:
    """Search the catalogue with a raw Koha q-filter JSON object.

    Example: {"title":["Exact Title"]}     -> exact / IN match
             {"title":{"-like":"%term%"}}  -> substring match
             {"author":{"-like":"%smith%"}} -> substring match
    """
    result = api.request(
        "GET", "/biblios", params={"q": filters_json, "_page": page, "_per_page": per_page}
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def get_biblio(biblio_id: int) -> str:
    """Get full details of a single bibliographic record (biblio_id)."""
    result = api.request("GET", f"/biblios/{biblio_id}")
    return json.dumps(result, indent=2)


@mcp.tool()
def get_biblio_items(biblio_id: int) -> str:
    """List the item copies attached to a biblio (biblio_id)."""
    result = api.request("GET", f"/biblios/{biblio_id}/items")
    return json.dumps(result, indent=2)


@mcp.tool()
def get_item(item_id: int) -> str:
    """Get details of a single item by its item_id."""
    result = api.request("GET", f"/items/{item_id}")
    return json.dumps(result, indent=2)


@mcp.tool()
def list_items(page: int = 1, per_page: int = 20) -> str:
    """List items (copies) in the catalogue with pagination."""
    result = api.request("GET", "/items", params={"_page": page, "_per_page": per_page})
    return json.dumps(result, indent=2)


@mcp.tool()
def get_public_biblio(biblio_id: int) -> str:
    """Get a biblio through the public (anonymous) API - no auth required.

    The public endpoint returns the raw MARC record (MARC-in-JSON).
    """
    result = api.request(
        "GET",
        f"/public/biblios/{biblio_id}",
        headers={"Accept": "application/marc-in-json"},
    )
    return json.dumps(result, indent=2)


# -------------------------------------------------------------- cataloguing --


def _build_marc_record(
    title: str,
    author: Optional[str] = None,
    subtitle: Optional[str] = None,
    isbn: Optional[str] = None,
    place: Optional[str] = None,
    publisher: Optional[str] = None,
    publication_year: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    fields = []
    if author:
        fields.append(
            {"100": {"ind1": "1", "ind2": " ", "subfields": [{"a": author}]}}
        )
    t245: dict = {"ind1": "1", "ind2": "0", "subfields": [{"a": title}]}
    if subtitle:
        t245["subfields"].append({"b": subtitle})
    fields.append({"245": t245})
    if isbn:
        fields.append(
            {"020": {"ind1": " ", "ind2": " ", "subfields": [{"a": isbn}]}}
        )
    if place or publisher or publication_year:
        sf = []
        if place:
            sf.append({"a": place})
        if publisher:
            sf.append({"b": publisher})
        if publication_year:
            sf.append({"c": publication_year})
        fields.append({"260": {"ind1": " ", "ind2": " ", "subfields": sf}})
    if notes:
        fields.append(
            {"500": {"ind1": " ", "ind2": " ", "subfields": [{"a": notes}]}}
        )
    return {"leader": "00000nam a22000007a 4500", "fields": fields}


@mcp.tool()
def create_biblio(marc_json: str) -> str:
    """Create a new bibliographic record from a MARC-in-JSON string.

    Each data field must include 'ind1'/'ind2' (use ' ' for empty).
    Returns the new biblio (id).
    """
    record = _parse_json(marc_json, "marc_json")
    result = api.request(
        "POST",
        "/biblios",
        body=record,
        content_type="application/marc-in-json",
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def create_biblio_simple(
    title: str,
    author: Optional[str] = None,
    subtitle: Optional[str] = None,
    isbn: Optional[str] = None,
    place: Optional[str] = None,
    publisher: Optional[str] = None,
    publication_year: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Convenience tool to catalog a new book with common bibliographic fields.

    Builds a basic MARC record and adds it to Koha. Returns the new biblio id.
    """
    record = _build_marc_record(
        title=title,
        author=author,
        subtitle=subtitle,
        isbn=isbn,
        place=place,
        publisher=publisher,
        publication_year=publication_year,
        notes=notes,
    )
    result = api.request(
        "POST", "/biblios", body=record, content_type="application/marc-in-json"
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def update_biblio(biblio_id: int, marc_json: str) -> str:
    """Replace the MARC record of an existing biblio (MARC-in-JSON string)."""
    record = _parse_json(marc_json, "marc_json")
    result = api.request(
        "PUT",
        f"/biblios/{biblio_id}",
        body=record,
        content_type="application/marc-in-json",
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def delete_biblio(biblio_id: int) -> str:
    """Delete a bibliographic record (biblio_id)."""
    result = api.request("DELETE", f"/biblios/{biblio_id}")
    return json.dumps(result, indent=2)


@mcp.tool()
def create_item(biblio_id: int, item_json: str) -> str:
    """Add an item (copy) to a biblio from a JSON string.

    Common fields: barcode, homebranch, holdingbranch, itemtype, notforloan,
    collection_code, copynumber.
    """
    data = _parse_json(item_json, "item_json")
    result = api.request("POST", f"/biblios/{biblio_id}/items", body=data)
    return json.dumps(result, indent=2)


@mcp.tool()
def update_item(biblio_id: int, item_id: int, item_json: str) -> str:
    """Update an item's fields (barcode cannot be changed via the API)."""
    data = _parse_json(item_json, "item_json")
    result = api.request("PUT", f"/biblios/{biblio_id}/items/{item_id}", body=data)
    return json.dumps(result, indent=2)


# --------------------------------------------------------------- circulation --


@mcp.tool()
def checkout_item(patron_id: int, item_id: int) -> str:
    """Issue (checkout) an item to a patron.

    Creates a checkout (loan) for the given patron_id and item_id.
    Returns the checkout record including the due date.
    """
    result = api.request("POST", "/checkouts", body={"patron_id": patron_id, "item_id": item_id})
    return json.dumps(result, indent=2)


@mcp.tool()
def renew_checkout(checkout_id: int) -> str:
    """Renew a checkout (checkout_id) and return the updated checkout."""
    result = api.request("POST", f"/checkouts/{checkout_id}/renewal")
    return json.dumps(result, indent=2)


@mcp.tool()
def return_item(barcode: str, branchcode: Optional[str] = None) -> str:
    """Return (checkin) an item by barcode.

    The Koha REST API has no checkin endpoint in this build, so returns run
    through Koha's internal circulation module as the library-koha user
    (requires the scoped sudo rule, see README).

    Returns a JSON document with ok/returned status and any messages.
    """
    branch = branchcode or BRANCHCODE
    cmd = ["sudo", "-u", KOHA_USER, RETURN_HELPER, barcode, branch, INSTANCE]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Return helper timed out") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"Return helper failed: {proc.stderr.strip() or proc.stdout.strip()}")
    try:
        return json.dumps(json.loads(proc.stdout), indent=2)
    except json.JSONDecodeError:
        return proc.stdout


@mcp.tool()
def list_patron_checkouts(patron_id: int) -> str:
    """List all active checkouts for a patron (patron_id)."""
    result = api.request("GET", f"/patrons/{patron_id}/checkouts")
    return json.dumps(result, indent=2)


@mcp.tool()
def list_checkouts(
    patron_id: Optional[int] = None,
    checked_in: Optional[bool] = None,
    page: int = 1,
    per_page: int = 20,
) -> str:
    """List checkouts. Optionally filter by patron_id and checked_in."""
    params: dict = {"_page": page, "_per_page": per_page}
    if patron_id is not None:
        params["patron_id"] = patron_id
    if checked_in is not None:
        params["checked_in"] = "true" if checked_in else "false"
    result = api.request("GET", "/checkouts", params=params)
    return json.dumps(result, indent=2)


# -------------------------------------------------------------------- holds --


@mcp.tool()
def place_hold(patron_id: int, biblio_id: int, pickup_library_id: str) -> str:
    """Place a hold on a biblio for a patron at a pickup library."""
    result = api.request(
        "POST",
        "/holds",
        body={
            "patron_id": patron_id,
            "biblio_id": biblio_id,
            "pickup_library_id": pickup_library_id,
        },
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def list_patron_holds(patron_id: int) -> str:
    """List all holds placed by a patron (patron_id)."""
    result = api.request("GET", f"/patrons/{patron_id}/holds")
    return json.dumps(result, indent=2)


@mcp.tool()
def cancel_hold(hold_id: int) -> str:
    """Cancel (delete) a hold by hold_id."""
    result = api.request("DELETE", f"/holds/{hold_id}")
    return json.dumps(result, indent=2)


# ------------------------------------------------------------------- patrons --


@mcp.tool()
def get_patron(patron_id: int) -> str:
    """Get a patron's details by patron_id (borrowernumber)."""
    result = api.request("GET", f"/patrons/{patron_id}")
    return json.dumps(result, indent=2)


@mcp.tool()
def search_patrons(
    query: str,
    field: str = "userid",
    page: int = 1,
    per_page: int = 20,
) -> str:
    """Search patrons by a field substring (e.g. userid, cardnumber, surname,
    firstname, email). Use '*' as prefix to make matching case-insensitive-safe."""
    term = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    q = json.dumps({field: {"-like": f"%{term}%"}})
    result = api.request("GET", "/patrons", params={"q": q, "_page": page, "_per_page": per_page})
    return json.dumps(result, indent=2)


# ------------------------------------------------------------------ libraries --


@mcp.tool()
def list_libraries() -> str:
    """List all library branches."""
    result = api.request("GET", "/libraries")
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    mcp.run()
