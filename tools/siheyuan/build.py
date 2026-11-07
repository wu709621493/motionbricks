# SPDX-License-Identifier: Apache-2.0
"""Build the c.1900 Beijing courtyard archive with Python's standard library.

Geometry is illustrative, in metres, X east / Y north / Z up. The JSON catalogue
is authoritative; all exports derive from it. No runtime or GPU imports occur.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / 'data/heritage/beijing_siheyuan_1900.json'
OUTPUT = ROOT / 'docs/heritage/beijing_siheyuan_1900'
TEMPLATE = Path(__file__).with_name('viewer.html')
COLORS = {'building': '#b8aa91', 'wall': '#9d9c8e', 'gate': '#906b51',
          'gallery': '#a28160', 'roof': '#535d5b'}


def validate(data):
    """Reject ambiguous evidence and malformed geometry before exporting."""
    def require(ok, message):
        if not ok:
            raise ValueError(message)

    def number(value, positive=False):
        return (type(value) in (float, int) and math.isfinite(value)
                and (not positive or value > 0))

    require(data['schema_version'] == 1, 'unsupported schema version')
    require(data['identity']['record_type'] == 'typological_reconstruction', 'record type')
    require(data['identity']['measured_survey'] is False, 'no measured survey available')
    require(data['target_period']['exact_snapshot'] is False, 'date is approximate')
    require(data['coordinates'] == dict(units='m', origin='假设地块西南角地面',
            x='east', y='north', z='up', georeferenced=False), 'unsupported coordinates')
    w, d = data['site']['width_m'], data['site']['depth_m']
    require(number(w, True) and number(d, True), 'invalid site extent')
    require(data['site']['dimension_status'] == 'hypothesis', 'site dimensions need evidence')
    sources = {s['id']: s for s in data['sources']}
    require(len(sources) == len(data['sources']), 'duplicate source ID')
    for s in sources.values():
        require(s['url'].startswith('https://'), 'source needs an HTTPS URL')
        require(bool(s['supports']) and bool(s['limitations']), 'source scope required')
    ids = set()
    for e in data['elements']:
        require(re.fullmatch(r'[a-z][a-z0-9_]*', e['id']) is not None, 'invalid element ID')
        require(e['id'] not in ids, 'duplicate element ID')
        ids.add(e['id'])
        require(e['kind'] in ('building', 'gate', 'gallery', 'wall'), 'unknown kind')
        require(e['ridge_axis'] in ('x', 'y'), 'invalid roof axis')
        require(e['facing'] in (None, 'north', 'south', 'east', 'west'), 'invalid facing')
        b = e['footprint_m']
        require(len(b) == 4 and all(number(v) for v in b), 'invalid footprint')
        x, y, dx, dy = b
        require(dx > 0 and dy > 0, 'nonpositive dimensions')
        require(x >= 0 and y >= 0 and x + dx <= w + 1e-8 and y + dy <= d + 1e-8,
                'footprint outside site')
        require(number(e['eave_m'], True) and number(e['roof_rise_m'])
                and e['roof_rise_m'] >= 0, 'invalid height')
        require(e['kind'] != 'wall' or e['roof_rise_m'] == 0, 'wall cannot have roof rise')
        if e['kind'] in ('gate', 'gallery'):
            require(min(dx, dy) > .4 and e['eave_m'] > .3, 'opening too small')
        for key in ('form_evidence', 'geometry_evidence'):
            ev = e[key]
            require(ev['status'] in data['evidence_levels'], 'unknown evidence status')
            require(set(ev['source_ids']) <= sources.keys(), 'unknown source reference')
            require(ev['status'] == 'hypothesis' or bool(ev['source_ids']),
                    'documented claim needs source')
        require(e['geometry_evidence']['status'] == 'hypothesis', 'no surveyed geometry')
    points = data['route']['points_m']
    require(len(points) >= 2 and all(len(p) == 2 and all(number(v) for v in p)
            for p in points), 'invalid route')
    require(number(data['route']['clearance_radius_m'], True), 'invalid route clearance')
    require('LOC1900' in sources and sources['LOC1900']['depicted_year'] == 1900
            and sources['LOC1900']['publication_year'] == 1902,
            'keep photograph date separate from publication date')


def box_mesh(b):
    x, y, z, dx, dy, dz = b
    vertices = [[x,y,z],[x+dx,y,z],[x+dx,y+dy,z],[x,y+dy,z],
                [x,y,z+dz],[x+dx,y,z+dz],[x+dx,y+dy,z+dz],[x,y+dy,z+dz]]
    faces = [[0,3,2,1],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7],[4,5,6,7]]
    return vertices, faces


def roof_mesh(e):
    x, y, dx, dy = e['footprint_m']
    z, h = e['eave_m'], e['roof_rise_m']
    # A closed triangular prism; no tile detail or unsupported eave overhang.
    v = [[x,y,z],[x+dx,y,z],[x+dx,y+dy,z],[x,y+dy,z]]
    if e['ridge_axis'] == 'x':
        v += [[x,y+dy/2,z+h],[x+dx,y+dy/2,z+h]]
        f = [[0,3,2,1],[0,1,5,4],[1,2,5],[2,3,4,5],[3,0,4]]
    else:
        v += [[x+dx/2,y,z+h],[x+dx/2,y+dy,z+h]]
        f = [[0,3,2,1],[0,1,4],[1,2,5,4],[2,3,5],[3,0,4,5]]
    return v, f


def geometry(data):
    parts = []
    for e in data['elements']:
        x,y,dx,dy = e['footprint_m']
        z = e['eave_m']
        boxes = []
        if e['kind'] in ('building', 'wall'):
            boxes.append([x,y,0,dx,dy,z])
        elif e['kind'] == 'gate':
            # Side piers and a lintel leave a real open passage north/south.
            boxes += [[x,y,0,.3,dy,z],[x+dx-.3,y,0,.3,dy,z],
                      [x+.3,y,z-.25,dx-.6,dy,.25]]
        else:
            # Open galleries: paired end posts and additional long-axis posts.
            count = max(1, math.ceil(max(dx,dy)/3))
            for i in range(count+1):
                t=i/count
                for edge in (0,1):
                    px=x+(dx-.15)*(t if dx>dy else edge)
                    py=y+(dy-.15)*(edge if dx>dy else t)
                    boxes.append([px,py,0,.15,.15,z])
            boxes.append([x,y,z-.15,dx,dy,.15])
        for i,b in enumerate(boxes):
            v,f=box_mesh(b)
            parts.append(dict(id=f"{e['id']}_{i}", element=e['id'], kind=e['kind'],
                              color=COLORS[e['kind']], bounds=b, vertices=v, faces=f))
        if e['roof_rise_m']:
            v,f=roof_mesh(e)
            parts.append(dict(id=e['id']+'_roof',element=e['id'],kind='roof',
                              color=COLORS['roof'],bounds=[x,y,z,dx,dy,e['roof_rise_m']],
                              vertices=v,faces=f))
    return parts


def check_route(data, parts):
    """Check a vertical 1.8 m envelope along an illustrative centre line.

    This is a geometric sanity check, not motion or accessibility validation.
    Rectangle expansion is conservative at corners.
    """
    r = data['route']['clearance_radius_m']
    for a,b in zip(data['route']['points_m'],data['route']['points_m'][1:]):
        steps=max(1, math.ceil(math.dist(a,b)/.05))
        for i in range(steps+1):
            t=i/steps; px=a[0]+(b[0]-a[0])*t; py=a[1]+(b[1]-a[1])*t
            for p in parts:
                x,y,z,dx,dy,dz=p['bounds']
                if z >= 1.8 or z+dz <= 0:
                    continue
                if x-r < px < x+dx+r and y-r < py < y+dy+r:
                    raise ValueError('route intersects '+p['id'])


def plan_svg(data):
    # Coordinates remain north-up. Output labels retain human-readable names.
    width,depth=data['site']['width_m'],data['site']['depth_m']
    scale=18; ox=80; oy=70
    def xy(x,y): return ox+x*scale, oy+(depth-y)*scale
    out=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 760" role="img" aria-labelledby="plan-title">',
         '<title id="plan-title">北京四合院约1900年：假设尺度、北向朝上的类型平面图</title>',
         '<style>text{font-family:Arial,"Noto Sans CJK SC",sans-serif;fill:#263d37}.label{font-size:12px}.room{stroke:#40564b;stroke-width:1.2}.room:focus{stroke:#a54d35;stroke-width:4;outline:none}</style>',
         '<rect width="600" height="760" fill="#f6f2e8"/>',
         '<text x="40" y="30" font-size="16">类型复原 · 所有尺寸为假设</text>',
         f'<rect x="{ox}" y="{oy}" width="{width*scale}" height="{depth*scale}" fill="#e9e1cf"/>']
    for e in data['elements']:
        x,y,dx,dy=e['footprint_m']; px,py=xy(x,y+dy)
        color=COLORS[e['kind']]
        if e['kind'] in ('gate','gallery'): color='#d9c8a8'
        out.append(f'<g class="room" tabindex="0" role="button" aria-label="{html.escape(e["name_zh"])}" data-element="{e["id"]}"><title>{html.escape(e["name_zh"])}：形制参考，尺寸假设</title><rect x="{px:.2f}" y="{py:.2f}" width="{dx*scale:.2f}" height="{dy*scale:.2f}" fill="{color}"/></g>')
        if e['kind']=='building':
            # Facade marker only; footprint is a massing outline, not floor-plan walls.
            cx,cy=xy(x+dx/2,y+dy/2)
            out.append(f'<text class="label" text-anchor="middle" x="{cx:.2f}" y="{cy:.2f}" pointer-events="none">{e["name_zh"]}</text>')
    points=' '.join(f'{xy(*p)[0]:.2f},{xy(*p)[1]:.2f}' for p in data['route']['points_m'])
    out.append(f'<polyline data-route="true" points="{points}" fill="none" stroke="#a34a36" stroke-width="2.5" stroke-dasharray="6 5" pointer-events="none"/>')
    for label,x,y in [('内院',12,19),('前院',6.6,7.3),('街门',20.5,2.6),('垂花门',12,10.7),('影壁',20.5,7.9),('胡同（示意）',12,-2.6)]:
        px,py=xy(x,y)
        out.append(f'<text class="label" text-anchor="middle" x="{px}" y="{py}" pointer-events="none">{label}</text>')
    out += ['<path d="M550 110 V65 M544 76 L550 65 L556 76" stroke="#263d37" fill="none" stroke-width="2"/><text x="544" y="55">N</text>',
            f'<path d="M80 717 h{5*scale}" stroke="#263d37" stroke-width="3"/><text x="80" y="738" font-size="12">0</text><text x="156" y="738" font-size="12">5 m（模型尺度）</text>',
            '</svg>']
    return '\n'.join(out)+'\n'


def obj_text(parts):
    out=['# MB-BJ-SHY-C1900-001 | hypothetical massing; NOT a surveyed property',
         '# units: metres; X east, Y north, Z up; origin at southwest ground corner',
         '# Original geometry: CC-BY-4.0; concept: Windy Wu; AI-assisted modelling']
    offset=1
    for p in parts:
        out.append('o '+p['id'])
        out.extend('v '+' '.join(f'{n:.6f}' for n in v) for v in p['vertices'])
        out.extend('f '+' '.join(str(i+offset) for i in f) for f in p['faces'])
        offset+=len(p['vertices'])
    return '\n'.join(out)+'\n'


def axonometric_svg(data, parts):
    """A static companion to the interactive view, using its initial projection."""
    angle = math.radians(35)
    c, s = math.cos(angle), math.sin(angle)
    def project(p):
        x, y, z = p[0]-12, p[1]-16, p[2] if len(p)>2 else 0
        return f'{450+(c*x-s*y)*20:.2f},{370-(s*x+c*y)*10-z*24:.2f}'
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 720" role="img" aria-labelledby="title">',
           '<title id="title">约1900年北京四合院类型体量图；全部几何为假设</title>',
           '<rect width="900" height="720" fill="#f6f2e8"/>']
    ground = ' '.join(project(p) for p in [[0,0],[24,0],[24,32],[0,32]])
    out.append(f'<polygon points="{ground}" fill="#e6decb"/>')
    route = ' '.join(project(p) for p in data['route']['points_m'])
    out.append(f'<polyline points="{route}" fill="none" stroke="#a34a36" stroke-width="2.5" stroke-dasharray="6 5"/>')
    faces = []
    for p in parts:
        for i, face in enumerate(p['faces']):
            v = [p['vertices'][j] for j in face]
            depth = sum(-s*(pt[0]-12)-c*(pt[1]-16)+pt[2]*.2 for pt in v)/len(v)
            faces.append((depth,p,i,v))
    for _, p, i, v in sorted(faces, key=lambda f:f[0]):
        points = ' '.join(project(pt) for pt in v)
        out.append(f'<polygon points="{points}" fill="{p["color"]}" stroke="#354f45" stroke-width=".7" stroke-linejoin="round"/>')
    out += ['<g font-family="Arial, Noto Sans CJK SC, sans-serif" fill="#233d35">',
            '<text x="40" y="48" font-size="26">北京四合院 · 约 1900 年</text>',
            '<text x="40" y="78" font-size="14">两进院落类型复原 / 所有位置、尺寸与色彩均为假设</text>',
            '<text x="40" y="675" font-size="14">MB-BJ-SHY-C1900-001 · 非实测 · X 东 / Y 北 / Z 上</text>',
            '</g></svg>']
    return '\n'.join(out)+'\n'


def scene_document(data, parts):
    cubes=[]
    for i,p in enumerate(parts,2):
        x,y,z,dx,dy,dz=p['bounds']
        color=[int(p['color'][j:j+2],16)/255 for j in (1,3,5)]
        cubes.append(dict(id=i,name=p['id'],parent_id=None,
            transform=dict(translation=[x+dx/2,y+dy/2,z+dz/2],rotation_xyzw=[0,0,0,1]),
            euler_degrees=[0,0,0], dimensions=dict(width=dx,depth=dy,height=dz),color=color))
    return dict(format='motionbricks.scene',schema_version=1,
        name='beijing_siheyuan_c1900_hypothetical_exterior_envelopes',rig='unitree_g1',
        editor=dict(selected_item_id=1, camera=dict(pos=[45,-28,38],pivot=[12,16,0],
                    pitch=-34.6,yaw=126.87,fov=45,near=.01,far=1000)),
        character_start=dict(id=1,transform=dict(translation=[20.5,-2,0],
            rotation_xyzw=[0,0,0,1]),euler_degrees=[0,0,0]),
        smart_primitives=[],solid_cubes=cubes)


def dumps(data):
    return json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n'


def build(data):
    validate(data)
    parts=geometry(data)
    check_route(data,parts)
    plan=plan_svg(data)
    embedded=dumps(dict(catalog=data,parts=parts)).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    viewer=TEMPLATE.read_text(encoding='utf-8').replace('__PLAN_SVG__',plan).replace('__ARCHIVE_JSON__',embedded)
    return {'index.html':viewer,'plan.svg':plan,'axonometric.svg':axonometric_svg(data,parts),
            'courtyard.obj':obj_text(parts),
            'courtyard.scene.json':dumps(scene_document(data,parts)),
            'catalog.json':dumps(data)}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--check',action='store_true',help='verify committed exports and manifest')
    args=parser.parse_args(argv)
    data=json.loads(CATALOG.read_text(encoding='utf-8'))
    files=build(data)
    hashes={name:hashlib.sha256(content.encode()).hexdigest() for name,content in files.items()}
    files['manifest.json']=dumps(dict(archive_id=data['archive_id'],revision=data['revision'],
        algorithm='sha256',files=hashes,note='Generated files only; manifest excludes itself.'))
    if args.check:
        stale=[name for name,content in files.items() if not (args.output/name).exists()
               or (args.output/name).read_bytes()!=content.encode('utf-8')]
        if stale:
            parser.exit(1,'Stale or missing exports: '+', '.join(stale)+'\n')
        print(f'Archive verified: {len(data["elements"])} elements, {len(data["sources"])} sources, {len(files)} files')
    else:
        args.output.mkdir(parents=True,exist_ok=True)
        for name,content in files.items():
            (args.output/name).write_bytes(content.encode('utf-8'))
        print(f'Built {len(files)} archive files in {args.output}')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
