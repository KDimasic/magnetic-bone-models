import trimesh, numpy as np, json
p='/mnt/agents/output/tibia_magnetic/source/skeleton.glb'
s=trimesh.load(p)
for name in ['right-tibia','left-tibia']:
    g=s.geometry[name]
    T=s.graph.get(name)[0] if name in s.graph.nodes_geometry else np.eye(4)
    # robust: find node referencing geometry
    for node in s.graph.nodes_geometry:
        if s.graph[node][1] == name:
            T=s.graph.get(node)[0]
            break
    m=g.copy(); m.apply_transform(T)
    print(name, 'vertices',len(m.vertices),'faces',len(m.faces))
    print('bounds m',m.bounds.tolist(),'extents mm',(m.extents*1000).tolist())
    print('watertight',m.is_watertight,'volume mm3',m.volume*1e9,'euler',m.euler_number)
    m.export('/mnt/agents/output/tibia_magnetic/source/'+name+'.stl')
