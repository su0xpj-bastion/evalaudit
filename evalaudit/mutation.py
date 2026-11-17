from __future__ import annotations

# Grader mutation testing.
#
# Take the reference solution, apply ONE small AST mutation (flip a comparison,
# swap +/-, nudge an int constant, ...). A mutant that the grader accepts but
# that EvalPlus's 999-input "plus" suite rejects is a *confirmed* wrong solution
# the grader lets through: we have a concrete input where it disagrees with
# ground truth. Mutants that pass everything are reported as "survived all" and
# are NOT counted as wrong (they may be semantically equivalent).

import ast
import copy
import random

COMPARE_SWAPS = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
}
BINOP_SWAPS = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.FloorDiv,
    ast.FloorDiv: ast.Mult,
    ast.Mod: ast.FloorDiv,
}
BOOLOP_SWAPS = {ast.And: ast.Or, ast.Or: ast.And}


def _sites(tree: ast.AST, entry_point: str) -> list[tuple[int, str]]:
    """Enumerate (node_index, operator) mutation sites in walk order, limited to
    the body of `entry_point` so helpers the tests also call stay intact."""
    target = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == entry_point),
        None,
    )
    if target is None:
        return []
    inside = {id(n) for n in ast.walk(target)}
    docstring = ast.get_docstring(target, clean=False) is not None and target.body[0]
    skip = {id(n) for n in ast.walk(docstring)} if docstring else set()
    sites: list[tuple[int, str]] = []
    for idx, node in enumerate(ast.walk(tree)):
        if id(node) not in inside or id(node) in skip:
            continue
        if isinstance(node, ast.Compare):
            for k, op in enumerate(node.ops):
                if type(op) in COMPARE_SWAPS:
                    sites.append((idx, f"cmp:{k}"))
        elif isinstance(node, (ast.BinOp, ast.AugAssign)) and type(node.op) in BINOP_SWAPS:
            sites.append((idx, "binop"))
        elif isinstance(node, ast.BoolOp) and type(node.op) in BOOLOP_SWAPS:
            sites.append((idx, "boolop"))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            sites.append((idx, "drop_not"))
        elif (
            isinstance(node, ast.Constant)
            and type(node.value) is int
        ):
            sites.append((idx, "int+1"))
            sites.append((idx, "int-1"))
        elif isinstance(node, ast.Constant) and type(node.value) is bool:
            sites.append((idx, "bool"))
    return sites


def _apply(tree: ast.AST, site: tuple[int, str]) -> ast.AST:
    tree = copy.deepcopy(tree)
    idx, kind = site
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    node = next(n for i, n in enumerate(ast.walk(tree)) if i == idx)
    if kind.startswith("cmp:"):
        k = int(kind.split(":")[1])
        node.ops[k] = COMPARE_SWAPS[type(node.ops[k])]()
    elif kind == "binop":
        node.op = BINOP_SWAPS[type(node.op)]()
    elif kind == "boolop":
        node.op = BOOLOP_SWAPS[type(node.op)]()
    elif kind == "drop_not":
        parent = parents[id(node)]
        for field, value in ast.iter_fields(parent):
            if value is node:
                setattr(parent, field, node.operand)
            elif isinstance(value, list):
                for j, item in enumerate(value):
                    if item is node:
                        value[j] = node.operand
    elif kind == "int+1":
        node.value += 1
    elif kind == "int-1":
        node.value -= 1
    elif kind == "bool":
        node.value = not node.value
    return tree


def mutants(source: str, entry_point: str, max_mutants: int = 25, seed: str = "") -> list[tuple[str, str]]:
    """Return up to `max_mutants` distinct (description, mutant_source) pairs."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    baseline = ast.unparse(tree)
    sites = _sites(tree, entry_point)
    random.Random(seed).shuffle(sites)
    out: list[tuple[str, str]] = []
    seen = {baseline}
    for site in sites:
        try:
            mutated = _apply(tree, site)
            src = ast.unparse(ast.fix_missing_locations(mutated))
            compile(src, "<mutant>", "exec")
        except Exception:  # noqa: BLE001 - invalid mutant, skip
            continue
        if src in seen:
            continue
        seen.add(src)
        out.append((f"{site[1]}@{site[0]}", src))
        if len(out) >= max_mutants:
            break
    return out
