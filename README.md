# StudioTwin for Blender

Local import bridge between Blender 5.1+ and StudioTwin. The extension applies
assets from the local filesystem to Blender scenes. It does not perform network
requests, store credentials, or manage generation jobs.

## Requirements

- Blender 5.1 or newer
- The official [Blender Lab MCP add-on](https://projects.blender.org/lab/blender_mcp)
- The hosted StudioTwin MCP configured in the AI agent

StudioTwin authentication is configured only in the AI agent's MCP settings.
This extension does not store an API key.

Blender extension manifests cannot declare another separately installed
extension as a dependency, so the official MCP add-on is installed and enabled
separately.

## Python API

The agent uploads inputs and manages generation through the hosted StudioTwin
MCP. It resolves output asset IDs, downloads the resulting presigned URLs to
the local filesystem, and passes absolute filepaths to Blender through the
official Blender MCP.

The official Blender MCP can call this stable API through
`execute_blender_code`:

```python
import importlib
import bpy

module_name = next(
    name for name in bpy.context.preferences.addons
    if name.endswith(".studiotwin")
)
studiotwin = importlib.import_module(module_name)

result = studiotwin.import_model("/absolute/path/to/generated.glb")
```

The Blender-side API provides explicit, JSON-returning operations for agent
orchestration:

```python
studiotwin.apply_environment_map(filepath)
studiotwin.import_model(filepath)
studiotwin.import_material(map_paths)
studiotwin.import_audio(filepath)
```

Environment maps support HDR and PNG files and switch every open 3D viewport to
Rendered shading. Models support GLB files. PBR materials accept `albedo`,
`heightmap`, `normals`, `roughness`, and `metalness` map paths and create a new
unassigned Blender material on every call.

## Package layout

```text
studiotwin/
|-- __init__.py
|-- importers.py
`-- blender_manifest.toml
```

Build or validate the extension from the `studiotwin` directory with a
supported Blender version:

```bash
blender --command extension validate
blender --command extension build
```
