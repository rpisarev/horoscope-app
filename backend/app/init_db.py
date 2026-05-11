from app import create_app, db


def init_db() -> None:
    app = create_app()

    with app.app_context():
        db.create_all()

    print("Database tables are ready.", flush=True)


if __name__ == "__main__":
    init_db()