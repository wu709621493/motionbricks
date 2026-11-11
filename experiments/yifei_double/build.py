# SPDX-License-Identifier: Apache-2.0
"""Original procedural audition, CPU only. Never claims neural inference."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FPS = 30
DURATION = 12
# Original illustrative anatomy, metres, Y up; not recovered from sample data.
# Joint names follow the SOMA manifest; proportions are NOT certified SOMA geometry.
RIG = [
    ("Hips", -1, (0, .92, 0)),
    ("Spine1", 0, (0, .12, 0)), ("Spine2", 1, (0, .12, 0)),
    ("Chest", 2, (0, .15, 0)), ("Neck1", 3, (0, .10, 0)),
    ("Neck2", 4, (0, .07, 0)), ("Head", 5, (0, .10, 0)),
    ("Jaw", 6, (0, -.04, .06)), ("LeftEye", 6, (.03, .03, .07)),
    ("RightEye", 6, (-.03, .03, .07)),
    ("LeftShoulder", 3, (.08, .03, 0)), ("LeftArm", 10, (.10, 0, 0)),
    ("LeftForeArm", 11, (.26, 0, 0)), ("LeftHand", 12, (.24, 0, 0)),
    ("LeftHandThumbEnd", 13, (.05, 0, .04)),
    ("LeftHandMiddleEnd", 13, (.08, 0, 0)),
    ("RightShoulder", 3, (-.08, .03, 0)), ("RightArm", 16, (-.10, 0, 0)),
    ("RightForeArm", 17, (-.26, 0, 0)), ("RightHand", 18, (-.24, 0, 0)),
    ("RightHandThumbEnd", 19, (-.05, 0, .04)),
    ("RightHandMiddleEnd", 19, (-.08, 0, 0)),
    ("LeftLeg", 0, (.09, -.03, 0)), ("LeftShin", 22, (0, -.43, 0)),
    ("LeftFoot", 23, (0, -.43, 0)), ("LeftToeBase", 24, (0, 0, .14)),
    ("RightLeg", 0, (-.09, -.03, 0)), ("RightShin", 26, (0, -.43, 0)),
    ("RightFoot", 27, (0, -.43, 0)), ("RightToeBase", 28, (0, 0, .14)),
]
INDEX = {joint[0]: i for i, joint in enumerate(RIG)}


def multiply(a, b):
    x, y, z, w = a
    X, Y, Z, W = b
    return [w*X+x*W+y*Z-z*Y, w*Y-x*Z+y*W+z*X,
            w*Z+x*Y-y*X+z*W, w*W-x*X-y*Y-z*Z]


def quaternion(x=0., y=0., z=0.):
    q = [0., 0., 0., 1.]
    for axis, degrees in enumerate((x, y, z)):
        half = math.radians(degrees) / 2
        r = [0., 0., 0., math.cos(half)]
        r[axis] = math.sin(half)
        q = multiply(q, r)
    return q


def rotate(q, vector):
    return multiply(multiply(q, [*vector, 0]), [-q[0], -q[1], -q[2], q[3]])[:3]


def smooth(v):
    v = min(1., max(0., v))
    return v*v*(3-2*v)


def pose(time):
    """A 12-second authored take: entrance, turn, salute. No sample clips."""
    if not math.isfinite(time):
        raise ValueError("time must be finite")
    t = min(float(DURATION), max(0., time))
    p = [[*offset, 0., 0., 0., 1.] for _, _, offset in RIG]
    def setq(name, **angles):
        p[INDEX[name]][3:] = quaternion(**angles)
    walk = math.sin(2 * math.pi * t) * (1 - smooth((t-3)/1))
    turn = smooth((t-4)/3)
    salute = smooth((t-8)/1.5) * (1-.7*smooth((t-10.5)/1.5))
    p[0][:3] = [.38*math.sin(math.pi * min(t,4)/4), .92+.018*abs(walk), 0]
    setq("Hips", y=360*turn)
    setq("Chest", y=12*salute, z=3*walk)
    setq("Head", y=-10*salute)
    setq("LeftLeg", x=25*walk)
    setq("RightLeg", x=-25*walk)
    setq("LeftShin", x=max(0., -walk)*28)
    setq("RightShin", x=max(0., walk)*28)
    setq("LeftArm", x=15*walk, z=-72+55*salute)
    setq("RightArm", x=-15*walk, z=72-130*salute)
    setq("LeftForeArm", y=-25*salute, z=-15-50*salute)
    setq("RightForeArm", y=20*salute, z=15+50*salute)
    setq("RightHand", y=25*salute)
    return p


def world_positions(local):
    """Quaternion forward kinematics, parent before child."""
    world, rotations = [], []
    for (_, parent, _), transform in zip(RIG, local):
        if parent < 0:
            world.append(transform[:3])
            rotations.append(transform[3:])
        else:
            offset = rotate(rotations[parent], transform[:3])
            world.append([a+b for a,b in zip(world[parent], offset)])
            rotations.append(multiply(rotations[parent], transform[3:]))
    return world


def pose_window(context_end=4., target_start=5.):
    return {"model":"soma", "joint_names":[r[0] for r in RIG],
            "context":[pose(context_end-(3-i)/FPS) for i in range(4)],
            "target":[pose(target_start+i/FPS) for i in range(4)]}


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "motionbricks/assets/onnx/soma/soma_n1.json").read_text())
    if manifest["joint_names"] != [r[0] for r in RIG]:
        raise ValueError("SOMA joint contract changed; review rig before export")
    spec = importlib.util.spec_from_file_location("preflight", ROOT/"tools/preflight.py")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    envelope = pose_window()
    checker.validate_poses(envelope, "soma", manifest["joint_names"])
    frames = [world_positions(pose(i/FPS)) for i in range(DURATION*FPS+1)]
    data = {"fps":FPS, "duration":DURATION,
            "names":[r[0] for r in RIG], "parents":[r[1] for r in RIG],
            "frames":[[[round(v,5) for v in xyz] for xyz in f] for f in frames]}
    fragment = (HERE/"preview_fragment.html").read_text().replace(
        "/*__MOTION_DATA__*/null", json.dumps(data,separators=(",",":")))
    (output/"yifei-double.fragment.html").write_text(fragment)
    wrapper = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>真假刘亦菲 · 双人试镜</title><style>body{margin:0;padding:24px;max-width:900px;margin:auto;font:16px/1.6 system-ui;color:#e9eef4;background:#101b25;--foreground:#e9eef4;--muted-foreground:#acbbc6;--border:#42515b;--viz-series-1:#6cdbbf;--viz-series-2:#c0a6fa}button,select,input{font:inherit}button,select{padding:8px 14px;color:inherit;background:#283844;border:1px solid #526674;border-radius:7px}input[type=range]{width:100%}.viz-controls,.viz-row{display:flex;gap:12px;flex-wrap:wrap;align-items:center}.form-label{flex:1;min-width:180px}.text-small{font-size:13px}.text-muted{color:var(--muted-foreground)}button{cursor:pointer}</style><body>'
    (output/"Yifei_Double_Audition.html").write_text(wrapper+fragment+'</body></html>')
    (output/"soma_pose_window.json").write_text(json.dumps(envelope,indent=2))
    return {"frames":len(frames), "fps":FPS, "joints":len(RIG),
            "pose_format":"PASS", "motion_source":"ORIGINAL_PROCEDURAL",
            "model_inference":"NOT_RUN", "identity_recognition":"NOT_IMPLEMENTED",
            "physics":"NOT_SIMULATED", "soma_proportions":"NOT_VALIDATED"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE/"output")
    args = parser.parse_args()
    print(json.dumps(build(args.output),ensure_ascii=False,indent=2))
