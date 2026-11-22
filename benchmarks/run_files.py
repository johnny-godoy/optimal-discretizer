"""Read the commit of the checkout, and append a benchmark run to a JSONL file. The benchmark scripts share both."""

from pathlib import Path

import orjson

# A line of .git/packed-refs holds a commit and a reference name.
_PACKED_REF_PARTS = 2


def resolve_git_commit(repo_root: Path) -> str:
    """Read the current git commit from the files of ``.git``, without a subprocess.

    Parameters
    ----------
    repo_root : Path
        The root of the checkout.

    Returns
    -------
    str
        The commit hash, or ``"unknown"`` if the files do not name one.

    """
    git_dir = repo_root / ".git"
    head_file = git_dir / "HEAD"
    if not head_file.exists():
        return "unknown"
    head_text = head_file.read_text(encoding="utf-8").strip()
    ref_prefix = "ref: "
    if not head_text.startswith(ref_prefix):
        return head_text
    ref_path = head_text.removeprefix(ref_prefix)
    commit_file = git_dir / ref_path
    if commit_file.exists():
        return commit_file.read_text(encoding="utf-8").strip()
    packed_refs = git_dir / "packed-refs"
    if not packed_refs.exists():
        return "unknown"
    for line in packed_refs.read_text(encoding="utf-8").splitlines():
        line_parts = line.split(" ", maxsplit=1)
        if line.startswith(("#", "^")) or len(line_parts) != _PACKED_REF_PARTS:
            continue
        sha, reference = line_parts
        if reference == ref_path:
            return sha
    return "unknown"


def append_jsonl(output_path: Path, payload: bytes) -> None:
    """Append one JSON document, written by ``orjson.dumps``, as a line of a JSONL file.

    Parameters
    ----------
    output_path : Path
        The JSONL file. The function creates it and its directory if they do not exist.
    payload : bytes
        The JSON document.

    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("ab") as handle:
        handle.write(payload)
        handle.write(b"\n")


def dumps(
    document: object,
) -> bytes:
    """Write a document as JSON, with numpy arrays and scalars as lists and numbers.

    Parameters
    ----------
    document : dict
        The run to write.

    Returns
    -------
    bytes
        The JSON text.

    """
    return orjson.dumps(document, option=orjson.OPT_SERIALIZE_NUMPY)
