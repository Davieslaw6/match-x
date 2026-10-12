"""python -m app.cli create-owner <username> | reset-owner-password <username>"""
import getpass, sys
from . import auth
from .db import SessionLocal, init_db

def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("create-owner", "reset-owner-password"):
        sys.exit(__doc__)
    init_db(); pw = getpass.getpass("Password (min 12 chars): ")
    if pw != getpass.getpass("Repeat: "): sys.exit("Passwords differ.")
    with SessionLocal() as db:
        try: (auth.create_owner if sys.argv[1] == "create-owner" else auth.reset_password)(db, sys.argv[2], pw)
        except ValueError as e: sys.exit(str(e))
    print("Done.")
main()
