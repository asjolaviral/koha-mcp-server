<div align="center">

# 📚 Koha MCP Server

**A Model Context Protocol (MCP) server that lets AI assistants talk directly
to the Koha library system through its REST API.**

</div>

Connect Claude Desktop, opencode, n8n or any MCP-capable client to your
Koha instance and let it search the catalogue, catalog records, issue, renew
and return items, and manage holds — using plain language.

## ✨ Features

- 🔍 **Catalogue search** — substring search over title / author / ISBN / publisher / ...
- 🛠 **Cataloguing** — create, update and delete biblios (MARC-in-JSON) and items
- 🔄 **Circulation** — Issue (checkout), Renew, and Return (checkin)
- 📌 **Holds** — place, list and cancel holds
- 👤 **Patrons** — lookup and search borrowers
- 🏫 **Libraries** — list branches
- 🔐 **OAuth2** `client_credentials` authentication with automatic token refresh

## 📖 Documentation

| Document | Contents |
|----------|----------|
| [INSTALLATION.md](docs/INSTALLATION.md) | Complete step-by-step setup guide (guidelines) |
| [CLIENT-CONFIGURATION.md](docs/CLIENT-CONFIGURATION.md) | Configure **opencode**, **Claude Desktop**, **n8n** |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Errors you may hit and their fixes |
| [test_client.py](test_client.py) | Self-test script |

## 🔧 Requirements

- **Koha** with the REST API enabled and an OAuth2 API key (client_id/secret)
- Python 3.12+ (the server) and Perl (only for the optional return helper)
- The server should run **on the same host as Koha** (returns use a local helper)

## 🚀 Quick start

```bash
git clone https://github.com/<you>/koha-mcp-server.git
cd koha-mcp-server

bash setup.sh                 # venv, deps, config, helper, sudo rule
nano config.json              # fill in your Koha credentials

.venv/bin/python test_client.py     # verify everything works
.venv/bin/python koha_mcp_server.py # start the MCP server (stdio)
```

## 🗂 Tools exposed

Search / catalogue, cataloguing, circulation, holds, patrons and libraries —
24 tools in total. See [INSTALLATION.md](INSTALLATION.md#tools) for the full list.

## 🧩 How it works

```
AI client (MCP)  <--stdio-->  koha_mcp_server.py (FastMCP)
                                   │
                                   ├─ OAuth2 client_credentials ──▶ Koha REST API
                                   │      GET/POST/PUT/DELETE /api/v1/...
                                   │
                                   └─ koha_return.pl (sudo -u <instance>-koha)
                                          C4::Circulation::AddReturn
```

The Koha REST API has **no checkin/return endpoint**, so returns go through
Koha's internal circulation module via a small, tightly scoped helper script.
Everything else is pure REST.

## 📄 License

[MIT](LICENSE)
