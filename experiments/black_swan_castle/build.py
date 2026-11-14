# SPDX-License-Identifier: Apache-2.0
"""Build a stylized Neuschwanstein-inspired scene with switchable ice-blue lights.

Python standard library only. Reuses the courtyard archive's mesh primitives;
the scene's artistic metre dimensions are not measurements of the real castle.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import struct

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SPEC = importlib.util.spec_from_file_location('courtyard_geometry', ROOT/'tools/siheyuan/build.py')
G = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(G)
MATERIALS = {
    'stone': '#c5ced5', 'trim': '#94a7b5', 'roof': '#243643',
    'gate': '#865c59', 'rock': '#354756', 'court': '#71828c',
    'forest': '#203e41', 'window': '#12333f', 'ice': '#83ddff',
}


def validate(config):
    if config['schema_version'] != 1 or config['geometry_status'] != 'stylized_not_surveyed':
        raise ValueError('stylized geometry status required')
    if config['historical_lighting'] is not False or config['units'] != 'm':
        raise ValueError('artistic lighting and metre coordinates required')
    light = config['lights']
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', light['color_srgb']):
        raise ValueError('invalid light color')
    strength = light['emissive_strength']
    if type(strength) not in (float, int) or not math.isfinite(strength) or not 0 <= strength <= 20:
        raise ValueError('invalid emissive strength')


def ring_mesh(x, y, z, radius, height, top_radius=None, sides=16):
    """Closed cylinder or truncated cone, with outward polygon winding."""
    top_radius = radius if top_radius is None else top_radius
    vertices = [[x+r*math.cos(2*math.pi*i/sides), y+r*math.sin(2*math.pi*i/sides), h]
                for r,h in [(radius,z),(top_radius,z+height)] for i in range(sides)]
    faces = [list(reversed(range(sides))), list(range(sides,2*sides))]
    faces += [[i,(i+1)%sides,(i+1)%sides+sides,i+sides] for i in range(sides)]
    return vertices, faces


def beam_mesh(a, b, radius=.12):
    direction = [b[i]-a[i] for i in range(3)]
    length = math.sqrt(sum(v*v for v in direction))
    if length < 1e-8:
        raise ValueError('zero length light strip')
    w = [v/length for v in direction]
    ref = [0,0,1] if abs(w[2]) < .9 else [0,1,0]
    u = [w[1]*ref[2]-w[2]*ref[1],w[2]*ref[0]-w[0]*ref[2],w[0]*ref[1]-w[1]*ref[0]]
    norm = math.sqrt(sum(v*v for v in u))
    u = [v/norm for v in u]
    v = [w[1]*u[2]-w[2]*u[1],w[2]*u[0]-w[0]*u[2],w[0]*u[1]-w[1]*u[0]]
    points = [[p[i]+radius*(s*u[i]+t*v[i]) for i in range(3)]
              for p in (a,b) for s,t in [(-1,-1),(1,-1),(1,1),(-1,1)]]
    return points, [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]


def model(config):
    validate(config)
    parts = []
    def add(name, material, mesh, group):
        vertices, faces = mesh
        low = [min(v[i] for v in vertices) for i in range(3)]
        high = [max(v[i] for v in vertices) for i in range(3)]
        parts.append(dict(id=name,material=material,group=group,vertices=vertices,faces=faces,
                          bounds=low+[high[i]-low[i] for i in range(3)]))
    def box(name, bounds, material='stone', group='palas'):
        add(name,material,G.box_mesh(bounds),group)
    def line(name,a,b,group):
        add(name,'ice',beam_mesh(a,b),group)
    def roof(name,x,y,z,w,d,h,group):
        add(name,'roof',G.roof_mesh(dict(footprint_m=[x,y,w,d],eave_m=z,roof_rise_m=h,ridge_axis='x')),group)
        for edge, yy in enumerate((y-.18,y+d+.18)):
            line(name+f'_eave{edge}',[x,yy,z],[x+w,yy,z],group)
        line(name+'_ridge',[x,y+d/2,z+h+.1],[x+w,y+d/2,z+h+.1],group)
        for edge, xx in enumerate((x-.15,x+w+.15)):
            for side, yy in enumerate((y,y+d)):
                line(name+f'_gable{edge}_{side}',[xx,yy,z],[xx,y+d/2,z+h+.1],group)
    def windows(name,x,y,z,w,h,group,rows=3,cols=7):
        # Surface decorations only: no claim to surveyed window counts or interiors.
        for row in range(rows):
            for col in range(cols):
                px=x+(col+1)*w/(cols+1); pz=z+(row+1)*h/(rows+1)
                box(f'{name}_pane{row}_{col}',[px-.56,y-.12,pz-.8,1.12,.14,1.7],'window',group)
                # Pointed arch impression from three light strips.
                for side in (-1,1):
                    line(f'{name}_jamb{row}_{col}_{side}',[px+side*.64,y-.2,pz-.85],[px+side*.64,y-.2,pz+.7],group)
                    line(f'{name}_arch{row}_{col}_{side}',[px+side*.64,y-.2,pz+.7],[px,y-.2,pz+1.15],group)
    def tower(name,x,y,z,r,h,spire,group):
        add(name,'stone',ring_mesh(x,y,z,r,h),group)
        add(name+'_collar','trim',ring_mesh(x,y,z+h-1,r*1.12,1.5),group)
        add(name+'_spire','roof',ring_mesh(x,y,z+h+.5,r*1.23,spire,.03),group)
        for i in range(4):
            angle=i*math.pi/2
            a=[x+r*1.25*math.cos(angle),y+r*1.25*math.sin(angle),z+h+.55]
            line(name+f'_spire_light{i}',a,[x,y,z+h+spire+.55],group)
        for i in range(16):
            a=2*math.pi*i/16; b=2*math.pi*(i+1)/16
            line(name+f'_ring{i}',[x+r*1.14*math.cos(a),y+r*1.14*math.sin(a),z+h],
                 [x+r*1.14*math.cos(b),y+r*1.14*math.sin(b),z+h],group)

    # Layered ridge and two distinct open courtyard terraces.
    add('rock_lower','rock',ring_mesh(0,0,-18,79,10,69,12),'landscape')
    add('rock_upper','rock',ring_mesh(-5,0,-8,67,8,60,12),'landscape')
    box('upper_court',[-4,-17,0,30,34,.8],'court','courts')
    box('lower_court',[26,-17,-1,28,34,.8],'court','courts')
    for i in range(7):
        box(f'court_step{i}',[24+i*.34,-9,-1+i/7, .34,18,.18],'trim','courts')
    # Offset paired palace masses, long side wings and the eastern gateway.
    box('palas_west',[-48,-13,0,27,26,30])
    roof('palas_west_roof',-48,-13,30,27,26,13,'palas')
    windows('palas_west',-48,-13,1,27,28,'palas',4,7)
    box('palas_east',[-23,-11,0,20,24,25])
    roof('palas_east_roof',-23,-11,25,20,24,10,'palas')
    windows('palas_east',-23,-11,1,20,23,'palas',3,5)
    for name,x,y,w,d,h in [('bower',-2,-20,30,6,15),('knights_house',-2,14,40,7,16)]:
        box(name,[x,y,0,w,d,h],'stone',name)
        roof(name+'_roof',x,y,h,w,d,6,name)
        windows(name,x,y,0,w,h,name,2,8)
    # Gateway has a genuinely open passage, not a black rectangle on a solid box.
    box('gate_left',[49,-17,-1,7,12,15],'gate','gateway')
    box('gate_right',[49,5,-1,7,12,15],'gate','gateway')
    box('gate_lintel',[49,-5,8,7,10,6],'gate','gateway')
    roof('gate_roof',49,-17,14,7,34,5,'gateway')
    for yy in (-17,17):
        tower('gate_tower_'+str(yy).replace('-','n'),52.5,yy,-1,3.2,19,7,'gateway')
    tower('round_tower',-45,-13,0,4,43,13,'towers')
    tower('stair_tower',-4,11,0,3.1,31,10,'towers')
    box('square_tower',[23,12,0,9,10,29],'stone','towers')
    box('square_crown',[22.5,11.5,28,10,11,1.2],'trim','towers')
    for x in (23,26,29,31):
        for y in (12,21):
            box(f'merlon_{x}_{y}',[x,y,29,1,1,1.8],'stone','towers')
    line('square_crown_front',[22.5,11.4,29],[32.5,11.4,29],'towers')
    # Restrained approach lights at ground level, separated from the architecture.
    for i in range(7):
        for y in (-7,7):
            x=56+i*1.8
            box(f'path_{i}_{y}',[x,y,-1.3,.3,.3,1.5],'trim','path')
            box(f'path_light_{i}_{y}',[x-.08,y-.08,.2,.46,.46,.25],'ice','path')
    box('approach',[55,-8,-1.8,15,16,.5],'court','path')
    for i in range(24):
        a=i*2.39996323; r=48+(i%4)*6
        x,y=math.cos(a)*r,math.sin(a)*r
        if -23<y<23: continue
        add(f'pine{i}','forest',ring_mesh(x,y,-5,2.6,9,.02,7),'landscape')
    return dict(config=config,materials={**MATERIALS,'ice':config['lights']['color_srgb']},parts=parts)


def linear_rgb(color):
    def convert(n):
        v=int(n,16)/255
        return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4
    return [convert(color[i:i+2]) for i in (1,3,5)]


def gltf(m):
    """Embedded-buffer glTF 2.0; convert Z-up metres to glTF Y-up metres."""
    buffer = bytearray(); views=[]; accessors=[]; meshes=[]; nodes=[]
    materials=[]; names=list(m['materials'])
    for name,color in m['materials'].items():
        mat=dict(name=name,pbrMetallicRoughness=dict(baseColorFactor=linear_rgb(color)+[1],metallicFactor=0,roughnessFactor=.8))
        if name=='ice':
            mat['emissiveFactor']=linear_rgb(color)
            mat['extensions']={'KHR_materials_emissive_strength':{'emissiveStrength':m['config']['lights']['emissive_strength']}}
        materials.append(mat)
    def accessor(values,fmt,component,kind,target,extents=False):
        while len(buffer)%4: buffer.append(0)
        offset=len(buffer)
        flat=[n for v in values for n in v]
        buffer.extend(struct.pack('<'+fmt*len(flat),*flat))
        views.append(dict(buffer=0,byteOffset=offset,byteLength=len(buffer)-offset,target=target))
        a=dict(bufferView=len(views)-1,componentType=component,count=len(values),type=kind)
        if extents:
            a.update(min=[min(v[i] for v in values) for i in range(3)],max=[max(v[i] for v in values) for i in range(3)])
        accessors.append(a)
        return len(accessors)-1
    grouped={}
    for p in m['parts']:
        if p['material'] not in grouped:
            grouped[p['material']]=dict(id=p['material'],material=p['material'],group='material_batch',vertices=[],faces=[])
        batch=grouped[p['material']]
        offset=len(batch['vertices'])
        batch['vertices'].extend(p['vertices'])
        batch['faces'].extend([[i+offset for i in f] for f in p['faces']])
    for part in grouped.values():
        pos=[];norm=[];indices=[]
        for face in part['faces']:
            face_points=[[part['vertices'][j][0],part['vertices'][j][2],-part['vertices'][j][1]] for j in face]
            a,b,c=face_points[:3]
            u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
            n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
            length=math.sqrt(sum(t*t for t in n))
            if length<1e-10: continue
            start=len(pos);pos.extend(face_points);norm.extend([[v/length for v in n]]*len(face))
            for i in range(1,len(face)-1):indices.extend([[start],[start+i],[start+i+1]])
        primitive=dict(attributes=dict(POSITION=accessor(pos,'f',5126,'VEC3',34962,True),NORMAL=accessor(norm,'f',5126,'VEC3',34962)),
                       indices=accessor(indices,'I',5125,'SCALAR',34963),material=names.index(part['material']))
        meshes.append(dict(name=part['id'],primitives=[primitive]))
        nodes.append(dict(name=part['id'],mesh=len(meshes)-1,extras=dict(group=part['group'])))
    return dict(asset=dict(version='2.0',generator='MotionBricks black_swan_castle stdlib builder'),
                extensionsUsed=['KHR_materials_emissive_strength'],scene=0,scenes=[dict(nodes=list(range(len(nodes))))],
                nodes=nodes,meshes=meshes,materials=materials,accessors=accessors,bufferViews=views,
                buffers=[dict(byteLength=len(buffer),uri='data:application/octet-stream;base64,'+base64.b64encode(buffer).decode())])


def obj_mtl(m):
    lines=['# Artistic local metre coordinates, Z up; CC-BY-4.0; Windy Wu / AI-assisted geometry','mtllib castle.mtl']
    offset=1
    for p in m['parts']:
        lines.extend(['o '+p['id'],'usemtl '+p['material']])
        lines.extend('v '+' '.join(f'{n:.5f}' for n in v) for v in p['vertices'])
        lines.extend('f '+' '.join(str(i+offset) for i in face) for face in p['faces'])
        offset+=len(p['vertices'])
    mats=[]
    for name,color in m['materials'].items():
        rgb=' '.join(f'{int(color[i:i+2],16)/255:.6f}' for i in (1,3,5))
        mats.extend(['newmtl '+name,'Kd '+rgb,'Ke '+(rgb if name=='ice' else '0 0 0'),'illum 2',''])
    return '\n'.join(lines)+'\n','\n'.join(mats)


def preview_svg(m):
    """Deterministic static night view, independent of browser availability."""
    width,height=1440,960
    angle=math.radians(22);elev=math.radians(24)
    c,s,ce,se=math.cos(angle),math.sin(angle),math.cos(elev),math.sin(elev)
    camera=[-s*ce,-c*ce,se]
    def project(p):
        return [width*.5+(c*p[0]-s*p[1])*7.4, height*.7-((s*p[0]+c*p[1])*se+p[2]*ce)*7.4]
    out=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 960" role="img" aria-labelledby="title desc">',
         '<title id="title">黑天鹅堡 · 冰蓝之夜</title><desc id="desc">以新天鹅堡为原型的艺术模型；黑曜石配色、冰蓝屋脊和窗拱灯饰；非实测复原。</desc>',
         '<defs><linearGradient id="sky" x2="0" y2="1"><stop stop-color="#061021"/><stop offset="1" stop-color="#1c3548"/></linearGradient>',
         '<linearGradient id="fog" x2="0" y2="1"><stop stop-color="#122c3e" stop-opacity="0"/><stop offset="1" stop-color="#0e2130" stop-opacity=".9"/></linearGradient>',
         '<filter id="glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="2"/><feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>',
         '<rect width="1440" height="960" fill="url(#sky)"/>']
    for i in range(75):
        out.append(f'<circle cx="{(i*127+43)%1440}" cy="{(i*97+41)%450}" r="{.6+(i%3)*.3}" fill="#bad9ef" opacity=".4"/>')
    out.append('<circle cx="1210" cy="174" r="19" fill="#c2dfec" filter="url(#glow)"/>')
    for layer in range(3):
        points=[[0,960]]+[[i*90,430+layer*80-math.sin(i*1.8+layer*2)*45-math.cos(i*.7+layer)*60] for i in range(17)]+[[1440,960]]
        out.append('<polygon points="'+' '.join(f'{x:.2f},{y:.2f}' for x,y in points)+f'" fill="{["#122438","#162c3d","#1a3343"][layer]}"/>')
    visible=[]
    for p in m['parts']:
        for face in p['faces']:
            vertices=[p['vertices'][i] for i in face]
            a,b,d=vertices[:3];u=[b[i]-a[i] for i in range(3)];v=[d[i]-a[i] for i in range(3)]
            n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
            length=math.sqrt(sum(t*t for t in n))
            if not length:continue
            n=[t/length for t in n]
            if sum(n[i]*camera[i] for i in range(3))<=.00001:continue
            center=[sum(v[i] for v in vertices)/len(vertices) for i in range(3)]
            visible.append(((s*center[0]+c*center[1])*ce-center[2]*se,p,vertices,n))
    projected=[]
    for depth,p,vertices,n in visible:
        xy=[project(v) for v in vertices]
        bounds=[min(p[i] for p in xy) for i in range(2)]+[max(p[i] for p in xy) for i in range(2)]
        projected.append((depth,p,vertices,n,xy,bounds))
    # Structural surfaces first. Clip emission against nearer structural faces,
    # so a large wall cannot paint over its own low-level window lights.
    solids=[f for f in projected if f[1]['material']!='ice']
    ordered=sorted(solids,key=lambda f:-f[0])+[f for f in projected if f[1]['material']=='ice']
    for number,(_,p,vertices,n,xy,bounds) in enumerate(ordered):
        color=[int(m['materials'][p['material']][i:i+2],16) for i in (1,3,5)]
        ice=p['material']=='ice'
        if p['material']=='stone':color=[66,94.4,120.1]
        if p['material']=='trim':color=[96,119,133]
        shade=.92 if ice else .39+max(0,n[0]*-.35+n[1]*-.45+n[2]*.82)*.32
        fill='#'+''.join(f'{min(255,round(t*shade)):02x}' for t in color)
        points=' '.join(','.join(f'{n:.2f}' for n in v) for v in xy)
        mask=''
        if ice:
            occluders=[]
            center=[sum(v[i] for v in vertices)/len(vertices) for i in range(3)]
            for _,solid,sv,sn,sxy,sbounds in solids:
                if bounds[2]<sbounds[0] or sbounds[2]<bounds[0] or bounds[3]<sbounds[1] or sbounds[3]<bounds[1]:continue
                t=sum(sn[i]*(sv[0][i]-center[i]) for i in range(3))/sum(sn[i]*camera[i] for i in range(3))
                if t>.02:
                    occluders.append(' '.join(','.join(f'{n:.2f}' for n in v) for v in sxy))
            if occluders:
                out.append(f'<defs><mask id="light{number}" maskUnits="userSpaceOnUse" x="0" y="0" width="1440" height="960"><rect width="1440" height="960" fill="white"/>'+''.join(f'<polygon points="{p}" fill="black"/>' for p in occluders)+'</mask></defs>')
                mask=f' mask="url(#light{number})"'
        polygon=f'<polygon points="{points}" fill="{fill}"'+(' filter="url(#glow)"' if ice else ' stroke="#0b1d2b" stroke-width=".4"')+'/>'
        out.append('<g'+mask+'>'+polygon+'</g>' if mask else polygon)
    out.extend(['<rect y="740" width="1440" height="220" fill="url(#fog)"/>',
        '<g font-family="Georgia, Songti SC, serif" fill="#e5f1f8"><text x="74" y="96" font-size="42">黑天鹅堡 · 冰蓝之夜</text></g>',
        '<g font-family="Arial, sans-serif" fill="#a5c9db" letter-spacing="3"><text x="76" y="134" font-size="13">BLACK SWAN / ICE BLUE · MOTIONBRICKS ATELIER</text>',
        '<text x="76" y="875" font-size="13">NEUSCHWANSTEIN-INSPIRED · STYLIZED, NOT SURVEYED</text><text x="76" y="906" font-size="12">Windy Wu · 吴孟城 / 2026.11 / CC BY 4.0</text></g></svg>'])
    return '\n'.join(out)+'\n'


def outputs(config):
    m=model(config)
    compact=json.dumps(m,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    embedded=compact.replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    viewer=(HERE/'viewer.html').read_text(encoding='utf-8').replace('__MODEL__',embedded)
    obj,mtl=obj_mtl(m)
    # MotionBricks currently supports colored cubes, not emissive mesh imports.
    # Keep its coarse envelope preview separate from the full glTF and web model.
    parts=[dict(p,color=m['materials'][p['material']]) for p in m['parts'] if p['material']!='ice']
    scene=G.scene_document({},parts)
    scene['name']='black_swan_castle_approximate_envelopes_NO_emissive_lights'
    scene['editor']['camera'].update(pos=[110,-150,100],pivot=[0,0,15],far=2000)
    scene['character_start']['transform']['translation']=[73,0,0]
    files={'index.html':viewer,'preview.svg':preview_svg(m),'model.json':compact+'\n','castle.gltf':G.dumps(gltf(m)),
           'castle.obj':obj,'castle.mtl':mtl,'castle.envelopes.scene.json':G.dumps(scene)}
    files['manifest.json']=G.dumps(dict(concept_id=config['concept_id'],algorithm='sha256',
        files={name:hashlib.sha256(s.encode()).hexdigest() for name,s in files.items()}))
    return files


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=HERE/'output')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    config=json.loads((HERE/'design.json').read_text(encoding='utf-8'))
    files=outputs(config)
    if args.check:
        stale=[n for n,s in files.items() if not (args.output/n).exists() or (args.output/n).read_bytes()!=s.encode()]
        if stale:parser.exit(1,'Stale/missing: '+', '.join(stale)+'\n')
    else:
        args.output.mkdir(parents=True,exist_ok=True)
        for name,s in files.items():(args.output/name).write_bytes(s.encode())
    print(f'Castle {"verified" if args.check else "built"}: {len(model(config)["parts"])} parts; {len(files)} files')


if __name__=='__main__':main()
