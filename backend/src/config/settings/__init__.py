"""Settings package.

Este paquete permite usar `DJANGO_SETTINGS_MODULE=config.settings` como alias
válido (cargando base por defecto).

Para entornos específicos usar:
- `config.settings.dev`
- `config.settings.prod`
- `config.settings.test`
"""

from .base import *  # noqa: F403
