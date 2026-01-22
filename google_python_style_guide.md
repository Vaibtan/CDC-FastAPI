# Google Python Style Guide

**Purpose**: This guide defines coding standards for Python code at Google. Use these rules consistently in all Python projects.

---

## 1. Code Formatting

### 1.1 Line Length
- **Maximum**: 80 characters
- **Exceptions**: 
  - Long import statements
  - URLs in comments
  - Long string module level constants
  - Pylint disable comments

### 1.2 Indentation
- Use **4 spaces** per indentation level
- **Never use tabs**
- Continuation lines should align vertically or use 4-space hanging indent

```python
# Correct
foo = long_function_name(
    var_one, var_two, var_three,
    var_four)

# Correct - hanging indent
foo = long_function_name(
    var_one, var_two,
    var_three, var_four
)
```

### 1.3 Blank Lines
- **Two blank lines** between top-level definitions (functions/classes)
- **One blank line** between method definitions
- **One blank line** between class docstring and first method
- **No blank line** after a `def` line

### 1.4 Whitespace
- No whitespace inside parentheses, brackets, or braces: `spam(ham[1], {'eggs': 2})`
- No whitespace before comma, semicolon, or colon
- Whitespace after comma, semicolon, or colon (except end of line)
- Surround binary operators with single space: `x == 1`, `x + y`
- No spaces around `=` for keyword arguments: `def complex(real, imag=0.0)`
- **Exception**: With type annotations, use spaces: `def complex(real, imag: float = 0.0)`
- No trailing whitespace

### 1.5 Line Continuation
- Use Python's implicit line joining inside parentheses, brackets, braces
- **Avoid backslashes** for line continuation

```python
# Correct
if (width == 0 and height == 0 and
    color == 'red' and emphasis == 'strong'):
    pass

# Wrong
if width == 0 and height == 0 and \
    color == 'red' and emphasis == 'strong':
    pass
```

### 1.6 Parentheses
- Use sparingly
- OK for tuples, implied line continuation, or indicating tuples
- Don't use in return statements or conditionals unless necessary

```python
# Correct
if foo:
    bar()
return spam, beans

# Wrong
if (x):
    bar()
return (foo)
```

### 1.7 Trailing Commas
- Recommended when closing bracket not on same line as final element
- Required for single-element tuples: `onesie = (foo,)`

---

## 2. Imports

### 2.1 Import Structure
- Always at top of file (after module docstring, before globals)
- Group imports in order:
  1. `from __future__ import` statements
  2. Python standard library
  3. Third-party modules/packages
  4. Code repository sub-packages
  5. Application-specific imports (deprecated, treat as sub-packages)

### 2.2 Import Format
```python
# Correct
from collections.abc import Mapping, Sequence
import os
import sys
from typing import Any, NewType

# Wrong
import os, sys
```

### 2.3 Import Rules
- Use `import x` for packages and modules only
- Use `from x import y` where `x` is package prefix, `y` is module name
- Use `from x import y as z` when:
  - Two modules named `y` would be imported
  - `y` conflicts with top-level name
  - `y` conflicts with common parameter name
  - `y` is inconveniently long
  - `y` is too generic
- Use full package paths (absolute imports, not relative)
- Sort imports lexicographically by full module path

```python
# Correct
from sound.effects import echo
echo.EchoFilter(input, output, delay=0.7)

# Wrong
import echo  # Relative import
```

---

## 3. Naming Conventions

### 3.1 Naming Styles

| Type | Convention | Example |
|------|-----------|---------|
| Packages | `lowercase` | `mypackage` |
| Modules | `lowercase_with_underscores` | `my_module.py` |
| Classes | `CapWords` | `MyClass` |
| Exceptions | `CapWords` (end with `Error`) | `MyCustomError` |
| Functions | `lowercase_with_underscores` | `my_function()` |
| Global/Class Constants | `CAPS_WITH_UNDERSCORES` | `MAX_OVERFLOW` |
| Global/Class Variables | `lowercase_with_underscores` | `global_var` |
| Instance Variables | `lowercase_with_underscores` | `instance_var` |
| Method Names | `lowercase_with_underscores` | `method_name()` |
| Function Parameters | `lowercase_with_underscores` | `function_parameter` |
| Local Variables | `lowercase_with_underscores` | `local_var` |

### 3.2 Internal/Private
- Prefix with single underscore `_` for internal use
- Prefix with double underscore `__` for class-private (rarely needed)

---

## 4. Statements

### 4.1 Simple Statements
- No semicolons to end lines
- Never put two statements on same line

### 4.2 Conditionals
- Use implicit `False` when possible
- `if foo:` instead of `if foo != []:`
- Always use `if foo is None:` (or `is not None`)
- Never compare boolean to `False` using `==`: use `if not x:`
- For sequences, use `if seq:` not `if len(seq):`
- For integers (not from `len()`), compare explicitly: `if i % 10 == 0:`

```python
# Correct
if not users:
    print('no users')
if x is None:
    x = []

# Wrong
if len(users) == 0:
    print('no users')
if x == None:
    x = []
```

---

## 5. Functions and Methods

### 5.1 Default Arguments
- OK to use, but:
  - **Never use mutable objects** as default values
  - Use `None` as default, then assign mutable in function body

```python
# Correct
def foo(a, b=None):
    if b is None:
        b = []

# Wrong
def foo(a, b=[]):  # Mutable default!
    ...
```

### 5.2 Function Length
- Prefer small, focused functions
- No hard limit, but consider breaking up if > 40 lines

### 5.3 Lambda Functions
- OK for one-liners
- If > 60-80 chars or multiline, use regular nested function
- Prefer `operator` module functions over lambda: `operator.mul` not `lambda x, y: x * y`

---

## 6. Classes

### 6.1 Properties
- Use `@property` decorator for attribute access
- Properties should be:
  - Cheap computations
  - Straightforward
  - Unsurprising
- Don't use properties for complex computations that subclasses might override

### 6.2 Decorators
- Use judiciously when there's clear advantage
- **Never use `staticmethod`** unless forced by external API (use module-level function)
- Use `classmethod` only for named constructors or class-specific global state modifications
- Write unit tests for decorators

### 6.3 Threading
- Don't rely on atomicity of built-in types
- Use `queue.Queue` for thread communication
- Use `threading` module and locking primitives
- Prefer `threading.Condition` over lower-level locks

---

## 7. Strings

### 7.1 String Formatting
- Use f-strings, `%` operator, or `.format()` method
- Don't format with `+` operator

```python
# Correct
x = f'name: {name}; score: {n}'
x = '%s, %s!' % (imperative, expletive)
x = '{}, {}'.format(first, second)

# Wrong
x = 'name: ' + name + '; score: ' + str(n)
```

### 7.2 Quote Style
- Pick single quotes or double quotes and be consistent within file
- Use triple double-quotes for multi-line strings (docstrings)
- Projects may use triple single-quotes for non-docstring multi-line if using single quotes for regular strings

### 7.3 Multi-line Strings
- Use concatenated single-line strings or `textwrap.dedent()`
- Avoid embedding extra indentation spaces

---

## 8. Comprehensions and Generators

### 8.1 List/Dict/Set Comprehensions
- OK for simple cases
- **No multiple `for` clauses**
- **No multiple `if` expressions** (except simple filter)
- Optimize for readability, not conciseness

```python
# Correct
result = [mapping_expr for value in iterable if filter_expr]

# Wrong
result = [(x, y) for x in range(10) for y in range(5) if x * y > 10]
```

### 8.2 Generators
- Use as needed
- Use `Yields:` in docstring, not `Returns:`
- Manage expensive resources with context managers

### 8.3 Default Iterators
- Use default iterators for types that support them

```python
# Correct
for key in adict: ...
if obj in alist: ...

# Wrong
for key in adict.keys(): ...
```

---

## 9. Exceptions

### 9.1 Exception Rules
- Use built-in exception classes when appropriate
- Custom exceptions must inherit from existing exception class
- Exception names should end in `Error`
- **Never use catch-all `except:`**
- Never catch `Exception` or `StandardError` unless re-raising or at top level
- Minimize code in `try` block
- Use `finally` for cleanup

### 9.2 Assertions
- **Don't use `assert` for data validation or in place of conditionals**
- Only use for verifying internal correctness (can be disabled)
- OK in pytest tests

```python
# Correct
if minimum < 1024:
    raise ValueError(f'Min. port must be at least 1024, not {minimum}.')

# Wrong - don't rely on assert
assert minimum >= 1024, 'Minimum port must be at least 1024.'
port = self._find_next_open_port(minimum)
```

---

## 10. Global State

### 10.1 Mutable Global State
- **Avoid mutable global state**
- If necessary:
  - Declare at module level or as class attribute
  - Make internal with `_` prefix
  - Provide public functions/methods for external access
  - Document design reasons in comments

### 10.2 Module Constants
- Permitted and encouraged
- Use `ALL_CAPS_WITH_UNDERSCORES`
- Prefix with `_` for internal use

```python
_MAX_HOLY_HANDGRENADE_COUNT = 3  # Internal
SIR_LANCELOTS_FAVORITE_COLOR = "blue"  # Public API
```

---

## 11. Nested Code

### 11.1 Nested Functions/Classes
- OK when closing over local variable (not just `self` or `cls`)
- Don't nest just to hide from module users (use `_` prefix instead)
- Makes testing easier

---

## 12. Type Annotations

### 12.1 General Rules
- **Strongly encouraged** for new code and when updating existing code
- Enable type checking with tools like `pytype`
- Annotate function/method arguments and return values
- Can annotate variables with similar syntax

```python
def func(a: int) -> list[int]:
    ...

a: SomeType = some_func()
```

### 12.2 Special Cases
- Don't annotate `self` or `cls` (use `Self` if needed for proper typing)
- Don't annotate `__init__` return value (always `None`)
- Use `Any` for types that can't be expressed
- Use `| None` for optional types (PEP 604 union syntax preferred over `Optional`)

### 12.3 Formatting Type Annotations
- One parameter per line for long signatures
- Return type on its own line or same line as last parameter
- Align closing parenthesis with `def`

```python
def my_method(
    self,
    first_var: int,
    second_var: Foo,
    third_var: Bar | None,
) -> int:
    ...
```

---

## 13. Documentation

### 13.1 Module Docstrings
- Every file should have module docstring
- Describe contents and usage
- Include usage examples if helpful

```python
"""A one-line summary of the module or program, terminated by a period.

Leave one blank line. The rest of this docstring should contain an
overall description of the module or program. Optionally, it may also
contain a brief description of exported classes and functions and/or usage
examples.

Typical usage example:

    foo = ClassFoo()
    bar = foo.function_bar()
"""
```

### 13.2 Function/Method Docstrings
- Required for functions that are:
  - Part of external API
  - Non-trivial
  - Not immediately obvious
- Describe calling syntax and semantics, not implementation
- Use descriptive or imperative style consistently

**Sections** (if applicable):
- `Args:` - Each parameter with type and description
- `Returns:` - Describe return value and type
- `Raises:` - Exceptions that callers need to handle
- `Yields:` - For generators

```python
def fetch_rows(
    table_handle: Table,
    keys: Sequence[bytes | str],
    require_all_keys: bool = False,
) -> Mapping[bytes, tuple[str, ...]]:
    """Fetches rows from a Smalltable.

    Retrieves rows pertaining to the given keys from the Table instance
    represented by table_handle. String keys will be UTF-8 encoded.

    Args:
        table_handle: An open smalltable.Table instance.
        keys: A sequence of strings representing the key of each table
            row to fetch. String keys will be UTF-8 encoded.
        require_all_keys: If True only rows with values set for all keys will be
            returned.

    Returns:
        A dict mapping keys to the corresponding table row data
        fetched. Each row is represented as a tuple of strings.

    Raises:
        IOError: An error occurred accessing the smalltable.
    """
```

### 13.3 Class Docstrings
- Describe what class instance represents
- Document public attributes in `Attributes:` section
- One-line summary should describe what instance represents

```python
class SampleClass:
    """Summary of class here.

    Longer class information...

    Attributes:
        likes_spam: A boolean indicating if we like SPAM or not.
        eggs: An integer count of the eggs we have laid.
    """
```

### 13.4 Comments
- Use complete sentences with proper punctuation
- Block comments: `#` followed by single space
- Inline comments: Two spaces before `#`
- Update comments when updating code

### 13.5 TODO Comments
- Use for temporary, short-term, or good-enough-but-not-perfect code

```python
# TODO: crbug.com/192795 - Investigate cpufreq optimizations.
# TODO(username): Use a "*" here for concatenation operator.
```

---

## 14. Main

### 14.1 Main Guard
- Even for scripts, make executable code callable from other modules
- Use `if __name__ == '__main__':` guard
- Minimal code at top level (only when pydocing is safe)

```python
def main():
    ...

if __name__ == '__main__':
    app.run(main)  # or main() if not using absl
```

---

## 15. Shebang Line
- Use `#!/usr/bin/env python3` (supports virtualenvs)
- Or `#!/usr/bin/python3`
- Only needed for executable files, not imported modules

---

## 16. Lint

### 16.1 Pylint
- Run `pylint` over your code
- Suppress warnings appropriately with comments:
  ```python
  def do_PUT(self):  # WSGI name, so pylint: disable=invalid-name
  ```
- Include explanation if symbolic name isn't clear
- Prefer `pylint: disable=name` over deprecated `pylint: disable-msg`

### 16.2 Unused Arguments
- Delete at beginning of function with explanation

```python
def viking_cafe_order(spam: str, beans: str, eggs: str | None = None) -> str:
    del beans, eggs  # Unused by vikings.
    return spam + spam + spam
```

---

## 17. Power Features (Avoid These)

### 17.1 Features to Avoid
- Custom metaclasses (except `abc.ABCMeta`, `dataclasses`, `enum`)
- Access to bytecode
- On-the-fly compilation
- Dynamic inheritance
- Object reparenting
- Import hacks
- Some uses of reflection/`getattr()`
- Modification of system internals
- `__del__` methods

### 17.2 Rationale
- Hard to read, understand, and debug
- May seem clever but creates maintenance burden
- Standard library modules using these are OK to use

---

## 18. Conditional Expressions (Ternary Operator)

- OK for simple cases
- Each portion must fit on one line

```python
# Correct
one_line = 'yes' if predicate(value) else 'no'

# Wrong - line breaking
bad = ('yes' if predicate(value) else
       'no')
```

---

## 19. Modern Python Features

### 19.1 Future Imports
- Use `from __future__ import` statements as needed
- Enables newer Python features in older runtimes
- Keep in file until confident code only runs in modern environments

```python
from __future__ import annotations  # For type annotations
```

---

## Summary Checklist

✅ **Formatting**: 80 chars, 4 spaces, proper whitespace  
✅ **Imports**: Absolute imports, grouped and sorted, one per line  
✅ **Naming**: snake_case for functions/variables, CapWords for classes  
✅ **Types**: Annotate public APIs, use type checker  
✅ **Docstrings**: Module, class, and public function docstrings with proper sections  
✅ **Exceptions**: Use built-in exceptions, no catch-all except  
✅ **Functions**: Small and focused, no mutable defaults  
✅ **Strings**: Use f-strings or .format(), consistent quotes  
✅ **Comprehensions**: Simple only, optimize for readability  
✅ **Lint**: Run pylint, fix or suppress warnings appropriately  
✅ **Main guard**: Use `if __name__ == '__main__':`  
✅ **Avoid**: Power features, mutable global state, assert for validation  

---

**Version**: Based on Google Python Style Guide (https://google.github.io/styleguide/pyguide.html)
**Last Updated**: December 2025
