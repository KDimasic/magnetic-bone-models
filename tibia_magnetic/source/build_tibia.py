import bpy, bmesh, trimesh, numpy as np, math, os, json, struct
from scipy.spatial.transform import Rotation
from mathutils import Vector

ROOT='/mnt/agents/output/tibia_magnetic'
PARTS=ROOT+'/parts'
CHECKS=ROOT+'/checks'
os.makedirs(PARTS,exist_ok=True); os.makedirs(CHECKS,exist_ok=True)

# Parameters, mm
LENGTH=400.0
CUT_LOW=85.0
CUT_HIGH=320.0
INNER_SCALE=0.74
END_WALL=3.2
MAG_R=3.10       # Ø6.20 pocket for Ø6.00 magnet
MAG_DEPTH=3.20   # for 3.00 mm magnet
BOSS_R=4.60
LONG_Z=[130.0,205.0,280.0]
TRANSVERSE_Y=[-5.0,7.0]

# Reset
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
for datablocks in (bpy.data.meshes,bpy.data.curves,bpy.data.materials,bpy.data.cameras,bpy.data.lights):
    pass

# Load, orient and scale anatomical source. Output coordinates are metres.
src=trimesh.load(ROOT+'/source/right-tibia.stl')
v=src.vertices.copy()
v[:,1]-=v[:,1].min(); v*=.4/v[:,1].max()
v=np.column_stack([v[:,0],-v[:,2],v[:,1]])
# Align the diaphysis centreline to Z using ten cross-sections.
cs=[]
for z in np.linspace(.09,.315,10):
    sec=trimesh.Trimesh(v,src.faces).section(plane_origin=[0,0,z],plane_normal=[0,0,1])
    p=sec.vertices
    cs.append([z,*((p[:,:2].min(0)+p[:,:2].max(0))/2)])
cs=np.array(cs)
fx=np.polyfit(cs[:,0],cs[:,1],1); fy=np.polyfit(cs[:,0],cs[:,2],1)
d=np.array([fx[0],fy[0],1.]); d/=np.linalg.norm(d)
R=Rotation.align_vectors([[0,0,1]],[d])[0].as_matrix()
v=v@R.T
c0=R@np.array([np.polyval(fx,.2),np.polyval(fy,.2),.2])
v-=c0; v[:,2]+=.2
# Exact overall Z length, uniform scale; set distal tip to Z=0.
v*=LENGTH/((v[:,2].max()-v[:,2].min())*1000.0)
v[:,2]-=v[:,2].min()
base_mm=v*1000.0
base_tm=trimesh.Trimesh(base_mm,src.faces)
base_tm.export(ROOT+'/source/tibia_aligned_400mm.stl')

# Determine longitudinal boss centres from actual exterior at Y=0.
def x_intersections_at_y0(mesh,z):
    sec=mesh.section(plane_origin=[0,0,z/1000.0],plane_normal=[0,0,1])
    if sec is None: raise RuntimeError('No section')
    p=sec.vertices*1000.0
    xs=[]
    # section contains multiple 3D edges; intersect each edge with Y=0
    for ent in sec.entities:
        pts=p[ent.points]
        for a,b in zip(pts[:-1],pts[1:]):
            if (a[1]==0): xs.append(a[0])
            if (a[1]-0)*(b[1]-0)<0:
                t=(0-a[1])/(b[1]-a[1]); xs.append(a[0]+t*(b[0]-a[0]))
    if not xs:
        # fallback nearest vertices
        xs=[p[np.argmin(abs(p[:,1])),0]]
    return min(xs),max(xs)

LONG_X=[]
for z in LONG_Z:
    xl,xr=x_intersections_at_y0(trimesh.Trimesh(v,src.faces),z)
    # Asymmetric inset follows the actual shaft curvature: the right-side
    # pocket needs additional depth to remain behind the external surface.
    LONG_X.append((xl+4.0,xr-6.0))
print('Longitudinal boss X:',LONG_X)


def mesh_obj(name, verts_m, faces):
    me=bpy.data.meshes.new(name+'_mesh'); me.from_pydata(verts_m,[],faces); me.update()
    ob=bpy.data.objects.new(name,me); bpy.context.collection.objects.link(ob)
    bm=bmesh.new(); bm.from_mesh(me); bmesh.ops.recalc_face_normals(bm,faces=bm.faces); bm.to_mesh(me); bm.free()
    return ob

base=mesh_obj('Анатомическая_основа',v,src.faces)

def activate(ob):
    bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active=ob

def apply_bool(ob,cutter,operation='DIFFERENCE'):
    activate(ob)
    mod=ob.modifiers.new(operation+'_'+cutter.name,'BOOLEAN'); mod.operation=operation; mod.solver='EXACT'; mod.object=cutter
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter,do_unlink=True)

def box(name,center,size):
    bpy.ops.mesh.primitive_cube_add(size=1,location=Vector(center)*.001)
    ob=bpy.context.object; ob.name=name; ob.dimensions=Vector(size)*.001
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return ob

def cyl(name,center,radius,depth,axis='Z',vertices=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius*.001,depth=depth*.001,end_fill_type='NGON',location=Vector(center)*.001)
    ob=bpy.context.object; ob.name=name
    if axis=='Y': ob.rotation_euler[0]=math.pi/2
    elif axis=='X': ob.rotation_euler[1]=math.pi/2
    bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    return ob

def copy_obj(ob,name):
    new=ob.copy(); new.data=ob.data.copy(); new.name=name; bpy.context.collection.objects.link(new); return new

def clip(ob,axis,lo,hi,name):
    center=[0,0,200]; size=[300,300,600]
    center[axis]=(lo+hi)/2; size[axis]=hi-lo
    cutter=box(name+'_clip',center,size)
    apply_bool(ob,cutter,'INTERSECT'); ob.name=name
    return ob

# Coarse complete structure
prox=clip(copy_obj(base,'prox'),2,0,CUT_LOW,'01_Нижняя_секция')
dist=clip(copy_obj(base,'dist'),2,CUT_HIGH,LENGTH+5,'04_Верхняя_секция')
mid_outer=clip(copy_obj(base,'mid_outer'),2,CUT_LOW,CUT_HIGH,'Средняя_наружная')
# Hollow with matching anatomical internal profile and 3.2 mm end walls.
inner=copy_obj(base,'inner')
for vert in inner.data.vertices:
    vert.co.x*=INNER_SCALE; vert.co.y*=INNER_SCALE
inner=clip(inner,2,CUT_LOW+END_WALL,CUT_HIGH-END_WALL,'Внутренняя_полость')
mid=copy_obj(mid_outer,'mid')
apply_bool(mid,inner,'DIFFERENCE'); mid.name='Средняя_полая'

# Internal reinforced pads, trimmed to the external anatomical silhouette.
def trimmed_boss(center,radius,depth,axis,name):
    b=cyl(name,center,radius,depth,axis)
    envelope=copy_obj(mid_outer,name+'_envelope')
    apply_bool(b,envelope,'INTERSECT')
    apply_bool(mid,b,'UNION')

for y in TRANSVERSE_Y:
    trimmed_boss([0,y,CUT_LOW+4.0],BOSS_R,10.0,'Z','Нижний_торцевой_босс')
    trimmed_boss([0,y,CUT_HIGH-4.0],BOSS_R,10.0,'Z','Верхний_торцевой_босс')
for z,(xl,xr) in zip(LONG_Z,LONG_X):
    for x in (xl,xr):
        trimmed_boss([x,0,z],5.5,18.0,'Y','Продольный_босс')

# Split the hollow middle into two closed longitudinal halves.
mid_neg=clip(copy_obj(mid,'mid_neg'),1,-100,0,'02_Средняя_половина_A')
mid_pos=clip(copy_obj(mid,'mid_pos'),1,0,100,'03_Средняя_половина_B')
bpy.data.objects.remove(mid,do_unlink=True)
bpy.data.objects.remove(mid_outer,do_unlink=True)
bpy.data.objects.remove(base,do_unlink=True)

# Pocket cutter with 0.1 mm Boolean overcut beyond the mating face.
def axial_pocket(ob,center,axis,axis_index,sign):
    # sign points into the part; cutter spans face-overcut to exact depth
    c=np.array(center,dtype=float)
    # Face is at centre; range is -0.1 opposite sign to +depth along sign
    c[axis_index]+=sign*(MAG_DEPTH-0.1)/2
    cutter=cyl('Паз_магнита_6x3',c,MAG_R,MAG_DEPTH+0.1,axis)
    apply_bool(ob,cutter,'DIFFERENCE')

# Transverse interfaces: one pair in each longitudinal half.
for y in TRANSVERSE_Y:
    axial_pocket(prox,[0,y,CUT_LOW],'Z',2,-1)  # into proximal, downward
    axial_pocket(mid_neg if y<0 else mid_pos,[0,y,CUT_LOW],'Z',2,+1)
    axial_pocket(mid_neg if y<0 else mid_pos,[0,y,CUT_HIGH],'Z',2,-1)
    axial_pocket(dist,[0,y,CUT_HIGH],'Z',2,+1)
# Longitudinal paired interfaces.
for ob,sign in [(mid_neg,-1),(mid_pos,+1)]:
    for z,(xl,xr) in zip(LONG_Z,LONG_X):
        for x in (xl,xr):
            axial_pocket(ob,[x,0,z],'Y',1,sign)

# Normalise the two complex Boolean results with a fine voxel pass (0.30 mm).
# This removes coincident internal faces while retaining the 6.2 mm pockets.
for ob in (mid_neg,mid_pos):
    activate(ob)
    mod=ob.modifiers.new('Топология_0_30мм','REMESH'); mod.mode='VOXEL'; mod.voxel_size=0.00030; mod.use_smooth_shade=True
    bpy.ops.object.modifier_apply(modifier=mod.name)

parts=[prox,mid_neg,mid_pos,dist]
# Recalculate normals and assign glTF-compatible colours.
colors=[(0.82,0.72,0.52,1),(0.65,0.78,0.88,1),(0.88,0.68,0.48,1),(0.74,0.80,0.60,1)]
for ob,col in zip(parts,colors):
    activate(ob)
    bm=bmesh.new(); bm.from_mesh(ob.data); bmesh.ops.recalc_face_normals(bm,faces=bm.faces); bm.to_mesh(ob.data); bm.free()
    for p in ob.data.polygons: p.use_smooth=True
    mat=bpy.data.materials.new(ob.name+'_материал'); mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get('Principled BSDF'); bsdf.inputs['Base Color'].default_value=col; bsdf.inputs['Roughness'].default_value=.38
    ob.data.materials.clear(); ob.data.materials.append(mat)
    ob['units']='metres; printing STL and 3MF in millimetres'
    ob['magnet_pocket_mm']='6.20 diameter x 3.20 deep; magnet 6 x 3'

# Save editable source without a backup copy on the mounted delivery volume.
bpy.context.preferences.filepaths.save_version=0
try:
    bpy.ops.wm.save_as_mainfile(filepath=ROOT+'/Большеберцовая_кость_магнитная.blend',check_existing=False,compress=True)
except RuntimeError as exc:
    print('Blend save deferred:',exc)

# Export watertight print parts in mm using Trimesh from evaluated Blender meshes.
manifest=[]
for ob in parts:
    dg=bpy.context.evaluated_depsgraph_get(); ev=ob.evaluated_get(dg); me=ev.to_mesh()
    verts=np.array([tuple(ob.matrix_world@v.co) for v in me.vertices])*1000.0
    me.calc_loop_triangles()
    faces=[tuple(t.vertices) for t in me.loop_triangles]
    ev.to_mesh_clear()
    tm=trimesh.Trimesh(verts,faces,process=True)
    path=PARTS+'/'+ob.name+'.stl'; tm.export(path)
    re=trimesh.load(path)
    manifest.append({'name':ob.name,'file':os.path.basename(path),'vertices':len(re.vertices),'triangles':len(re.faces),'watertight':bool(re.is_watertight),'volume_mm3':float(re.volume),'bounds_mm':re.bounds.tolist(),'extents_mm':re.extents.tolist()})
print(json.dumps(manifest,ensure_ascii=False,indent=2))
with open(CHECKS+'/part_manifest.json','w') as f: json.dump(manifest,f,ensure_ascii=False,indent=2)

# Assembled monochrome 3MF, named independent objects in millimetres.
scene=trimesh.Scene()
for item in manifest:
    scene.add_geometry(trimesh.load(PARTS+'/'+item['file']),geom_name=item['name'],node_name=item['name'])
scene.export(ROOT+'/Большеберцовая_кость_магнитная.3mf')

# Coloured assembled GLB in metres. Only preview copies of the two dense
# middle shells are decimated; the printable STL/3MF remain full precision.
preview_parts=[]
for ob,ratio in zip(parts,[1.0,0.18,0.18,1.0]):
    p=copy_obj(ob,ob.name+'_preview')
    if ratio<1.0:
        activate(p); mod=p.modifiers.new('Preview_decimation','DECIMATE'); mod.ratio=ratio
        bpy.ops.object.modifier_apply(modifier=mod.name)
    p.name=ob.name
    preview_parts.append(p)
bpy.ops.object.select_all(action='DESELECT')
for ob in preview_parts: ob.select_set(True)
bpy.context.view_layer.objects.active=preview_parts[0]
bpy.ops.export_scene.gltf(filepath=ROOT+'/Большеберцовая_кость_магнитная.glb',export_format='GLB',use_selection=True,export_apply=True,export_materials='EXPORT',export_texcoords=True,export_normals=True,export_cameras=False,export_lights=False,export_animations=False)
for ob in preview_parts: bpy.data.objects.remove(ob,do_unlink=True)

# Add explicit up-axis metadata to GLB JSON chunk without altering geometry.
glb=ROOT+'/Большеберцовая_кость_магнитная.glb'
with open(glb,'rb') as f: data=f.read()
magic,ver,total=struct.unpack_from('<III',data,0)
json_len,json_type=struct.unpack_from('<II',data,12)
doc=json.loads(data[20:20+json_len].decode('utf-8').rstrip(' \x00'))
doc.setdefault('asset',{}).setdefault('extras',{})['up_axis']='y'
doc['asset']['extras']['front_axis']='z'
doc['asset']['extras']['physical_units']='m'
rest=data[20+json_len:]
j=json.dumps(doc,separators=(',',':'),ensure_ascii=False).encode('utf-8'); j+=b' '*((4-len(j)%4)%4)
out=struct.pack('<III',magic,ver,12+8+len(j)+len(rest))+struct.pack('<II',len(j),json_type)+j+rest
with open(glb,'wb') as f: f.write(out)

# Design record
record={'length_mm':LENGTH,'cuts_mm':[CUT_LOW,CUT_HIGH],'physical_parts':4,'magnet_pairs':10,'magnets_total':20,'pocket_diameter_mm':6.2,'pocket_depth_mm':3.2,'middle_internal_scale':INNER_SCALE,'middle_end_wall_mm':END_WALL,'longitudinal_levels_mm':LONG_Z,'longitudinal_boss_x_mm':LONG_X,'transverse_y_mm':TRANSVERSE_Y,'source':'BodyParts3D right tibia via organui/skeleton-3D; CC BY-SA 2.1 Japan'}
with open(CHECKS+'/design_parameters.json','w') as f: json.dump(record,f,ensure_ascii=False,indent=2)
print('BUILD COMPLETE')
