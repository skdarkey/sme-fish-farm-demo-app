"""Repair the existing local Google configuration without printing credentials."""
from pathlib import Path
import re
import secrets
import tomllib

from farm.auth_config import login_providers


def main():
    path = Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml"
    original = path.read_text(encoding="utf-8-sig")
    parsed = tomllib.loads(original)
    auth = parsed.get("auth", {})
    if not isinstance(auth.get("google"), dict):
        raise ValueError("Expected the existing [auth.google] section.")
    section = ""
    output = []
    for line in original.splitlines(keepends=True):
        match = re.match(r"\s*\[([^]]+)\]", line)
        if match:
            section = match.group(1)
        # Streamlit reads these settings from the shared section only.
        if section == "auth.google" and re.match(r"\s*(redirect_uri|cookie_secret)\s*=", line):
            continue
        if section == "auth" and re.match(r"\s*cookie_secret\s*=", line):
            old = auth.get("cookie_secret", "")
            if len(old) < 32 or old.startswith("REPLACE_"):
                line = 'cookie_secret = "' + secrets.token_urlsafe(48) + '"\n'
        output.append(line)
    updated = "".join(output)
    validated = tomllib.loads(updated)
    login_providers(validated["auth"])
    for key in ("client_id", "client_secret", "server_metadata_url"):
        assert validated["auth"]["google"][key] == auth["google"][key]
    assert validated["auth"]["redirect_uri"] == auth["redirect_uri"]
    path.write_text(updated, encoding="utf-8")
    print("Validated Google settings; credentials and shared callback preserved. Cookie secret secured; redundant nested settings removed.")


if __name__ == "__main__":
    main()
