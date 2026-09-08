from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import wave

import bpy


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import studiotwin  # noqa: E402


def _expect_value_error(callback) -> None:
    try:
        callback()
    except ValueError:
        return
    raise AssertionError("Expected ValueError")


def _write_image(filepath: Path, color: tuple[float, float, float, float]) -> None:
    image = bpy.data.images.new(filepath.stem, width=2, height=2)
    image.generated_color = color
    image.filepath_raw = str(filepath)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def _write_audio(filepath: Path) -> None:
    with wave.open(str(filepath), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(struct.pack("<800h", *([0] * 800)))


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        environment_path = directory / "environment.png"
        albedo_path = directory / "albedo.png"
        height_path = directory / "height.png"
        metalness_path = directory / "metalness.png"
        normals_path = directory / "normals.png"
        roughness_path = directory / "roughness.png"
        audio_path = directory / "sound.wav"
        model_path = directory / "model.glb"
        _write_image(environment_path, (0.1, 0.2, 0.4, 1.0))
        _write_image(albedo_path, (0.4, 0.2, 0.1, 1.0))
        _write_image(height_path, (0.5, 0.5, 0.5, 1.0))
        _write_image(metalness_path, (0.2, 0.2, 0.2, 1.0))
        _write_image(normals_path, (0.5, 0.5, 1.0, 1.0))
        _write_image(roughness_path, (0.5, 0.5, 0.5, 1.0))
        _write_audio(audio_path)

        unsupported_environment = directory / "environment.exr"
        unsupported_environment.touch()
        unsupported_model = directory / "model.gltf"
        unsupported_model.touch()
        _expect_value_error(
            lambda: studiotwin.apply_environment_map(str(unsupported_environment))
        )
        _expect_value_error(lambda: studiotwin.import_model(str(unsupported_model)))
        _expect_value_error(
            lambda: studiotwin.import_material({"basecolor": str(albedo_path)})
        )

        world_before = bpy.context.scene.world
        if world_before is None:
            world_before = bpy.data.worlds.new("StudioTwin Smoke Test World")
            bpy.context.scene.world = world_before
        world_count_before = len(bpy.data.worlds)
        environment = studiotwin.apply_environment_map(str(environment_path))
        world = bpy.context.scene.world
        assert world is world_before
        assert len(bpy.data.worlds) == world_count_before
        nodes = world.node_tree.nodes
        env_node = nodes["StudioTwin Environment"]
        assert environment == {
            "type": "environment_map",
            "filepath": str(environment_path.resolve()),
            "image": env_node.image.name,
            "world": world.name,
        }
        background = nodes["Background"]
        assert Path(bpy.path.abspath(env_node.image.filepath)).resolve() == (
            environment_path.resolve()
        )
        assert not env_node.inputs["Vector"].is_linked
        assert any(
            link.from_node == env_node and link.to_node == background
            for link in world.node_tree.links
        )
        viewports = [
            area.spaces.active
            for window in bpy.context.window_manager.windows
            for area in window.screen.areas
            if area.type == "VIEW_3D"
        ]
        assert all(viewport.shading.type == "RENDERED" for viewport in viewports)

        bpy.ops.mesh.primitive_cube_add()
        source = bpy.context.object
        bpy.ops.export_scene.gltf(
            filepath=str(model_path),
            export_format="GLB",
            use_selection=True,
        )
        bpy.data.objects.remove(source, do_unlink=True)
        model = studiotwin.import_model(str(model_path))
        assert model["meshes"]

        target = bpy.data.objects[model["meshes"][0]]
        material_count_before = len(target.data.materials)
        material = studiotwin.import_material(
            {
                "albedo": str(albedo_path),
                "heightmap": str(height_path),
                "metalness": str(metalness_path),
                "normals": str(normals_path),
                "roughness": str(roughness_path),
            }
        )
        assert len(target.data.materials) == material_count_before
        assert "object" not in material
        second_material = studiotwin.import_material({"albedo": str(albedo_path)})
        assert second_material["material"] != material["material"]
        assert material["material"] in bpy.data.materials
        assert second_material["material"] in bpy.data.materials

        audio = studiotwin.import_audio(str(audio_path), frame_start=1)
        assert audio["frameStart"] == 1

        result = {
            "audio": audio,
            "environment": environment,
            "material": material,
            "model": model,
        }
        print("StudioTwin importer smoke test passed")
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
