"""Run with Blender 4.2+: blender -b --python tools/build_blender_avatar.py.

Creates an editable, rigid-skinned chibi Guga, GLB and compact Qt mesh bundle.
Only existing local expression art is used; no downloaded character assets.
Runtime coordinates are X right / Y up / Z toward the viewer.
"""
import bpy
import gzip
import json
import math
import sys
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'resources/models/guga_3d'
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)


def xyz(v):
    return (v[0], -v[2], v[1])


def runtime(v):
    return [round(v[0], 5), round(v[2], 5), round(-v[1], 5)]


def material(name, color, metallic=0., roughness=.48):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    m['display_color'] = list(color)
    return m


ink = material('Hood · soft charcoal', (.075, .085, .105), roughness=.38)
hair = material('Hair · warm espresso', (.055, .045, .044), roughness=.42)
ivory = material('Belly · warm porcelain', (.92, .90, .85), roughness=.65)
skin = material('Face · peach', (.98, .77, .64), roughness=.64)
gold = material('Beak and feet · butter yellow', (.98, .65, .12), roughness=.38)
silver = material('Scarf clasp · satin silver', (.55, .59, .61), .65, .26)
red = material('Scarf tab · coral', (.76, .19, .17))
white = material('Hood eyes · cream', (.97, .98, .97))
black = material('Pupils and lenses', (.018, .029, .045), .15, .22)
blue = material('Hairpin · ice blue', (.39, .69, .77), .3)
shine = material('Lens reflections', (.48, .79, .92), .45)
meshes = []


def finish(obj, mat, group):
    obj.data.materials.append(mat)
    obj['motion_group'] = group
    for poly in obj.data.polygons:
        poly.use_smooth = True
    meshes.append(obj)
    return obj


def ellipsoid(name, loc, size, mat, group='body', rotation=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=20, location=xyz(loc))
    ob = bpy.context.object
    ob.name = name
    ob.scale = (size[0], size[2], size[1])
    if rotation:
        # Rotation about the runtime Z axis (depth).
        ob.rotation_euler[1] = -math.radians(rotation)
    return finish(ob, mat, group)


def tube(name, points, radius, mat, group='head'):
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth, curve.bevel_resolution = radius, 3
    spl = curve.splines.new('BEZIER')
    spl.bezier_points.add(len(points) - 1)
    for b, point in zip(spl.bezier_points, points):
        b.co = xyz(point)
        b.handle_left_type = b.handle_right_type = 'AUTO'
    ob = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.convert(target='MESH')
    ob = bpy.context.object
    ob.select_set(False)
    return finish(ob, mat, group)


# Volumes remain real geometry on the sides and back.
ellipsoid('Suit', (0, -.53, 0), (.63, .76, .48), ink)
ellipsoid('Belly', (0, -.57, .32), (.48, .61, .23), ivory)
for sign, label in ((-1, 'left'), (1, 'right')):
    ellipsoid('Flipper ' + label, (sign * .69, -.42, .015), (.16, .49, .16), ink,
              'wing_' + label, rotation=sign * 28)
    ellipsoid('Foot ' + label, (sign * .32, -1.24, .17), (.24, .105, .30), gold,
              'foot_' + label)
from tools.blender_reference_head import build_reference_head
reference_image = build_reference_head(bpy, ROOT, ellipsoid, finish, ink)

# Collar and the familiar metal clasp, modelled as rounded curves.
tube('Collar', [(-.48, .08, .39), (-.3, -.02, .55), (0, -.07, .58), (.3, -.02, .55), (.48, .08, .39)], .052, silver, 'body')
ellipsoid('Coral tab', (-.29, -.05, .59), (.067, .08, .035), red)
for i in range(2):
    x, y, z = .035 + i * .075, -.12 - i * .15, .66 + i * .02
    tube('Chain link %s' % i, [(x-.06, y+.08, z), (x-.09, y+.13, z),
         (x-.02, y+.14, z), (x+.12, y-.08, z), (x+.10, y-.13, z),
         (x+.04, y-.12, z), (x-.06, y+.08, z)], .025, silver, 'body')

# Accessories use the same head anchor and turn together with the face.
for sign in (-1, 1):
    ellipsoid('Sunglasses lens', (sign * .28, .35, .72), (.23, .105, .025), black, 'glasses')
    tube('Sunglasses glint', [(sign*.28-.09, .39, .747), (sign*.28-.02, .32, .748)], .012, shine, 'glasses')
tube('Sunglasses bridge', [(-.06, .38, .72), (0, .40, .73), (.06, .38, .72)], .023, black, 'glasses')
for sign in (-1, 1):
    tube('Sunglasses arm', [(sign * .48, .39, .71), (sign * .65, .41, .42)], .02, black, 'glasses')

# Export a small, versioned mesh bundle for the existing Qt application.
deps = bpy.context.evaluated_depsgraph_get()
bundle = {'version': 1, 'coordinates': 'x-right,y-up,z-front', 'projection': 'orthographic', 'meshes': [],
          'pivots': {'body': [0, -.4, 0], 'head': [0, .16, 0], 'hair': [0, .75, .2],
                     'wing_left': [-.55, -.08, 0], 'wing_right': [.55, -.08, 0],
                     'foot_left': [-.32, -1.15, .1], 'foot_right': [.32, -1.15, .1],
                     'glasses': [0, .16, 0]}}
for ob in meshes:
    ev = ob.evaluated_get(deps)
    mesh = ev.to_mesh()
    mesh.calc_loop_triangles()
    matrix = ob.matrix_world
    normal_matrix = matrix.to_3x3().inverted().transposed()
    flat = []
    for tri in mesh.loop_triangles:
        for li in tri.loops:
            loop = mesh.loops[li]
            vertex = mesh.vertices[loop.vertex_index]
            normal = (normal_matrix @ vertex.normal).normalized()
            uv_coord = list(mesh.uv_layers.active.data[li].uv) if mesh.uv_layers.active else [0., 0.]
            flat.extend(runtime(matrix @ vertex.co) + runtime(normal) + [round(x, 5) for x in uv_coord])
    bundle['meshes'].append({'name': ob.name, 'group': ob['motion_group'],
                            'color': list(ob.data.materials[0]['display_color']),
                            'textured': bool(ob.get('expression_texture')), 'vertices': flat})
    ev.to_mesh_clear()
with gzip.open(OUT / 'avatar.mesh.json.gz', 'wt', encoding='utf-8') as f:
    json.dump(bundle, f, separators=(',', ':'))

# A real armature + rigid weights keeps the generated .blend/GLB editable.
arm_data = bpy.data.armatures.new('Guga skeleton')
arm = bpy.data.objects.new('Guga · animation rig', arm_data)
bpy.context.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
bones = {}
for group, pivot in {'root': [0,0,0], **bundle['pivots']}.items():
    bone = arm_data.edit_bones.new(group)
    bone.head = xyz(pivot)
    bone.tail = xyz([pivot[0], pivot[1]+.18, pivot[2]])
    bones[group] = bone
for name, bone in bones.items():
    if name != 'root':
        bone.parent = bones['head' if name in ('hair', 'glasses') else 'root']
bpy.ops.object.mode_set(mode='OBJECT')
for ob in meshes:
    group = ob.vertex_groups.new(name=ob['motion_group'])
    group.add(list(range(len(ob.data.vertices))), 1., 'REPLACE')
    modifier = ob.modifiers.new('Guga rigid skinning', 'ARMATURE')
    modifier.object = arm
    ob.parent = arm
for bone in arm.pose.bones:
    bone.rotation_mode = 'XYZ'

from ui.avatar_motion import AvatarMotion
scene = bpy.context.scene
scene.render.fps = 30
for clip, length in [('idle', 4), ('spin', 2.2), ('sneak_peek', 3), ('dance', 4), ('wave', 1.8)]:
    action = bpy.data.actions.new(clip)
    arm.animation_data_create()
    arm.animation_data.action = action
    motion = AvatarMotion()
    if clip == 'dance': motion.dancing = True
    elif clip != 'idle': motion.trigger_action(clip)
    frames = int(length * 30)
    for frame in range(1, frames + 1):
        p = motion.advance(1/30)
        root, head = arm.pose.bones['root'], arm.pose.bones['head']
        root.rotation_euler = (0, math.radians(p.yaw), math.radians(p.roll))
        root.location = (p.side, p.lift, 0)
        head.rotation_euler = (math.radians(p.head_pitch), math.radians(p.head_yaw), math.radians(p.head_roll))
        arm.pose.bones['hair'].rotation_euler[2] = math.radians(p.hair)
        arm.pose.bones['wing_left'].rotation_euler[2] = math.radians(-p.wing_left)
        arm.pose.bones['wing_right'].rotation_euler[2] = math.radians(p.wing_right)
        for bone in arm.pose.bones:
            bone.keyframe_insert('rotation_euler', frame=frame, group=bone.name)
        root.keyframe_insert('location', frame=frame, group='root')
    track = arm.animation_data.nla_tracks.new()
    track.name = clip
    track.strips.new(clip, 1, action)
    track.mute = True
arm.animation_data.action = None
for bone in arm.pose.bones:
    bone.rotation_euler = (0, 0, 0)
    bone.location = (0, 0, 0)
# Glasses hidden by default in the authoring scene (runtime toggles by group).
for ob in meshes:
    if ob['motion_group'] == 'glasses':
        ob.hide_render = True
scene.frame_start, scene.frame_end = 1, 120
scene.frame_set(1)
scene.world.color = (.18, .20, .25)
scene.render.engine = 'BLENDER_EEVEE_NEXT'
scene.render.resolution_x, scene.render.resolution_y = 600, 800
scene.render.resolution_percentage = 100
scene.render.film_transparent = True
bpy.ops.object.camera_add(location=(3.8, -7.5, 2.6))
camera = bpy.context.object
direction = Vector((0, 0, .2)) - camera.location
camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
camera.data.type, camera.data.ortho_scale = 'ORTHO', 3.8
scene.camera = camera
for loc, energy, size in [((-3,-4,6), 650, 5), ((4,-1,3), 400, 4), ((0,3,5), 800, 3)]:
    bpy.ops.object.light_add(type='AREA', location=loc)
    light = bpy.context.object
    light.data.energy, light.data.shape, light.data.size = energy, 'DISK', size
    light.rotation_euler = (-light.location).to_track_quat('-Z', 'Y').to_euler()
# Reference image is packed for future hand sculpting.
reference = bpy.data.objects.new('REFERENCE · original Guga (not rendered)', None)
reference.empty_display_type = 'IMAGE'
reference.data = reference_image
reference.location = (2.5, 0, .5)
bpy.context.collection.objects.link(reference)
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'guga.blend'))
bpy.ops.object.select_all(action='DESELECT')
for ob in meshes + [arm]:
    ob.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.export_scene.gltf(filepath=str(OUT / 'guga.glb'), use_selection=True,
                          export_format='GLB', export_animations=True, export_animation_mode='NLA_TRACKS')
scene.render.filepath = str(OUT / 'blender-preview.png')
bpy.ops.render.render(write_still=True)
print('GUGA_AVATAR_OK', len(meshes), 'meshes;', sum(len(m['vertices'])//24 for m in bundle['meshes']), 'triangles')
