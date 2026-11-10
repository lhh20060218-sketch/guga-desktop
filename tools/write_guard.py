# -*- coding: utf-8 -*-
"""写入路径硬闸：拒绝把文件写到用户目录根部或直属一层。

20261110w 事故（第三次）：PowerShell 里的 ``$home`` 是只读自动变量 ``C:\\Users\\l``，
一条“复制配置到临时 home”的命令因此把配置副本写成了 ``C:\\Users\\l\\ai_config.json``。
本模块把所有写入前的路径校验集中到一处：

- 解析成绝对路径（``os.path.abspath`` + ``Path.resolve``）；
- 拒绝 ``~`` / ``$HOME`` / ``$home`` 这类会随环境漂移的写法；
- 拒绝等于 ``C:\\Users\\<用户>`` 根；
- 拒绝落在 ``C:\\Users\\<用户>\\`` 直属一层，白名单目录（AppData）除外；
- ``D:\\...`` 等非用户目录正常放行。

单独执行：python tools/test_write_guard.py
"""
from __future__ import annotations

import os
from pathlib import Path

#: 允许直接写在用户目录下的白名单（系统约定的可写子目录）。
ALLOWED_USER_CHILDREN = frozenset({"appdata"})

#: 会随环境漂移的写法：出现即拒绝，要求调用方给绝对路径。
_FORBIDDEN_MARKERS = ("~", "$home", "${home}", "%userprofile%")


class UnsafeWritePath(ValueError):
    """路径会让文件落到用户目录根部/直属一层，或使用了不可控的相对写法。"""

    code = "unsafe_write_path"


def user_home() -> Path:
    return Path.home().resolve()


def resolve_write_path(path) -> Path:
    """解析并校验写入路径；不安全时抛 ``UnsafeWritePath``。

    返回值一定是绝对路径，调用方应直接用它写入（不要再用原始字符串）。
    """
    raw = str(path or "").strip()
    if not raw:
        raise UnsafeWritePath("写入路径为空")
    lowered = raw.lower()
    for marker in _FORBIDDEN_MARKERS:
        if marker in lowered:
            raise UnsafeWritePath("禁止使用 %s 这类相对写法，请给绝对路径：%s"
                                  % (marker, raw))
    resolved = Path(os.path.abspath(os.path.expandvars(raw))).resolve()
    home = user_home()
    if resolved == home:
        raise UnsafeWritePath("拒绝写入用户目录根：%s" % resolved)
    try:
        relative = resolved.relative_to(home)
    except ValueError:
        return resolved                      # D:\... 等非用户目录：放行
    parts = relative.parts
    if len(parts) == 1 and parts[0].casefold() not in ALLOWED_USER_CHILDREN:
        raise UnsafeWritePath("拒绝写入用户目录直属一层：%s" % resolved)
    return resolved
