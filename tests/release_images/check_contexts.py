"""Check release allowlists with BuildKit's matcher and synthetic files only.

Run from the repository root: python3 -B tests/release_images/check_contexts.py
Requires the local Docker daemon and BuildKit. No RUN instructions, registry
pulls, application imports, runtime containers, secrets or databases are used.
"""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {
    "backend": (
        "demo_fixture_import.py", "fixtures/demo-2026-11-15-v1.json",
        "demo_tools/bootstrap.py", "demo_tools/demo_common.py", "demo_tools/migrate.py",
        "demo_tools/import-fixtures.py", "requirements.txt", "wsgi.py", "paid_execution_policy.py",
        "paid_admission_policy.py", "alembic.ini", "app/__init__.py",
        "app/services/readiness_service.py", "migrations/env.py",
        "migrations/versions/0008_generation_job_leases.py",
        "migrations/script.py.mako", "utils/generation_job_inspect.py",
    ),
    "frontend": (
        "package.json", "package-lock.json", "index.html", "vite.config.js",
        "tsconfig.json", "postcss.config.cjs", "tailwind.config.cjs",
        "Caddyfile.release", "caddy-entrypoint.sh", "src/main.js", "src/App.vue",
        "src/api/forecast.ts", "src/style.css",
        "src/assets/zodiac/constellations/aries.png",
    ),
}
COMMON_DENIED = (
    ".env", ".env.production", ".env.py", ".env.js", "private.env",
    ".npmrc", ".pypirc", "pip.conf", ".git/config", "secrets/token.py",
    "secrets/token.js", "private.key", "private.pem", "credentials.py",
    "credentials.js", "credentials.json", "local_secret.json", "local_secret.py", "local_secret.ts", "tests/probe.py",
    "tests/probe.js", "artifacts/probe.py", "artifacts/probe.js",
    "node_modules/probe.js", "dist/probe.js", "unlisted.txt",
)
PREFIXES = {
    "backend": ("", "app/", "app/deep/", "migrations/", "utils/", "demo_tools/", "fixtures/"),
    "frontend": ("", "src/", "src/deep/", "src/assets/"),
}
EXTRA_DENIED = {
    "backend": (
        "tasks.py", "run.py", "test_db_guard.py", "tests/conftest.py",
        "app/test_example.py", "app/example_test.py", "app/instance/example.py",
        "app/__pycache__/example.py", "app/.venv/example.py",
    ),
    "frontend": (
        "vitest.config.js", "poc/client.js", "tests/unit/example.spec.ts",
        "src/__tests__/example.js", "src/example.spec.ts", "src/example.test.js",
        "src/coverage/example.js",
    ),
}


def check_context(docker: str, workspace: Path, service: str) -> None:
    context = workspace / service
    context.mkdir()
    # Reuse the real policy but never copy application files or real secrets.
    (context / "Dockerfile.release").write_text("FROM scratch\nCOPY . /\n")
    shutil.copyfile(
        ROOT / service / "Dockerfile.release.dockerignore",
        context / "Dockerfile.release.dockerignore",
    )
    denied = {
        prefix + name
        for prefix in PREFIXES[service]
        for name in COMMON_DENIED
    } | set(EXTRA_DENIED[service])
    expected = set(ALLOWED[service])
    assert not expected & denied
    for name in expected | denied:
        path = context / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("allowed\n" if name in expected else "EXCLUDED_CANARY\n")

    exported = workspace / f"{service}-export"
    result = subprocess.run(
        [
            docker, "--host", "unix:///var/run/docker.sock", "build",
            "--progress=plain", "-f", "Dockerfile.release", "--output",
            f"type=local,dest={exported}", ".",
        ],
        cwd=context,
        env={
            "PATH": os.defpath,
            "DOCKER_CONFIG": str(workspace / "docker-config"),
            "DOCKER_BUILDKIT": "1",
        },
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    actual = {
        path.relative_to(exported).as_posix()
        for path in exported.rglob("*") if path.is_file()
    }
    if actual != expected:
        raise AssertionError(
            f"{service}: unexpected={sorted(actual - expected)}, "
            f"missing={sorted(expected - actual)}"
        )
    print(f"{service}: {len(expected)} allowed files; {len(denied)} canaries excluded")


def main() -> None:
    docker = shutil.which("docker", path=os.defpath)
    if docker is None:
        raise SystemExit("Docker is required for release context verification")
    with tempfile.TemporaryDirectory(prefix="horoscope-release-contexts-") as tmp:
        workspace = Path(tmp)
        (workspace / "docker-config").mkdir()
        for service in ALLOWED:
            check_context(docker, workspace, service)


if __name__ == "__main__":
    main()
