"""Turn math expressions into utility node networks (no expression nodes!).

Expression nodes are slow and do not evaluate in parallel. This module parses
a small math language and builds the equivalent network of utility nodes::

    from jeffy.core import expression
    expression.build("L_arm_JNT.sx = L_arm_CTL.stretch * 0.5 + 1")
    expression.build('''
        blend_LOC.ty = clamp(ctl.ty, 0, 10) / 10;
        blend_LOC.tx = ctl.flag > 0.5 ? ctl.tx : -ctl.tx
    ''')

Grammar
-------
* numbers, plugs (``node.attr``, ``node.attr[0]``, namespaces allowed),
  constants ``pi`` and ``e``
* operators ``+ - * / ^`` (``^`` = power, right associative), unary ``-``,
  parentheses
* comparisons ``== != > >= < <=`` - only inside a ternary ``a > b ? x : y``
* functions: ``clamp(x, lo, hi)``, ``min(a, b)``, ``max(a, b)``, ``abs(x)``,
  ``sqrt(x)``, ``pow(a, b)``, ``lerp(a, b, t)``, ``reverse(x)``,
  ``remap(x, in_lo, in_hi, out_lo, out_hi)``, ``sin(deg)``, ``cos(deg)``,
  ``distance(nodeA, nodeB)``
* statements: ``target.attr = expression`` separated by ``;`` or new lines.

Constant sub-expressions are folded at build time, so ``ctl.tx * (2 * 3)``
creates a single multiply node.
"""

import math
import re

# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------
_TOKEN_SPEC = (
    ("NUMBER", r"\d+\.\d*(?:[eE][-+]?\d+)?|\.\d+(?:[eE][-+]?\d+)?|\d+(?:[eE][-+]?\d+)?"),
    ("PLUG", r"[A-Za-z_|:][\w|:]*(?:\.[A-Za-z_]\w*(?:\[\d+\])?)+"),
    ("NAME", r"[A-Za-z_][\w|:]*"),
    ("OP", r"==|!=|>=|<=|[-+*/^(),?:<>=;]"),
    ("NEWLINE", r"\n"),
    ("SKIP", r"[ \t\r]+"),
    ("MISMATCH", r"."),
)
_TOKEN_RE = re.compile("|".join("(?P<%s>%s)" % pair for pair in _TOKEN_SPEC))

CONSTANTS = {"pi": math.pi, "e": math.e}
COMPARISONS = ("==", "!=", ">", ">=", "<", "<=")
FUNCTIONS = {
    "clamp": 3,
    "min": 2,
    "max": 2,
    "abs": 1,
    "sqrt": 1,
    "pow": 2,
    "lerp": 3,
    "reverse": 1,
    "remap": 5,
    "sin": 1,
    "cos": 1,
    "distance": 2,
}


class ExpressionError(ValueError):
    pass


class Token(object):
    __slots__ = ("kind", "value", "position")

    def __init__(self, kind, value, position):
        self.kind = kind
        self.value = value
        self.position = position

    def __repr__(self):
        return "Token(%s, %r)" % (self.kind, self.value)


def tokenize(text):
    tokens = []
    for match in _TOKEN_RE.finditer(text):
        kind = match.lastgroup
        value = match.group()
        if kind == "SKIP":
            continue
        if kind == "MISMATCH":
            raise ExpressionError("Unexpected character %r at %d" % (value, match.start()))
        if kind == "NEWLINE":
            kind, value = "OP", ";"
        tokens.append(Token(kind, value, match.start()))
    tokens.append(Token("EOF", None, len(text)))
    return tokens


# ---------------------------------------------------------------------------
# Parser (precedence climbing) -> AST of tuples
#   ("num", value) ("plug", "n.a") ("name", "node") ("neg", expr)
#   ("bin", op, left, right) ("cmp", op, left, right)
#   ("ternary", cmp, a, b) ("call", fname, [args])
#   ("assign", "n.a", expr)
# ---------------------------------------------------------------------------
_BINARY_PRECEDENCE = {"+": 10, "-": 10, "*": 20, "/": 20, "^": 30}


class Parser(object):
    def __init__(self, text):
        self.tokens = tokenize(text)
        self.index = 0

    @property
    def current(self):
        return self.tokens[self.index]

    def advance(self):
        token = self.tokens[self.index]
        self.index += 1
        return token

    def expect(self, value):
        token = self.advance()
        if token.value != value:
            raise ExpressionError("Expected %r at %d, got %r" % (value, token.position, token.value))
        return token

    # statements ------------------------------------------------------------
    def parse_program(self):
        statements = []
        while self.current.kind != "EOF":
            if self.current.value == ";":
                self.advance()
                continue
            statements.append(self.parse_statement())
        return statements

    def parse_statement(self):
        target = self.advance()
        if target.kind != "PLUG":
            raise ExpressionError("Statement must start with a target plug (node.attr), got %r" % target.value)
        self.expect("=")
        expr = self.parse_expression()
        if self.current.kind != "EOF" and self.current.value != ";":
            raise ExpressionError("Unexpected %r at %d" % (self.current.value, self.current.position))
        return ("assign", target.value, expr)

    # expressions -----------------------------------------------------------
    def parse_expression(self):
        condition = self.parse_comparison()
        if self.current.value == "?":
            if condition[0] != "cmp":
                raise ExpressionError("Ternary condition must be a comparison")
            self.advance()
            when_true = self.parse_expression()
            self.expect(":")
            when_false = self.parse_expression()
            return ("ternary", condition, when_true, when_false)
        if condition[0] == "cmp":
            raise ExpressionError("Comparisons are only allowed as ternary conditions")
        return condition

    def parse_comparison(self):
        left = self.parse_binary(0)
        if self.current.value in COMPARISONS:
            op = self.advance().value
            right = self.parse_binary(0)
            return ("cmp", op, left, right)
        return left

    def parse_binary(self, min_precedence):
        left = self.parse_unary()
        while True:
            op = self.current.value
            precedence = _BINARY_PRECEDENCE.get(op) if self.current.kind == "OP" else None
            if precedence is None or precedence < min_precedence:
                break
            self.advance()
            next_min = precedence if op == "^" else precedence + 1
            right = self.parse_binary(next_min)
            left = ("bin", op, left, right)
        return left

    def parse_unary(self):
        if self.current.value == "-":
            self.advance()
            return ("neg", self.parse_unary())
        if self.current.value == "+":
            self.advance()
            return self.parse_unary()
        return self.parse_primary()

    def parse_primary(self):
        token = self.advance()
        if token.kind == "NUMBER":
            return ("num", float(token.value))
        if token.kind == "PLUG":
            return ("plug", token.value)
        if token.kind == "NAME":
            if self.current.value == "(":
                return self.parse_call(token)
            if token.value in CONSTANTS:
                return ("num", CONSTANTS[token.value])
            return ("name", token.value)
        if token.value == "(":
            expr = self.parse_expression()
            self.expect(")")
            return expr
        raise ExpressionError("Unexpected %r at %d" % (token.value, token.position))

    def parse_call(self, name_token):
        name = name_token.value
        if name not in FUNCTIONS:
            raise ExpressionError("Unknown function %r" % name)
        self.expect("(")
        args = []
        if self.current.value != ")":
            while True:
                args.append(self.parse_expression())
                if self.current.value == ",":
                    self.advance()
                    continue
                break
        self.expect(")")
        if len(args) != FUNCTIONS[name]:
            raise ExpressionError("%s() takes %d arguments (%d given)" % (name, FUNCTIONS[name], len(args)))
        return ("call", name, args)


def parse(text):
    """Parse a program and return a list of ``("assign", plug, ast)``."""
    return Parser(text).parse_program()


def parse_expression(text):
    parser = Parser(text)
    expr = parser.parse_expression()
    if parser.current.kind != "EOF":
        raise ExpressionError("Unexpected %r" % parser.current.value)
    return expr


# ---------------------------------------------------------------------------
# Evaluation / building
# ---------------------------------------------------------------------------
def _compare(op, a, b):
    return {
        "==": a == b,
        "!=": a != b,
        ">": a > b,
        ">=": a >= b,
        "<": a < b,
        "<=": a <= b,
    }[op]


def _fold(fname, args):
    """Compute a function on constant arguments."""
    if fname == "clamp":
        return max(args[1], min(args[2], args[0]))
    if fname == "min":
        return min(args)
    if fname == "max":
        return max(args)
    if fname == "abs":
        return abs(args[0])
    if fname == "sqrt":
        return math.sqrt(args[0])
    if fname == "pow":
        return math.pow(args[0], args[1])
    if fname == "lerp":
        return args[0] + (args[1] - args[0]) * args[2]
    if fname == "reverse":
        return 1.0 - args[0]
    if fname == "remap":
        value, lo, hi, out_lo, out_hi = args
        t = 0.0 if hi == lo else max(0.0, min(1.0, (value - lo) / (hi - lo)))
        return out_lo + (out_hi - out_lo) * t
    if fname == "sin":
        return math.sin(math.radians(args[0]))
    if fname == "cos":
        return math.cos(math.radians(args[0]))
    raise ExpressionError("Cannot fold %s" % fname)


_BINARY_FOLD = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "/": lambda a, b: a / b,
    "^": lambda a, b: math.pow(a, b),
}


class Builder(object):
    """Walks the AST. Constants are folded; everything else is delegated to
    a *backend* exposing the :mod:`jeffy.core.nodes` API (``multiply``,
    ``add``, ``subtract``, ``divide``, ``power``, ``negate``, ``clamp``,
    ``minimum``, ``maximum``, ``absolute``, ``blend``, ``reverse``, ``remap``,
    ``condition``, ``sin_cos``, ``distance_between`` and ``connect``).
    """

    def __init__(self, backend):
        self.backend = backend

    def build(self, expr):
        kind = expr[0]
        if kind == "num":
            return expr[1]
        if kind == "plug":
            return expr[1]
        if kind == "name":
            raise ExpressionError("Bare name %r is only valid as distance() argument" % expr[1])
        if kind == "neg":
            value = self.build(expr[1])
            return -value if isinstance(value, float) else self.backend.negate(value)
        if kind == "bin":
            return self._binary(expr[1], self.build(expr[2]), self.build(expr[3]))
        if kind == "ternary":
            _cmp, op, left, right = expr[1]
            left_value, right_value = self.build(left), self.build(right)
            when_true, when_false = self.build(expr[2]), self.build(expr[3])
            if isinstance(left_value, float) and isinstance(right_value, float):
                return when_true if _compare(op, left_value, right_value) else when_false
            return self.backend.condition(left_value, op, right_value, when_true, when_false)
        if kind == "call":
            return self._call(expr[1], expr[2])
        raise ExpressionError("Unknown node %r" % (kind,))

    def _binary(self, op, a, b):
        a_const, b_const = isinstance(a, float), isinstance(b, float)
        if a_const and b_const:
            return _BINARY_FOLD[op](a, b)
        backend = self.backend
        if op == "+":
            if a_const and a == 0.0:
                return b
            if b_const and b == 0.0:
                return a
            return backend.add(a, b)
        if op == "-":
            if b_const and b == 0.0:
                return a
            return backend.subtract(a, b)
        if op == "*":
            if a_const and a == 1.0:
                return b
            if b_const and b == 1.0:
                return a
            return backend.multiply(a, b)
        if op == "/":
            if b_const:
                if b == 0.0:
                    raise ExpressionError("Division by zero")
                return a if b == 1.0 else backend.multiply(a, 1.0 / b)
            return backend.divide(a, b)
        if op == "^":
            if b_const and b == 1.0:
                return a
            return backend.power(a, b)
        raise ExpressionError("Unknown operator %r" % op)

    def _call(self, fname, arg_exprs):
        if fname == "distance":
            names = []
            for arg in arg_exprs:
                if arg[0] not in ("name", "plug"):
                    raise ExpressionError("distance() expects node names")
                names.append(arg[1].split(".")[0])
            return self.backend.distance_between(names[0], names[1])
        args = [self.build(arg) for arg in arg_exprs]
        if all(isinstance(a, float) for a in args):
            return _fold(fname, args)
        backend = self.backend
        if fname == "clamp":
            return backend.clamp(args[0], args[1], args[2])
        if fname == "min":
            return backend.minimum(args[0], args[1])
        if fname == "max":
            return backend.maximum(args[0], args[1])
        if fname == "abs":
            return backend.absolute(args[0])
        if fname == "sqrt":
            return backend.power(args[0], 0.5)
        if fname == "pow":
            return backend.power(args[0], args[1])
        if fname == "lerp":
            return backend.blend(args[0], args[1], args[2])
        if fname == "reverse":
            return backend.reverse(args[0])
        if fname == "remap":
            return backend.remap(*args)
        if fname in ("sin", "cos"):
            sin_plug, cos_plug = backend.sin_cos(args[0])
            return sin_plug if fname == "sin" else cos_plug
        raise ExpressionError("Unknown function %r" % fname)

    def run(self, program):
        """Build every statement of a parsed program; returns target plugs."""
        targets = []
        for _kind, target, expr in program:
            value = self.build(expr)
            self.backend.connect(value, target)
            targets.append(target)
        return targets


def build(text, backend=None):
    """Parse ``text`` and build it in the scene. Returns the driven plugs."""
    if backend is None:
        from jeffy.core import nodes as backend
    return Builder(backend).run(parse(text))
