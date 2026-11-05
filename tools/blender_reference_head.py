"""Reference-projected head: preserve authored silhouette instead of re-inventing it.

This is a curved 2.5D shell plus a back volume, not a fully sculpted face.
"""
import math


def build_reference_head(bpy, root, ellipsoid, finish, ink):
    image = bpy.data.images.load(str(root / 'resources/expressions/normal_transparent.png'))
    image.pack()
    width, height = image.size
    pixels = list(image.pixels)
    # Use the whole authored hood/hair/face, not just a cropped face disk.
    # Relative dimensions follow the original head (about 60% of its height).
    scale = 1.88 / width
    cut_y = height * .595
    cols, rows = 84, 72
    verts, uvs, mask = [], [], []
    for row in range(rows + 1):
        py = row / rows * cut_y
        vertical = (py - cut_y * .49) / (cut_y * .56)
        for col in range(cols + 1):
            px = col / cols * width
            x = (px - width/2) * scale
            horizontal = x / .96
            depth = .08 + .58 * math.sqrt(max(0., 1-horizontal*horizontal)) * math.sqrt(max(.06, 1-vertical*vertical))
            verts.append((x, -depth, 1.49-py*scale))
            uvs.append((px/width, 1-py/height))
            ix, iy = min(width-1, int(px)), min(height-1, max(0,int(height-1-py)))
            mask.append(pixels[(iy*width+ix)*4+3] > .03)
    faces = []
    stride = cols+1
    for row in range(rows):
        for col in range(cols):
            a = row*stride+col
            for tri in ((a,a+stride,a+1),(a+1,a+stride,a+stride+1)):
                if any(mask[i] for i in tri): faces.append(tri)
    mesh = bpy.data.meshes.new('Reference silhouette · curved UV shell')
    mesh.from_pydata(verts, [], faces)
    mesh.uv_layers.new(name='Full original head')
    mesh.update()
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            mesh.uv_layers.active.data[li].uv = uvs[mesh.loops[li].vertex_index]
    mat = bpy.data.materials.new('Original head · unlit colors')
    mat.use_nodes = True
    mat['display_color'] = [1.,1.,1.]
    nodes = mat.node_tree.nodes
    nodes.clear()
    tex = nodes.new('ShaderNodeTexImage');tex.image=image
    emission=nodes.new('ShaderNodeEmission')
    transparent=nodes.new('ShaderNodeBsdfTransparent')
    mix=nodes.new('ShaderNodeMixShader')
    output=nodes.new('ShaderNodeOutputMaterial')
    links=mat.node_tree.links
    links.new(tex.outputs['Color'],emission.inputs['Color'])
    links.new(tex.outputs['Alpha'],mix.inputs[0])
    links.new(transparent.outputs[0],mix.inputs[1])
    links.new(emission.outputs[0],mix.inputs[2])
    links.new(mix.outputs[0],output.inputs['Surface'])
    mat.surface_render_method='DITHERED'
    ob=bpy.data.objects.new('Head · original hood hair face and ribbon',mesh)
    bpy.context.collection.objects.link(ob)
    finish(ob,mat,'head')
    ob['expression_texture']=True
    # Close the very same silhouette into a volume. A separate spherical fill
    # leaves a visible gap behind the face when the head turns sideways.
    back=[]
    for x, front_depth, z in verts:
        u=x/.96
        vertical=(z-.68)/.90
        depth=.12+.39*math.sqrt(max(0.,1-u*u))*math.sqrt(max(.03,1-vertical*vertical))
        back.append((x,depth,z))
    n=len(verts)
    edges={}
    for tri in faces:
        for a,b in zip(tri,(tri[1],tri[2],tri[0])):
            key=tuple(sorted((a,b)))
            if key in edges:edges[key]=None
            else:edges[key]=(a,b)
    shell_faces=[tuple(n+i for i in reversed(tri)) for tri in faces]
    for edge in edges.values():
        if edge is not None:
            a,b=edge
            shell_faces.extend(((a,b,n+b),(a,n+b,n+a)))
    shell=bpy.data.meshes.new('Original contour · closed sides and back')
    shell.from_pydata(verts+back,[],shell_faces)
    shell.update()
    shell_ob=bpy.data.objects.new('Hood · continuous side and back',shell)
    bpy.context.collection.objects.link(shell_ob)
    finish(shell_ob,ink,'head')
    return image
