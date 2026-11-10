# SPDX-License-Identifier: Apache-2.0
import copy
import hashlib
import importlib.util
import json
from html.parser import HTMLParser
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('bahayuan',ROOT/'experiments/bahayuan/build.py')
B=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(B)


class ConceptTests(unittest.TestCase):
    def setUp(self):
        self.config=json.loads((B.HERE/'design.json').read_text())

    def test_counts_and_source_identity(self):
        path=ROOT/self.config['source_file'];before=path.read_bytes()
        m=B.model(self.config)
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(m['source_sha256'],hashlib.sha256(before).hexdigest())
        self.assertEqual(len(m['records']),116)
        self.assertEqual(len(m['courtyards']),8)
        self.assertEqual(len({r['id'] for r in m['records']}),116)
        self.assertEqual([sum(r['level']==i for r in m['records']) for i in range(4)],[8,80,24,4])
        self.assertTrue(all(r['evidence']=='design_hypothesis' for r in m['records']))

    def test_upper_storeys_supported_with_setback(self):
        m=B.model(self.config)
        for r in m['records']:
            if r['level']<2:continue
            below=next(s for s in m['records'] if s['module']==r['module'] and s['source_element']==r['source_element'] and s['level']==r['level']-1)
            self.assertAlmostEqual(r['base_z_m'],below['base_z_m']+below['height_m'])
            x,y,dx,dy=r['footprint_m'];a,b,da,db=below['footprint_m']
            self.assertGreaterEqual(x,a);self.assertGreaterEqual(y,b)
            self.assertLessEqual(x+dx,a+da+1e-8);self.assertLessEqual(y+dy,b+db+1e-8)
        self.assertAlmostEqual(max(p['bounds'][2]+p['bounds'][5] for p in m['parts']),11.9)

    def test_courtyard_obstruction_rejected(self):
        c=copy.deepcopy(self.config);c['courtyard_voids_local_m'][0]=[7,26,2,2]
        with self.assertRaisesRegex(ValueError,'courtyard covered'):B.model(c)

    def test_unfounded_claim_and_impossible_setback_rejected(self):
        for field in ('historical_claim','structurally_verified','occupancy_approved'):
            c=copy.deepcopy(self.config);c[field]=True
            with self.assertRaises(ValueError):B.model(c)
        c=copy.deepcopy(self.config);c['third_storey_setback_m']=4
        with self.assertRaises(ValueError):B.model(c)

    def test_reservations_excluded_from_solids(self):
        m=B.model(self.config);ids={r['id'] for r in m['records'] if r['kind']=='reservation'}
        self.assertEqual(len(ids),8)
        self.assertFalse(any(p['element'] in ids for p in m['parts']))

    def test_overlapping_module_and_invalid_origin_rejected(self):
        for origin in ([0,0],[float('nan'),0]):
            c=copy.deepcopy(self.config);c['module_origins_m'][1]=origin
            with self.assertRaises(ValueError):B.model(c)

    def test_deterministic_exports_and_hashes(self):
        first=B.outputs(self.config);self.assertEqual(first,B.outputs(self.config))
        manifest=json.loads(first['manifest.json'])
        for name,digest in manifest['files'].items():self.assertEqual(hashlib.sha256(first[name].encode()).hexdigest(),digest)
        self.assertNotIn('MB-BJ-SHY-C1900-001',first['concept.obj'])

    def test_static_pages_and_floor_projections(self):
        files=B.outputs(self.config)
        class Links(HTMLParser):
            def handle_starttag(self,tag,attrs):
                if tag in ('script','iframe','object'):raise AssertionError(tag)
                for key,value in attrs:
                    if key in ('href','src') and value not in files:raise AssertionError(value)
        for name in ('index.html','inventory.html'):Links().feed(files[name])
        self.assertLess(len(files['index.html'].encode()),12000)
        self.assertEqual(files['inventory.html'].count('<article id='),116)
        for name,level,count in [('plan.svg',1,80),('floor2.svg',2,24),('floor3.svg',3,4)]:
            groups=ET.fromstring(files[name]).findall('.//{http://www.w3.org/2000/svg}g')
            self.assertEqual(len(groups),count)
            self.assertTrue(all(g.attrib['data-level']==str(level) for g in groups))
        full=ET.fromstring(files['massing.svg']);hidden=ET.fromstring(files['massing-no-roofs.svg'])
        polygons=lambda root:root.findall('.//{http://www.w3.org/2000/svg}polygon')
        roofs=sum(len(p['faces']) for p in B.model(self.config)['parts'] if p['kind']=='roof')
        self.assertEqual(len(polygons(full))-len(polygons(hidden)),roofs)


if __name__=='__main__':unittest.main()
