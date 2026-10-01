import math

import pytest

from jeffy.core import expression as ex


class RecordingBackend(object):
    """Fake node backend: returns readable strings and records calls."""

    def __init__(self):
        self.calls = []
        self.connections = []

    def _op(self, name, *args):
        self.calls.append((name,) + args)
        return "%s(%s)" % (name, ", ".join(str(a) for a in args))

    def __getattr__(self, name):
        if name in ("multiply", "add", "subtract", "divide", "power", "negate", "clamp", "minimum", "maximum",
                    "absolute", "blend", "reverse", "remap", "distance_between"):
            return lambda *args: self._op(name, *args)
        if name == "condition":
            return lambda a, op, b, t, f: self._op("condition", a, op, b, t, f)
        if name == "sin_cos":
            return lambda value: ("sin(%s)" % value, "cos(%s)" % value)
        raise AttributeError(name)

    def connect(self, value, target):
        self.connections.append((value, target))


def build(text):
    backend = RecordingBackend()
    targets = ex.build(text, backend=backend)
    return backend, targets


def test_tokenize_plugs():
    tokens = ex.tokenize("ns:node.translateX * 2 + n.wm[0]")
    kinds = [t.kind for t in tokens]
    assert kinds == ["PLUG", "OP", "NUMBER", "OP", "PLUG", "EOF"]


def test_precedence():
    backend, _ = build("out.tx = a.tx + b.tx * 2")
    assert backend.calls == [("multiply", "b.tx", 2.0), ("add", "a.tx", "multiply(b.tx, 2.0)")]


def test_power_right_associative_and_unary():
    expr = ex.parse_expression("2 ^ 3 ^ 2")
    assert ex.Builder(RecordingBackend()).build(expr) == 512.0
    # unary minus binds tighter than ^ (documented behaviour)
    assert ex.Builder(RecordingBackend()).build(ex.parse_expression("-2 ^ 2")) == 4.0


def test_constant_folding():
    backend, _ = build("out.tx = a.tx * (2 * 3) + 0")
    assert backend.calls == [("multiply", "a.tx", 6.0)]
    assert backend.connections == [("multiply(a.tx, 6.0)", "out.tx")]


def test_identity_simplifications():
    backend, _ = build("out.tx = a.tx * 1 / 1 - 0")
    assert backend.calls == []
    assert backend.connections == [("a.tx", "out.tx")]


def test_division_by_constant_becomes_multiply():
    backend, _ = build("out.tx = a.tx / 4")
    assert backend.calls == [("multiply", "a.tx", 0.25)]


def test_functions_and_constants():
    backend, _ = build("out.tx = clamp(a.tx, 0, pi)")
    assert backend.calls == [("clamp", "a.tx", 0.0, math.pi)]
    backend, _ = build("out.tx = lerp(a.tx, b.tx, c.w)")
    assert backend.calls[0][0] == "blend"
    backend, _ = build("out.tx = sin(a.rx)")
    assert backend.connections == [("sin(a.rx)", "out.tx")]
    backend, _ = build("out.tx = distance(locA, locB)")
    assert backend.calls == [("distance_between", "locA", "locB")]


def test_folded_functions():
    _backend, _ = build("out.tx = max(1, 2) + abs(-3) + remap(5, 0, 10, 0, 1)")
    assert _backend.connections == [(5.5, "out.tx")]


def test_ternary():
    backend, _ = build("out.tx = a.flag > 0.5 ? a.tx : -a.tx")
    assert backend.calls[-1][0] == "condition"
    assert backend.calls[-1][2] == ">"
    backend, _ = build("out.tx = 1 < 2 ? 10 : 20")
    assert backend.connections == [(10.0, "out.tx")]


def test_multiple_statements():
    _backend, targets = build("a.tx = b.tx; a.ty = b.ty\n a.tz = 1")
    assert targets == ["a.tx", "a.ty", "a.tz"]


@pytest.mark.parametrize("text", [
    "a.tx = ",
    "tx = 1",
    "a.tx = b.tx > 1",
    "a.tx = unknown(1)",
    "a.tx = clamp(1, 2)",
    "a.tx = (1 + 2",
    "a.tx = 1 / 0",
    "a.tx = 1 $ 2",
    "a.tx = bare + 1",
])
def test_errors(text):
    with pytest.raises(ex.ExpressionError):
        build(text)
