"""Build or serve the documentation with Zensical, after the proof papers are exported.

Run it from the repo root: ``uv run --group docs python -m scripts.build_docs [build|serve]``. CI runs the same
command, so a local build fails exactly when CI fails.

The proof papers of ``proofs/papers/<topic>/paper.typ`` are compiled into ``docs/proofs/<topic>.pdf``, and the proof
pages link to them.

Zensical prints a ``griffe:`` warning for a docstring that does not render, for example a parameter that the function
does not have, and still exits with code 0. The ``build`` command fails when the output has such a warning.

The strict build checks the links of the Markdown, but not the ``href`` and ``src`` of raw HTML, such as the frame of a
paper. Zensical rewrites a relative address in raw HTML as relative to the Markdown file, not to the built page. The
``build`` command reads each built page and fails when a link names no file of the site.
"""

import argparse  # ruff: ignore[banned-api] -- the scripts run with the dev group only, which has no command-line library
import html.parser
import posixpath
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- marimo and Zensical only offer their build as a command
import sys
import tomllib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import override
from urllib.parse import unquote, urlsplit

import structlog
import typst

logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent
PAPERS_ROOT = ROOT / "proofs" / "papers"
PAPER_DIR = ROOT / "docs" / "proofs"
SITE_DIR = ROOT / "site"
CONFIG = ROOT / "zensical.toml"
WARNING_PREFIX = "griffe:"
LINK_ATTRIBUTES = frozenset({"href", "src"})


def export_papers() -> None:
    """Compile each proof paper of ``proofs/papers/`` into ``docs/proofs/<topic>.pdf``.

    The paper of a topic imports the shared style of ``proofs/papers/``, so that folder is the root of the compilation.
    Compiling takes a second, so the function compiles every paper on every call. A paper that does not compile fails
    the build.

    """
    for paper in sorted(PAPERS_ROOT.glob("*/paper.typ")):
        PAPER_DIR.mkdir(parents=True, exist_ok=True)
        typst.compile(paper, output=PAPER_DIR / f"{paper.parent.name}.pdf", root=PAPERS_ROOT)


def find_warnings(output: str) -> list[str]:
    """Find the docstring warnings in the output of a Zensical build.

    Parameters
    ----------
    output: str
        The text that the build printed.

    Returns
    -------
    list[str]
        The lines that start with ``griffe:``, in order.

    """
    return [line for line in output.splitlines() if line.startswith(WARNING_PREFIX)]


class _LinkCollector(html.parser.HTMLParser):
    """Collect the ``href`` and ``src`` addresses of one HTML page, in order."""

    def __init__(self) -> None:
        super().__init__()
        self.addresses: list[str] = []

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.addresses.extend(value for name, value in attrs if name in LINK_ATTRIBUTES and value)


def site_path_prefix(config: Path) -> str:
    """Return the path of ``site_url`` in the Zensical config, with a slash at each end.

    Parameters
    ----------
    config: Path
        The ``zensical.toml`` file.

    Returns
    -------
    str
        For example ``/optimal-discretizer/``, or ``/`` when the site is at the root of its host.

    """
    site_url: str = tomllib.loads(config.read_text(encoding="utf-8"))["project"]["site_url"]
    site_path = urlsplit(site_url).path.strip("/")
    return f"/{site_path}/" if site_path else "/"


def resolve_link(page: str, address: str, prefix: str) -> str | None:
    """Return the path in the site that a link of a page names.

    Parameters
    ----------
    page: str
        The path of the page in the site, for example ``kmeans-1d-proof/index.html``.
    address: str
        The ``href`` or ``src`` of the link.
    prefix: str
        The path of the site on its host, from ``site_path_prefix``.

    Returns
    -------
    str | None
        The path in the site, which starts with ``..`` when the link leaves the site. ``None`` for an external link
        or an anchor of the same page, which the check skips.

    """
    parts = urlsplit(address)
    if parts.scheme or parts.netloc or not parts.path:
        return None
    path = unquote(parts.path)
    if path.startswith("/"):
        # the theme writes absolute paths in the 404 page, because the server shows it at any address
        return posixpath.normpath(path.removeprefix(prefix)) if path.startswith(prefix) else ".." + path
    return posixpath.normpath(posixpath.join(posixpath.dirname(page), path))


def find_broken_links(site_dir: Path, prefix: str) -> list[str]:
    """Find the internal links of the built site that name no file of the site.

    Parameters
    ----------
    site_dir: Path
        The built site.
    prefix: str
        The path of the site on its host, from ``site_path_prefix``.

    Returns
    -------
    list[str]
        One ``page: address`` line for each broken link, in the order of the pages and of the links.

    """
    broken: list[str] = []
    for page_file in sorted(site_dir.rglob("*.html")):
        collector = _LinkCollector()
        collector.feed(page_file.read_text(encoding="utf-8"))
        page = page_file.relative_to(site_dir).as_posix()
        for address in collector.addresses:
            target_path = resolve_link(page, address, prefix)
            if target_path is None:
                continue
            target = site_dir / target_path
            if target.is_dir():
                target /= "index.html"
            if target_path.startswith("..") or not target.is_file():
                broken.append(f"{page}: {address}")
    return broken


def build() -> int:
    """Build the site in strict mode, and fail on a docstring warning.

    Returns
    -------
    int
        The exit code: the code of Zensical if it fails, 1 if the output has a warning, and 0 otherwise.

    """
    export_papers()
    command = [sys.executable, "-m", "zensical", "build", "--strict"]
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed argv from sys.executable, never untrusted input
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    # one text for both streams, so the gate sees the warnings wherever Zensical writes them
    output = result.stdout + result.stderr
    sys.stdout.write(output)
    if result.returncode:
        return result.returncode
    warnings = find_warnings(output)
    for warning in warnings:
        logger.error("docstring warning", warning=warning)
    broken_links = find_broken_links(SITE_DIR, site_path_prefix(CONFIG))
    for broken_link in broken_links:
        logger.error("broken link", link=broken_link)
    return int(bool(warnings or broken_links))


def serve() -> int:
    """Start the preview server of Zensical.

    Returns
    -------
    int
        The exit code of the server.

    """
    export_papers()
    command = [sys.executable, "-m", "zensical", "serve"]
    return subprocess.run(command, cwd=ROOT, check=False).returncode  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed argv from sys.executable, never untrusted input


COMMANDS: dict[str, Callable[[], int]] = {"build": build, "serve": serve}


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command of the script.

    Parameters
    ----------
    argv: Sequence[str] | None
        The arguments of the command line, without the program name. ``None`` reads ``sys.argv``.

    Returns
    -------
    int
        The exit code of the command.

    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("command", nargs="?", default="build", choices=sorted(COMMANDS))
    return COMMANDS[parser.parse_args(argv).command]()


if __name__ == "__main__":
    sys.exit(main())
