"""Fail unless every lint/type/coverage/test workaround carries a written reason next to it.

See ``scripts/ignore_sites.py`` for what counts as a workaround and where its reason goes. Run it as a module from the
repo root: ``uv run python -m scripts.check_ignores``. ``scripts/compile_ignores.py`` renders the same data for audit.
"""

import sys

from scripts.ignore_sites import find_sites


def main() -> int:
    """Report every workaround that has no reason, or a reason too thin to explain anything.

    Returns
    -------
    int
        The process exit code: 0 if every workaround is justified, 1 otherwise.

    """
    errors = [
        f"{site.location} ({site.program}): {problem} - explain why it cannot be fixed, or remove the workaround"
        for site in find_sites()
        if (problem := site.reason_problem)
    ]
    for error in errors:
        sys.stderr.write(f"{error}\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
