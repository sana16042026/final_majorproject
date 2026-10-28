"""
Manage login accounts for the MPLADS Road Monitoring System.

Add a user:
    python create_user.py USERNAME PASSWORD ROLE [SCOPE] [--name "Full Name"]

    python create_user.py vendor_017 pass123 vendor VEN-017
    python create_user.py admin_nashik secret1 district_admin Nashik
    python create_user.py mp_101 secret1 ministry MP-MA-101
    python create_user.py auditor2 secret1 auditor
    python create_user.py citizen2 secret1 citizen

Roles and what SCOPE means:
    district_admin  SCOPE = district name (optional, empty = all districts)
    ministry        SCOPE = mp_id         (optional, empty = all projects)
    vendor          SCOPE = vendor_id     (required)
    auditor         no scope (sees everything, view only)
    citizen         no scope (public view)

Other commands:
    python create_user.py --list
    python create_user.py USERNAME PASSWORD ROLE [SCOPE] --update    (change an existing user)
    python create_user.py --delete USERNAME

Tip: use "-" as the password to be asked for it, so it does not stay in your
terminal history:   python create_user.py vendor_017 - vendor VEN-017
"""
import argparse
import getpass
import re
import sys

from werkzeug.security import generate_password_hash
from db import get_db_connection

ROLES = {
    'district_admin': 'District Administrator',
    'ministry': 'Nodal Ministry / MP',
    'auditor': 'Auditor',
    'vendor': 'Contractor',
    'citizen': 'Citizen',
}
SCOPE_COLUMN = {'district_admin': 'district', 'ministry': 'mp_id', 'vendor': 'vendor_id'}


def connect():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM `users` LIMIT 1")
        return conn
    except Exception as e:
        if '1146' in str(e) or "doesn't exist" in str(e):
            sys.exit("The users table is missing. Run 'python init_db.py' first.")
        sys.exit(f"Database error: {e}")


def fetch_one(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def execute(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)


def list_users(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT username, role, district, mp_id, vendor_id, full_name "
                    "FROM `users` ORDER BY role, username")
        rows = cur.fetchall()
    if not rows:
        print("No users yet.")
        return
    print(f"{'USERNAME':<18}{'ROLE':<16}{'SCOPE':<18}FULL NAME")
    print("-" * 70)
    for r in rows:
        scope = r['district'] or r['mp_id'] or r['vendor_id'] or '(all)'
        print(f"{r['username']:<18}{r['role']:<16}{scope:<18}{r['full_name'] or ''}")


def delete_user(conn, username):
    row = fetch_one(conn, "SELECT role FROM `users` WHERE username = %s", (username,))
    if not row:
        sys.exit(f"User '{username}' does not exist.")
    if row['role'] == 'district_admin':
        admins = fetch_one(conn, "SELECT COUNT(*) AS c FROM `users` WHERE role = 'district_admin'")['c']
        if admins <= 1:
            sys.exit("Refusing to delete the only District Administrator account.")
    execute(conn, "DELETE FROM `users` WHERE username = %s", (username,))
    print(f"Deleted user '{username}'.")


def scope_exists(conn, column, value):
    row = fetch_one(conn, f"SELECT COUNT(*) AS c FROM `road_projects` WHERE {column} = %s", (value,))
    return bool(row and row['c'])


def save_user(conn, args):
    username, password, role, scope = args.username, args.password, args.role, args.scope

    if not re.fullmatch(r'[A-Za-z0-9_.\-]{3,50}', username):
        sys.exit("Username must be 3-50 characters: letters, digits, _ . -")
    if role not in ROLES:
        sys.exit(f"Unknown role '{role}'. Choose one of: {', '.join(ROLES)}")

    if password == '-':
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            sys.exit("Passwords do not match.")
    if len(password) < 6:
        sys.exit("Password must be at least 6 characters.")

    column = SCOPE_COLUMN.get(role)
    district = mp_id = vendor_id = None
    if role == 'vendor' and not scope:
        sys.exit("A vendor needs a vendor ID, e.g. python create_user.py vendor_017 pass123 vendor VEN-017")
    if scope and not column:
        print(f"Note: role '{role}' has no scope, ignoring '{scope}'.")
        scope = None
    if scope:
        if column == 'district':
            district = scope
        elif column == 'mp_id':
            mp_id = scope
        else:
            vendor_id = scope
        if not scope_exists(conn, column, scope):
            print(f"Warning: no projects found with {column} = '{scope}' yet. "
                  "This user will see an empty dashboard until such data is uploaded.")

    full_name = args.name or (f"{ROLES[role]} ({scope})" if scope else ROLES[role])
    existing = fetch_one(conn, "SELECT user_id FROM `users` WHERE username = %s", (username,))
    pw_hash = generate_password_hash(password)

    if existing and not args.update:
        sys.exit(f"User '{username}' already exists. Add --update to change it.")

    if existing:
        execute(conn, "UPDATE `users` SET password_hash=%s, full_name=%s, role=%s, "
                      "district=%s, mp_id=%s, vendor_id=%s WHERE username=%s",
                (pw_hash, full_name, role, district, mp_id, vendor_id, username))
        print(f"Updated user '{username}' ({role}, scope: {scope or 'all'}). "
              "If they are logged in, they must log out and in again.")
    else:
        execute(conn, "INSERT INTO `users` (username, password_hash, full_name, role, district, mp_id, vendor_id) "
                      "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (username, pw_hash, full_name, role, district, mp_id, vendor_id))
        print(f"Created user '{username}' ({role}, scope: {scope or 'all'}). They can log in at /login.")


def main():
    parser = argparse.ArgumentParser(description="Manage MPLADS login accounts",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=__doc__)
    parser.add_argument('username', nargs='?')
    parser.add_argument('password', nargs='?')
    parser.add_argument('role', nargs='?')
    parser.add_argument('scope', nargs='?')
    parser.add_argument('--name', help="Full name shown in the top bar")
    parser.add_argument('--update', action='store_true', help="Change an existing user")
    parser.add_argument('--list', action='store_true', help="Show all users")
    parser.add_argument('--delete', metavar='USERNAME', help="Delete a user")
    args = parser.parse_args()

    conn = connect()
    try:
        if args.list:
            list_users(conn)
        elif args.delete:
            delete_user(conn, args.delete)
        elif args.username and args.password and args.role:
            save_user(conn, args)
        else:
            parser.print_help()
    finally:
        conn.close()


if __name__ == '__main__':
    main()
