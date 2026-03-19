"""Domain modules package.

Supports package portions in multiple roots during migrations
(`repo_root/modulos` + `backend/src/modulos`).
"""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
