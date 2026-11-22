"""Read and write a summary as a JSON file: an example of an adapter that does I/O."""

import os
from pathlib import Path

import attrs
import orjson

from optimal_discretizer.domain.summary import Summary


def write_summary(summary: Summary, path: str | os.PathLike[str]) -> None:
    """Write a summary to a JSON file.

    Parameters
    ----------
    summary: Summary
        The summary to write.
    path: str | os.PathLike[str]
        The file. The function replaces a file that exists.

    """
    Path(path).write_bytes(orjson.dumps(attrs.asdict(summary), option=orjson.OPT_INDENT_2))


def read_summary(path: str | os.PathLike[str]) -> Summary:
    """Read a summary from a JSON file that ``write_summary`` wrote.

    Parameters
    ----------
    path: str | os.PathLike[str]
        The file.

    Returns
    -------
    Summary
        The summary in the file.

    """
    fields: dict[str, float] = orjson.loads(Path(path).read_bytes())
    return Summary(
        count=int(fields["count"]),
        minimum=fields["minimum"],
        maximum=fields["maximum"],
        mean=fields["mean"],
    )
