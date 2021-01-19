import string


def is_num_alpha(c):
    return c in string.ascii_letters or c in string.digits

def is_var(s):
    return s[0] in string.ascii_letters and all(is_num_alpha(c) for c in s)

def all_space(s):
    return all(c==' ' for c in s)

def all_num(s):
    return all(c in string.digits for c in s)

# ---------------- Scanner
# 如果是字母数字，则表示 symbol 或者 number
# 如果是 <= => == = + - * /，则表示分隔
# 如果是空格，则表示分隔或者空格
# 如果是 : ，表示新的块出现了
# scan 阶段，把换行和空格都考虑进入，作为一个 token，由 parse 来决定 indent 是否正确
class Scanner:
    def __init__(self, s):
        self.s = s
        self.tokstream = self.rescan(self.scan(s))
        self.token = None

    def next_token(self):
        self.token = next(self.tokstream)
        return self.token

    def scan(self, s):
        delimiter = '~+-*/=<>%'
        parse_delimiter = False
        token = ''
        for c in s:
            if parse_delimiter:                     # 当前正在解析 delimiter
                if c in delimiter:
                    token += c                      # 解析如 <= => += 这样的 token
                else:
                    parse_delimiter = False         # delimiter 解析完毕，返回
                    yield token                          
                    if is_num_alpha(c) or c == ' ':
                        token = c
                    elif c in '()' or c == ':' or c == ',' or c == '\n':
                        yield c
                        token = ''
            else:                                   # 当前没有解析 delimiter
                if c in delimiter:                  # 遇到一个 delimiter
                    yield token                     # 说明当前的 token 解析完毕，返回
                    parse_delimiter = True          # 
                    token = c                       # 解析如 + - * / 这样的 token
                elif is_num_alpha(c):               # 
                    if token and all_space(token):  # 空白解析完成
                        yield token                 # 否则，正在解析数学字母
                        token = ''                  # 
                    token += c                      
                elif c == ' ':
                    if all_space(token):            # parse space
                        token += c
                    else:
                        yield token                 # 原 token 解析完成
                        token = c                   # 开始解析空白
                elif c in '\n(),:':
                    if token:
                        yield token
                        token = ''
                    yield c
        if token:
            yield token

    def rescan(self, tokstream):
        "re-scan to remove useless token and generate start and end mark for every token"
        row = 1
        col_s = 1
        col_e = 0
        newline = False
        for token in tokstream:
            if all_space(token):
                if newline:
                    newline = False
                    col_e = col_s + len(token)
                    yield token, [row, col_s, col_e]
                    col_s = col_e
                else:
                    # only update position
                    col_s = col_s + len(token)
            elif token == '\n':
                newline = True
                col_e = col_s + 1
                yield token, [row, col_s, col_e]
                row += 1
                col_s = 1
            else:
                newline = False
                col_e = col_s + len(token)
                yield token, [row, col_s, col_e]
                col_s = col_e
        yield None, [0, 0, 0]

# ----------------- Ast
class PyExpr: pass

class PyNull(PyExpr):
    def __init__(self):
        super().__init__()
    def __repr__(self):
        return "PyNull"


class PyInt(PyExpr):
    def __init__(self, val):
        super().__init__()
        self.val = val
    def __repr__(self):
        return f"{self.val}"
    def __eq__(self, other):
        return self.val == other.val
    def __add__(self, other):
        return PyInt(self.val + other.val)
    def __sub__(self, other):
        return PyInt(self.val - other.val)
    def __mul__(self, other):
        return PyInt(self.val * other.val)
    def __truediv__(self, other):
        return PyInt(self.val // other.val)


class PyVar(PyExpr):
    def __init__(self, name):
        super().__init__()
        self.name = name
    def __repr__(self):
        return f"PyVar({self.name})"
    def __eq__(self, other):
        return other.name == self.name


class PyCall(PyExpr):
    def __init__(self, fn, args):
        super().__init__()
        self.fn = fn
        self.args = args
    def __repr__(self):
        return f"PyCall({self.fn})"


class PyDefun(PyExpr):

    def __init__(self, name, args, body, env):
        super().__init__()
        self.name = name
        self.args = args
        self.body = body
        self.env = env

    def __call__(self, params):
        assert(len(params) == len(self.args))
        for (name, val) in zip(self.args, params):
            self.env = extend(name, val, self.env)
        # function always have a return value
        res = list(interpret(self.body, self.env))
        return res[-1]

    def __repr__(self):
        return f"PyDefun({self.name})"


class PyOp2(PyExpr):
    def __init__(self, op, e1, e2):
        self.op = op
        self.e1 = e1
        self.e2 = e2
    def __repr__(self):
        return f"({self.op} {self.e1} {self.e2})"


class PyDefvar(PyExpr):
    def __init__(self, var, val):
        super().__init__()
        self.var = var
        self.val = val
    def __repr__(self):
        return f"PyDefvar({self.var}, {self.val})"


# ------------- Parser
def match(scanner, e):
    token, [row, col_s, _] = scanner.token
    assert token == e, f"expect {e} in row {row} column {col_s}"
    scanner.next_token()


def parse_expr(scanner, indent='', simple=False):
    """ parse expr without blank and leave `\n` """
    token, [row, col, _] = scanner.token
    if token == 'def':
        return parse_defun(scanner, indent)
    elif token == '(':
        expr = parse_parent(scanner)
        if simple: return expr
        return parse_op2(expr, scanner)
    elif all_num(token):
        expr = parse_num(scanner)
        if simple: return expr
        return parse_op2(expr, scanner)
    elif is_var(token):
        sym = PyVar(token)
        scanner.next_token()
        if scanner.token[0] is None:  # input end
            return sym
        elif scanner.token[0] == '(': # funcall start
            expr = parse_funcall(sym, scanner)
            if simple: return expr
            return parse_op2(expr, scanner)
        elif scanner.token[0] == ',': # funcall argslist
            return sym
        elif scanner.token[0] == ')': # funcall finish
            return sym
        elif scanner.token[0] == '=': # defvar
            return parse_defvar(sym, scanner)
        elif scanner.token[0] == '\n':
            return sym
        elif scanner.token[0] in '+-*/':
            return parse_op2(sym, scanner)
        else:
            token, [row, col, _] = scanner.token
            raise Exception(f"unrecognize: `{sym.name} {token}` in row {row} col {col} ")
    else:
        raise Exception(f"unrecognize: `{token}` in row {row} col {col} ")

def parse_num(scanner):
    pyint = PyInt(int(scanner.token[0]))
    scanner.next_token()
    return pyint

def parse_var(scanner):
    var = PyVar(scanner.token[0])
    scanner.next_token()
    return var

def parse_defvar(sym, scanner):
    match(scanner, '=')
    expr = parse_expr(scanner)
    return PyDefvar(sym, expr)

def parse_parent(scanner):
    match(scanner, '(')
    expr = parse_expr(scanner)
    match(scanner, ')')
    return expr

precedure = { '+': 20, '-': 20, '*': 40, '/': 40 }
def parse_op2(expr, scanner, expr_prec=0):
    # [op, expr]*
    if not scanner.token[0] or scanner.token[0] not in '+-*/':
        return expr
    op, _ = scanner.token
    op_prec = precedure[op]
    if op_prec < expr_prec:
        return expr
    scanner.next_token()
    next_expr = parse_expr(scanner, simple=True)
    # check if there is another op
    if not scanner.token[0] or scanner.token[0] not in '+-*/':
        return PyOp2(op, expr, next_expr)
    # yes, there is still something to parse
    next_op, _ = scanner.token
    next_op_prec = precedure[next_op]
    if op_prec < next_op_prec:
        next_expr = parse_op2(next_expr, scanner, op_prec+1)
    expr = PyOp2(op, expr, next_expr)
    return parse_op2(expr, scanner, expr_prec)


def parse_defun(scanner, preindent):
    match(scanner, 'def')
    fn, [row, col, _] = scanner.token
    assert is_var(fn), f"`{fn}` in row {row} col {col} is not a valid function name"
    scanner.next_token()
    # parse args
    args = []
    match(scanner, '(')
    while scanner.token[0] != ')':
        token, [row, col, _] = scanner.token
        assert is_var(token), f"bad variable name in row {row} col {col}"
        arg = PyVar(scanner.token[0])
        args.append(arg)
        scanner.next_token()
        if scanner.token[0] == ')': break
        match(scanner, ',')
    match(scanner, ')')
    match(scanner, ':')
    match(scanner, '\n') # this is necessary newline
    while scanner.token[0] == '\n':
        scanner.next_token() # skip extra newline
    # here, parse body
    body = []
    indent, [row, _, col] = scanner.token
    if not all_space(indent) or indent < preindent:
        raise Exception(f"bad indent in row {row}, col {col}")
    while True:
        scanner.next_token()
        if scanner.token[0] == 'return':
            scanner.next_token()
            last_expr = parse_expr(scanner, indent)
            body.append(last_expr)
            break
        # without `return`
        expr = parse_expr(scanner, indent)
        body.append(expr)
        # if expr is a defun, it will leave indent
        # else it will leave \n
        while scanner.token[0] == '\n':
            scanner.next_token()
        next_indent, [row, _, col] = scanner.token
        if next_indent == indent:
            continue
        elif next_indent is None or next_indent < indent or not all_space(next_indent):
            # next_indent is None: mean we reach the eof
            # next indent < indent: mean current block is done
            # next_indent isn't indent at all, mean we reach the symbol of next line
            last_expr = PyNull()
            body.append(last_expr)
            break
        else:
            raise Exception(f"bad indent in row {row}, col {col}")
    # now, fn, args, and body is ready, env will be appended when interpreted
    return PyDefun(PyVar(fn), args, body, PyNull())

def parse_funcall(fn, scanner):
    # fn (???)
    match(scanner, '(')
    args = []
    while scanner.token[0] != ')':
        arg = parse_expr(scanner)
        args.append(arg)
        if scanner.token[0] == ')': break
        match(scanner, ',')
    match(scanner, ')')
    return PyCall(fn, args)

# ------------ env
def empty_env():
    def search(v: str):
        raise Exception(f"variable {v} not found!")
    return search

def extend(saved_var, saved_val, env):
    def search(v: str):
        if v == saved_var:
            return saved_val
        return lookup(env, v)
    return search

def lookup(env, v: str):
    return env(v)

def interpret_helper(expr, env):
    if isinstance(expr, PyVar):
        return lookup(env, expr)
    elif isinstance(expr, (PyInt, PyNull)):
        return expr
    elif isinstance(expr, PyCall):
        fn = lookup(env, expr.fn)
        args = [interpret_helper(arg, env) for arg in expr.args]
        return fn(args)
    elif isinstance(expr, PyOp2):
        e1 = interpret_helper(expr.e1, env)
        e2 = interpret_helper(expr.e2, env)
        if   expr.op == '+': return e1 + e2
        elif expr.op == '-': return e1 - e2
        elif expr.op == '*': return e1 * e2
        elif expr.op == '/': return e1 / e2
        else: raise Exception(f"Unknown operation `{expr.op}`")
    else:
        raise Exception("Invalid Expr")

def interpret(exprs, env):
    for expr in exprs:
        if isinstance(expr, PyDefvar):
            val = interpret_helper(expr.val, env)
            env = extend(expr.var, val, env)
        elif isinstance(expr, PyDefun):
            expr.env = env
            env = extend(expr.name, expr, env)
        else:
            yield interpret_helper(expr, env)

def parse(prog):
    scanner = Scanner(prog)
    scanner.next_token()
    abs_prog = []
    while scanner.token[0] != None:
        while scanner.token[0] == '\n':
            scanner.next_token()
        expr = parse_expr(scanner)
        while scanner.token[0] == '\n':
            scanner.next_token()
        abs_prog.append(expr)
    return abs_prog

def interp_demo(filename):
    with open(filename) as f:
        source = f.read()
    ast = parse(source)
    res = interpret(ast, empty_env())
    for (i, x) in enumerate(res):
        print(f"Out[{i}]: {x}")

if __name__ == '__main__':
    interp_demo('demo.py')
    # interp_demo('error.py')