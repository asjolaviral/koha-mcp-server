# Koha MCP Server — Installation Guide (Guidelines)

This guide walks through establishing the Koha MCP Server from scratch, on a
Debian/Ubuntu host running the Koha package distribution (tested with
**Koha 26.05.01** on **Ubuntu 24.04.4 LTS**).

It assumes the Koha REST API is already enabled. If yours is not, complete the
steps in the section [Prerequisite: enable the Koha REST API](#prerequisite-enable-the-koha-rest-api)
first.

---

## Table of contents

1. [Architecture](#1-architecture)
2. [Prerequisites](#2-prerequisites)
3. [Prerequisite: enable the Koha REST API](#prerequisite-enable-the-koha-rest-api)
4. [Get an OAuth2 API key (client_id / secret)](#4-get-an-oauth2-api-key)
5. [Clone / copy the repository](#5-clone--copy-the-repository)
6. [Install Python dependencies](#6-install-python-dependencies)
7. [Configure the server](#7-configure-the-server)
8. [Install the return helper + sudo rule](#8-install-the-return-helper--sudo-rule)
9. [Self-test the installation](#9-self-test-the-installation)
10. [Run the MCP server](#10-run-the-mcp-server)
11. [Tools exposed](#11-tools-exposed)
12. [Connect your client](#12-connect-your-client)

---

## 1. Architecture

```
AI client (MCP)  <--stdio-->  koha_mcp_server.py (FastMCP)
                                   │
                                   ├─ OAuth2 client_credentials ──▶ Koha REST API
                                   │      GET/POST/PUT/DELETE /api/v1/...
                                   │
                                   └─ koha_return.pl (sudo -u <instance>-koha)
                                          C4::Circulation::AddReturn
```

Two integration paths:

- **REST (primary):** all search, catalogue, circulation, holds and patron
  operations go over the HTTP REST API with an OAuth2 bearer token.
- **Local helper (returns only):** the Koha REST API exposes **no checkin
  endpoint**, so returning an item is done through Koha's internal
  `C4::Circulation::AddReturn` module. The server calls a small Perl helper as
  the Koha system user via a scoped `sudo` rule.

---

## 2. Prerequisites

- A working **Koha instance** with the REST API enabled.
- **Root/sudo** access on the Koha host.
- **Python 3.12+** and `python3-venv` (Debian/Ubuntu):
  ```bash
  sudo apt update
  sudo apt install -y python3 python3-venv
  ```
- The Koha command-line tools on `PATH`: `koha-mysql`, `koha-shell`,
  `koha-plack` (Debian packages place them in `/usr/sbin`).
- An **OAuth2 API key** for the Koha REST API (step 4).

---

## Prerequisite: enable the Koha REST API

If `/api/v1/` is not already answering, enable it:

1. **Enable the Apache modules Plack needs** and restart Apache:
   ```bash
   sudo a2enmod headers proxy proxy_http proxy_wstunnel
   sudo systemctl restart apache2
   ```
2. **Enable and start Plack** (the REST API is served through Plack):
   ```bash
   sudo koha-plack --enable library          # your instance name
   sudo koha-plack --start library
   sudo koha-plack --status library          # -> "Plack running for library"
   ```
3. **Check the REST system preferences** (staff client → Administration →
   System preferences, or directly in the DB):
   ```bash
   sudo koha-mysql library -e "SELECT variable,value FROM systempreferences
     WHERE variable LIKE '%REST%' OR variable LIKE '%OAuth%';"
   ```
   Required values: `RESTPublicAPI=1`, `RESTOAuth2ClientCredentials=1`.
   Optional: `RESTBasicAuth=1`, `RESTPublicAnonymousRequests=1`.
4. **Verify the endpoint** (may need `Accept: application/json`):
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/v1/
   # -> 200
   ```

> Troubleshooting for this stage (missing modules, Plack timeouts, missing
> `api_keys`/`oauth_clients` tables) is in
> [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

---

## 4. Get an OAuth2 API key

The REST API authenticates with **OAuth2 `client_credentials`**. Create an API
key through the staff client:

> **Patrons** → your account → **API keys** tab → **Create new key**

You get a `client_id` and a one-time plain-text `client_secret`. Save them
immediately — the secret is stored hashed and cannot be retrieved again.

To verify the key works:

```bash
curl -X POST http://<koha-host>/api/v1/oauth/token \
  -d "grant_type=client_credentials" \
  -d "client_id=<CLIENT_ID>" \
  -d "client_secret=<CLIENT_SECRET>"
# -> {"access_token":"...","expires_in":3600,"token_type":"Bearer"}
```

---

## 5. Clone / copy the repository

```bash
git clone https://github.com/<you>/koha-mcp-server.git
cd koha-mcp-server
```

(Or copy the folder onto the Koha host.)

---

## 6. Install Python dependencies

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

`requirements.txt` installs `fastmcp` (the FastMCP SDK) and `httpx`.

---

## 7. Configure the server

```bash
cp config.example.json config.json
nano config.json
```

```json
{
  "base_url": "http://192.168.29.214",
  "client_id": "YOUR-OAUTH2-CLIENT-ID",
  "client_secret": "YOUR-OAUTH2-CLIENT-SECRET",
  "instance": "library",
  "branchcode": "GVP",
  "koha_user": "library-koha",
  "return_helper": "/usr/local/lib/koha-mcp/scripts/koha_return.pl"
}
```

| Key             | Description                                              |
|-----------------|----------------------------------------------------------|
| `base_url`      | Host where Koha answers (the REST API is served from it) |
| `client_id`     | API key client_id from step 4                            |
| `client_secret` | API key client_secret from step 4                        |
| `instance`      | Koha instance name (matches `/etc/koha/sites/<instance>`)|
| `branchcode`    | Default branch used for returns                          |
| `koha_user`     | Koha system user, normally `<instance>-koha`             |
| `return_helper` | Installed path of the return helper script               |

The server looks for the config in this order:

1. `KOHA_MCP_CONFIG` environment variable
2. `./config.json` (next to `koha_mcp_server.py`)
3. `~/.koha-mcp/config.json`

> 🔒 **Keep `config.json` out of version control.** It is already listed in
> `.gitignore`. If you also keep a copy in `~/.koha-mcp/config.json`, the repo
> folder stays 100% safe to upload.

---

## 8. Install the return helper + sudo rule

Returns run through a Perl helper as the Koha system user. Install the helper
and grant the **only** privilege needed for it:

```bash
INSTANCE="library"
KOHA_USER="${INSTANCE}-koha"

# 1. Install the helper where the Koha user can reach it
sudo mkdir -p /usr/local/lib/koha-mcp/scripts
sudo install -m 0755 scripts/koha_return.pl /usr/local/lib/koha-mcp/scripts/koha_return.pl

# 2. Scoped sudo rule: <user> may run ONLY the return script as the Koha user
USER_="$(whoami)"
echo "$USER_ ALL=($KOHA_USER) NOPASSWD: /usr/local/lib/koha-mcp/scripts/koha_return.pl" \
  | sudo tee /etc/sudoers.d/koha-mcp
sudo chmod 0440 /etc/sudoers.d/koha-mcp
sudo visudo -c -f /etc/sudoers.d/koha-mcp
```

Why this is needed: the helper opens Koha's log files, which only the Koha
system user can write. The rule is deliberately **scoped to a single script** —
it grants nothing else.

> Alternatively, skip `sudo` entirely by adding your user to the
> `library-koha` group (`sudo usermod -aG library-koha $USER`) and running the
> helper directly — but then the helper must run under the group via
> `sg library-koha -c '...'`. The sudo rule is the recommended approach.

---

## 9. Self-test the installation

```bash
.venv/bin/python test_client.py
```

Expected output (values differ per instance):

```
[OK]   list_libraries: ...
[OK]   search_patrons(userid=viral): ...
[OK]   search_catalogue(title=advertising): ...
[OK]   get_public_biblio(4): ...
All self-tests passed.
```

You can also exercise the circulation lifecycle directly:

```bash
.venv/bin/python - <<'PY'
import sys; sys.path.insert(0, ".")
import koha_mcp_server as k

print(k.checkout_item(1, 4))       # issue item 4 to patron 1
print(k.renew_checkout(1))         # renew that checkout
print(k.return_item("TEST-0001"))  # return by barcode
PY
```

---

## 10. Run the MCP server

```bash
.venv/bin/python koha_mcp_server.py
```

The server speaks **MCP over stdio** by default — it prints the MCP protocol on
stdin/stdout and waits for a client to connect.

To serve it over **SSE/HTTP** (e.g. for n8n), change the last line in
`koha_mcp_server.py`:

```python
mcp.run()                                  # stdio (default)
# mcp.run(transport="sse", host="0.0.0.0", port=8000)   # SSE/HTTP
```

---

## 11. Tools exposed

| Tool                    | Description                                           |
|-------------------------|-------------------------------------------------------|
| `search_catalogue`      | Substring search of biblios (field + term)            |
| `search_catalogue_raw`  | Search with a raw q-filter JSON                       |
| `get_biblio`            | Full biblio details                                   |
| `get_biblio_items`      | Item copies of a biblio                               |
| `get_item` / `list_items` | Single item / all items                             |
| `get_public_biblio`     | Public (anonymous) MARC record of a biblio            |
| `create_biblio`         | Add biblio from MARC-in-JSON                          |
| `create_biblio_simple`  | Add biblio from plain fields (title/author/isbn/...)  |
| `update_biblio` / `delete_biblio` | Edit / remove a biblio                      |
| `create_item` / `update_item` | Add / edit an item (copy)                      |
| `checkout_item`         | Issue an item to a patron                             |
| `renew_checkout`        | Renew a checkout                                      |
| `return_item`           | Return (checkin) an item by barcode                   |
| `list_patron_checkouts` / `list_checkouts` | List loans                      |
| `place_hold` / `list_patron_holds` / `cancel_hold` | Hold management      |
| `get_patron` / `search_patrons` | Patron lookup                                  |
| `list_libraries`        | Library branches                                      |

---

## 12. Connect your client

- **opencode** → see [CLIENT-CONFIGURATION.md](CLIENT-CONFIGURATION.md#opencode)
- **Claude Desktop** → see [CLIENT-CONFIGURATION.md](CLIENT-CONFIGURATION.md#claude-desktop)
- **n8n** → see [CLIENT-CONFIGURATION.md](CLIENT-CONFIGURATION.md#n8n)

---

## Known limitations

- The `q` filter on `/biblios` and `/patrons` performs **DB-level filtering**
  (substring `LIKE`), not full-text/Zebra search. For wide searches prefer
  field-specific terms (e.g. `title`, `author`).
- `barcode` cannot be changed on an item through the REST API once set
  (`Properties not allowed: barcode`).
- Duplicate-record protection is active: creating a biblio whose ISBN already
  exists returns `Duplicate biblio <id>`.
- The OAuth2 access token is cached and refreshed automatically (1 h validity).
