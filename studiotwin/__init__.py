"""StudioTwin local asset importers for Blender 5.1 and newer."""

from __future__ import annotations

try:
    import bpy
except ImportError:
    bpy = None

if bpy is not None:
    from .importers import (
        apply_environment_map,
        import_audio,
        import_material,
        import_model,
    )


def register() -> None:
    """Register the extension."""


def unregister() -> None:
    """Unregister the extension from Blender."""
