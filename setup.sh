#!/usr/bin/env bash
#
# setup.sh - one-shot installer for the Koha MCP Server
#
# Steps performed:
#   1. Create a Python virtualenv and install dependencies
#   2. Create config.json from the example (you edit credentials afterwards)
#   3. Install the return helper under /usr/local/lib/koha-mcp/scripts/
#   4. Install a scoped sudo rule so the server can run the return helper
#      as the Koha system user (returns are done via Koha internals)
#
# Usage:
#   bash setup.sh
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SELF_USER="${SUDO_USER:-$(whoami)}"
SELF_HOME="$(eval echo "~$SELF_USER")"

echo "==> [1/4] Python virtualenv + dependencies"
python3 -m venv "$REPO_DIR/.venv"
"$REPO_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$REPO_DIR/.venv/bin/pip" install --quiet -r "$REPO_DIR/requirements.txt"

echo "==> [2/4] Configuration"
if [[ -f "$REPO_DIR/config.json" ]]; then
    echo "    config.json already exists - leaving it untouched."
else
    if [[ -f "$SELF_HOME/.koha-mcp/config.json" ]]; then
        echo "    found $SELF_HOME/.koha-mcp/config.json - reusing it."
    else
        cp "$REPO_DIR/config.example.json" "$REPO_DIR/config.json"
        echo "    created config.json from config.example.json."
        echo "    >>> EDIT config.json with your Koha API credentials before running the server. <<<"
    fi
fi

echo "==> [3/4] Install return helper"
read -rp "    Koha instance name [library]: " INSTANCE
INSTANCE="${INSTANCE:-library}"
KOHA_USER="${INSTANCE}-koha"
HELPER_DEST="/usr/local/lib/koha-mcp/scripts/koha_return.pl"
sudo mkdir -p /usr/local/lib/koha-mcp/scripts
sudo install -m 0755 "$REPO_DIR/scripts/koha_return.pl" "$HELPER_DEST"

echo "==> [4/4] Scoped sudo rule for returns"
if [[ "$(id -u)" -eq 0 ]]; then
    echo "    Running as root; the sudo rule will grant $SELF_USER access."
fi
SUDOERS_FILE="/etc/sudoers.d/koha-mcp"
RULE="$SELF_USER ALL=($KOHA_USER) NOPASSWD: $HELPER_DEST"
echo "    Rule: $RULE"
echo "$RULE" | sudo tee "$SUDOERS_FILE" >/dev/null
sudo chmod 0440 "$SUDOERS_FILE"
sudo visudo -c -f "$SUDOERS_FILE"

echo
echo "==> Done. Quick self-test:"
echo "    $REPO_DIR/.venv/bin/python $REPO_DIR/test_client.py"
echo
echo "==> Next steps:"
echo "    1. Edit config.json with your real base_url / client_id / client_secret"
echo "       (or run the server with: KOHA_MCP_CONFIG=~/.koha-mcp/config.json)"
echo "    2. Start the server:  $REPO_DIR/.venv/bin/python $REPO_DIR/koha_mcp_server.py"
echo "    3. Connect your client - see CLIENT-CONFIGURATION.md"
