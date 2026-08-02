# Enable the Koha REST API

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
   curl -s -o /dev/null -w "%{http_code}\n" http://localhost/api/v1/
   # -> 200
   ```

## Get an OAuth2 API key

The REST API authenticates with **OAuth2 `client_credentials`**. Create an API
key through the staff client:

> **Patrons** → your account → **More** → Manage API Keys → **Generate a new client id/key pair**

You get a `client_id` and a one-time plain-text `client_secret`. Save them immediately — the secret is stored hashed and cannot be retrieved again.

To verify the key works:

```bash
curl -X POST http://<koha-host>/api/v1/oauth/token \
  -d "grant_type=client_credentials" \
  -d "client_id=<CLIENT_ID>" \
  -d "client_secret=<CLIENT_SECRET>"
# -> {"access_token":"...","expires_in":3600,"token_type":"Bearer"}
```   

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
git clone https://github.com/<you>/koha-mcp-server.git
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
  "base_url": "http://192.168.xxx.xxx",
  "client_id": "YOUR-OAUTH2-CLIENT-ID",
  "client_secret": "YOUR-OAUTH2-CLIENT-SECRET",
  "instance": "library",
  "branchcode": "GVP",
  "koha_user": "library-koha",
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
export KOHA_MCP_CONFIG=/home/viral/.koha-mcp/config.json
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
[OK]   search_patrons(userid=viral): ...
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
