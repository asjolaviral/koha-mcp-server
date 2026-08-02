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
   
# Prerequisite
- A working **Koha instance** with the REST API enabled.
- **Root/sudo** access on the Koha host.
- **Python 3.12+** and `python3-venv` (Debian/Ubuntu):
  ```bash
  sudo apt update
  sudo apt install -y python3 python3-venv
  ```
