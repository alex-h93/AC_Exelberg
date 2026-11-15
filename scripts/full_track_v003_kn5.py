"""Bounded v003 independent-reader entrypoint; legacy validator stays byte-for-byte.

v002's sealed package pins the old validator hash. Reuse its Reader and invariant
checks, but explicitly parameterize asset counts here (defaults 32, hard cap128).
No vendor module imports or runtime monkey-patching.
"""
from validate_kn5 import Reader,require

def parse(data, *, max_file=None, max_nodes=64, max_texture=1024*1024,
          max_materials=32, max_textures=32):
    require(0<max_texture<=8*1024*1024,'unsafe texture budget')
    require(0<max_materials<=128 and 0<max_textures<=128,'unsafe asset count budget')
    reader=Reader(data,max_file=max_file,max_nodes=max_nodes)
    require(bytes(reader.take(6))==b'sc6969','bad magic')
    require(reader.number()==5,'only KN5 v5 supported')
    textures=[]
    for _ in range(reader.count(max_textures,12)):
        active=reader.flag('I');name=reader.string();size=reader.count(max_texture)
        textures.append(dict(active=active,name=name,data=bytes(reader.take(size))))
    materials=[]
    for _ in range(reader.count(max_materials,18)):
        material=dict(name=reader.string(),shader=reader.string(),blend=reader.number('B'),alpha=reader.flag(),depth=reader.number())
        require(material['blend'] in (0,1,2) and material['depth'] in (0,1,2),'unknown material enum')
        properties={}
        for _ in range(reader.count(64,44)):
            name=reader.string();require(name not in properties,'duplicate property');properties[name]=reader.floats(10)
        material['properties']=properties
        material['bindings']=[(reader.string(),reader.number(),reader.string()) for _ in range(reader.count(32,12))]
        materials.append(material)
    root=reader.node();require(reader.pos==len(data),'trailing bytes');nodes=[]
    def flatten(node):
        nodes.append(node)
        for child in node['children']:flatten(child)
    flatten(root)
    require(len({n['name'] for n in nodes})==len(nodes),'duplicate node names')
    names=[t['name'] for t in textures]
    require(len(set(names))==len(names),'duplicate texture names')
    require(len({m['name'] for m in materials})==len(materials),'duplicate materials')
    for material in materials:require(all(b[2] in names for b in material['bindings']),'missing texture binding')
    for node in nodes:
        if node['kind']==2:require(node['material']<len(materials),'material out of range')
    return dict(textures=textures,materials=materials,root=root,nodes=nodes,bytes_consumed=reader.pos)
