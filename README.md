# 用 Python 写一个 Python

本教程使用 Python 实现了一个小型 Python 解释器。它能够解释执行以下代码

```py
def manda(m, a):
    def sky(s):
        return s + 4
    def sea(s):
        return s * 2
    return m + a - sea(m) * sky(a)

x = 4
y = 2

manda(x, y)
```

给出缩进不当的代码，如下面的 `d = c + 1`
```py
b = 10
def sky(a):
    c = b * 2
      d = c + 1
    return d * a

sky(b)
```
标准 Python 的错误提示为
```sh
File "error.py", line 4
    d = c + 1
    ^
IndentationError: unexpected indent
```

本项目的错误提示为
```rust
Exception: bad indent in row 4, col 7
```

很不错吧？只要多写几行代码，就可以复现标准 Python 的错误提示了 ：）

总代码量

    psp.py              : 345
    test_psp.py         : 113
    ----------------------------
    total               : 458


不到 400 行的代码里可塞不下很多东西呢。鉴于之前的 EoC 系列介绍了许多解释器和编译器的内容，为了与之互补，这次教程的重点在于编译器的前端，也即 lexer 和 parser。解释器方面支持以下内容：

+ 数据类型：整型
+ 词法作用域的函数，支持嵌套
+ 变量定义
+ 二元操作符（+-*/）及小括号

如你所见，这个项目还有广阔的天地可以拓展呢！比如 `if`，`for`，布尔运算等等……

我将详细解释以下内容

+ 一个简单而不失强大的 scanner (lexer)
+ Python 缩进代码块的解析
+ message passing 范式的环境表示
+ 基于优先级的二元运算符的解析
+ Python 函数的解释运行

如果你在玩的时候发现解释错误，很可能是一些边边角角没有被覆盖，比如不支持写成一行代码块`def my(f): return f`，相信你可以完善它！

### 1. scanner

scan 阶段分两步走：第一步，先把所有类型的 token 都保留下来，包括所有的空格和换行。其中，需要特别注意的是运算符的解析，比如

```py
a = fn(x+b, c*d)
```

注意到`+`、`*`两边不存在空格，所以不能依赖空格来分 token，而且这样的运算符可以包含多个字符，如`+=`，`<=`。实际上，这些运算符分开了多个操作数，所以我称之为`delimiter`，用一个标记`parse_delimiter`来指导解析。

第二步，得到基础的 token 流之后，我们只保留每行第一个空白区域，因为 Python 的缩进只关心第一个。同时，计算出每一个 token 的位置，即行与列。

让我们先写`scan`，建立一个叫`psp.py`的文件，写入

```py
def scan(s):
    delimiter = '~+-*/=<>%'     # 支持的符号
    parse_delimiter = False     # 标识是否正在解析 delimiter
    token = ''                  # 初始 token
```
现在我们遍历字符串 s，以下是 for 语句的主体

```py
    for c in s:
        if parse_delimiter:                 # 当前正在解析 delimiter
            if c in delimiter               # 遇到 c 仍然是 delimiter，加到原来的 token 上
                token += c                  # 可以解析如 <= => += 这样的 token
            else:                           # 遇到 c 不是 delimiter
                parse_delimiter = False     # 说明 delimiter 解析完毕，返回
                yield token
                # NOTE: 代码块1...
        else:                               # 当前没有解析 delimiter
            if c in delimiter:              # 遇到一个 delimiter
                yield token                 # 说明当前的 token 解析完毕，返回
                parse_delimiter = True      # 
                token = c                   # 可以解析如 + - * / 这样的 token
            else:
                # NOTE: 代码块2...
```

我们现在已经搞定 delimiter 的解析了，现在看看其他的符号。我们先写`代码块1`的情况。（注意，我忽略了代码的缩进）

```py
if is_num_alpha(c) or c == ' ':
    token = c
elif c in '()' or c == ':' or c == ',' or c == '\n':
    yield c
    token = ''
```

因为字母和空格都可以累加（即多个写在一起），所以我们先把`c`存到`token`中，以等待后续相同的字符。其他如括号，冒号，逗号，换行，不能叠加，所以必须返回，同时将 token 清空。

这里的`is_num_alpha`定义

```py
import string

def is_num_alpha(c):
    return c in string.ascii_letters or c in string.digits
```

现在我们看看代码块2，先看数字字母的解析

```py
if is_num_alpha(c):                
    if token and all_space(token):  # token 是空白，而 c 是数字或者字母
        yield token                 # 说明空白解析完成，返回
        token = ''                  # 
    token += c                      # 否则，正在解析数字字母，需要累加
```

然后是空白的解析

```py
elif c == ' ':
    if all_space(token):    # parse space
        token += c
    else:
        yield token         # 原 token 解析完成
        token = c           # 开始解析空白
```

括号、换行、冒号、逗号。这四个家伙又组团了。

```py
elif c in '\n():,':
    if token != '':         # 只要当前不为空，即视为 token 解析完成
        yield token
        token = ''
    yield c                 # 本身作为独立符号返回
```

这就是代码块2的全部了，我们忽略了其余的符号。

最后加一句

```py
def scan(s):
    # ..
    if token:
        yield token
```

确保最后一个 token 也被返回了。这是函数 `scan`。我们用到了一个简单的函数`all_space`。

```py
def all_space(s):
    return all(c==' ' for c in s)
```

接下来，我们做第二步，即保留必须的 indent（缩进），忽略其他空白符，并计算每个 token 的位置信息。我们将之命为`rescan`

> 虽然叫`rescan`，但`scan`返回了一个生成器，`rescan`直接对着生成器的每个输出操作，因此，我们只遍历了一次`s`而已。

我们的思路是这样子的：对于每个 token

+ 如果是空白符，检测是否为行首；如果是，则计算它的行列信息并一起返回，如果不是，则忽略，但仍更新列信息
+ 如果是换行符，设行首标志为真，连同它的行列信息一起返回，同时更新行列信息
+ 如果是其他符号，只计算行列信息并一起返回

```py
def rescan(self, tokstream):
    "re-scan to remove useless token and generate start and end mark for every token"
    row = 1
    col_s = 1
    col_e = 0
    newline = False
    for token in tokstream:
        if all_space(token):                                # 空白符，且处于行首
            if newline:
                newline = False     
                col_e = col_s + len(token)
                yield token, [row, col_s, col_e]            # 这里返回了行首的缩进
                col_s = col_e
            else:                                           # 如果不是行首的空白符，就忽略掉
                col_s = col_s + len(token)                  # 但仍要更新列起始坐标
        elif token == '\n':                                 
            newline = True
            col_e = col_s + 1                               # 换行符，需要更新行坐标和列坐标
            yield token, [row, col_s, col_e]
            row += 1
            col_s = 1
        else:                                               # 其他符号，更新坐标即可
            newline = False
            col_e = col_s + len(token)
            yield token, [row, col_s, col_e]
            col_s = col_e
    yield None, [0, 0, 0]
```

最后，当 tokenstream 结束了，我返回 None 作为标志。

这就是了！

因为在后文，我采用的是递归下降的方法来解析，需要缓存当前的一个 token，所以我用一个类包装起上面俩函数。定义如下：

```py
class Scanner:
    def __init__(self, s):
        self.s = s
        self.tokstream = self.rescan(self.scan(s))
        self.token = None

    def next_token(self):
        self.token = next(self.tokstream)
        return self.token
    
    def scan(self, s):
        # ..

    def rescan(self, tokstream):
        # ..
```

这里，`token` 成为一个缓存！现在测试一下吧！

建一个叫`test_psp.py`的文件，写入

```py
from psp import Scanner


def test_scanner1():
    s = "y = (x + 1)"
    scan = Scanner(s)
    assert("y" == scan.next_token()[0])
    assert("=" == scan.next_token()[0])
    assert("(" == scan.next_token()[0])
    assert("x" == scan.next_token()[0])
    assert("+" == scan.next_token()[0])
    assert("1" == scan.next_token()[0])
    assert(")" == scan.next_token()[0])
```

需要安装好`pytest`，然后运行

```sh
pytest
```

测试通过即是胜利！更多的测试用例可见代码

### 2. abstract syntax

这一节，我们定义抽象语法树，也即语言的语义。我们支持一种数据类型（整型），变量及函数的定义。此外，支持二元运算和函数调用。所有这些，我都称之为表达式。

```py
class PyExpr: pass
```

定义变量
```py
class PyVar(PyExpr):
    def __init__(self, name):
        super().__init__()                  # 可省略
        self.name = name
    def __repr__(self):
        return f"PyVar({self.name})"
    def __eq__(self, other):
        return other.name == self.name
```
通过实现`__eq__`，我重载了`==`运算符。`__repr__`指定了使用`print`时输出的格式，间接地指定了使用`str`时输出的格式。

定义整型
```py
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
```
我重载了额外四个算术运算符，注意`/`重载时使用了整除运算`//`。

Python 的每个函数都会有返回值，如果没有`return`语句，返回值为`None`。我采用了这个语义，所以我们也需要一个`Null`

```py
class PyNull(PyExpr):
    def __init__(self):
        super().__init__()
    def __repr__(self):
        return "PyNull"
```

接着是赋值语句
```py
class PyDefvar(PyExpr):
    def __init__(self, var, val):
        super().__init__()
        self.var = var
        self.val = val
    def __repr__(self):
        return f"PyDefvar({self.var}, {self.val})"
```

函数定义
```py
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
```
我这里的定义不是很好，因为我把函数定义本身变成了一个函数，而这两者是有所不同的。但就这样吧，读者可任意更改。

函数的定义，我们需要函数名，参数，函数体，以及它**被定义时的环境**，因为我们实现的是词法作用域的函数。我重载了`__call__`，这使得`PyDefun`可以调用。调用时，先将参数传入环境，然后逐行解释`body`的内容。这里的`interpret`是解释器入口函数，我们返回`body`中最后一行的运行结果。等我们写到`interpret`时，读者可回看这一部分的内容，相信会更加清晰。

最后，我们还需要函数调用以及二元运算

```py
class PyCall(PyExpr):
    def __init__(self, fn, args):
        super().__init__()
        self.fn = fn
        self.args = args
    def __repr__(self):
        return f"PyCall({self.fn})"
```

```py
class PyOp2(PyExpr):
    def __init__(self, op, e1, e2):
        self.op = op
        self.e1 = e1
        self.e2 = e2
    def __repr__(self):
        return f"({self.op} {self.e1} {self.e2})"
```
注意到二元运算的`__repr__`中，采用了`LISP`的格式。


### 3. parser

现在来到本次教程的重点部分了。我们可以先分析一下 Python 的代码组织形式。

一个 `Python` 程序是由许多的表达式（expr）构成的。通常来讲，一个 expr 占一行。多个 expr 可以以`代码块`的方式组织。以冒号`:`标识`代码块`的开始。每个代码块都有它的缩进（indent）。可以声明新的块的语句有`def`、`if`、`for`、`while`、`class`等等。

一个块可以包含多个块。如下示例代码中，全局块含了四个 expr：一个 `PyDefun`，两个`PyDefvar`，一个`PyCall`。其中的`PyDefun`又包含了两个`PyDefun`和一个`PyOp2`，而这个`PyOp2`又包含了更多的`PyOp2`和`PyCall`。全局块的缩进为 0，`manda`的缩进为 4，而`sky`和`sea`的缩进为 8。
```py
def manda(m, a):
    def sky(s):
        return s + 4
    def sea(s):
        return s * 2
    return m + a - sea(m) * sky(a)

x = 4
y = 2

manda(myadd(x, y), mysub(y, x))
```
这个例子展示了我们将定义的语言方方面面的特性，如果在解析时有所困惑，可以回来看看这个例子。

我将采用递归下降的方式来解析，这里采用的文法也被称为`LR(1)`。

```py
def parse_expr(scanner, indent='', simple=False):
    """ parse expr without blank and leave `\n` """
    token, [row, col, _] = scanner.toke
```
我们从全局块开始，因此`indent`为空串，`indent`只会在解析`PyDefun`时用到。`simple`只会在解析`PyOp2`的时候用到，举个例子：对于以下这一个复合语句来说，当前的 token 位于 a 处。如果`simple==True`，则只会解析`a`，返回一个`PyVar`，否则，将解析整个式子，返回一个`PyOp2`。
```py
m = a - sea(m) * sky(a)
    ^
  token
```

好了，思想准备工作做完了。现在开始解析。我们先建立全局观：

```py
def parse_expr(scanner, indent='', simple=False):
    """ parse expr without blank and leave `\n` """
    token, [row, col, _] = scanner.token
    if token == 'def':                                  # 遇到关键字 def，肯定是函数定义
        return parse_defun(scanner, indent)
    elif token == '(':                                  # 遇到 ( ，肯定是括号表达式
        expr = parse_parent(scanner)
        if simple: return expr                          # 如果 simple == True，就直接返回
        return parse_op2(expr, scanner)                 # 否则，接着解析一个 PyOp2
    elif all_num(token):                                # 
        expr = parse_num(scanner)                       # 解析数字
        if simple: return expr                          # 
        return parse_op2(expr, scanner)
    elif is_var(token):
        # ...
```
这里解析了**看一眼**就能识别的表达式。由于数字和括号表达式是可以组合成`PyOp2`的，所以我们多了一个判断。

除了以上情况，我们发现 token 是一个变量，那有可能是`a`，`a + b`，`a()`等很多种情况。这时我们需要**多看一眼**。

```py
def parse_expr(scanner, indent='', simple=False):
    token, [row, col, _] = scanner.token
    # 已完成
    elif is_var(token):
        sym = PyVar(token)
        scanner.next_token()
        # 未完成
    else:
        raise Exception(f"unrecognize: `{token}` in row {row} col {col} ")
```
我们先将当前的 `token` 转成一个`PyVar`，然后我们读下一个`token`。（注意，我将忽略缩进）

第一种情况是，已经到达文件尾了。
```py
if scanner.token[0] is None:  # input end
    return sym
```

第二，我们遇到了左括号，这意味着函数调用，而函数调用也是可以组合到`PyOp2`中的。

```py
elif scanner.token[0] == '(': # funcall start
    expr = parse_funcall(sym, scanner)
    if simple: return expr
    return parse_op2(expr, scanner)
```

第三，发现逗号，这意味着我们在解析函数调用时的参数。读者可能有疑问：为什么不能是函数定义时的参数呢？这两者最大的区别在于，定义时的形式参数只能是`PyVar`，而调用时的参数可以是多种表达式，如`PyOp2`，`PyInt`等。
```py
elif scanner.token[0] == ',': # funcall argslist
    return sym
```

第四，发现右括号。这意味着函数调用结束了。
```py
elif scanner.token[0] == ')': # funcall finish
    return sym
```

第五，发现等号`=`，意味着这是一个赋值语句。
```py
elif scanner.token[0] == '=': # defvar
    return parse_defvar(sym, scanner)
```

第六，发现换行符，这意味着一行的结束。注意，我们并不解析换行符。
```py
elif scanner.token[0] == '\n':
    return sym
```

第七，是运算符。如果不是，就是语法错误。
```py
elif scanner.token[0] in '+-*/':
    return parse_op2(sym, scanner)
else:
    token, [row, col, _] = scanner.token
    raise Exception(f"unrecognize: `{sym.name} {token}` in row {row} col {col} ")
```

这样，我们完成了`parse_expr`。总体的结构也清晰了。 

现在，我们逐个完成那些`parse_*`函数。

最简单的两个： int， var。我们在 parse 的同时，吃掉了当前的 token 。这是递归下降的标准做法。
```py
def parse_num(scanner):
    pyint = PyInt(int(scanner.token[0]))
    scanner.next_token()
    return pyint

def parse_var(scanner):
    var = PyVar(scanner.token[0])
    scanner.next_token()
    return var
```

这里我想先定义一个辅助函数，以便提升代码可读性。
```py
def match(scanner, e):
    token, [row, col_s, _] = scanner.token
    assert token == e, f"expect {e} in row {row} column {col_s}"
    scanner.next_token()
```
`match`判断当前的 token 与 e 是否相同，如果相同，则把当前的 token 吃掉，不同则报错。我们将频繁使用这个函数。


下面解析赋值语句，回顾一下，sym 已经保存了等号左边的变量，当前的 token 应该是一个等号。我们需要解析右边的表达式，并赋值给左边的变量。
```py
def parse_defvar(sym, scanner):
    match(scanner, '=')
    expr = parse_expr(scanner)
    return PyDefvar(sym, expr)
```

下面解析括号。当前的 token 是一个左括号。我们解析括号中的表达式，并吃掉右边的括号。
```py
def parse_parent(scanner):
    match(scanner, '(')
    expr = parse_expr(scanner)
    match(scanner, ')')
    return expr
```

下面解析函数调用，我们已经解析了一个函数名`fn`，且当前的 token 是一个左括号，我们解析它的参数列表，并吃掉它的右括号。
```py
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
```

现在，我们剩下最难的两个 `PyOp2` 和 `PyDefun` 的解析。

我将使用运算符优先级的方法来解析 `PyOp2`，这一部分的内容，我参考了这份 [llvm 教程](https://llvm.org/docs/tutorial/MyFirstLanguageFrontend/LangImpl02.html)。
```py
precedure = { '+': 20, '-': 20, '*': 40, '/': 40 }
def parse_op2(expr, scanner, expr_prec=0):
    # [op, expr]*
    # ...
```
这个函数只会在解析了第一个表达式之后被调用，也即参数中的 `expr`。它会往下解析可能存在的「二元运算对」，即`[op, expr]*`。我们以一个具体的例子来说明。假设我们将解析以下式子。显然，1 被解析，并移动 token 位于 + 处。

```py
1 + 2 * 3 - 4
  ^
  token
```
剩下的是二元运算对 [+,2]，[*,3]，[-,4] 。参数中的 `expr_prec` 指的是表达式的优先级。初始为 0 。我们逐行解释代码：

一开始，我们需要判断接下来的内容是否是二元运算对。（注意，我忽略了缩进）
```py
if not scanner.token[0] or scanner.token[0] not in '+-*/':
    return expr
```

如果是，我们则需要读出当前的运算符，并与运算符的优先级跟表达式的优先级作对比。如果运算符的优先级低于表达式的优先级，则不再解析，直接返回。这样做的理由，希望在后文可以解释清楚。
```py
op, _ = scanner.token
op_prec = precedure[op]
if op_prec < expr_prec:
    return expr
```

以我们的例子来说，当前的表达式是`1`，其优先级为`0`，运算符为`+`，其优先级为`20`，显然要继续往下解析。但是，我们只要取出下一个**简单表达式**就行了！
```py
scanner.next_token()
next_expr = parse_expr(scanner, simple=True)    # 只取简单表达式
```
这里我们将取到`2`。

这时我们需要判断 token 是否已经位于行尾了。如果是这样，则表示解析结束，我们返回当前的`PyOp2`。
```py
if not scanner.token[0] or scanner.token[0] not in '+-*/':
    return PyOp2(op, expr, next_expr)
```

但在我们这个例子中，token 实际上还在`*`处。
```py
1 + 2 * 3 - 4
      ^
      token
```

所以我们必须比较`+`和`*`的优先级。显然`*`优先级更高，意味着`2`要跟`*`的后面的语句结合。这时候，我们看到

```py
2 * 3 - 4
  ^ 
  token
```
刚好是一个二元运算的复合语句，我们可以用`parse_op2`来递归解析。

```py
next_op, _ = scanner.token
next_op_prec = precedure[next_op]
if op_prec < next_op_prec:
    next_expr = parse_op2(next_expr, scanner, op_prec+1)
```
注意到，我们的表达式优先级为`op_prec+1`，具体而言，是`+`的优先级加`1`，为`21`。这会使得语句解析到后面的`-`处停下，使得`+`比`-`更早被解析。也就是说，使得同等级的语句从左到右按顺序解析。
```py
1 + 2 * 3 - 4
^   ^^^^^ ^
0   21    20
```

最后，等`*`解析完了，跟`+`相结合，并继续解析剩下的`-`号。
```py
expr = PyOp2(op, expr, next_expr)
return parse_op2(expr, scanner, expr_prec)
```
这次，我们传的是表达式的优先级，也即是`0`，所以后面的`-`可以被正确地解析。这样我们完成了`parse_op2`。

现在来看看`parse_defun`。

```py
def parse_defun(scanner, preindent):
    match(scanner, 'def')
    fn, [row, col, _] = scanner.token
    assert is_var(fn), f"`{fn}` in row {row} col {col} is not a valid function name"
    scanner.next_token()
    # ...
```
这个函数需要额外一个`preindemt`参数，表明它的上级代码块的缩进。以上代码解析了函数名。接下来我们解析参数列表，这与之前的函数调用很像。

```py
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
```

在这之后，我们期待有一个冒号和换行，同时，忽略多余的换行。
```py
    match(scanner, ':')
    match(scanner, '\n') # this is necessary newline
    while scanner.token[0] == '\n':
        scanner.next_token() # skip extra newline
```

现在我们开始解析函数体了。我们的 token 位于行首表示缩进，我们期待 indent 会大于它上一级代码块的缩进，否则报错。
```py
    body = []
    indent, [row, _, col] = scanner.token
    if not all_space(indent) or indent < preindent:
        raise Exception(f"bad indent in row {row}, col {col}")
```

因为我们函数体的语句是任意多的，所以用一个无限循环来解析。首先判断当前的语句是否为`return`
```py
    while True:
        scanner.next_token()                    # eat indent
        if scanner.token[0] == 'return':
            scanner.next_token()
            last_expr = parse_expr(scanner, indent)
            body.append(last_expr)
            break
```
否则，为任意一个普通的语句，先解析它。
```py
        expr = parse_expr(scanner, indent)
        body.append(expr)
```
之后，我们要判断下一个语句是否属于当前代码块。我们需要先跳过换行符。
```py
        # if expr is a defun, it will leave indent
        # else it will leave \n
        while scanner.token[0] == '\n':
            scanner.next_token(
```

现在，我们来到了非空行的行首，若为当前的缩进，则继续循环解析。
```py
        next_indent, [row, _, col] = scanner.token
        if next_indent == indent:
            continue
```
否则，我们可能到达了文件尾，或者当前的代码块已经结束了，也有可能是下一行的符号。不管怎么样，说明我们的解析结束，以`Null`作为最后一个语句返回。除此之外，就是语法错误了。
```py
        elif next_indent is None or next_indent < indent or not all_space(next_indent):
            last_expr = PyNull()
            body.append(last_expr)
            break
        else:
            raise Exception(f"bad indent in row {row}, col {col}")
```

最后，我们返回一个`PyDefun`
```py
    # now, fn, args, and body is ready, env will be appended when interpreted
    return PyDefun(PyVar(fn), args, body, PyNull())
```

写些测试吧！

```py
# test_psp.py
def test_parse3():
    s = "(1 + 2) - 3 / 4"
    scan = Scanner(s)
    scan.next_token()
    expr = parse_expr(scan)
    assert isinstance(expr, PyOp2)
    assert str(expr) == '(- (+ 1 2) (/ 3 4))'
```

我们再写个入口函数

```py
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
```

至此，parser 完成！
 
### 4. interpreter

本教程最后一个内容是解释器。因为在之前的 EoC 中，我们实现过四个解释器了，所以这里不会很详细解释。言归正传，我们先看看环境表示

```py
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
```

这是 message-passing 风格的环境表示。env 本身是一个函数`search`，或者说闭包(closure)。拓展环境使用 extend，传入的 var、val 和 env 被 search 捕获了。查找变量时，先与闭包中捕获的 var 对比，如果没有，再从它捕获的 env 中查找。

好了。现在来看看解释器

```py
def interpret(exprs, env):
    for expr in exprs:
        if isinstance(expr, PyDefvar):
            val = interpret_helper(expr.val, env)
            env = extend(expr.var, val, env)
        elif isinstance(expr, PyDefun):
            expr.env = env      # bind runtime environment
            env = extend(expr.name, expr, env)
        else:
            yield interpret_helper(expr, env)
```

在我们的语句中，有两种修改环境的语句，其余都是有返回值的语句，我们用一个 helper 来解释。

```py
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
```

这样，我们的小 Python 语言总算完成了！

以下是一个使用示例。

```py
def interp_demo(filename):
    with open(filename) as f:
        source = f.read()
    ast = parse(source)
    res = interpret(ast, empty_env())
    for (i, x) in enumerate(res):
        print(f"Out[{i}]: {x}")

if __name__ == '__main__':
    interp_demo('demo.py')
```

让我们测试一下吧！

```py
def test_interpret1():
    s = """\
def haha(a, b):
    def hahaha(z):
        return z * 2
    return hahaha(a) + b * b - a / b
y = 1
x = 2
z = haha(x, y)
z
"""
    cfg = parse(s)
    res = list(interpret(cfg, empty_env()))
    assert res[-1] == PyInt(3)

def test_interpret2():
    s = "1 + 2 * 3 - 4 / 5"
    cfg = parse(s)
    res = list(interpret(cfg, empty_env()))
    assert res[-1] == PyInt(7)
```

#### 初心

这份教程源于我对 llvm 官网上一份教程的学习。那份教程中实现了一门语法类似 Python 的小语言。当时我就想，是否能实现成「真」的 Python 呢？然后时不时会思考如何解析 Python 的语法。直到最近有点时间，我才着手实现。因为收获颇丰，遂有此文。

#### 结语

    纸上得到终觉浅，绝知此事要躬行。


#### 自愿购买

本教程定价 ￥32，可自愿购买，可使用自定义折扣券。

![wechat](./wechat.png)