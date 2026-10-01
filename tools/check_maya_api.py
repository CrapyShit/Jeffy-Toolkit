#!/usr/bin/env python
"""Static validation of Maya API usage against the ``maya-stubs`` package.

Maya is not available on CI machines, so this script parses the source code
of the toolkit and checks every:

* ``cmds.<command>(...)`` call - the command must exist and every keyword
  flag must be a valid (long) flag name of that command.
* ``om.<Name>`` / ``oma.<Name>`` reference - the class/function must exist in
  ``maya.api.OpenMaya`` / ``maya.api.OpenMayaAnim``.
* ``om.<Class>.<member>`` reference - the member must exist on the class
  (or one of its bases).

Usage::

    pip install maya-stubs
    python tools/check_maya_api.py            # checks scripts/jeffy
    python tools/check_maya_api.py path/to/src --stubs path/to/maya-stubs

Exit code is 1 when problems were found.
"""

from __future__ import annotations

import argparse
import ast
import os
import site
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SOURCE = os.path.join(ROOT, "scripts", "jeffy")

API_MODULES = {
    "maya.api.OpenMaya": "api/OpenMaya.pyi",
    "maya.api.OpenMayaAnim": "api/OpenMayaAnim.pyi",
    "maya.api.OpenMayaUI": "api/OpenMayaUI.pyi",
}


def find_stubs():
    candidates = []
    try:
        candidates.extend(site.getsitepackages())
    except AttributeError:  # pragma: no cover - virtualenv quirks
        pass
    candidates.append(site.getusersitepackages())
    candidates.extend(sys.path)
    for base in candidates:
        path = os.path.join(base, "maya-stubs")
        if os.path.isdir(path):
            return path
    return None


# ---------------------------------------------------------------------------
# Stub parsing
# ---------------------------------------------------------------------------
def parse_cmds(path):
    """Return ``{command: set(flags) or None}`` (None = accepts anything)."""
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    commands = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        args = node.args
        if args.kwarg is not None:
            commands[node.name] = None
            continue
        names = {a.arg for a in args.kwonlyargs}
        names.update(a.arg for a in args.args)
        commands[node.name] = names
    return commands


def parse_api(path):
    """Return ``(module_names, classes)`` where classes maps name -> members."""
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    module_names = set()
    classes = {}
    bases = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            module_names.add(node.name)
            members = set()
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    members.add(item.name)
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    members.add(item.target.id)
                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            members.add(target.id)
                elif isinstance(item, ast.ClassDef):
                    members.add(item.name)
            classes[node.name] = members
            bases[node.name] = [b.id for b in node.bases if isinstance(b, ast.Name)]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module_names.add(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            module_names.add(node.target.id)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    module_names.add(target.id)

    def resolve(name, seen=None):
        seen = seen or set()
        if name in seen or name not in classes:
            return set()
        seen.add(name)
        result = set(classes[name])
        for base in bases.get(name, []):
            result |= resolve(base, seen)
        return result

    return module_names, {name: resolve(name) for name in classes}


# ---------------------------------------------------------------------------
# Source scanning
# ---------------------------------------------------------------------------
class Checker(ast.NodeVisitor):
    def __init__(self, filename, commands, api):
        self.filename = filename
        self.commands = commands
        self.api = api
        self.cmds_aliases = set()
        self.api_aliases = {}
        self.errors = []

    # imports ---------------------------------------------------------------
    def visit_Import(self, node):
        for alias in node.names:
            if alias.name == "maya.cmds" and alias.asname:
                self.cmds_aliases.add(alias.asname)
            if alias.name in self.api and alias.asname:
                self.api_aliases[alias.asname] = alias.name

    def visit_ImportFrom(self, node):
        if node.module == "maya":
            for alias in node.names:
                if alias.name == "cmds":
                    self.cmds_aliases.add(alias.asname or "cmds")
        if node.module == "maya.api":
            for alias in node.names:
                full = "maya.api." + alias.name
                if full in self.api:
                    self.api_aliases[alias.asname or alias.name] = full

    # usage -----------------------------------------------------------------
    def _error(self, node, message):
        self.errors.append("%s:%d: %s" % (self.filename, node.lineno, message))

    def visit_Call(self, node):
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in self.cmds_aliases
        ):
            name = func.attr
            if name not in self.commands:
                self._error(node, "unknown command cmds.%s" % name)
            else:
                flags = self.commands[name]
                if flags is not None:
                    for keyword in node.keywords:
                        if keyword.arg is None:
                            continue  # **kwargs expansion - cannot check
                        if keyword.arg not in flags:
                            self._error(
                                node,
                                "cmds.%s has no flag '%s'" % (name, keyword.arg),
                            )
        self.generic_visit(node)

    def visit_Attribute(self, node):
        value = node.value
        # om.Name
        if isinstance(value, ast.Name):
            if value.id in self.cmds_aliases and node.attr not in self.commands:
                self._error(node, "unknown command cmds.%s" % node.attr)
            module = self.api_aliases.get(value.id)
            if module:
                names, _classes = self.api[module]
                if node.attr not in names:
                    self._error(node, "%s has no attribute '%s'" % (module, node.attr))
        # om.Class.member
        if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
            module = self.api_aliases.get(value.value.id)
            if module:
                _names, classes = self.api[module]
                members = classes.get(value.attr)
                if members is not None and node.attr not in members:
                    self._error(
                        node,
                        "%s.%s has no member '%s'" % (module, value.attr, node.attr),
                    )
        self.generic_visit(node)


def iter_python_files(path):
    if os.path.isfile(path):
        yield path
        return
    for root, _dirs, files in os.walk(path):
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(root, name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("paths", nargs="*", default=[DEFAULT_SOURCE])
    parser.add_argument("--stubs", default=None, help="path to the maya-stubs folder")
    args = parser.parse_args(argv)

    stubs = args.stubs or find_stubs()
    if not stubs:
        print("maya-stubs not found - install it with 'pip install maya-stubs'")
        return 2

    commands = parse_cmds(os.path.join(stubs, "cmds", "__init__.pyi"))
    api = {}
    for module, rel in API_MODULES.items():
        path = os.path.join(stubs, rel)
        if os.path.isfile(path):
            api[module] = parse_api(path)

    errors = []
    count = 0
    for base in args.paths:
        for filename in iter_python_files(base):
            count += 1
            with open(filename, encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), filename)
            checker = Checker(os.path.relpath(filename, ROOT), commands, api)
            checker.visit(tree)
            errors.extend(checker.errors)

    for error in errors:
        print(error)
    print("checked %d files, %d problem(s)" % (count, len(errors)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
