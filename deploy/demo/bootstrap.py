"""Explicit one-time provisioning of a fresh, dedicated PostgreSQL cluster."""

import argparse

from demo_common import (
    ADMIN, DATABASE, IMPORTER, OWNER, READONLY, connect, password, require,
    require_empty_public, run_safely, validate_environment, verify_session,
)


def verify_fresh_cluster(connection):
    verify_session(connection, "postgres", ADMIN)
    databases = connection.execute("SELECT datname FROM pg_database ORDER BY datname").fetchall()
    require(databases == [("postgres",), ("template0",), ("template1",)],
            "Existing database refused; a fresh dedicated cluster is required.")
    roles = connection.execute(
        "SELECT rolname FROM pg_roles WHERE rolname !~ '^pg_' ORDER BY rolname"
    ).fetchall()
    require(roles == [(ADMIN,)], "Existing roles refused; a fresh dedicated cluster is required.")
    schemas = connection.execute(
        "SELECT nspname FROM pg_namespace WHERE nspname !~ '^pg_' "
        "AND nspname <> 'information_schema' ORDER BY nspname"
    ).fetchall()
    require(schemas == [("public",)], "Existing schemas refused.")
    require_empty_public(connection)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-new-isolated-cluster", action="store_true", required=True)
    parser.parse_args()
    instance = validate_environment()
    role_passwords = {role: password(role) for role in (ADMIN, OWNER, IMPORTER, READONLY)}
    require(len(set(role_passwords.values())) == 4, "Each demo role needs a distinct password.")
    from psycopg import sql

    with connect(ADMIN, "postgres") as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            verify_fresh_cluster(connection)
        # Role creation is transactional. CREATE DATABASE must run separately.
        with connection.transaction():
            for role in (OWNER, IMPORTER, READONLY):
                connection.execute(sql.SQL(
                    "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    "NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}"
                ).format(sql.Identifier(role), sql.Literal(role_passwords[role])))
            connection.execute("ALTER ROLE demo_readonly SET default_transaction_read_only = on")
        connection.execute("CREATE DATABASE horoscope_demo OWNER demo_owner TEMPLATE template0")

    with connect(ADMIN) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            verify_session(connection, DATABASE, ADMIN)
            require_empty_public(connection)
        with connection.transaction():
            connection.execute("REVOKE ALL ON DATABASE horoscope_demo FROM PUBLIC")
            connection.execute("GRANT CONNECT ON DATABASE horoscope_demo TO demo_owner, demo_importer, demo_readonly")
            connection.execute("ALTER SCHEMA public OWNER TO demo_owner")
            connection.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
            connection.execute("GRANT USAGE ON SCHEMA public TO demo_importer, demo_readonly")
            connection.execute("SET LOCAL ROLE demo_owner")
            connection.execute("CREATE SCHEMA demo_control AUTHORIZATION demo_owner")
            connection.execute("REVOKE ALL ON SCHEMA demo_control FROM PUBLIC")
            connection.execute("CREATE TABLE demo_control.identity ("
                               "id integer PRIMARY KEY CHECK (id = 1), "
                               "purpose text NOT NULL CHECK (purpose = 'horoscope-demo'), "
                               "contract_version integer NOT NULL CHECK (contract_version = 1), "
                               "instance_id uuid NOT NULL, "
                               "database_name text NOT NULL CHECK (database_name = 'horoscope_demo'), "
                               "importer_role text NOT NULL CHECK (importer_role = 'demo_importer'))")
            connection.execute("INSERT INTO demo_control.identity VALUES "
                               "(1, 'horoscope-demo', 1, %s, 'horoscope_demo', 'demo_importer')", (instance,))
            connection.execute("GRANT USAGE ON SCHEMA demo_control TO demo_importer, demo_readonly")
            connection.execute("GRANT SELECT ON demo_control.identity TO demo_importer, demo_readonly")
            # Future migration functions are not automatically callable by readers.
            connection.execute("ALTER DEFAULT PRIVILEGES FOR ROLE demo_owner "
                               "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC")
    print("Demo identity and roles created. Run the separate initial migration tool next.")


if __name__ == "__main__":
    run_safely(main)
