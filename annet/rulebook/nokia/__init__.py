from collections import OrderedDict as odict
from collections.abc import Callable
from typing import Any

from annet.annlib.types import Op
from annet.rulebook import common, juniper


def _name(row: str) -> str:
    return row.split(maxsplit=1)[0]


def _count_names(cfg: odict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in cfg:
        name = _name(row)
        counts[name] = counts.get(name, 0) + 1
    return counts


def leaf_deletes(diff_foo: Callable[..., list[common.DiffItem]]) -> Callable[..., list[common.DiffItem]]:
    """
    MD-CLI deletes a leaf (or a whole leaf-list) by its name only: "delete /configure system location".
    A leaf value change "name old" -> "name new" is shown as removed/added rows (like "no hostname"/"hostname"
    on other vendors) and becomes "delete <leaf>" followed by the set, both applied in one commit.

    After parsing, a leaf ("name value") and a single-key list entry without children ("interface "x" { }")
    look the same. So a childless row is shortened to its name only if this name is unique in the old block:
    deleting by name then removes exactly the same thing in both cases. Otherwise the full row is kept.
    """

    def wrapper(
        old: odict[str, Any], new: odict[str, Any], diff_pre: odict[str, Any], *args: Any, **kwargs: Any
    ) -> list[common.DiffItem]:
        diff = diff_foo(old, new, diff_pre, *args, **kwargs)
        old_names = _count_names(old)

        ret = []
        deletes: dict[str, common.DiffItem] = {}
        for item in diff:
            row = item.row
            if item.op != Op.REMOVED or old.get(row) or old_names.get(_name(row)) != 1:
                ret.append(item)
                continue
            name = _name(row)
            if name == row.strip():
                ret.append(item)
                continue
            attrs = dict(item.diff_pre["attrs"], reverse="delete {}")
            # own pseudo-rule: make_pre groups by raw_rule and takes attrs from the first item,
            # so the added row with the new value would otherwise impose the rule's reverse
            diff_pre_match = dict(item.diff_pre, raw_rule=name, rule=name, key=(name,), attrs=attrs)
            deletes[name] = common.DiffItem(item.op, row, item.children, diff_pre_match)

        # show the old value right before the new one: "- name old", "+ name new"
        ordered = []
        for item in ret:
            if item.op == Op.ADDED and (delete := deletes.pop(_name(item.row), None)):
                ordered.append(delete)
            ordered.append(item)
        return [*deletes.values(), *ordered]

    return wrapper


default_diff = leaf_deletes(juniper.default_diff)
ordered_diff = leaf_deletes(juniper.ordered_diff)
