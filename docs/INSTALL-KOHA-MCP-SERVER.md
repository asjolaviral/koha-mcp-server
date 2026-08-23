# Prerequisite
- A working **Koha instance** with the REST API enabled.
- **Root/sudo** access on the Koha host.
- **Python 3.12+** and `python3-venv` (Debian/Ubuntu):
  ```bash
  sudo apt update
  sudo apt install -y python3 python3-venv
  ```
# Clone the repository

```bash
git clone https://github.com/asjolaviral/koha-mcp-server.git
cd koha-mcp-server
```

# Install Python dependencies

```bash
bash setup.sh                 # venv, deps, config, helper, sudo rule
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```
# Configure the server

```bash
cp config.example.json config.json
nano config.json
```

```json
{
  "base_url": "http://192.168.xxx.xxx", # you server URL
  "client_id": "YOUR-OAUTH2-CLIENT-ID",
  "client_secret": "YOUR-OAUTH2-CLIENT-SECRET",
  "instance": "library", # your library instance name
  "branchcode": "GVP", # your library code
  "koha_user": "library-koha", # automatically populated using setup.sh
  "return_helper": "/usr/local/lib/koha-mcp/scripts/koha_return.pl"
}
```

| Key             | Description                                               |
| --------------- | --------------------------------------------------------- |
| `base_url`      | Host where Koha answers (the REST API is served from it)  |
| `client_id`     | API key client_id                                         |
| `client_secret` | API key client_secret                                     |
| `instance`      | Koha instance name (matches `/etc/koha/sites/<instance>`) |
| `branchcode`    | Default branch/library used for returns                   |
| `koha_user`     | Koha system user, normally `<instance>-koha`              |
| `return_helper` | Installed path of the return helper script                |
The server looks for the config in this order:

1. `KOHA_MCP_CONFIG` environment variable
2. `./config.json` (next to `koha_mcp_server.py`)
3. `~/.koha-mcp/config.json`

```
export KOHA_MCP_CONFIG=/home/<user>/.koha-mcp/config.json
```

**Install the return helper + sudo rule**

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

Why this is needed: the helper opens Koha's log files, which only the Koha system user can write. The rule is deliberately **scoped to a single script** it grants nothing else.

## Test the installation

```bash
.venv/bin/python test_client.py
```

Expected output (values differ per instance): **Need to modify the patron**

```
[OK]   list_libraries: ...
[OK]   search_patrons(userid=viral): ... // here viral is patron username
[OK]   search_catalogue(title=advertising): ...
[OK]   get_public_biblio(4): ...
All self-tests passed.
```

## Run the MCP server

```bash
.venv/bin/python koha_mcp_server.py
```

The server speaks to **MCP over stdio** by default — it prints the MCP protocol on stdin/stdout and waits for a client to connect.

To serve it over **Server-Sent Events (SSE)/HTTP** (e.g. for n8n), change the last line in
`koha_mcp_server.py`:

```python
mcp.run()                                  # stdio (default)
# mcp.run(transport="sse", host="0.0.0.0", port=8000)   # SSE/HTTP
```
## Tools exposed

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



# Connect your client

- **opencode** → see [CLIENT-CONFIGURATION.md](CLIENT-CONFIGURATION.md#opencode)
- **Claude Desktop** → see [CLIENT-CONFIGURATION.md](CLIENT-CONFIGURATION.md#claude-desktop)
- **n8n** → see [CLIENT-CONFIGURATION.md](CLIENT-CONFIGURATION.md#n8n)

# Known limitations

- The `q` filter on `/biblios` and `/patrons` performs **DB-level filtering**
  (substring `LIKE`), not full-text/Zebra search. For wide searches prefer
  field-specific terms (e.g. `title`, `author`).
- `barcode` cannot be changed on an item through the REST API once set
  (`Properties not allowed: barcode`).
- Duplicate-record protection is active: creating a biblio whose ISBN already
  exists returns `Duplicate biblio <id>`.
- The OAuth2 access token is cached and refreshed automatically (1 h validity).
