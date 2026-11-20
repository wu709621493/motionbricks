"""Build a zero-dependency Minecraft Java 1.21 hospital walk-through data pack.

Run: python examples/minecraft/jjpcs_hospital.py
Place JJPCS_Hospital_1_21.zip in a disposable creative world's datapacks/
directory, /reload, then /function jjpcs:build while standing on flat ground.
Overwrites a 41 x 20 x 11 box starting two blocks east and one block below
your feet, extending south. Use in loaded chunks with commands enabled.
Green: clinical transfer. Blue: guests. Orange: waste. Scaffolding stands
in for lift cars: jump/sneak to change levels. Open roofs allow inspection.
This blockout uses no inference, mods, server credentials or live systems.
"""
import itertools
import json
import zipfile
from collections import deque

commands = []
blocks = {}


def box(x1, y1, z1, x2, y2, z2, material):
    bounds = (x1, y1, z1, x2, y2, z2)
    assert 0 <= x1 <= x2 <= 40 and 0 <= y1 <= y2 <= 10 and 0 <= z1 <= z2 <= 19
    coords = " ".join(f"~{v}" for v in bounds)
    commands.append(f"fill {coords} minecraft:{material}")
    for point in itertools.product(range(x1, x2+1), range(y1, y2+1), range(z1, z2+1)):
        blocks[point] = material


def label(x,y,z,title):
    # Freestanding oak signs, supported by the finished floor.
    msg = json.dumps({"text":title},ensure_ascii=False)
    commands.append(f"""setblock ~{x} ~{y} ~{z} minecraft:oak_sign[rotation=8]{{front_text:{{messages:['{msg}','""','""','""']}}}}""")


def build():
    commands.clear()
    blocks.clear()
    box(0,0,0,40,10,19,"air")
    # Two wings. Each floor's rear service lane is enclosed to the ceiling.
    for x,end in [(0,17),(22,40)]:
        for y in [0,5]:
            box(x,y,0,end,y,19,"smooth_quartz")
            for edge in [x,end]:
                box(edge,y+1,0,edge,y+4,19,"white_concrete")
                box(edge,y+2,2,edge,y+3,5,"glass")
            for z in [0,14,19]:
                box(x,y+1,z,end,y+4,z,"white_concrete")
            box(x+1,y,7,end-1,y,9,"lime_concrete")
            box(x+1,y,16,end-1,y,17,"orange_concrete")
            # Bed bays with low privacy screens and contrasting pillows.
            for bx in [x+3,x+9]:
                box(bx,y+1,2,bx+1,y+1,4,"light_blue_concrete")
                box(bx,y+1,2,bx+1,y+1,2,"white_wool")
                box(bx+2,y+1,2,bx+2,y+2,4,"birch_planks")
            box(x+1,y,11,end-1,y,12,"light_blue_concrete")
            for lx in [x+2,end-2]:
                box(lx,y,6,lx,y,6,"sea_lantern")
    # Enclosed clinical bridge at both levels, with separate outside service exit.
    for y in [0,5]:
        box(17,y,6,22,y,10,"lime_concrete")
        for x in [17,22]:
            box(x,y+1,7,x,y+3,9,"air")
        for z in [6,10]:
            box(18,y+1,z,21,y+3,z,"glass")
    box(18,10,6,21,10,10,"smooth_quartz")
    box(5,1,0,7,3,0,"air")
    box(12,1,19,14,3,19,"air")
    box(11,1,15,11,2,15,"orange_concrete")
    # Sealed handoff lockers in the partition: loaded from clean side,
    # collected from rear. Full blocks, no personnel passage.
    for y in [1,6]:
        box(8,y,14,8,y,14,"barrel")
    for x,z in [(5,12),(5,16),(30,12)]:
        box(x,5,z,x,5,z,"air")
        box(x,1,z,x,6,z,"scaffolding")
    for x,y,z,name in [(2,1,1,"JJPCS | ENTRY"),(2,6,1,"JJPCS | WARD"),
                         (25,1,6,"ED | HANDOFF"),(25,6,6,"NEONATAL UNIT"),
                         (6,1,12,"GUEST LIFT"),(6,6,12,"GUEST LIFT"),
                         (6,1,16,"WASTE LIFT"),(6,6,16,"WASTE LIFT"),
                         (13,1,15,"WASTE | PICKUP"),(9,6,13,"WASTE HANDOFF")]:
        label(x,y,z,name)


def reachable(start):
    # Indoor walking grid only. Two-block clearance; vertical travel at shafts.
    seen = {start}
    queue = deque([start])
    while queue:
        x,y,z = queue.popleft()
        for dx,dy,dz in [(1,0,0),(-1,0,0),(0,0,1),(0,0,-1),(0,1,0),(0,-1,0)]:
            a,b,c = x+dx,y+dy,z+dz
            point = (a,b,c)
            if not (0 <= a <= 40 and 1 <= b <= 9 and 0 <= c <= 19) or point in seen:
                continue
            cell = blocks.get(point)
            if cell not in ('air','scaffolding') or blocks.get((a,b+1,c)) not in ('air','scaffolding'):
                continue
            if dy and 'scaffolding' not in (blocks[x,y,z],cell):
                continue
            if cell == 'air' and blocks.get((a,b-1,c)) == 'air':
                continue
            seen.add(point)
            queue.append(point)
    return seen


if __name__ == '__main__':
    build()
    clinical = reachable((8,6,5))
    waste = reachable((8,6,15))
    assert {(25,6,8),(25,1,8),(5,1,12),(8,6,13)} <= clinical
    assert {(13,1,19),(5,1,16)} <= waste and clinical.isdisjoint(waste)
    with zipfile.ZipFile("JJPCS_Hospital_1_21.zip","w",zipfile.ZIP_DEFLATED) as pack:
        pack.writestr("pack.mcmeta",json.dumps({"pack":{"pack_format":48,"description":"JJPCS hospital transfer and service routes"}}))
        pack.writestr("data/jjpcs/function/build.mcfunction","execute align xyz positioned ~2 ~-1 ~ run function jjpcs:layout\n")
        pack.writestr("data/jjpcs/function/layout.mcfunction","\n".join(commands)+"\n")
    print("Built pack and verified separate indoor routes.")
