"""Create the initial admin user.

Run once against a configured database:

    python admin.py

Credentials come from the environment so nothing secret lives in this file:

    DB_PASSWORD      MySQL password
    ADMIN_USERNAME   username for the admin account
    ADMIN_PASSWORD   password for the admin account (stored hashed)
"""
import os
import sys

import mysql.connector
from werkzeug.security import generate_password_hash


def _require_env(name):
    value = os.environ.get(name)
    if not value:
        sys.exit(
            f"{name} is not set. See .env.example; export the values before running this script."
        )
    return value


DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "user": os.environ.get("DB_USER", "root"),
    "password": _require_env("DB_PASSWORD"),
    "database": os.environ.get("DB_NAME", "banking_project"),
}

username = _require_env("ADMIN_USERNAME")
password = _require_env("ADMIN_PASSWORD")
hashed = generate_password_hash(password)

con = mysql.connector.connect(**DB_CONFIG)
cur = con.cursor()
cur.execute(
    "INSERT INTO users (username, password, role, full_name) VALUES (%s,%s,'admin',%s)",
    (username, hashed, "Administrator"),
)
con.commit()
print(f"Admin user '{username}' created.")
cur.close()
con.close()
