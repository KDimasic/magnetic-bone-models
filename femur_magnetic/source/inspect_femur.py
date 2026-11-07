import trimesh, numpy as np
p='/mnt/agents/output/tibia_magnetic/source/skeleton.glb'
s=trimesh.load(p)
name='right-femur'
g=s.geometry[name]
T=np.eye(4)
for node in s.graph.nodes_geometry:
    if s.graph[node][1] == name:
        T=s.graph.get(node)[0]
        break
m=g.copy(); m.apply_transform(T)
print(name, 'vertices',len(m.vertices),'faces',len(m.faces))
print('bounds m',m.bounds.tolist(),'extents mm',(m.extents*1000).tolist())
print('watertight',m.is_watertight,'volume mm3',m.volume*1e9,'euler',m.euler_number)
m.export('/mnt/agents/output/femur_magnetic/source/right-femur.stl')
