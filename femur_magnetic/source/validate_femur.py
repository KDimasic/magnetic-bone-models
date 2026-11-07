import trimesh, numpy as np, json, os, zipfile, xml.etree.ElementTree as ET, struct, manifold3d
ROOT=os.environ.get('MODEL_ROOT','/mnt/agents/output/femur_magnetic'); P=ROOT+'/parts'; C=ROOT+'/checks'
BASENAME=os.environ.get('OUTPUT_BASENAME','Бедренная_кость_магнитная')
names=['01_Нижняя_секция','02_Средняя_половина_A','03_Средняя_половина_B','04_Верхняя_секция']
parts={n:trimesh.load(P+'/'+n+'.stl') for n in names}
par=json.load(open(C+'/design_parameters.json'))
length=par['length_mm']; cut_low,cut_high=par['cuts_mm']; split_y=par['split_y_mm']
report={'geometry':[], 'pockets':[], 'pocket_containment':[], 'assembled_intersections':[], 'assembly_paths':[], 'hollow':{}, 'formats':{}}
for n,m in parts.items():
    ok=m.is_watertight and m.is_winding_consistent and m.nondegenerate_faces().all() and np.isfinite(m.vertices).all()
    report['geometry'].append({'part':n,'finite_vertices':bool(np.isfinite(m.vertices).all()),'watertight':bool(m.is_watertight),'winding_consistent':bool(m.is_winding_consistent),'nondegenerate_faces':bool(m.nondegenerate_faces().all()),'triangles':len(m.faces),'volume_mm3':float(m.volume),'extents_mm':m.extents.tolist(),'status':'pass' if ok else 'fail'})
assembled=trimesh.util.concatenate(list(parts.values()))
report['overall']={'bounds_mm':assembled.bounds.tolist(),'extents_mm':assembled.extents.tolist(),'length_z_mm':float(assembled.extents[2]),'status':'pass' if abs(assembled.extents[2]-length)<.001 else 'fail'}

pockets=[]
xl_trans,xu_trans=par['transverse_x_mm']
for y in par['transverse_y_mm']:
    half=names[1] if y<split_y else names[2]
    pockets += [(names[0],[xl_trans,y,cut_low],2,-1,'Нижний торец'),(half,[xl_trans,y,cut_low],2,+1,'Средняя, нижний торец'),(half,[xu_trans,y,cut_high],2,-1,'Средняя, верхний торец'),(names[3],[xu_trans,y,cut_high],2,+1,'Верхний торец')]
for z,(xl,xr) in zip(par['longitudinal_levels_mm'],par['longitudinal_boss_x_mm']):
    for x in (xl,xr):
        pockets += [(names[1],[x,split_y,z],1,-1,'Продольный стык'),(names[2],[x,split_y,z],1,+1,'Продольный стык')]
base=trimesh.load(ROOT+'/source/femur_aligned_450mm.stl')
for part,center,axis,sign,label in pockets:
    m=parts[part]; c=np.array(center,dtype=float)
    def point(depth,r=0,a=0):
        p=c.copy(); p[axis]+=sign*depth
        other=[i for i in range(3) if i!=axis]
        p[other[0]]+=r*np.cos(a); p[other[1]]+=r*np.sin(a)
        return p
    depths=[.2,1.5,3.0]
    empty_ok=all(not m.contains([point(d)])[0] for d in depths)
    bottom_ok=bool(m.contains([point(3.4)])[0])
    radial_empty=all(not m.contains([point(1.5,2.95,a)])[0] for a in np.linspace(0,2*np.pi,12,endpoint=False))
    material_ok=all(bool(m.contains([point(1.5,3.25,a)])[0]) for a in np.linspace(0,2*np.pi,12,endpoint=False))
    ok=empty_ok and bottom_ok and radial_empty and material_ok
    report['pockets'].append({'part':part,'interface':label,'center_mm':center,'axis':axis,'direction':sign,'clear_bore_to_3mm':empty_ok,'material_at_3_4mm':bottom_ok,'radius_2_95_clear':radial_empty,'material_at_radius_3_25':material_ok,'status':'pass' if ok else 'fail'})
    probes=[]
    for d in [.15,1.5,3.0]:
        probes.append(point(d))
        probes += [point(d,2.95,a) for a in np.linspace(0,2*np.pi,12,endpoint=False)]
    outside=int((~base.contains(np.array(probes))).sum())
    report['pocket_containment'].append({'part':part,'interface':label,'center_mm':center,'sampled_points':len(probes),'outside_original_surface_points':outside,'status':'pass' if outside==0 else 'fail'})

def as_manifold(m):
    me=manifold3d.Mesh64(np.ascontiguousarray(m.vertices,dtype=np.float64),np.ascontiguousarray(m.faces,dtype=np.uint64))
    return manifold3d.Manifold(me)
def intersection_volume(a,b):
    if (a.bounds[1]<b.bounds[0]-1e-7).any() or (b.bounds[1]<a.bounds[0]-1e-7).any(): return 0.
    result=as_manifold(a)^as_manifold(b); mesh=result.to_mesh64()
    if result.is_empty() or len(mesh.tri_verts)==0: return 0.
    vv=np.array(mesh.vert_properties,copy=True)[:,:3]; ff=np.array(mesh.tri_verts,copy=True)
    return float(trimesh.Trimesh(vv,ff,process=False).volume)
for i,a in enumerate(names):
    for b in names[i+1:]:
        vol=intersection_volume(parts[a],parts[b])
        report['assembled_intersections'].append({'a':a,'b':b,'intersection_volume_mm3':vol,'status':'pass' if abs(vol)<1e-5 else 'fail'})

distances=[40,30,20,15,10,7.5,5,3,2,1,.5,.2]
steps=[('1. Соединить половины A и B',names[2],[0,1,0],[names[1]]),('2. Установить нижнюю секцию',names[0],[0,0,-1],[names[1],names[2]]),('3. Установить верхнюю секцию',names[3],[0,0,1],[names[0],names[1],names[2]])]
for label,moving,axis,installed in steps:
    samples=[]; ok=True
    for d in distances:
        moved=parts[moving].copy(); moved.apply_translation(np.array(axis)*d)
        collisions=[]
        for fixed in installed:
            vol=intersection_volume(moved,parts[fixed])
            if abs(vol)>=1e-5: collisions.append({'part':fixed,'volume_mm3':vol}); ok=False
        samples.append({'distance_mm':d,'collisions':collisions})
    report['assembly_paths'].append({'step':label,'moving_part':moving,'direction':axis,'range_mm':[40,.2],'samples':samples,'status':'pass' if ok else 'fail'})

for z in par.get('hollow_probe_z_mm',[120.,201.,282.]):
    pts=np.array([[0,split_y-2,z],[0,split_y+2,z]])
    occupied=[bool(parts[n].contains([p])[0]) for n in names[1:3] for p in pts]
    report['hollow'][f'z_{z}']={'clear':not any(occupied),'status':'pass' if not any(occupied) else 'fail'}
for z,x in [(cut_low+1.5,xl_trans),(cut_high-1.5,xu_trans)]:
    checks=[]
    for n,y in [(names[1],split_y-1),(names[2],split_y+.25)]: checks.append(bool(parts[n].contains([[x,y,z]])[0]))
    report['hollow'][f'end_wall_{z}']={'material_present':all(checks),'status':'pass' if all(checks) else 'fail'}

f3=ROOT+'/'+BASENAME+'.3mf'
with zipfile.ZipFile(f3) as z:
    bad=z.testzip(); files=z.namelist(); xml=z.read('3D/3dmodel.model'); root=ET.fromstring(xml)
    ns={'m':root.tag.split('}')[0].strip('{')}
    unit=root.attrib.get('unit'); objs=root.findall('.//m:object',ns); builds=root.findall('.//m:build/m:item',ns)
    names3=[o.attrib.get('name') for o in objs]
scene3=trimesh.load(f3)
ok3=bad is None and unit=='millimeter' and names3==names and len(builds)==4 and len(scene3.geometry)==4 and abs(scene3.extents[2]-length)<.001
report['formats']['3mf']={'zip_crc_error':bad,'required_content_types':'[Content_Types].xml' in files,'relationships':'_rels/.rels' in files,'unit':unit,'object_names':names3,'build_items':len(builds),'reopened_geometry':len(scene3.geometry),'extents_mm':scene3.extents.tolist(),'status':'pass' if ok3 else 'fail'}

fg=ROOT+'/'+BASENAME+'.glb'; data=open(fg,'rb').read(); magic,version,total=struct.unpack_from('<III',data,0)
jlen,jtype=struct.unpack_from('<II',data,12); doc=json.loads(data[20:20+jlen].decode().rstrip(' \x00'))
node_info=[]
for node in doc.get('nodes',[]):
    if 'mesh' in node:
        mesh=doc['meshes'][node['mesh']]; node_info.append({'name':node.get('name'),'mesh':node['mesh'],'primitives':len(mesh['primitives'])})
scene_g=trimesh.load(fg)
triangles=0
for mesh in doc['meshes']:
    for prim in mesh['primitives']: triangles+=doc['accessors'][prim['indices']]['count']//3
external=[b['uri'] for b in doc.get('buffers',[]) if 'uri' in b]
node_names=[x['name'] for x in node_info]
glb_ok=magic==0x46546C67 and version==2 and total==len(data) and node_names==names and not external and abs(scene_g.extents[1]-length/1000)<1e-6
report['formats']['glb']={'valid_header':magic==0x46546C67,'version':version,'declared_length_matches':total==len(data),'scene_count':len(doc.get('scenes',[])),'mesh_count':len(doc.get('meshes',[])),'material_count':len(doc.get('materials',[])),'nodes':node_info,'triangles':triangles,'external_buffers':external,'asset_extras':doc.get('asset',{}).get('extras'),'extents_m':scene_g.extents.tolist(),'file_bytes':len(data),'status':'pass' if glb_ok else 'fail'}

json.dump(report,open(C+'/validation_report.json','w'),ensure_ascii=False,indent=2)
print('geometry',all(x['status']=='pass' for x in report['geometry']))
print('overall',report['overall'])
print('pockets',sum(x['status']=='pass' for x in report['pockets']),'/',len(report['pockets']))
print('containment',sum(x['status']=='pass' for x in report['pocket_containment']),'/',len(report['pocket_containment']))
print('assembled intersections',report['assembled_intersections'])
print('assembly paths',[(x['step'],x['status']) for x in report['assembly_paths']])
print('hollow',report['hollow'])
print('formats',report['formats'])
failed=[]
def walk(x,path=''):
    if isinstance(x,dict):
        if x.get('status')=='fail': failed.append(path)
        for k,v in x.items(): walk(v,path+'/'+k)
    elif isinstance(x,list):
        for i,v in enumerate(x): walk(v,path+'/'+str(i))
walk(report)
if failed: raise RuntimeError('Failed checks: '+', '.join(failed))
print('ALL DIGITAL CHECKS PASSED')
