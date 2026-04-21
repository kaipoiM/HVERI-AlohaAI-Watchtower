#!/usr/bin/env python3
"""
AlohaAI Watchtower — Admin Account Manager
Run this directly on the server via SSH to manage admin accounts.

Usage:
  python manage_admins.py add    --username jay --email jay@example.com
  python manage_admins.py list
  python manage_admins.py reset  --email jay@example.com
  python manage_admins.py delete --email jay@example.com
"""

import sys
import argparse
import secrets
import string

# Make sure we can import from the backend package
sys.path.insert(0, "/var/www/HVERI-AlohaAI-Watchtower/watchtower")

from passlib.context import CryptContext
from backend.watchtower import DatabaseManager

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
db = DatabaseManager()


def generate_temp_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def cmd_add(args):
    existing = db.get_admin_by_login(args.email) or db.get_admin_by_login(args.username)
    if existing:
        print(f"ERROR: An admin with that email or username already exists.")
        sys.exit(1)

    temp_pass = generate_temp_password()
    hashed    = pwd_context.hash(temp_pass)
    db.create_admin(args.username, args.email, hashed)

    print(f"\n✅ Admin created successfully.")
    print(f"   Username : {args.username}")
    print(f"   Email    : {args.email}")
    print(f"   Temp pass: {temp_pass}")
    print(f"\n   Send this password to the new admin.")
    print(f"   They will be prompted to change it on first login.\n")


def cmd_list(args):
    admins = db.list_admins()
    if not admins:
        print("No admin accounts found.")
        return

    print(f"\n{'ID':<5} {'Username':<20} {'Email':<35} {'Must Change':<12} {'Last Login'}")
    print("-" * 90)
    for a in admins:
        must = "Yes" if a["must_change_password"] else "No"
        last = a["last_login"] or "Never"
        print(f"{a['id']:<5} {a['username']:<20} {a['email']:<35} {must:<12} {last}")
    print()


def cmd_reset(args):
    admin = db.get_admin_by_login(args.email)
    if not admin:
        print(f"ERROR: No admin found with email '{args.email}'.")
        sys.exit(1)

    temp_pass = generate_temp_password()
    hashed    = pwd_context.hash(temp_pass)
    db.update_password(admin["id"], hashed, must_change=1)

    print(f"\n✅ Password reset for {admin['username']} ({admin['email']}).")
    print(f"   New temp pass: {temp_pass}")
    print(f"\n   They will be prompted to change it on next login.\n")


def cmd_delete(args):
    admin = db.get_admin_by_login(args.email)
    if not admin:
        print(f"ERROR: No admin found with email '{args.email}'.")
        sys.exit(1)

    confirm = input(f"Delete admin '{admin['username']}' ({admin['email']})? [yes/N]: ")
    if confirm.strip().lower() != "yes":
        print("Cancelled.")
        return

    db.delete_admin(admin["id"])
    print(f"✅ Admin '{admin['username']}' deleted.\n")


def main():
    parser = argparse.ArgumentParser(description="Manage AlohaAI Watchtower admin accounts.")
    sub = parser.add_subparsers(dest="command")

    # add
    p_add = sub.add_parser("add", help="Create a new admin with a temp password")
    p_add.add_argument("--username", required=True)
    p_add.add_argument("--email",    required=True)

    # list
    sub.add_parser("list", help="List all admin accounts")

    # reset
    p_reset = sub.add_parser("reset", help="Reset an admin's password to a new temp password")
    p_reset.add_argument("--email", required=True)

    # delete
    p_del = sub.add_parser("delete", help="Delete an admin account")
    p_del.add_argument("--email", required=True)

    args = parser.parse_args()

    if args.command == "add":
        cmd_add(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "reset":
        cmd_reset(args)
    elif args.command == "delete":
        cmd_delete(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
