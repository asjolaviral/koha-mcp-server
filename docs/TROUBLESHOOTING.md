# Troubleshooting

Real errors encountered while building and installing the Koha MCP Server,
with their causes and fixes.

---

## REST API does not answer

### A. `/api/v1/` times out (curl returns `000`, no bytes)

```
$ curl -s http://localhost:8089/api/v1/
( hangs / "Operation timed out with 0 bytes received" )
```

**Cause:** Plack is not running. Apache proxies `/api/v1/` to the Plack
(Starman) socket, which is dead.

**Fix:**

```bash
sudo a2enmod headers proxy proxy_http proxy_wstunnel
sudo systemctl restart apache2
sudo koha-plack --enable library
sudo koha-plack --start library
sudo koha-plack --status library     # -> "Plack running for library"
```

### B. `WARNING: koha-plack requires some Apache modules that you are missing.`

**Cause:** missing Apache modules.

**Fix:** `sudo a2enmod headers proxy proxy_http proxy_wstunnel` then restart
Apache.

### C. `Table 'koha_library.oauth_clients' doesn't exist` / missing API tables

**Cause:** this Koha build manages OAuth2 clients through the `api_keys` table
(via `Koha::ApiKeys`) rather than the upstream `oauth_clients` table; or the
schema is incomplete.

**Check:**

```bash
sudo koha-mysql library -e "SHOW TABLES LIKE 'api_keys'; DESCRIBE api_keys;"
```

If a required table is genuinely missing, try a schema sync:

```bash
sudo koha-upgrade-schema library
# "No database change required" means the Version syspref already matches
```

---

## Authentication / tokens

### D. `bad bcrypt settings` or HTTP 500 from `/api/v1/oauth/token`

**Cause:** the API key's stored secret is corrupt (not a valid bcrypt hash).
This happened after an API key was edited manually in the DB.

**Fix:** delete the broken key and create a fresh one (Patrons → API keys →
Create new key, or via `Koha::ApiKey`). Use the new `client_id`/`client_secret`.

### E. `401` responses after a while

**Cause:** the access token expired. This is handled automatically — the server
refreshes the token before expiry (1 h lifetime). If you still see 401s, make
sure the API key is still `active` in the DB:

```bash
sudo koha-mysql library -e "SELECT client_id, active FROM api_keys;"
```

---

## Search

### F. `Unknown column 'keyword' in 'WHERE'` (HTTP 500) on `/biblios?q=...`

**Cause:** the `q` filter is applied as a **DB column filter**, not a
full-text index. Column names must be real biblio/biblioitems columns
(`title`, `author`, `publisher`, `isbn`, ...) — there is no `keyword` column.

**Fix:** use a real field, e.g. `search_catalogue(query, field="title")`.

### G. Empty results for `q={"title":["..."]}`

**Cause:** an array value is an **exact / IN** match on the full column value,
so `["Advertising"]` does not match `Advertising management : ...`.

**Fix:** use a substring `LIKE` filter:

```json
{"title": {"-like": "%advertising%"}}
```

### H. `/biblios` returns a list of content-types instead of data

```
["application/json","application/marcxml+xml","application/marc-in-json","application/marc","text/plain"]
```

**Cause:** the biblio endpoints negotiate format and reject the default
`Accept: */*`.

**Fix:** send `Accept: application/json`. The MCP server already does this.

### I. `Expected application/marcxml+xml, application/marc-in-json, application/marc, text/plain - got application/json`

**Cause:** the **public** biblio endpoint only returns MARC formats.

**Fix:** request `Accept: application/marc-in-json` for `/public/biblios/...`.
The `get_public_biblio` tool already does this.

---

## Cataloguing

### J. `Field 245 must have indicators (use ' ' for empty indicators)`

**Cause:** MARC-in-JSON data fields must carry `ind1`/`ind2`.

**Fix:** add indicators to every data field, e.g.
`{"245": {"ind1": "1", "ind2": "0", "subfields": [{"a": "Title"}]}}`.
`create_biblio_simple` builds valid records automatically.

### K. `Duplicate biblio <id>`

**Cause:** Koha's duplicate-record detection matched an existing record (e.g.
same ISBN).

**Fix:** expected behaviour, not an error. Supply a different ISBN or use
`create_biblio` with the full MARC record.

### L. `Properties not allowed: barcode`

**Cause:** the item `barcode` field is immutable through the REST update
endpoint — it can only be set when the item is created.

**Fix:** set the barcode at creation time, or update it directly in the DB.

---

## Return helper / sudo

### M. `Can't locate C4/Circulation.pm in @INC`

**Cause:** the helper could not find the Koha Perl modules.

**Fix:** make sure `/usr/share/koha/lib` is on `@INC` and `KOHA_CONF` points at
`/etc/koha/sites/<instance>/koha-conf.xml`. The helper sets both itself (from
`KOHA_INSTANCE`, default `library`).

### N. `Can't open /var/log/koha/library/<...>.log (Permission denied)`

**Cause:** the helper (run as your user) cannot write Koha's log files.

**Fix:** run the helper as the Koha system user via the scoped sudo rule:

```bash
sudo visudo -f /etc/sudoers.d/koha-mcp
# <user> ALL=(library-koha) NOPASSWD: /usr/local/lib/koha-mcp/scripts/koha_return.pl
```

Then call it through `sudo -u library-koha` (the server does this).

### O. `sudo: sorry, you are not allowed to set the following environment variables`

**Cause:** `sudo` strips custom environment variables unless the rule allows it.

**Fix:** do not rely on env vars through `sudo`. The instance is now passed as
a positional argument: `koha_return.pl BARCODE BRANCH INSTANCE`.

### P. `sudo: unable to execute ... : Permission denied`

**Cause:** the helper lived under a home directory with mode `700`, so the Koha
user could not traverse to it.

**Fix:** install the helper under a world-traversable path (the default is
`/usr/local/lib/koha-mcp/scripts/`).

---

## Client connection

### Q. Tools do not appear in the MCP client

- Confirm the server starts standalone: `.venv/bin/python koha_mcp_server.py`
- Run `.venv/bin/python test_client.py` to check the config/credentials.
- Check the client's own error logs:
  - Claude Desktop: `~/Library/Logs/Claude/mcp*.log` (macOS)
  - opencode: run opencode with debug logging enabled
- Make sure `command`/`args` in the client config are **absolute paths**.

### R. n8n cannot connect

- Ensure the server is running with the **SSE/HTTP** transport (the default is
  stdio, which n8n cannot use).
- From the n8n host, reach the server: `curl http://<server>:8000/sse`
- Keep the port bound to a trusted network (see CLIENT-CONFIGURATION.md).
