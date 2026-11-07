import trimesh, numpy as np, json, os, struct, bpy, bmesh, manifold3d
from scipy.spatial.transform import Rotation

ROOT=os.environ.get('MODEL_ROOT','/mnt/agents/output/tibia_magnetic'); PARTS=ROOT+'/parts'; CHECKS=ROOT+'/checks'
os.makedirs(PARTS,exist_ok=True); os.makedirs(CHECKS,exist_ok=True)
BASENAME=os.environ.get('OUTPUT_BASENAME','Большеберцовая_кость_магнитная')
LENGTH=400.; CUT_LOW=85.; CUT_HIGH=float(os.environ.get('CUT_HIGH','273')); INNER_SCALE=.74; END_WALL=3.2
MAG_R=3.10; MAG_DEPTH=3.20
LONG_Z=[float(x) for x in os.environ.get('LONG_Z','125,233').split(',')]; TRANSVERSE_Y=[-5.,7.]
HOLLOW_Z=[float(x) for x in os.environ.get('HOLLOW_Z','110,152,248').split(',')]

# Anatomical source: BodyParts3D right tibia, via organui/skeleton-3d.
src=trimesh.load(ROOT+'/source/right-tibia.stl')
v=src.vertices.copy(); v[:,1]-=v[:,1].min(); v*=.4/v[:,1].max(); v=np.column_stack([v[:,0],-v[:,2],v[:,1]])
cs=[]
for z in np.linspace(.09,.315,10):
    sec=trimesh.Trimesh(v,src.faces).section(plane_origin=[0,0,z],plane_normal=[0,0,1]); p=sec.vertices
    cs.append([z,*((p[:,:2].min(0)+p[:,:2].max(0))/2)])
cs=np.array(cs); fx=np.polyfit(cs[:,0],cs[:,1],1); fy=np.polyfit(cs[:,0],cs[:,2],1)
d=np.array([fx[0],fy[0],1.]); d/=np.linalg.norm(d); R=Rotation.align_vectors([[0,0,1]],[d])[0].as_matrix()
v=v@R.T; c0=R@np.array([np.polyval(fx,.2),np.polyval(fy,.2),.2]); v-=c0; v[:,2]+=.2
v*=LENGTH/((v[:,2].max()-v[:,2].min())*1000.); v[:,2]-=v[:,2].min(); v*=1000.
base=trimesh.Trimesh(v,src.faces,process=True)
assert base.is_watertight
base.export(ROOT+'/source/tibia_aligned_400mm.stl')

def box(center,size):
    m=trimesh.creation.box(extents=size); m.apply_translation(center); return m

def cyl(center,radius,depth,axis='Z'):
    m=trimesh.creation.cylinder(radius=radius,height=depth,sections=64)
    if axis=='Y': m.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,[1,0,0]))
    elif axis=='X': m.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,[0,1,0]))
    m.apply_translation(center); return m

def as_manifold(m):
    vv=np.ascontiguousarray(m.vertices,dtype=np.float64); ff=np.ascontiguousarray(m.faces,dtype=np.uint64)
    if vv.ndim!=2 or ff.ndim!=2 or ff.shape[1]!=3: raise RuntimeError(f'Bad mesh arrays {vv.shape} {ff.shape}')
    mesh=manifold3d.Mesh64(vv,ff)
    result=manifold3d.Manifold(mesh)
    if result.status()!=manifold3d.Error.NoError: raise RuntimeError('Non-manifold input')
    return result

def from_manifold(m):
    mesh=m.to_mesh64()
    verts=np.array(mesh.vert_properties,dtype=np.float64,copy=True)[:,:3]
    faces=np.array(mesh.tri_verts,dtype=np.int64,copy=True)
    return trimesh.Trimesh(verts,faces,process=False)

def intersect(a,b): return from_manifold(as_manifold(a)^as_manifold(b))
def difference(a,b): return from_manifold(as_manifold(a)-as_manifold(b))
def union(a,b): return from_manifold(as_manifold(a)+as_manifold(b))
def clip(a,axis,lo,hi):
    c=[0,0,200]; s=[300,300,600]; c[axis]=(lo+hi)/2; s[axis]=hi-lo
    return intersect(a,box(c,s))

def x_intersections(mesh,z):
    sec=mesh.section(plane_origin=[0,0,z],plane_normal=[0,0,1]); p=sec.vertices; xs=[]
    for ent in sec.entities:
        pts=p[ent.points]
        for a,b in zip(pts[:-1],pts[1:]):
            if a[1]*b[1]<0:
                t=-a[1]/(b[1]-a[1]); xs.append(a[0]+t*(b[0]-a[0]))
    if not xs: raise RuntimeError('No Y=0 intersection')
    return min(xs),max(xs)

LONG_X=[]
for z in LONG_Z:
    xl,xr=x_intersections(base,z); LONG_X.append((xl+4.,xr-6.))

# Three sections; middle is hollow and then divided into two halves.
lower=clip(base,2,0,CUT_LOW)
upper=clip(base,2,CUT_HIGH,LENGTH+5)
mid_outer=clip(base,2,CUT_LOW,CUT_HIGH)
inner=base.copy(); inner.vertices[:,:2]*=INNER_SCALE
inner=clip(inner,2,CUT_LOW+END_WALL,CUT_HIGH-END_WALL)
mid=difference(mid_outer,inner)

# Internal pads, trimmed to the original exterior so no boss changes the silhouette.
def add_boss(center,radius,depth,axis):
    global mid
    b=intersect(cyl(center,radius,depth,axis),mid_outer)
    print('boss',center,axis,'faces',len(b.faces),'volume',b.volume,'watertight',b.is_watertight)
    if len(b.faces)==0 or not b.is_watertight or b.volume<=0: raise RuntimeError('Invalid trimmed boss')
    mid=union(mid,b)
    print(' mid status',len(mid.faces),mid.volume,mid.is_watertight,mid.is_winding_consistent)
for y in TRANSVERSE_Y:
    add_boss([0,y,CUT_LOW+4.],4.6,10.,'Z')
    add_boss([0,y,CUT_HIGH-4.],4.6,10.,'Z')
for z,(xl,xr) in zip(LONG_Z,LONG_X):
    for x in (xl,xr): add_boss([x,0,z],5.5,18.,'Y')
mid_a=clip(mid,1,-100,0); mid_b=clip(mid,1,0,100)

# Pocket opens 0.1 mm beyond the mating plane and ends exactly 3.2 mm inside.
def pocket(ob,center,axis,axis_index,sign):
    c=np.array(center,dtype=float); c[axis_index]+=sign*(MAG_DEPTH-.1)/2
    return difference(ob,cyl(c,MAG_R,MAG_DEPTH+.1,axis))
for y in TRANSVERSE_Y:
    lower=pocket(lower,[0,y,CUT_LOW],'Z',2,-1)
    ob=mid_a if y<0 else mid_b
    ob=pocket(ob,[0,y,CUT_LOW],'Z',2,+1)
    ob=pocket(ob,[0,y,CUT_HIGH],'Z',2,-1)
    if y<0: mid_a=ob
    else: mid_b=ob
    upper=pocket(upper,[0,y,CUT_HIGH],'Z',2,+1)
for sign,name in [(-1,'A'),(+1,'B')]:
    ob=mid_a if sign<0 else mid_b
    for z,(xl,xr) in zip(LONG_Z,LONG_X):
        for x in (xl,xr): ob=pocket(ob,[x,0,z],'Y',1,sign)
    if sign<0: mid_a=ob
    else: mid_b=ob

named=[('01_Нижняя_секция',lower),('02_Средняя_половина_A',mid_a),('03_Средняя_половина_B',mid_b),('04_Верхняя_секция',upper)]
manifest=[]
for name,m in named:
    m.remove_unreferenced_vertices(); m.export(PARTS+'/'+name+'.stl')
    re=trimesh.load(PARTS+'/'+name+'.stl')
    manifest.append({'name':name,'file':name+'.stl','vertices':len(re.vertices),'triangles':len(re.faces),'watertight':bool(re.is_watertight),'winding_consistent':bool(re.is_winding_consistent),'volume_mm3':float(re.volume),'bounds_mm':re.bounds.tolist(),'extents_mm':re.extents.tolist()})
print(json.dumps(manifest,ensure_ascii=False,indent=2))
assert all(x['watertight'] for x in manifest)
with open(CHECKS+'/part_manifest.json','w') as f: json.dump(manifest,f,ensure_ascii=False,indent=2)

scene=trimesh.Scene()
for name,m in named: scene.add_geometry(m,geom_name=name,node_name=name)
scene.export(ROOT+'/'+BASENAME+'.3mf')

# Blender editable source and coloured GLB, same full-precision geometry as print files.
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
colors=[(.82,.72,.52,1),(.65,.78,.88,1),(.88,.68,.48,1),(.74,.80,.60,1)]
for (name,m),col in zip(named,colors):
    me=bpy.data.meshes.new(name+'_mesh'); me.from_pydata(m.vertices*.001,[],m.faces.tolist()); me.update()
    ob=bpy.data.objects.new(name,me); bpy.context.collection.objects.link(ob)
    bm=bmesh.new(); bm.from_mesh(me); bmesh.ops.recalc_face_normals(bm,faces=bm.faces); bm.to_mesh(me); bm.free()
    for p in me.polygons:
        c=p.center*1000.; n=p.normal
        on_transverse=abs(n.z)>.9999 and min(abs(c.z-CUT_LOW),abs(c.z-CUT_HIGH))<.01
        on_longitudinal=abs(n.y)>.9999 and abs(c.y)<.01
        p.use_smooth=not (on_transverse or on_longitudinal)
    mat=bpy.data.materials.new(name+'_материал'); mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get('Principled BSDF'); bsdf.inputs['Base Color'].default_value=col; bsdf.inputs['Roughness'].default_value=.38
    me.materials.append(mat); ob['units']='m'; ob['pocket_mm']='6.20 x 3.20 for 6 x 3 magnet'
bpy.context.preferences.filepaths.save_version=0
try: bpy.ops.wm.save_as_mainfile(filepath=ROOT+'/'+BASENAME+'.blend',check_existing=False,compress=True)
except RuntimeError as exc: print('Blend save warning:',exc)
bpy.ops.object.select_all(action='DESELECT')
for ob in bpy.context.scene.objects: ob.select_set(True)
bpy.context.view_layer.objects.active=bpy.context.scene.objects[0]
bpy.ops.export_scene.gltf(filepath=ROOT+'/'+BASENAME+'.glb',export_format='GLB',use_selection=True,export_apply=True,export_materials='EXPORT',export_texcoords=True,export_normals=True,export_cameras=False,export_lights=False,export_animations=False)

# Explicit axis metadata.
glb=ROOT+'/'+BASENAME+'.glb'; data=open(glb,'rb').read()
json_len,json_type=struct.unpack_from('<II',data,12); doc=json.loads(data[20:20+json_len].decode().rstrip(' \x00'))
doc.setdefault('asset',{}).setdefault('extras',{}).update({'up_axis':'y','front_axis':'z','physical_units':'m'})
rest=data[20+json_len:]; j=json.dumps(doc,separators=(',',':'),ensure_ascii=False).encode(); j+=b' '*((4-len(j)%4)%4)
out=struct.pack('<III',0x46546C67,2,12+8+len(j)+len(rest))+struct.pack('<II',len(j),json_type)+j+rest
open(glb,'wb').write(out)
record={'length_mm':LENGTH,'cuts_mm':[CUT_LOW,CUT_HIGH],'middle_length_mm':CUT_HIGH-CUT_LOW,'physical_parts':4,'magnet_pairs':8,'longitudinal_magnet_pairs':len(LONG_Z)*2,'transverse_magnet_pairs':4,'magnets_total':16,'pocket_diameter_mm':6.2,'pocket_depth_mm':3.2,'middle_internal_scale':INNER_SCALE,'middle_end_wall_mm':END_WALL,'longitudinal_levels_mm':LONG_Z,'longitudinal_boss_x_mm':LONG_X,'transverse_y_mm':TRANSVERSE_Y,'hollow_probe_z_mm':HOLLOW_Z,'geometry_method':'Manifold solid Boolean; identical print and preview meshes','source':'BodyParts3D right tibia via organui/skeleton-3d; CC BY-SA 2.1 Japan'}
with open(CHECKS+'/design_parameters.json','w') as f: json.dump(record,f,ensure_ascii=False,indent=2)
print('SOLID BUILD COMPLETE')
