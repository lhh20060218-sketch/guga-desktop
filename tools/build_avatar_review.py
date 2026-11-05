"""Independent continuous-head prototype. NEVER writes resources/ or live config.
Blender: -b --python tools/build_avatar_review.py
"""
import bpy
import json
import math
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/avatar-review-20261026';OUT.mkdir(exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'resources/models/guga_3d/guga.blend'))
arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
arm.animation_data_clear()
for bone in arm.pose.bones:bone.rotation_euler=(0,0,0);bone.location=(0,0,0)
for ob in list(bpy.context.scene.objects):
    if ob.type=='MESH' and ob.get('motion_group') in ('head','hair','glasses'):
        bpy.data.objects.remove(ob,do_unlink=True)
new=[]
def xyz(p):return (p[0],-p[2],p[1])
def mat(name,c,metal=0,rough=.65):
    m=bpy.data.materials.new(name);m.use_nodes=True;m.diffuse_color=(*c,1)
    bs=m.node_tree.nodes['Principled BSDF'];bs.inputs['Base Color'].default_value=(*c,1)
    bs.inputs['Roughness'].default_value=rough;bs.inputs['Metallic'].default_value=metal
    return m
hood=mat('Review · soft black hood',(.045,.049,.057),rough=.52)
hair=mat('Review · dark warm hair',(.027,.021,.019),rough=.47)
skin=mat('Review · skin',(.95,.70,.54),rough=.75)
gold=mat('Review · triangular beak',(.98,.64,.08),rough=.48)
white=mat('Review · flat hood eye',(.96,.97,.95))
pupil=mat('Review · hood pupil',(.015,.022,.026))
blue=mat('Review · ribbon',(.26,.56,.67),metal=.1)
def attach(ob,material,group='head'):
    ob.data.materials.append(material);ob['motion_group']=group
    for p in ob.data.polygons:p.use_smooth=True
    ob.parent=arm
    g=ob.vertex_groups.new(name=group);g.add(list(range(len(ob.data.vertices))),1.,'REPLACE')
    m=ob.modifiers.new('Review rig','ARMATURE');m.object=arm
    new.append(ob);return ob
def sphere(name,location,size,material,group='head'):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48,ring_count=32,location=xyz(location))
    ob=bpy.context.object;ob.name=name;ob.scale=(size[0],size[2],size[1])
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return attach(ob,material,group)
def mesh(name,vertices,faces,material,group='head'):
    data=bpy.data.meshes.new(name);data.from_pydata([xyz(v) for v in vertices],[],faces);data.update()
    ob=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(ob)
    return attach(ob,material,group)

# A complete closed head, not a separate image plate in front of a sphere.
face=sphere('Review · continuous facial volume',(0,.49,.18),(.55,.58,.40),skin)
uv=face.data.uv_layers.active
mask=face.data.color_attributes.new(name='FaceFeatures',type='FLOAT_COLOR',domain='POINT')
def smooth(a,b,v):
    k=max(0,min(1,(v-a)/(b-a)));return k*k*(3-2*k)
for v in face.data.vertices:
    pos=face.matrix_world@v.co;x,y,z=pos.x,pos.z,-pos.y
    # Keep the original eyes/brows/mouth as surface coloration on the head.
    q=(x/.48)**4+((y-.48)/.31)**4
    w=(1-smooth(.55,1.1,q))*smooth(.28,.48,z)
    mask.data[v.index].color=(w,w,w,1)
for p in face.data.polygons:
    for li in p.loop_indices:
        pos=face.matrix_world@face.data.vertices[face.data.loops[li].vertex_index].co
        uv.data[li].uv=(.5+pos.x/1.10*.48,1-(.445-(pos.z-.5)*.187))
face_material=skin.copy();face_material.name='Review · original features on curved skin'
nodes=face_material.node_tree.nodes;links=face_material.node_tree.links
tex=nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(ROOT/'resources/expressions/playful_transparent.png'));tex.image.pack()
attr=nodes.new('ShaderNodeVertexColor');attr.layer_name='FaceFeatures'
mix=nodes.new('ShaderNodeMixRGB');mix.inputs[1].default_value=(.95,.70,.54,1)
links.new(attr.outputs['Color'],mix.inputs[0]);links.new(tex.outputs['Color'],mix.inputs[2])
links.new(mix.outputs[0],nodes['Principled BSDF'].inputs['Base Color'])
links.new(mix.outputs[0],nodes['Principled BSDF'].inputs['Emission Color'])
nodes['Principled BSDF'].inputs['Emission Strength'].default_value=.4
face.data.materials.clear();face.data.materials.append(face_material)
sphere('Review · nose',(0,.46,.572),(.025,.032,.034),skin)

# Smooth hood wraps from the front opening round the temples to the back.
# Profile rings are interpolated; no rectangular extruded silhouette shell.
profile=[(.61,.64,.48,.40),(.71,.78,.60,.39),(.84,.88,.64,.09),
         (.76,.82,.64,-.28),(.51,.63,.64,-.54),(.10,.16,.64,-.66)]
def cat(a,b,c,d,t):
    return .5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t)
verts=[];segments=80;rings=(len(profile)-1)*8+1
for i in range(rings):
    u=i/(rings-1)*(len(profile)-1);j=min(len(profile)-2,int(u));t=u-j
    values=[cat(profile[max(0,j-1)][k],profile[j][k],profile[j+1][k],profile[min(len(profile)-1,j+2)][k],t) for k in range(4)]
    rx,ry,cy,z=values
    for k in range(segments):
        a=k/segments*math.tau;verts.append((rx*math.cos(a),cy+ry*math.sin(a),z))
faces=[]
for i in range(rings-1):
    for k in range(segments):
        a=i*segments+k;b=i*segments+(k+1)%segments
        faces.append((a,b,b+segments,a+segments))
pole=len(verts);verts.append((0,.64,-.68))
for k in range(segments):faces.append(((rings-1)*segments+k,(rings-1)*segments+(k+1)%segments,pole))
cap=mesh('Review · continuous cloth hood',verts,faces,hood)
solid=cap.modifiers.new('Fabric thickness','SOLIDIFY');solid.thickness=.018
sub=cap.modifiers.new('Smooth cloth','SUBSURF');sub.levels=1

# Hair strands are tapered swept solids, not independent sausage spheres.
sphere('Review · bob volume',(0,.47,.05),(.66,.65,.42),hair,'hair')
def strand(name,points,widths,thickness=.035):
    vertices=[];sides=12
    for (x,y,z),w in zip(points,widths):
        for k in range(sides):
            a=k/sides*math.tau;vertices.append((x+w*math.cos(a),y,z+thickness*math.sin(a)))
    faces=[]
    for i in range(len(points)-1):
        for k in range(sides):
            a=i*sides+k;b=i*sides+(k+1)%sides;faces.append((a,b,b+sides,a+sides))
    faces.extend((tuple(reversed(range(sides))),tuple((len(points)-1)*sides+k for k in range(sides))))
    ob=mesh(name,vertices,faces,hair,'hair')
    sub=ob.modifiers.new('Soft tapered strand','SUBSURF');sub.levels=2
    return ob
# Connected fringe with a gently scalloped lower edge, avoiding bead-like bangs.
v=[];f=[];cols=56;rows=8
for row in range(rows+1):
    t=row/rows
    for col in range(cols+1):
        x=-.47+.94*col/cols
        bottom=.765+.035*abs(x)/.47+.009*math.cos(x*46)
        y=1.025*(1-t)+bottom*t
        z=.46+.13*t-.07*(abs(x)/.47)**2
        v.append((x,y,z))
for row in range(rows):
    for col in range(cols):
        a=row*(cols+1)+col;f.append((a,a+1,a+cols+2,a+cols+1))
fringe=mesh('Review · connected fringe',v,f,hair,'hair')
thickness=fringe.modifiers.new('Fringe thickness','SOLIDIFY');thickness.thickness=.018
rounding=fringe.modifiers.new('Soft fringe surface','SUBSURF');rounding.levels=1
for sign in (-1,1):
    for i in range(3):
        x=sign*(.51+.045*i)
        strand('Review · side lock %s %s'%(sign,i),[(x,.91,.28-i*.07),
            (x*1.10,.64,.35-i*.06),(x*1.10,.33,.39-i*.05),
            (x*1.15,.14+i*.025,.34-i*.04)], [.065,.095,.085,.014],.04)

def oval(name,center,normal,w,h,material):
    n=Vector(normal).normalized();up=Vector((0,1,0));up=(up-n*up.dot(n)).normalized();right=up.cross(n)
    v=[center];f=[]
    for i in range(64):
        a=i/64*math.tau;p=Vector(center)+right*(w*math.cos(a))+up*(h*math.sin(a));v.append(tuple(p))
    for i in range(64):f.append((0,i+1,(i+1)%64+1))
    ob=mesh(name,v,f,material)
    thick=ob.modifiers.new('Surface thickness','SOLIDIFY');thick.thickness=.004
    return ob
for sign in (-1,1):
    n=(sign*.12,.45,.88);c=(sign*.27,1.295,.436)
    oval('Review · flush hood eye',c,n,.078,.118,white)
    c=tuple(c[i]+Vector(n).normalized()[i]*.006 for i in range(3))
    oval('Review · flush hood pupil',c,n,.033,.061,pupil)
beak=mesh('Review · rounded triangular beak',[(0,1.255,.44),(-.23,1.105,.43),(.23,1.105,.43),
         (0,1.14,.63)],[(0,2,1),(0,1,3),(0,3,2),(1,2,3)],gold)
bev=beak.modifiers.new('Soft triangular edges','BEVEL');bev.width=.018;bev.segments=3
for sign in (-1,1):
    ob=sphere('Review · blue ribbon petal',(-.57+sign*.035,.92+sign*.05,.49),(.035,.12,.018),blue)
    ob.rotation_euler[1]=math.radians(-sign*42)

# Independent stage and render budget: 6 fixed angles + 2 head-turn poses.
scene=bpy.context.scene;scene.render.engine='BLENDER_EEVEE_NEXT'
scene.eevee.taa_render_samples=32
scene.render.resolution_x=360;scene.render.resolution_y=480;scene.render.resolution_percentage=100
scene.render.film_transparent=True;scene.view_settings.view_transform='Standard'
camera=scene.camera;camera.data.type='ORTHO';camera.data.ortho_scale=3.65
def camera_at(angle):
    a=math.radians(angle);camera.location=(7*math.sin(a),-7*math.cos(a),.35)
    camera.rotation_euler=(Vector((0,0,.10))-camera.location).to_track_quat('-Z','Y').to_euler()
camera_at(0)
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'candidate-continuous-head.blend'))
for angle in (0,35,-35,90,-90,180):
    camera_at(angle);scene.render.filepath=str(OUT/f'view-{angle}.png');bpy.ops.render.render(write_still=True)
camera_at(0)
for name,yaw,pitch in [('look-left',-14,-3),('look-right',14,-3)]:
    arm.pose.bones['head'].rotation_euler=(math.radians(pitch),math.radians(yaw),0)
    scene.render.filepath=str(OUT/(name+'.png'));bpy.ops.render.render(write_still=True)
arm.pose.bones['head'].rotation_euler=(0,0,0)
data=dict(candidate_only=True,approved_for_live=False,visual_review='pending',
    no_live_resource_writes=True,facial_volume_depth_ratio=round(.8/1.1,3),
    has_separate_image_plate=False,views=[0,35,-35,90,-90,180],head_pose_views=['look-left','look-right'])
(OUT/'candidate-audit.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
print('REVIEW_CANDIDATE_CREATED',str(OUT))
