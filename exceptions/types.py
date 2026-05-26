from typing import Callable

type ExceptionRegistry = dict[type[Exception], Callable]
