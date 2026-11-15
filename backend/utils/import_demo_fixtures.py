"""CLI for the isolated offline demo importer; never starts Flask or generation."""
from demo_fixture_import import main

if __name__ == '__main__':
    raise SystemExit(main())
