"""内置出行模式。

新增模式只要在这里多导入一个模块，模块内部调用 ``register(YourMode())`` 即可；
前端会自动从 ``/api/modes`` 读到新条目并渲染它声明的附加选项。
"""

from . import commute, travel  # noqa: F401
from .base import Item, Mode, ModeResult, Section

__all__ = ["Mode", "ModeResult", "Section", "Item", "commute", "travel"]
