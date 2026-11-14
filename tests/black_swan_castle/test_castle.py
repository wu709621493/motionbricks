# SPDX-License-Identifier: Apache-2.0
import base64
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('castle',ROOT/'experiments/black_swan_castle/build.py')
B=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(B)


class CastleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=json.loads((B.HERE/'design.json').read_text())
        cls.model=B.model(cls.config)
        cls.files=B.outputs(cls.config)

    def test_closed_finite_meshes_and_outward_faces(self):
        ids=set()
        for p in self.model['parts']:
            self.assertNotIn(p['id'],ids);ids.add(p['id'])
            self.assertTrue(all(math.isfinite(n) for v in p['vertices'] for n in v))
            center=[sum(v[i] for v in p['vertices'])/len(p['vertices']) for i in range(3)]
            edges={}
            for f in p['faces']:
                self.assertGreaterEqual(len(f),3)
                a,b,c=[p['vertices'][j] for j in f[:3]]
                u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
                n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
                self.assertGreater(sum(n[i]*(a[i]-center[i]) for i in range(3)),0,p['id'])
                for a,b in zip(f,f[1:]+f[:1]):
                    k=tuple(sorted((a,b)));edges[k]=edges.get(k,0)+1
            self.assertTrue(all(n==2 for n in edges.values()),p['id'])

    def test_courtyards_and_gateway_remain_open(self):
        def occupied(x,y,z,p):
            a,b,c,w,d,h=p['bounds'];return a<x<a+w and b<y<b+d and c<z<c+h
        architecture=[p for p in self.model['parts'] if p['group'] not in ('landscape','path')]
        for point in [(10,0,2),(38,0,2),(52,0,2)]:
            self.assertFalse(any(occupied(*point,p) for p in architecture),point)

    def test_lights_are_separate_and_cover_architecture(self):
        lights=[p for p in self.model['parts'] if p['material']=='ice']
        self.assertGreater(len(lights),100)
        self.assertEqual({p['group'] for p in lights},{'palas','bower','knights_house','gateway','towers','path'})
        scene=json.loads(self.files['castle.envelopes.scene.json'])
        self.assertFalse(any(p['name'] in {x['id'] for x in lights} for p in scene['solid_cubes']))
        self.assertIn('NO_emissive_lights',scene['name'])

    def test_gltf_buffers_indices_normals_axes_and_emission(self):
        g=json.loads(self.files['castle.gltf']);raw=base64.b64decode(g['buffers'][0]['uri'].split(',')[1])
        self.assertEqual(len(raw),g['buffers'][0]['byteLength'])
        def values(index):
            a=g['accessors'][index];v=g['bufferViews'][a['bufferView']]
            self.assertEqual(v['byteOffset']%4,0)
            count=a['count']*(3 if a['type']=='VEC3' else 1)
            self.assertEqual(v['byteLength'],count*4)
            self.assertLessEqual(v['byteOffset']+v['byteLength'],len(raw))
            return struct.unpack_from('<'+('f' if a['componentType']==5126 else 'I')*count,raw,v['byteOffset'])
        for mesh in g['meshes']:
            p=mesh['primitives'][0];pos=values(p['attributes']['POSITION']);normal=values(p['attributes']['NORMAL']);idx=values(p['indices'])
            self.assertTrue(all(math.isfinite(v) for v in pos+normal))
            self.assertEqual(len(idx)%3,0);self.assertLess(max(idx),len(pos)//3)
            for i in range(0,len(normal),3):self.assertAlmostEqual(math.hypot(*normal[i:i+3]),1,places=5)
        ice=next(m for m in g['materials'] if m['name']=='ice')
        self.assertEqual(ice['extensions']['KHR_materials_emissive_strength']['emissiveStrength'],4)
        self.assertGreater(ice['emissiveFactor'][2],ice['emissiveFactor'][0])
        first=g['meshes'][0]['primitives'][0]
        positions=values(first['attributes']['POSITION'])
        original=self.model['parts'][0]['vertices'][self.model['parts'][0]['faces'][0][0]]
        for a,b in zip(positions[:3],[original[0],original[2],-original[1]]):self.assertAlmostEqual(a,b,places=4)

    def test_manifest_and_deterministic_build(self):
        self.assertEqual(self.files,B.outputs(self.config))
        for name,digest in json.loads(self.files['manifest.json'])['files'].items():
            self.assertEqual(hashlib.sha256(self.files[name].encode()).hexdigest(),digest)
        svg=ET.fromstring(self.files['preview.svg'])
        self.assertEqual(svg.attrib['viewBox'],'0 0 1440 960')

    def test_no_historical_claim_or_invalid_light(self):
        for key,value in [('historical_lighting',True),('geometry_status','surveyed')]:
            config=copy.deepcopy(self.config);config[key]=value
            with self.assertRaises(ValueError):B.model(config)
        for value in [-1,float('nan'),True,100]:
            config=copy.deepcopy(self.config);config['lights']['emissive_strength']=value
            with self.assertRaises(ValueError):B.model(config)


if __name__=='__main__':unittest.main()
