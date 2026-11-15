"""Supply the isolated importer URL from its secret file without logging it."""

import os
import sys

from demo_common import (
    DATABASE, IMPORTER, child_environment, database_url, require, run_safely,
    validate_environment,
)


def main():
    instance = validate_environment()
    require(os.environ.get("DEMO_EXPECTED_ROLE") == IMPORTER, "Unexpected demo importer role.")
    require("DEMO_FIXTURE_DATABASE_URL" not in os.environ, "An externally supplied importer URL is forbidden by this wrapper.")
    env = child_environment()
    env.update({
        "DEMO_FIXTURE_DATABASE_URL": database_url(IMPORTER),
        "DEMO_EXPECTED_INSTANCE_ID": str(instance),
        "DEMO_EXPECTED_DATABASE": DATABASE,
        "DEMO_EXPECTED_ROLE": IMPORTER,
    })
    os.execve(sys.executable, [sys.executable, "-m", "utils.import_demo_fixtures", *sys.argv[1:]], env)


if __name__ == "__main__":
    run_safely(main)
