"""Bake the runtime motion into a COPY of the approved model; never rebuild it.

blender -b --python tools/export_blender_motions.py
Outputs go to runtime/motion-v2, leaving all source model assets unchanged.
"""
import bpy
import hashlib
import json
import math
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ui.avatar_motion import AvatarMotion

out=ROOT/'runtime/motion-v2';out.mkdir(exist_ok=True)
source=ROOT/'resources/models/guga_3d/guga.blend'
bpy.ops.wm.open_mainfile(filepath=str(source))
arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']

def geometry_hash():
    h=hashlib.sha256()
    for ob in sorted(meshes,key=lambda o:o.name):
        h.update(ob.name.encode())
        for v in ob.data.vertices:h.update(repr(tuple(v.co)).encode())
        for poly in ob.data.polygons:h.update(repr(tuple(poly.vertices)).encode())
    return h.hexdigest()

before=geometry_hash()
# The metal links get an attachment bone; their vertices are not remodeled.
if 'pendant' not in arm.data.bones:
    bpy.context.view_layer.objects.active=arm
    bpy.ops.object.mode_set(mode='EDIT')
    b=arm.data.edit_bones.new('pendant')
    b.head=(.03,-.66,-.08);b.tail=(.03,-.66,.10)
    b.parent=arm.data.edit_bones['root']
    bpy.ops.object.mode_set(mode='OBJECT')
    for ob in meshes:
        if ob.name.startswith('Chain link'):
            for group in list(ob.vertex_groups):ob.vertex_groups.remove(group)
            ob.vertex_groups.new(name='pendant').add(list(range(len(ob.data.vertices))),1.,'REPLACE')
arm.animation_data_clear();arm.animation_data_create()
for bone in arm.pose.bones:bone.rotation_mode='XYZ'

actions={}
for name,seconds in [('idle',4),('spin',2.6),('sneak_peek',3.4),('wave',2.2),
                     ('dance',4),('bounce',1.5),('nod',1.8)]:
    action=bpy.data.actions.new('motion_v2_'+name);actions[name]=action
    arm.animation_data.action=action
    m=AvatarMotion()
    if name!='idle':m.trigger_action(name)
    for frame in range(1,round(seconds*30)+1):
        p=m.advance(1/30)
        for bone in arm.pose.bones:
            bone.rotation_euler=(0,0,0);bone.location=(0,0,0);bone.scale=(1,1,1)
        def rotate(name,x=0,y=0,z=0):
            arm.pose.bones[name].rotation_euler=tuple(math.radians(v) for v in (x,y,z))
        root=arm.pose.bones['root']
        rotate('root',p.pitch,p.yaw,p.roll)
        root.location=(p.side,p.lift,p.depth)
        root.scale=(1/math.sqrt(p.squash),p.squash,1/math.sqrt(p.squash))
        rotate('head',p.head_pitch,p.head_yaw,p.head_roll)
        rotate('wing_left',p.wing_left_pitch,p.wing_left_yaw,-p.wing_left)
        rotate('wing_right',p.wing_right_pitch,p.wing_right_yaw,p.wing_right)
        rotate('foot_left',p.foot_left_pitch,p.foot_left_yaw)
        rotate('foot_right',p.foot_right_pitch,p.foot_right_yaw)
        arm.pose.bones['foot_left'].location[1]=p.foot_left_lift
        arm.pose.bones['foot_right'].location[1]=p.foot_right_lift
        rotate('pendant',-p.pitch*.2,0,p.pendant_roll)
        for bone in arm.pose.bones:
            for prop in ('rotation_euler','location','scale'):
                bone.keyframe_insert(prop,frame=frame,group=bone.name)
    track=arm.animation_data.nla_tracks.new();track.name=name
    track.strips.new(name,1,action);track.mute=True

arm.animation_data.action=None
for bone in arm.pose.bones:
    bone.rotation_euler=(0,0,0);bone.location=(0,0,0);bone.scale=(1,1,1)
bpy.context.scene.frame_set(1)
assert before==geometry_hash(),'Motion bake must not alter model geometry'
bpy.ops.object.select_all(action='DESELECT')
for ob in meshes+[arm]:ob.select_set(True)
bpy.context.view_layer.objects.active=arm
bpy.ops.export_scene.gltf(filepath=str(out/'guga-actions-v2.glb'),use_selection=True,
    export_format='GLB',export_animations=True,export_animation_mode='NLA_TRACKS')
arm.animation_data.action=actions['dance']
bpy.context.scene.frame_start=1;bpy.context.scene.frame_end=120
bpy.context.scene.frame_set(25)
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(out/'guga-actions-v2.blend'))
result=dict(ok=True,geometry_unchanged=True,geometry_hash=before,clips=list(actions),
            source_untouched=str(source),output=str(out/'guga-actions-v2.blend'))
(out/'blender-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('GUGA_MOTION_BAKE_OK',json.dumps(result))
