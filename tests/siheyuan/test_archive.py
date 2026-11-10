# SPDX-License-Identifier: Apache-2.0
"""Evidence, export and passability regressions for the heritage archive."""
import ast
import copy
import importlib.util
import json
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('siheyuan_build',ROOT/'tools/siheyuan/build.py')
build=importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads(build.CATALOG.read_text(encoding='utf-8'))

    def test_catalog_and_exterior_route(self):
        build.validate(self.data)
        build.check_route(self.data,build.geometry(self.data))
        self.assertFalse(self.data['identity']['photo_matched'])

    def test_reject_bad_source_and_unfounded_geometry(self):
        for field,value in [('source_ids',['MISSING']),('status','primary')]:
            d=copy.deepcopy(self.data)
            d['elements'][0]['geometry_evidence'][field]=value
            with self.assertRaises(ValueError):
                build.validate(d)
        d=copy.deepcopy(self.data)
        d['elements'][0]['form_evidence']['source_ids']=[]
        with self.assertRaises(ValueError):
            build.validate(d)

    def test_reject_invalid_coordinates_and_ids(self):
        for value in (float('nan'),float('inf'),-1,True,100):
            d=copy.deepcopy(self.data)
            d['elements'][0]['footprint_m'][2]=value
            with self.assertRaises(ValueError):
                build.validate(d)
        d=copy.deepcopy(self.data)
        d['elements'][1]['id']=d['elements'][0]['id']
        with self.assertRaises(ValueError):
            build.validate(d)

    def test_photograph_capture_and_publication_remain_distinct(self):
        d=copy.deepcopy(self.data)
        d['sources'][0]['depicted_year']=1902
        with self.assertRaisesRegex(ValueError,'photograph date'):
            build.validate(d)

    def test_route_detects_blocked_gate(self):
        parts=build.geometry(self.data)
        parts.append(dict(id='blocked_gate',bounds=[18.6,1,0,3.8,.4,3]))
        with self.assertRaisesRegex(ValueError,'blocked_gate'):
            build.check_route(self.data,parts)

    def test_mesh_is_closed_outward_and_scene_matches_bounds(self):
        parts=build.geometry(self.data)
        scene=build.scene_document(self.data,parts)
        self.assertEqual(len(scene['solid_cubes']),len(parts))
        self.assertEqual(len({c['id'] for c in scene['solid_cubes']}),len(parts))
        for p,c in zip(parts,scene['solid_cubes']):
            edges={}
            volume=0
            for f in p['faces']:
                for a,b in zip(f,f[1:]+f[:1]):
                    self.assertNotEqual(a,b)
                    self.assertTrue(0 <= a < len(p['vertices']))
                    key=tuple(sorted((a,b)))
                    edges.setdefault(key,[]).append((a,b))
                a=p['vertices'][f[0]]
                for i in range(1,len(f)-1):
                    b=p['vertices'][f[i]];cpt=p['vertices'][f[i+1]]
                    cross=[b[1]*cpt[2]-b[2]*cpt[1],b[2]*cpt[0]-b[0]*cpt[2],b[0]*cpt[1]-b[1]*cpt[0]]
                    volume+=sum(x*y for x,y in zip(a,cross))/6
            self.assertGreater(volume,0,p['id'])
            for edge in edges.values():
                self.assertEqual(len(edge),2,p['id'])
                self.assertEqual(edge[0],tuple(reversed(edge[1])),p['id'])
            x,y,z,dx,dy,dz=p['bounds']
            self.assertEqual(c['dimensions'],dict(width=dx,depth=dy,height=dz))
            self.assertEqual(c['transform']['translation'],[x+dx/2,y+dy/2,z+dz/2])

    def test_html_escapes_embedded_json(self):
        d=copy.deepcopy(self.data)
        d['elements'][0]['description_zh']='</script><script>alert(1)</script>'
        page=build.build(d)['interactive.html']
        self.assertNotIn('</script><script>alert(1)</script>',page)
        self.assertIn('\\u003c/script\\u003e',page)

    def test_plan_escapes_component_names_as_text(self):
        d=copy.deepcopy(self.data)
        label='正房 <script>alert(1)</script> & "未核实"'
        d['elements'][0]['name_zh']=label
        root=ET.fromstring(build.plan_svg(d))
        self.assertFalse(root.findall('.//{http://www.w3.org/2000/svg}script'))
        labels=root.findall('.//{http://www.w3.org/2000/svg}text')
        self.assertIn(label,[n.text for n in labels])

    def test_static_entry_has_no_script_and_resolves_local_assets(self):
        files=build.build(self.data)
        class Links(HTMLParser):
            def handle_starttag(self,tag,attrs):
                if tag in ('script','iframe','object'):raise AssertionError(tag)
                for key,value in attrs:
                    if key in ('src','href') and not value.startswith('https://'):
                        if value not in files and value!='manifest.json':raise AssertionError(value)
        for name in ('index.html','inventory.html'):Links().feed(files[name])
        self.assertLess(len(files['index.html'].encode()),12000)
        self.assertNotIn('archive-data',files['index.html'])
        self.assertEqual(files['inventory.html'].count('<article id='),20)
        self.assertIn('archive-data',files['interactive.html'])

    def test_export_fields_match_upstream_scene_contract(self):
        # Read the actual upstream field tuples without importing its GPU stack.
        def constants(path):
            result={}
            for node in ast.parse(path.read_text(encoding='utf-8')).body:
                if isinstance(node,ast.Assign) and isinstance(node.value,ast.Tuple):
                    for name in node.targets:
                        if isinstance(name,ast.Name):
                            result[name.id]=ast.literal_eval(node.value)
            return result
        io=constants(ROOT/'app/runtime/common/io/document_io.py')
        sc=constants(ROOT/'app/runtime/common/io/scene_document.py')
        scene=build.scene_document(self.data,build.geometry(self.data))
        self.assertEqual(set(scene),set(io['_HEADER_FIELDS']+sc['_CONTENT_FIELDS']))
        self.assertEqual(set(scene['editor']),{'selected_item_id','camera'})
        self.assertEqual(set(scene['editor']['camera']),set(io['_CAMERA_FIELDS']))
        self.assertEqual(set(scene['character_start']),set(sc['_CHARACTER_START_FIELDS']))
        for cube in scene['solid_cubes']:
            self.assertEqual(set(cube),set(sc['_SOLID_CUBE_FIELDS']))
            self.assertEqual(set(cube['transform']),set(io['TRANSFORM_FIELDS']))
            self.assertEqual(set(cube['dimensions']),set(sc['_SOLID_CUBE_DIMENSION_FIELDS']))

    def test_rebuild_and_tamper_detection(self):
        self.assertEqual(build.build(self.data),build.build(self.data))
        with tempfile.TemporaryDirectory() as tmp:
            build.main(['--output',tmp])
            self.assertEqual(build.main(['--output',tmp,'--check']),0)
            path=Path(tmp)/'plan.svg';path.write_text('tampered',encoding='utf-8')
            with self.assertRaises(SystemExit) as error:
                build.main(['--output',tmp,'--check'])
            self.assertEqual(error.exception.code,1)


if __name__=='__main__':
    unittest.main()
