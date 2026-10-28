#!/usr/bin/env python3
"""Hash a password for the dashboard's /admin login.

Asks twice (not echoed) and prints the .env line to paste:
    DASHBOARD_ADMIN_PASSWORD_HASH=scrypt:<n>:<r>:<p>:<salt hex>:<hash hex>
Hex and colons only, so compose doesn't interpolate anything. Must match app/auth.py.
"""
import getpass
import hashlib
import secrets
import sys

N, R, P = 2**14, 8, 1


def main() -> None:
    pw = getpass.getpass("Dashboard admin password: ")
    if len(pw) < 12:
        sys.exit("Use at least 12 characters.")
    if getpass.getpass("Again: ") != pw:
        sys.exit("Passwords don't match.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(pw.encode(), salt=salt, n=N, r=R, p=P, dklen=32)
    print(f"DASHBOARD_ADMIN_PASSWORD_HASH=scrypt:{N}:{R}:{P}:{salt.hex()}:{digest.hex()}")


if __name__ == "__main__":
    main()
