# OOOZet - Bot społeczności OOOZ
# Copyright (C) 2023-2026 Karol "digitcrusher" Łacina
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import importlib, os, pkgutil, sys
from pathlib import Path

for path, _, _ in os.walk(os.path.dirname(__spec__.origin)):
  prefix = ''.join(f'{i}.' for i in Path(path).relative_to(sys.path[0]).parts)
  for mod_info in pkgutil.iter_modules([path], prefix):
    importlib.import_module(mod_info.name)
