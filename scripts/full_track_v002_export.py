"""Project-local Blender 5.2 corner-normal adapter for the pinned KN5 Studio API.

No installed/vendor edits, second add-on, downloads, autofix operator, or new writer.
The reviewed hierarchy/material/DDS/KN5 writer remains in use. This narrow override
extracts actual mesh.corner_normals instead of MeshLoop.normal's zero/deprecated
Blender 5.2 result and preserves float32 corner XYZ+UV exactly when deduplicating.
Mikk tangents are orthogonalized against those actual normals; collapsed-UV-only
fallbacks use a deterministic perpendicular axis and are explicitly counted.
"""
import numpy as np


def exporter_class(addon):
    api=addon.exporter
    class FullTrackV002Exporter(api.KN5Exporter):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            self.corner_adapter=[]

        def _process_mesh_geometry(self,obj,scale_vec=None):
            if scale_vec is not None or self.options.get('apply_modifiers',True):
                raise ValueError('v002 adapter requires unscaled, explicit unmodified meshes')
            mesh=obj.to_mesh()
            try:
                if not mesh or not mesh.polygons:raise ValueError('Empty source mesh')
                if any(len(p.vertices)!=3 for p in mesh.polygons):
                    bm=api.bmesh.new();bm.from_mesh(mesh);api.bmesh.ops.triangulate(bm,faces=bm.faces[:]);bm.to_mesh(mesh);bm.free()
                mesh.calc_loop_triangles();mesh.calc_tangents()
                normals=np.array([n.vector[:] for n in mesh.corner_normals],dtype=float)
                uv=mesh.uv_layers.active.data
                submeshes=[];current=None;lookup={};material_id=None;fallbacks=0;orthogonalized=0
                for tri in mesh.loop_triangles:
                    mat=obj.material_slots[tri.material_index].material.name
                    mid=self.material_map[mat]
                    if current is None or material_id!=mid or len(current.vertices)>65530:
                        if current is not None:submeshes.append(current)
                        current=api.SubmeshData(mid);lookup={};material_id=mid
                    positions=np.array([mesh.vertices[i].co[:] for i in tri.vertices],dtype=float)
                    cross=np.cross(positions[1]-positions[0],positions[2]-positions[0]);length=np.linalg.norm(cross)
                    if not np.isfinite(length) or length<=1e-12:raise ValueError('Degenerate source triangle '+obj.name)
                    face_normal=cross/length;indices=[]
                    for li in tri.loops:
                        loop=mesh.loops[li];n=normals[li].copy();nl=np.linalg.norm(n)
                        if not mesh.polygons[tri.polygon_index].use_smooth:
                            # Exact outward flat normal, including sub-mm terrain-cut triangles.
                            n=face_normal.copy();nl=1.
                        if nl<1e-8:n=face_normal.copy();fallbacks+=1
                        else:n/=nl
                        raw_t=np.array(loop.tangent[:],dtype=float)
                        t=raw_t-n*(raw_t@n);tl=np.linalg.norm(t)
                        if tl<1e-8:
                            axis=np.eye(3)[np.argmin(abs(n))];t=np.cross(axis,n);tl=np.linalg.norm(t);fallbacks+=1
                        t/=tl
                        if np.linalg.norm(t-raw_t)>2e-5:orthogonalized+=1
                        p=mesh.vertices[loop.vertex_index].co
                        # KN5 float32 conversion happens explicitly before keying; no rounded UV welds.
                        xyz=np.array([p.x,p.z,-p.y],dtype=np.float32)
                        nn=np.array([n[0],n[2],-n[1]],dtype=np.float32)
                        tt=np.array([t[0],t[2],-t[1]],dtype=np.float32)
                        raw_uv=uv[li].uv;tex=np.array([raw_uv.x,1-float(raw_uv.y)],dtype=np.float32)
                        key=xyz.tobytes()+nn.tobytes()+tex.tobytes()+tt.tobytes()
                        index=lookup.get(key)
                        if index is None:
                            index=len(current.vertices);lookup[key]=index
                            current.vertices.append(api.KN5Vertex(tuple(float(x) for x in xyz),tuple(float(x) for x in nn),
                                tuple(float(x) for x in tex),tuple(float(x) for x in tt)))
                        indices.append(index)
                    current.indices.extend((indices[1],indices[2],indices[0]))
                if current is not None:submeshes.append(current)
                self.corner_adapter.append(dict(name=obj.name,triangles=len(mesh.loop_triangles),
                    actual_corner_normals=True,degenerate_uv_or_normal_fallback_corners=fallbacks,
                    orthogonalized_tangent_corners=orthogonalized,
                    uint16_parts=len(submeshes),vertices=sum(len(s.vertices) for s in submeshes)))
                return submeshes
            finally:
                obj.to_mesh_clear()
    return FullTrackV002Exporter
