# Sign-in and access levels

Pondwise uses Streamlit's native `st.login()`, `st.user`, and `st.logout()` with
OpenID Connect (OIDC). Passwords, MFA, recovery and identity registration belong
to your identity provider. Pondwise registers the verified issuer/subject pair
on first sign-in with **pending** access. Email and provider-supplied role claims
never grant application permissions.

| Role | Pages / actions |
| --- | --- |
| Pending | Own registration status only; no farm records |
| Stocktaker | Daily records and pond water visits, including record corrections |
| Manager | All pages, analytics, exports, imports, farm setup and user access |
| Disabled | No farm access |

Permissions apply to the whole farm database. This version does not implement
per-pond or multi-tenant access. Stocktakers can see the records needed for their
record-keeping work across this farm. Navigation and page dispatch are checked
server-side, and writes/imports/inference recheck database permissions. Permissions
are not cached; revocations take effect on the next interaction. Data already
rendered in a user's browser cannot be recalled.

## Configure the provider

1. Register an OIDC web application with Google, Microsoft Entra ID, Auth0, Keycloak
   or another provider. Enable the provider's user invitation/self-registration
   policy as appropriate. Both a default provider under `[auth]` and named
   providers such as `[auth.google]` are supported.
2. Allow the exact callback `http://127.0.0.1:8501/oauth2callback` for local use.
   For deployment use the application's HTTPS URL with `/oauth2callback` appended.
3. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`, then fill
   in the client ID, client secret and metadata URL from the provider. The example
   metadata URL is for Google; substitute your tenant URL for another provider.
4. Generate a cookie secret, for example with
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`, and place it in
   the secrets file. Keep that file private.
5. Set `AUTH_MODE=oidc` in `.env` (also the default if absent). Install the updated
   requirements, which include Streamlit's authentication dependencies. Restart
   Streamlit after changing authentication configuration.

For a named Google provider, keep `redirect_uri` and `cookie_secret` in `[auth]`;
put `client_id`, `client_secret` and `server_metadata_url` under `[auth.google]`.
The app detects this structure and calls `st.login("google")`. Open the app using
the same hostname as the callback: `localhost` and `127.0.0.1` are not interchangeable
for browser authentication cookies. The callback must exactly match an authorized
redirect URI in Google Cloud. A cookie secret must be random and at least 32 characters.

Run only one copy of the app. The project pins the listener to `127.0.0.1:8501`
so a second launch cannot silently serve a different instance on IPv6 at the same
port. If the port is occupied, use the existing instance or stop it before restarting.
After changing secrets, restart the active instance and begin a fresh login from
the home page, not an old OAuth callback URL. The public login page does not expose
technical diagnostics. Administrators should inspect server logs for configuration
or OAuth callback failures. For tokens rejected as issued in the future, check
Windows clock synchronization rather than disabling token validation.
6. Sign in. A first-time user sees **Access requested** and can expand their own
   identity details. Have the trusted server operator grant the first manager:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users --issuer "ISSUER_FROM_LOGIN" --subject "SUBJECT_FROM_LOGIN"
```

This is an operator-only bootstrap/recovery command, not a browser-accessible
function. It must run against the same database configuration as the app.
Refresh the app after bootstrapping. The manager can then approve registered
users as stocktakers/managers and disable accounts on **User access**. Managers
cannot change their own role/status, preventing accidental self-lockout. Access
changes are recorded in `access_audit`.

## Local demo only

Set both `APP_MODE=demo` and `AUTH_MODE=demo` for a local synthetic-data preview.
This grants a clearly labeled demo manager and is **not authentication**. It cannot
administer real user accounts and is rejected with PostgreSQL. Default OIDC mode
fails closed when credentials are absent; there is no automatic demo fallback.

The app honors an identity token's `exp` claim when present. Streamlit's identity
cookie can outlast a provider session; disabling the app account is the immediate
application-side revocation mechanism on the next request. Require HTTPS for a
deployed app and configure MFA/session policies at your identity provider.

References: [Streamlit authentication](https://docs.streamlit.io/develop/concepts/connections/authentication),
[st.login](https://docs.streamlit.io/develop/api-reference/user/st.login).
