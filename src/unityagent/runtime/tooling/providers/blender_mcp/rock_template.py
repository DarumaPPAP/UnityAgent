"""レビュー済み岩Template。BlenderはGeometry/FBXのみを制作し、Hash/ManifestはHostが確定する。"""
import json

ROCK_MARKER = "UNITYAGENT_ROCK_V1:"

def rock_template(fbx_path, manifest_path=None):
    """Blender MCP Safe Mode互換: hashlib/open/os/任意Scriptは実行しない。"""
    return """import bpy, json, math
from mathutils import Vector
output = """ + repr(str(fbx_path)) + """
name = "UnityAgentRock"
if bpy.data.objects.get(name) is not None:
    raise RuntimeError("Existing UnityAgentRock; scene reconciliation required")
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.5, location=(0,0,0))
rock = bpy.context.active_object
rock.name = name
for vertex in rock.data.vertices:
    p = vertex.co.copy()
    factor = 1.0 + 0.14 * math.sin(p.x*13 + p.y*7 + p.z*11)
    vertex.co = Vector((p.x*factor, p.y*factor*0.82, p.z*factor*0.72))
for polygon in rock.data.polygons:
    polygon.use_smooth = False
material = bpy.data.materials.new("UnityAgentRockMaterial")
material.diffuse_color = (0.32, 0.29, 0.25, 1.0)
rock.data.materials.append(material)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project()
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='DESELECT')
rock.select_set(True)
bpy.context.view_layer.objects.active = rock
bpy.ops.export_scene.fbx(filepath=output, use_selection=True, object_types={'MESH'},
    global_scale=1.0, apply_unit_scale=True, axis_forward='-Z', axis_up='Y',
    use_mesh_modifiers=True, add_leaf_bones=False, bake_anim=False, path_mode='AUTO')
record = {"schema_version":"1.0", "object_name":name, "vertices":len(rock.data.vertices),
    "triangles":sum(len(p.vertices)-2 for p in rock.data.polygons),
    "dimensions":list(rock.dimensions), "scale":list(rock.scale),
    "uv_layers":len(rock.data.uv_layers), "texture_dependencies":[]}
print("UNITYAGENT_ROCK_V1:" + json.dumps(record, sort_keys=True))
"""
