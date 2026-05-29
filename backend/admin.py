"""Backend provisioning CLI for the platform owner.

No public signup — you create and manage tenants here. On Railway, run via:
    railway run python -m backend.admin <command> ...
Locally:
    .venv\\Scripts\\python -m backend.admin <command> ...

Commands:
    create-business  "<name>"
    create-user      <business_id> <email> "<full name>" [password]
    set-active       <business_id> <on|off>
    reset-password   <email> [password]
    list-businesses
    list-users       [business_id]
"""
from __future__ import annotations
import argparse
import secrets
import sys

from . import storage
from .security import hash_password


def _gen_password() -> str:
    return secrets.token_urlsafe(9)


def cmd_create_business(args) -> None:
    storage.init_db()
    bid = storage.create_business(args.name)
    print(f"Created business #{bid}: {args.name} (active)")
    print(f"Next: python -m backend.admin create-user {bid} someone@example.com \"Full Name\"")


def cmd_create_user(args) -> None:
    storage.init_db()
    if not storage.get_business(args.business_id):
        sys.exit(f"No business with id {args.business_id}")
    if storage.get_user_by_email(args.email):
        sys.exit(f"A user with email {args.email} already exists")
    password = args.password or _gen_password()
    uid = storage.create_user(args.business_id, args.email, args.name, hash_password(password))
    print(f"Created user #{uid}: {args.name} <{args.email}> in business #{args.business_id}")
    print(f"Temporary password: {password}")
    print("Share this with the user — they'll be required to set their own password on first login.")


def cmd_set_active(args) -> None:
    storage.init_db()
    if not storage.get_business(args.business_id):
        sys.exit(f"No business with id {args.business_id}")
    on = args.state.lower() in ("on", "1", "true", "active", "yes")
    storage.set_business_active(args.business_id, on)
    print(f"Business #{args.business_id} is now {'ACTIVE' if on else 'INACTIVE (users blocked)'}")


def cmd_reset_password(args) -> None:
    storage.init_db()
    user = storage.get_user_by_email(args.email)
    if not user:
        sys.exit(f"No user with email {args.email}")
    password = args.password or _gen_password()
    storage.set_user_password(user["id"], hash_password(password))
    print(f"Password reset for {args.email}")
    print(f"New password: {password}")


def cmd_list_businesses(args) -> None:
    storage.init_db()
    for b in storage.list_businesses():
        flag = "active" if b["active"] else "INACTIVE"
        n = len(storage.list_users(b["id"]))
        print(f"#{b['id']:>3}  {b['name']}  [{flag}]  users={n}")


def cmd_list_users(args) -> None:
    storage.init_db()
    for u in storage.list_users(args.business_id):
        print(f"#{u['id']:>3}  biz#{u['business_id']}  {u['name']} <{u['email']}>")


def cmd_create_admin(args) -> None:
    storage.init_db()
    if storage.get_admin_by_email(args.email):
        sys.exit(f"An admin with email {args.email} already exists")
    password = args.password or _gen_password()
    aid = storage.create_admin(args.email, args.name, hash_password(password))
    print(f"Created platform admin #{aid}: {args.name} <{args.email}>")
    print(f"Password: {password}")
    print("Sign in at /admin/login")


def cmd_list_admins(args) -> None:
    storage.init_db()
    for a in storage.list_admins():
        print(f"#{a['id']:>3}  {a['name']} <{a['email']}>")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="backend.admin", description="Provision tenants & users")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("create-business"); s.add_argument("name"); s.set_defaults(fn=cmd_create_business)
    s = sub.add_parser("create-user")
    s.add_argument("business_id", type=int); s.add_argument("email"); s.add_argument("name")
    s.add_argument("password", nargs="?", default=None); s.set_defaults(fn=cmd_create_user)
    s = sub.add_parser("set-active")
    s.add_argument("business_id", type=int); s.add_argument("state"); s.set_defaults(fn=cmd_set_active)
    s = sub.add_parser("reset-password")
    s.add_argument("email"); s.add_argument("password", nargs="?", default=None); s.set_defaults(fn=cmd_reset_password)
    s = sub.add_parser("list-businesses"); s.set_defaults(fn=cmd_list_businesses)
    s = sub.add_parser("list-users"); s.add_argument("business_id", type=int, nargs="?", default=None); s.set_defaults(fn=cmd_list_users)
    s = sub.add_parser("create-admin")
    s.add_argument("email"); s.add_argument("name"); s.add_argument("password", nargs="?", default=None)
    s.set_defaults(fn=cmd_create_admin)
    s = sub.add_parser("list-admins"); s.set_defaults(fn=cmd_list_admins)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
