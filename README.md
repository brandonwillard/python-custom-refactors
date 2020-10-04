![refactors-tests](https://github.com/brandonwillard/python-custom-refactors/workflows/refactors-tests/badge.svg)

# Python Custom Refactors

Custom refactors written in LibCST.

## Installation

To install from source:
```bash
git clone git@github.com:brandonwillard/python-custom-refactors.git
cd python-custom-refactors
pip install -r requirements.txt
```

# Implemented Refactors

## Convert "indirect" module/package references into "direct" references.

For example, consider the package, `pkg`, defined by the following files:

`pkg/__init__.py`:
```python
import pkg.mod1 as foo

from pkg.mod1 import var1

var2 = 0
```

`pkg/mod1.py`:
```python
var1 = 10
```

`pkg/mod2.py`:
```python
import pkg

from pkg import foo, var1, var2

print(pkg.foo)
print(pkg.var1)
print(pkg.var2)
print(var1)
print(foo.var1)
```

Refactoring would produce the following new package files:

`pkg/__init__.py`:
```python
var2 = 0
```

`pkg/mod1.py`:
```python
var1 = 10
```

`pkg/mod2.py`:
```python
import pkg
import pkg.mod1
import pkg.mod1 as foo

from pkg import var2
from pkg.mod1 import var1

print(pkg.mod1)
print(pkg.mod1.var1)
print(pkg.var2)
print(var1)
print(foo.var1)
```
