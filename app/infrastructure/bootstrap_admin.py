from getpass import getpass

from app.domain.entities import Account
from app.infrastructure.database import SessionLocal, initialize_database
from app.infrastructure.passwords import hash_password
from app.infrastructure.repositories import UserRepository


def main() -> None:
    initialize_database()
    username = input("Initial administrator username: ").strip()
    password = getpass("Initial administrator password (10+ characters): ")
    if len(password) < 10:
        raise SystemExit("Password must contain at least 10 characters.")

    with SessionLocal() as session:
        users = UserRepository(session)
        if users.get_by_username(username) is not None:
            raise SystemExit("That username already exists.")
        users.add(
            Account(
                id=0,
                username=username,
                password_hash=hash_password(password),
                role="admin",
                approved=True,
            )
        )
    print("Administrator account created.")


if __name__ == "__main__":
    main()
