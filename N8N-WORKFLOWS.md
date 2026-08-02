# Connecting Koha MCP Server to n8n — Workflow Guide

This guide shows how to connect the **Koha MCP Server** (running over SSE) to
**n8n** and build workflows around the Koha tools.

## Prerequisites

- The Koha MCP Server started with the **SSE** transport, e.g.:

  ```python
  # last line of koha_mcp_server.py
  mcp.run(transport="sse", host="0.0.0.0", port=8000)
  ```

  ```bash
  .venv/bin/python koha_mcp_server.py
  ```

  Verify it from another host:

  ```bash
  curl http://<server-ip>:8000/sse
  ```

  (It holds the connection open — a 200-ish response / no error means it is up.)

- **n8n** with the MCP nodes. n8n **1.x+** ships:
  - **MCP Server Tool** — connects to an external MCP server and discovers its tools
  - **MCP Tool** — calls one specific tool from that server

---

## 1. Add the MCP Server Tool node

1. Open (or create) an n8n workflow.
2. Click **+** (insert node) and search for **MCP Server Tool**.
3. Configure the node:

   | Setting       | Value                                        |
   |---------------|----------------------------------------------|
   | Transport     | `SSE`                                        |
   | URL           | `http://localhost:8000/sse`                  |

   - n8n runs on the **same host** → use `http://localhost:8000/sse`
   - n8n runs on **another host** → use the server's LAN IP, e.g.
     `http://192.168.29.214:8000/sse`

4. Click **Test connection** (or let n8n fetch tools). You should see the 24
   Koha tools appear (e.g. `search_catalogue`, `checkout_item`, `return_item`).

> The MCP Server Tool node is a "root" node — it does not run by itself. It
> makes the connected tools available to **MCP Tool** nodes downstream.

---

## 2. Call a tool with the MCP Tool node

1. Add an **MCP Tool** node.
2. In the node's connection picker, select the **MCP Server Tool** node you
   added (or add a new one from inside the node).
3. From **Tool name**, choose the Koha tool you want to call.
4. Fill the **parameters** exposed by that tool.

**Example — `search_catalogue`:**

```
Tool name:    search_catalogue
query:        {{ $json.query }}      (or a literal, e.g. "advertising")
field:        title
page:         1
per_page:     20
```

The result comes back as a JSON **string** inside `$json.output`. Parse it with
a **Code** node before further processing:

```js
// Code node
const tools = JSON.parse($json.output);
return items = tools.map(t => ({
  biblio_id: t.biblio_id,
  title: t.title,
  author: t.author,
}));
```

---

## 3. Example workflows

### Workflow A — Catalogue search via webhook

```
[Webhook Trigger] → [MCP Tool: search_catalogue] → [Code: parse JSON] → [Respond to Webhook]
```

1. **Webhook Trigger** — GET/POST endpoint, receives `{ "query": "experiments" }`.
2. **MCP Tool `search_catalogue`**:
   - `query: {{ $json.body.query }}`
   - `field: title`
3. **Code** — parse the output and keep `biblio_id`, `title`, `author`.
4. **Respond to Webhook** — return the list of matches.

**Try it:** call your webhook with
`{"query": "advertising management"}` and get the catalogue results back as JSON.

### Workflow B — Circulation lifecycle (issue → renew → return)

```
[Manual / Webhook] → [MCP Tool: checkout_item] → [MCP Tool: renew_checkout]
                 → [MCP Tool: return_item] → [Code: summary]
```

1. **MCP Tool `checkout_item`** — parameters `patron_id` and `item_id`.
   Returns the checkout record (gives you `checkout_id` and `due_date`).
2. **MCP Tool `renew_checkout`** — parameter `checkout_id` taken from the
   previous node:
   ```
   checkout_id: {{ JSON.parse($json.output).checkout_id }}
   ```
3. **MCP Tool `return_item`** — parameter `barcode` (e.g. `TEST-0001`).
4. **Code** — build a human-readable summary:
   ```js
   const due = JSON.parse($json.output);
   return { message: `Item returned. ok=${due.ok} returned=${due.returned}` };
   ```

### Workflow C — Place a hold from a search result

```
[Webhook] → [MCP Tool: search_catalogue] → [Code: pick first biblio_id]
          → [MCP Tool: place_hold] → [Respond]
```

1. **Webhook** receives `{ "patronId": 1, "pickup": "GVP" }`.
2. **MCP Tool `search_catalogue`** finds the biblio.
3. **Code** selects `biblio_id` (e.g. `biblio_id = JSON.parse($json.output)[0].biblio_id`).
4. **MCP Tool `place_hold`**:
   ```
   patron_id:          {{ $json.body.patronId }}
   biblio_id:          {{ $json.biblio_id }}
   pickup_library_id:  {{ $json.body.pickup }}
   ```
5. Respond with the new `hold_id`.

---

## 4. Parameter mapping cheat-sheet

| Tool             | Typical parameters                          |
|------------------|---------------------------------------------|
| `search_catalogue` | `query`, `field` (title/author/isbn/...), `page`, `per_page` |
| `get_biblio`     | `biblio_id`                                 |
| `checkout_item`  | `patron_id`, `item_id`                      |
| `renew_checkout` | `checkout_id`                               |
| `return_item`    | `barcode`, `branchcode` (optional)          |
| `place_hold`     | `patron_id`, `biblio_id`, `pickup_library_id` |
| `list_patron_checkouts` | `patron_id`                          |
| `get_patron` / `search_patrons` | `patron_id` / `query`+`field`   |

Notes:

- The **output of an MCP Tool node is a JSON string** in `$json.output`. Always
  `JSON.parse()` it (Code node) before reading fields.
- For `return_item` and any other tool, the server automatically refreshes the
  Koha OAuth2 token, so no token handling is needed in n8n.
- Use n8n expressions (`{{ ... }}`) to flow values between nodes.

---

## 5. Security notes

- The server currently binds `0.0.0.0:8000` — anyone who can reach that port
  can use the Koha API credentials.
  - For trusted LANs only, or
  - Bind `host="127.0.0.1"` and put n8n on the same host, or
  - Put nginx/Caddy in front of `/sse` with TLS and auth.
- If you expose the port publicly, add authentication at the proxy layer.

---

## 6. Troubleshooting

| Symptom                              | Fix                                              |
|--------------------------------------|--------------------------------------------------|
| "Failed to connect to MCP server"    | Confirm the server is running (`ss -tlnp | grep 8000`); check the URL is `http://host:8000/sse` (SSE transport, not the root `/`). |
| Works on localhost, not from another host | The server must be reachable: `curl http://<server-ip>:8000/sse`; check the firewall. |
| "No tools found"                     | The server must be started with the **SSE** transport (stdio cannot be reached by n8n). |
| Tool output looks like text, not fields | Parse `$json.output` with `JSON.parse()` in a Code node. |
| Tool returns `NotIssued` for a return | The item was not on loan — expected behaviour, the item is still checked in. |
