import shlex
from collections import OrderedDict as odict
from collections.abc import Callable
from typing import Any

from annet.annlib.types import Op
from annet.rulebook import common, juniper


def _name(row: str) -> str:
    return row.split(maxsplit=1)[0]


def _is_leaf_list(row: str) -> bool:
    return row.rstrip().endswith("]")


def _is_name_value(row: str) -> bool:
    try:
        return len(shlex.split(row)) == 2
    except ValueError:
        return False


def _count_names(cfg: odict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in cfg:
        name = _name(row)
        counts[name] = counts.get(name, 0) + 1
    return counts


def leaf_deletes(diff_foo: Callable[..., list[common.DiffItem]]) -> Callable[..., list[common.DiffItem]]:
    """
    MD-CLI deletes a leaf (or a whole leaf-list) by its name only: "delete /configure system location",
    and setting a leaf overwrites its value, so "name old" -> "name new" needs no delete at all.

    After parsing, a leaf ("name value") and a single-key list entry without children ("interface "x" { }")
    look the same. So a childless row is shortened to its name only if this name is unique in the old block:
    deleting by name then removes exactly the same thing in both cases. Otherwise the full row is kept.
    """

    def wrapper(
        old: odict[str, Any], new: odict[str, Any], diff_pre: odict[str, Any], *args: Any, **kwargs: Any
    ) -> list[common.DiffItem]:
        diff = diff_foo(old, new, diff_pre, *args, **kwargs)
        old_names = _count_names(old)
        new_names = _count_names(new)
        new_childless = {_name(row): row for row in new if not new[row]}

        ret = []
        for item in diff:
            row = item.row
            if item.op != Op.REMOVED or old.get(row) or old_names.get(_name(row)) != 1:
                ret.append(item)
                continue
            name = _name(row)
            if name == row.strip():
                ret.append(item)
                continue
            replacement = new_childless.get(name)
            if (
                replacement is not None
                and new_names.get(name) == 1
                and not _is_leaf_list(row)
                and not _is_leaf_list(replacement)
                and _is_name_value(row)
                and _is_name_value(replacement)
            ):
                # leaf value change - the set command overwrites it
                continue
            attrs = dict(item.diff_pre["attrs"], reverse="delete {}")
            diff_pre_match = dict(item.diff_pre, key=(name,), attrs=attrs)
            ret.append(common.DiffItem(item.op, name, item.children, diff_pre_match))
        return ret

    return wrapper


default_diff = leaf_deletes(juniper.default_diff)
ordered_diff = leaf_deletes(juniper.ordered_diff)
