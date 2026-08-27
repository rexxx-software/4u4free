# SteaMidra - Steam game setup and manifest tool (SFF)
# Copyright (c) 2025-2026 Midrag (https://github.com/Midrags)
#
# This file is part of SteaMidra.
#
# SteaMidra is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Steam redistributable depot identifiers used by Lua generation."""

_REDIST_DEPOTS: frozenset[int] = frozenset(
    {
        1004,
        1005,
        1006,
        228500,
        228980,
        228981,
        228982,
        228983,
        228984,
        228985,
        228986,
        228987,
        228988,
        228989,
        228990,
        229000,
        229001,
        229002,
        229003,
        229004,
        229005,
        229006,
        229007,
        229010,
        229011,
        229012,
        229020,
        229021,
        229030,
        229031,
        229032,
        229033,
        229040,
        229060,
        229080,
    }
)
