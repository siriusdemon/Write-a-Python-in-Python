def myadd(a, b):
    return a + b

def mysub(c, d):
    return c + d

myadd(1, 3) + mysub(2, 4)


def manda(m, a):

    def sky(s):
        return s + 4

    def sea(s):
        return s * 2

    return m + a - sea(m) * sky(a)

x = 4
y = 2

manda(myadd(x, y), mysub(y, x))

def ret_null():
    x = 0


ret_null()