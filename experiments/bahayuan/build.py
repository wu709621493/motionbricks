# SPDX-License-Identifier: Apache-2.0
"""Deterministic contemporary eight-courtyard massing; no construction claims."""
from __future__ import annotations
import argparse
import copy
import hashlib
import html
import importlib.util
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SPEC = importlib.util.spec_from_file_location('heritage_geometry', ROOT / 'tools/siheyuan/build.py')
G = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(G)


def validate(config):
    if config['status'] != 'contemporary_design_hypothesis' or any(config[k] is not False for k in
            ('historical_claim', 'structurally_verified', 'occupancy_approved')):
        raise ValueError('concept must remain unverified and nonhistorical')
    for key in ('storey_height_m', 'third_storey_height_m', 'third_storey_setback_m'):
        if type(config[key]) not in (int, float) or not math.isfinite(config[key]) or config[key] <= 0:
            raise ValueError('invalid ' + key)
    if len(config['module_origins_m']) != 4 or len(config['courtyard_voids_local_m']) != 2:
        raise ValueError('four two-courtyard modules required')
    if len(config['vertical_reserves_local_m']) != 2:
        raise ValueError('two vertical reservations per module required')
    origins=config['module_origins_m']
    for point in origins:
        if len(point)!=2 or not all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in point):
            raise ValueError('invalid module origin')
    for i,(x,y) in enumerate(origins):
        for a,b in origins[i+1:]:
            if min(x+24,a+24)>max(x,a) and min(y+32,b+32)>max(y,b):
                raise ValueError('module footprints overlap')
    if set(config['third_storey_ids']) - set(config['second_storey_ids']):
        raise ValueError('unsupported third storey')
    if config['source_file'] != 'data/heritage/beijing_siheyuan_1900.json':
        raise ValueError('source must be the retained archive')


def model(config):
    validate(config)
    raw = (ROOT / config['source_file']).read_bytes()
    source = json.loads(raw)
    G.validate(source)
    buildings = {e['id'] for e in source['elements'] if e['kind'] == 'building'}
    if not set(config['second_storey_ids']) <= buildings:
        raise ValueError('unknown second-storey source')
    records, parts, courts = [], [], []
    h = config['storey_height_m']

    def append(e, source_id, module, level, z=0):
        record = dict(id=e['id'], source_element=source_id, module=module, level=level,
                      kind=e['kind'], name_zh=e['name_zh'], footprint_m=e['footprint_m'],
                      base_z_m=z, height_m=e['eave_m'], roof_rise_m=e['roof_rise_m'],
                      evidence='design_hypothesis', structural_status='not_assessed')
        records.append(record)
        for p in G.geometry({'elements':[e]}):
            p['level'] = level
            p['bounds'][2] += z
            for v in p['vertices']:
                v[2] += z
            parts.append(p)

    for i,(ox,oy) in enumerate(config['module_origins_m'],1):
        for original in source['elements']:
            original_id=original['id']
            e=copy.deepcopy(original)
            e['id']=f'm{i}_{original_id}_l1'
            e['name_zh']=f'{i}号模块·{original["name_zh"]}·一层'
            e['footprint_m'][0]+=ox; e['footprint_m'][1]+=oy
            if original_id in config['second_storey_ids']:
                e['eave_m']=h; e['roof_rise_m']=0
            append(e,original_id,i,1)
            if original_id in config['second_storey_ids']:
                e['id']=f'm{i}_{original_id}_l2'
                e['name_zh']=f'{i}号模块·{original["name_zh"]}·二层'
                e['roof_rise_m']=0 if original_id in config['third_storey_ids'] else original['roof_rise_m']
                append(e,original_id,i,2,h)
            if original_id in config['third_storey_ids']:
                setback=config['third_storey_setback_m']
                x,y,dx,dy=e['footprint_m']
                if min(dx,dy) <= 2*setback:
                    raise ValueError('setback consumes footprint')
                e['footprint_m']=[x+setback,y+setback,dx-2*setback,dy-2*setback]
                e['id']=f'm{i}_{original_id}_l3'
                e['name_zh']=f'{i}号模块·{original["name_zh"]}·三层退台'
                e['eave_m']=config['third_storey_height_m'];e['roof_rise_m']=original['roof_rise_m']
                append(e,original_id,i,3,2*h)
        for j,(x,y,dx,dy) in enumerate(config['courtyard_voids_local_m'],1):
            courts.append(dict(id=f'm{i}_court{j}',footprint_m=[x+ox,y+oy,dx,dy],open_to_sky=True))
        for j,(x,y,dx,dy) in enumerate(config['vertical_reserves_local_m'],1):
            rid=f'm{i}_vertical_reserve{j}'
            height=2*h+config['third_storey_height_m']
            records.append(dict(id=rid,source_element=None,module=i,level=0,kind='reservation',
                name_zh=f'{i}号模块·竖向交通预留{j}',footprint_m=[x+ox,y+oy,dx,dy],
                base_z_m=0,height_m=height,roof_rise_m=0,evidence='design_hypothesis',
                structural_status='not_assessed',traversable=False))
    # Reservations are inventory spaces, deliberately excluded from solid meshes.
    w,d=config['site_m']
    for r in records:
        x,y,dx,dy=r['footprint_m']
        if not all(type(v) in (int,float) and math.isfinite(v) for v in [x,y,dx,dy]) or min(dx,dy)<=0 or min(x,y)<0 or x+dx>w+1e-8 or y+dy>d+1e-8:
            raise ValueError('invalid footprint '+r['id'])
    for c in courts:
        x,y,dx,dy=c['footprint_m']
        for p in parts:
            a,b,z,da,db,dz=p['bounds']
            if min(x+dx,a+da)-max(x,a)>1e-8 and min(y+dy,b+db)-max(y,b)>1e-8:
                raise ValueError('courtyard covered by '+p['id'])
    return dict(config=config,source_sha256=hashlib.sha256(raw).hexdigest(),
                records=records,courtyards=courts,parts=parts)


def plan(m, level=1):
    level_name={1:'一层',2:'二层',3:'三层'}[level]
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 880" role="img" aria-label="八合院{level_name}体量投影">',
         '<rect width="700" height="880" fill="#f6f2e8"/>',
         f'<text x="30" y="30" font-size="20">八合院概念 / {level_name}体量投影 / 非施工图</text>',
         '<text x="30" y="55" font-size="14">绿色为露天院落的地面范围，不表示楼上的悬空庭院</text>']
    def rect(fp,fill,extra=''):
        x,y,dx,dy=fp
        return f'<rect x="{50+x*10}" y="{800-(y+dy)*10}" width="{dx*10}" height="{dy*10}" fill="{fill}" stroke="#46594c" {extra}/>'
    for r in m['records']:
        if r['level']==level:
            out.append(f'<g data-level="{level}" data-element="{r["id"]}">'+rect(r['footprint_m'],G.COLORS[r['kind']])+f'<title>{html.escape(r["name_zh"])}</title></g>')
    for i,c in enumerate(m['courtyards'],1):
        out.append(rect(c['footprint_m'],'#c7d9b8'))
        x,y,dx,dy=c['footprint_m']
        out.append(f'<text x="{50+(x+dx/2)*10}" y="{800-(y+dy/2)*10}" text-anchor="middle" font-size="13">院 {i}</text>')
    for r in m['records']:
        if r['kind']=='reservation':out.append(rect(r['footprint_m'],'none','stroke-dasharray="3 3"'))
    out.append('<text x="620" y="95">北 N ↑</text><text x="30" y="845" font-size="13">54 × 70 m 假设地块 · 虚线为竖向交通预留，未建实际楼梯</text></svg>')
    return '\n'.join(out)+'\n'


def outputs(config):
    m=model(config)
    embedded=G.dumps(m).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    viewer=(HERE/'viewer.html').read_text().replace('__MODEL__',embedded).replace('__PLAN__',plan(m))
    obj=G.obj_text(m['parts']).replace('MB-BJ-SHY-C1900-001','MB-BJ-BHY-C2026-001')
    scene=G.scene_document({},m['parts'])
    scene['name']='bahayuan_2026_contemporary_nontraversable_massing'
    scene['editor']['camera'].update(pos=[95,-60,85],pivot=[27,35,0],far=2000)
    files={'model.json':G.dumps(m),'plan.svg':plan(m),'interactive.html':viewer,
           'floor2.svg':plan(m,2),'floor3.svg':plan(m,3),
           'massing.svg':G.SIMPLE.massing_svg(m['parts'],config['site_m'],'八合院 · 二层围合与三层退台'),
           'massing-no-roofs.svg':G.SIMPLE.massing_svg(m['parts'],config['site_m'],'八合院 · 隐去屋顶的封闭体量',show_roofs=False),
           'concept.obj':obj,'concept.scene.json':G.dumps(scene)}
    records=[dict(id=r['id'],name=r['name_zh'],description=
             f'平面 {r["footprint_m"][2]} × {r["footprint_m"][3]} m；底标高 {r["base_z_m"]} m；体量高 {r["height_m"]} m。'+
             ('仅为竖向交通预留，没有实际楼梯。' if r['kind']=='reservation' else '封闭体量，未建室内通道。')+
             ' 所有参数为当代设计假设，未做结构验证。') for r in m['records']]
    files.update(G.SIMPLE.pages('八合院 · 二三层概念',
        '四个两进模块，8个露天院落、116条记录。二层围合，正房局部三层退台；尺寸为假设，非古建加层施工方案。',
        'massing.svg',[('看一层与八个院落','plan.svg'),('看二层','floor2.svg'),('看三层退台','floor3.svg'),('看无屋顶体量','massing-no-roofs.svg')],
        [('下载三维模型','concept.obj'),('下载设计数据','model.json'),('下载场景文件','concept.scene.json'),('下载校验清单','manifest.json')],records))
    files['manifest.json']=G.dumps({'concept_id':config['concept_id'],'algorithm':'sha256',
        'files':{n:hashlib.sha256(c.encode()).hexdigest() for n,c in files.items()},
        'note':'Generated files only; geometry is hypothetical; reservations excluded from meshes.'})
    return files


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=HERE/'output')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args(argv)
    config=json.loads((HERE/'design.json').read_text())
    files=outputs(config)
    if args.check:
        stale=[n for n,c in files.items() if not (args.output/n).exists() or (args.output/n).read_bytes()!=c.encode()]
        if stale:parser.exit(1,'Stale/missing: '+', '.join(stale)+'\n')
    else:
        args.output.mkdir(parents=True,exist_ok=True)
        for n,c in files.items():(args.output/n).write_bytes(c.encode())
    print(f'Concept {"verified" if args.check else "built"}: 8 courtyards, {len(model(config)["records"])} records, {len(files)} files')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
