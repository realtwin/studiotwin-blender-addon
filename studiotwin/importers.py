"""Deterministic Blender import primitives for StudioTwin outputs."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import bpy


_ENVIRONMENT_EXTENSIONS = {".hdr", ".png"}
_MODEL_EXTENSIONS = {".glb"}
_AUDIO_EXTENSIONS = {".aif", ".aiff", ".flac", ".mp3", ".ogg", ".wav"}
_IMAGE_EXTENSIONS = {".hdr", ".jpeg", ".jpg", ".png", ".tif", ".tiff"}
_PBR_MAP_TYPES = {"albedo", "heightmap", "metalness", "normals", "roughness"}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def _require_file(filepath: str, extensions: set[str], label: str) -> Path:
    path = Path(bpy.path.abspath(filepath)).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label} file not found: {path}")
    if path.suffix.lower() not in extensions:
        supported = ", ".join(sorted(extensions))
        raise ValueError(
            f"Unsupported {label} format '{path.suffix}'; expected one of: {supported}"
        )
    return path


def _asset_name(prefix: str, path: Path) -> str:
    stem = _SAFE_NAME.sub("_", path.stem).strip("_.") or "Asset"
    return f"{prefix}_{stem}"


def _node(nodes: Any, node_type: str, name: str) -> Any:
    existing = nodes.get(name)
    if existing is not None and existing.bl_idname == node_type:
        return existing
    node = nodes.new(node_type)
    node.name = name
    node.label = name
    return node


def _connect(links: Any, output_socket: Any, input_socket: Any) -> None:
    for link in tuple(input_socket.links):
        links.remove(link)
    links.new(output_socket, input_socket)


def _load_image(path: Path, *, non_color: bool = False) -> Any:
    image = bpy.data.images.load(str(path), check_existing=True)
    if non_color:
        image.colorspace_settings.name = "Non-Color"
    return image


def apply_environment_map(filepath: str) -> dict[str, Any]:
    """Apply an equirectangular environment map to the scene's world."""

    path = _require_file(filepath, _ENVIRONMENT_EXTENSIONS, "environment map")
    name = _asset_name("StEnvironmentMap", path)

    # Reuse the scene World so its existing background/output setup stays intact.
    world = bpy.context.scene.world or bpy.data.worlds.new(name)
    world.name = name
    bpy.context.scene.world = world
    world.use_nodes = True

    # Persist the source path in the .blend for provenance and future reimporting.
    world["studiotwin_source"] = str(path)
    nodes = world.node_tree.nodes
    links = world.node_tree.links

    envmap = nodes.get("StudioTwin Environment") or nodes.new(
        "ShaderNodeTexEnvironment"
    )

    envmap.name = "StudioTwin Environment"
    envmap.label = "StudioTwin Environment"
    envmap.image = _load_image(path)

    # Remove mapping links left by the previous rotation-enabled importer.
    for link in tuple(envmap.inputs["Vector"].links):
        links.remove(link)

    background = nodes.get("Background")
    if background is not None:
        _connect(links, envmap.outputs["Color"], background.inputs["Color"])

    # Show the imported environment immediately in every open 3D viewport.
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.shading.type = "RENDERED"

    return {
        "type": "environment_map",
        "filepath": str(path),
        "image": envmap.image.name,
        "world": world.name,
    }


def import_model(filepath: str) -> dict[str, Any]:
    """Import a GLB model and report the created Blender data."""
    path = _require_file(filepath, _MODEL_EXTENSIONS, "model")
    objects_before = set(bpy.data.objects.keys())
    outcome = bpy.ops.import_scene.gltf(filepath=str(path))
    if "FINISHED" not in outcome:
        raise RuntimeError(f"Blender could not import {path.name}: {sorted(outcome)}")

    imported_objects = [obj for obj in bpy.data.objects if obj.name not in objects_before]
    base_name = _asset_name("StModel", path)
    for index, obj in enumerate(imported_objects):
        obj.name = base_name if index == 0 else f"{base_name}_{index:02d}"
        obj["studiotwin_source"] = str(path)

    return {
        "type": "model",
        "filepath": str(path),
        "objects": [obj.name for obj in imported_objects],
        "meshes": [obj.name for obj in imported_objects if obj.type == "MESH"],
    }


def import_material(
    map_paths: dict[str, str],
    *,
    name: str | None = None,
    displacement_scale: float = 0.1,
) -> dict[str, Any]:
    """Import a PBR material from explicit StudioTwin map paths."""
    if not map_paths:
        raise ValueError("At least one PBR map is required")
    if displacement_scale < 0:
        raise ValueError("Displacement scale must be zero or greater")

    normalized: dict[str, Path] = {}
    for map_type, filepath in map_paths.items():
        key = map_type.lower()
        if key not in _PBR_MAP_TYPES:
            raise ValueError(f"Unsupported PBR map type: {map_type}")
        normalized[key] = _require_file(filepath, _IMAGE_EXTENSIONS, f"{key} texture")

    first_path = next(iter(normalized.values()))
    material_name = name.strip() if name and name.strip() else _asset_name("StMaterial", first_path)
    material = bpy.data.materials.new(material_name)
    material.use_nodes = True
    material["studiotwin_maps"] = {key: str(path) for key, path in normalized.items()}

    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.name = "StudioTwin Principled BSDF"
    bsdf.label = "StudioTwin Principled BSDF"
    output = nodes["Material Output"]
    output.name = "StudioTwin Material Output"
    output.label = "StudioTwin Material Output"
    bsdf.location = (260, 80)
    output.location = (560, 80)
    _connect(links, bsdf.outputs["BSDF"], output.inputs["Surface"])

    texture_positions = {
        "albedo": (-620, 340),
        "normals": (-620, 80),
        "roughness": (-620, -100),
        "metalness": (-620, -280),
        "heightmap": (-620, -480),
    }
    socket_names = {"albedo": "Base Color", "roughness": "Roughness", "metalness": "Metallic"}

    for map_type, path in normalized.items():
        texture = _node(nodes, "ShaderNodeTexImage", f"StudioTwin {map_type.title()}")
        texture.image = _load_image(path, non_color=map_type != "albedo")
        texture.location = texture_positions[map_type]

        if map_type == "normals":
            normal = _node(nodes, "ShaderNodeNormalMap", "StudioTwin Normal Map")
            normal.location = (-100, 20)
            _connect(links, texture.outputs["Color"], normal.inputs["Color"])
            _connect(links, normal.outputs["Normal"], bsdf.inputs["Normal"])
        elif map_type == "heightmap":
            displacement = _node(nodes, "ShaderNodeDisplacement", "StudioTwin Displacement")
            displacement.location = (260, -260)
            displacement.inputs["Scale"].default_value = displacement_scale
            _connect(links, texture.outputs["Color"], displacement.inputs["Height"])
            _connect(links, displacement.outputs["Displacement"], output.inputs["Displacement"])
        else:
            _connect(links, texture.outputs["Color"], bsdf.inputs[socket_names[map_type]])

    return {
        "type": "pbr_material",
        "material": material.name,
        "maps": {key: str(path) for key, path in normalized.items()},
    }


def import_audio(
    filepath: str,
    *,
    frame_start: int | None = None,
    channel: int | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Add an audio file to the current scene's sequencer."""
    path = _require_file(filepath, _AUDIO_EXTENSIONS, "audio")
    scene = bpy.context.scene
    editor = scene.sequence_editor or scene.sequence_editor_create()
    strips = getattr(editor, "strips", None)
    if strips is None:  # Blender versions before the sequencer API rename.
        strips = editor.sequences
    existing = list(strips)
    target_channel = channel if channel is not None else max(
        (strip.channel for strip in existing), default=0
    ) + 1
    if target_channel < 1:
        raise ValueError("Audio channel must be one or greater")
    target_frame = scene.frame_current if frame_start is None else frame_start
    strip_name = name.strip() if name and name.strip() else _asset_name("StAudio", path)
    strip = strips.new_sound(
        name=strip_name,
        filepath=str(path),
        channel=target_channel,
        frame_start=target_frame,
    )
    if hasattr(strip, "show_waveform"):
        strip.show_waveform = True
    strip["studiotwin_source"] = str(path)
    scene.frame_end = max(scene.frame_end, int(strip.frame_final_end))

    return {
        "type": "audio",
        "filepath": str(path),
        "strip": strip.name,
        "channel": strip.channel,
        "frameStart": int(strip.frame_start),
        "frameEnd": int(strip.frame_final_end),
    }


__all__ = (
    "apply_environment_map",
    "import_audio",
    "import_material",
    "import_model",
)
