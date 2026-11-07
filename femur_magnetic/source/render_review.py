import bpy, os
from mathutils import Vector
ROOT=os.environ.get('MODEL_ROOT','/mnt/agents/output/femur_magnetic'); OUT=ROOT+'/checks'
BASENAME=os.environ.get('OUTPUT_BASENAME','Бедренная_кость_магнитная')

def reset():
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)

def setup():
    sc=bpy.context.scene; sc.render.engine='CYCLES'; sc.cycles.device='CPU'; sc.cycles.samples=48
    sc.render.resolution_x=900; sc.render.resolution_y=1100; sc.render.resolution_percentage=100
    sc.world.use_nodes=True
    bg=sc.world.node_tree.nodes.get('Background'); bg.inputs['Color'].default_value=(.055,.065,.08,1); bg.inputs['Strength'].default_value=.45
    sc.view_settings.look='AgX - Medium High Contrast'
    for loc,power,size in [((.28,-.40,.62),24,.4),((-.40,-.12,.34),14,.3),((.12,.40,.45),18,.3)]:
        bpy.ops.object.light_add(type='AREA',location=loc); l=bpy.context.object; l.data.energy=power; l.data.shape='DISK'; l.data.size=size
        l.rotation_euler=(Vector((0,0,.225))-l.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.object.camera_add(location=(.55,-.78,.42)); cam=bpy.context.object; sc.camera=cam
    cam.data.type='ORTHO'; cam.data.ortho_scale=.55; cam.data.clip_end=20
    cam.rotation_euler=(Vector((0,0,.225))-cam.location).to_track_quat('-Z','Y').to_euler()
    return cam

def load_glb():
    bpy.ops.import_scene.gltf(filepath=ROOT+'/'+BASENAME+'.glb')
    return [o for o in bpy.context.scene.objects if o.type=='MESH']

def render(name):
    bpy.context.scene.render.filepath=OUT+'/'+name+'.png'; bpy.ops.render.render(write_still=True)

reset(); parts=load_glb(); cam=setup(); render('01_Собранная_модель_GLB')
for o in parts:
    if o.name.startswith('01_'): o.location.z-=.05
    elif o.name.startswith('02_'): o.location.y-=.05
    elif o.name.startswith('03_'): o.location.y+=.05
    elif o.name.startswith('04_'): o.location.z+=.05
cam.data.ortho_scale=.64; cam.rotation_euler=(Vector((0,0,.225))-cam.location).to_track_quat('-Z','Y').to_euler()
render('02_Разобранная_модель_GLB')
for o in parts:
    if o.name.startswith('01_') or o.name.startswith('04_'): o.hide_render=True
cam.location=(.34,.40,.29); cam.data.ortho_scale=.34
cam.rotation_euler=(Vector((0,0,.23))-cam.location).to_track_quat('-Z','Y').to_euler()
render('03_Пазы_средней_секции_GLB')
print('RENDERS COMPLETE')
