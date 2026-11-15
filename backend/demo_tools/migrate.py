"""Initial demo migrations only; never invoked by the web server."""

import subprocess

from demo_common import (
    OWNER, child_environment, connect, database_url, require, require_empty_public,
    run_safely, validate_environment, verify_marker,
)


def main():
    instance = validate_environment()
    with connect(OWNER) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            verify_marker(connection, instance, OWNER)
            require_empty_public(connection)
    env = child_environment()
    env["DATABASE_URL"] = database_url(OWNER)
    result = subprocess.run(["alembic", "upgrade", "head"], cwd="/app", env=env,
                            capture_output=True, check=False)
    require(result.returncode == 0, "Initial demo migration failed; database state needs operator inspection.")
    with connect(OWNER) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            verify_marker(connection, instance, OWNER)
        with connection.transaction():
            # No broad/default table grants and no lifecycle/audit permissions.
            connection.execute("GRANT SELECT ON public.zodiac_signs, public.forecasts, "
                               "public.prompt_versions, public.alembic_version TO demo_readonly")
            connection.execute("GRANT SELECT ON public.zodiac_signs, public.forecasts TO demo_importer")
            connection.execute("GRANT INSERT ON public.forecasts TO demo_importer")
            connection.execute("GRANT USAGE ON SEQUENCE public.forecasts_id_seq TO demo_importer")
    print("Initial demo migrations and restricted grants complete.")


if __name__ == "__main__":
    run_safely(main)
