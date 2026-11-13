# MotionBricks: Scalable Real-Time Motions with Modular Latent Generative Model and Smart Primitives

<div align="center">
  <h2>少用token，多办事儿🤪</h2>
  <p><a href="docs/charity_trust_st_jude_guo_meimei_zh.md">先别催我哭，让我看看账：St. Jude 与郭美美事件的信任比较</a></p>
</div>

<p align="center">
  <a href="https://nvlabs.github.io/motionbricks/"><img src="https://img.shields.io/badge/Project-Page-blue" alt="Project Page"></a>
  <a href="https://arxiv.org/abs/2604.24833"><img src="https://img.shields.io/badge/arXiv-2604.24833-b31b1b.svg" alt="Paper"></a>
  <a href="#checkpoints"><img src="https://img.shields.io/badge/Hugging%20Face-Models-yellow" alt="Hugging Face Models"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-76B900.svg" alt="License"></a>
  <img src="docs/media/teaser.jpg" alt="MotionBricks animates characters and robots with one model" width="100%">
</p>

MotionBricks is a modular latent generative model that animates characters and robots in real time. It fills in the motion between four recent poses and up to four target poses. Three learned modules share the work, as [How MotionBricks works](#how-motionbricks-works) explains. Smart Primitives turn target poses into building blocks for navigation and object interaction, so behaviors like vaulting and sitting snap together like bricks, with no retraining.

This repository provides pretrained MotionBricks models, based on the [SIGGRAPH 2026 paper](https://arxiv.org/abs/2604.24833), and everything you need to put them to work:

- **Pretrained models** for the [SOMA body model](https://github.com/NVlabs/SOMA-X) and the Unitree G1 robot. They ship as ONNX files, with the pretrained [checkpoints](#checkpoints) on Hugging Face.
- **A Python runtime**, built on [Warp](https://github.com/NVIDIA/warp), [Newton](https://github.com/newton-physics/newton), and [TensorRT](https://github.com/NVIDIA/TensorRT), that chains generations into continuous motion.
- **Two demos**: an [Inbetweener](#inbetweener) that generates motion between poses you place, and a [Scene Preview](#scene-preview) where a character walks, runs, vaults, ducks, and sits its way through a scene.
- **Two editors** to author your own [Smart Primitives](#editors) and [scenes](#editors).

The demos show one way to drive the model. Your application decides where the targets come from. New to MotionBricks? The [guided tutorial](docs/guided_tutorial.md) walks through all four apps as it builds one interaction scene.

## News

- MotionBricks has its own repository and a pretrained model for SOMA humans. The first release was a Unitree G1 preview in [GR00T Whole-Body Control](https://github.com/NVlabs/GR00T-WholeBodyControl/tree/main/motionbricks).

## Setup

For dependency-free environment and pose-format checks before installing the runtime, see [CPU-safe preflight](docs/preflight.md).

For Ubuntu/macOS CPU tooling, unsupported-platform handling and bounded GPU example execution, see [platform safety](docs/platform_safety.md).

For a proposed TPU backend architecture and admission gates (not implemented support), see [TPU integration protocol](docs/tpu_integration_protocol.md).

The runtime uses TensorRT, which requires an NVIDIA GPU. The demos were tested on Windows and Linux (x86-64) with an NVIDIA GeForce RTX 4090.

Install [Git LFS](https://git-lfs.com/) and [uv](https://docs.astral.sh/uv/getting-started/installation/). Then clone this repository and run these commands from its root:

```sh
git lfs pull
uv sync
```

The first launch of each model and precision builds a TensorRT plan. This takes a few minutes. Plans are cached in `.trt-cache/`, so later launches start quickly. Each app section below gives its command.

## How MotionBricks works

<p align="center">
  <img src="docs/media/core_idea.gif" alt="Context poses in green, a strobe of generated poses, and a target pose in blue" width="100%">
</p>

Each generation fills in the motion between two sets of poses at 30 Hz:

- The **context** is the four most recent poses of the character (green above).
- The **target** is one to four poses that the motion should reach (blue above). One pose sets where the character ends up and stops. More poses also set how it moves at that point.

The model decides how long the transition takes. One generation produces 6 to 16 tokens of four poses, or about 0.6 to 1.9 s of motion. [Generation length](docs/runtime_api.md#generation-length) explains the frame counts.

Three learned modules share the work:

- The **root module** predicts the duration and the path of the root.
- The **pose module** is a masked token transformer. It predicts the motion tokens along that path.
- The **decoder** turns the tokens into continuous motion that reaches the targets. It uses a VQ-VAE with several codebook heads.

Longer motion comes from chaining generations. The runtime plays the generated motion, records what it played, and uses the last four recorded poses as the context of the next generation. Your application decides the targets. That choice is what turns one inbetweening model into keyframe animation, continuous locomotion, or object interactions. The [paper](https://arxiv.org/abs/2604.24833) covers the method, the training data, and the evaluation.

### One runtime for SOMA and G1

Both models generate the same way. Only the pose layout differs. The apps and the runtime work the same for both rigs, so one code path drives a human skeleton and a robot. [Engines](docs/runtime_api.md#engines) describes the two layouts.

## Repository layout

The `motionbricks` package is the library. The demos and editors in `app` are built on it.

| Folder | Contents |
| --- | --- |
| [motionbricks](motionbricks) | The library: engines, motion players, recorder, blend spaces, pivots, and the ONNX models |
| [app](app) | The demos, the two editors, and the character runtime they share |
| [assets](assets) | Sample motion clips, Smart Primitives, and the gym scenes |
| [docs](docs) | Guides and model cards, with runnable examples in [docs/examples](docs/examples) |
| [tools/onnx](tools/onnx) | The standalone ONNX exporter |

## Inbetweener

Start here to see the core idea. Choose poses from clips, place them in the view, and generate motion through them in order.

<table>
  <tr>
    <th>SOMA</th>
    <th>Unitree G1</th>
  </tr>
  <tr>
    <td><img src="docs/media/inbetweener_soma.gif" alt="SOMA Inbetweener" width="100%"></td>
    <td><img src="docs/media/inbetweener_g1.gif" alt="Unitree G1 Inbetweener" width="100%"></td>
  </tr>
</table>

Run it with this command:

```sh
uv run python -m app.inbetweener_demo
```

[Inbetweener](docs/inbetweener.md) lists its options and things to try. It also walks through the code.

## Scene Preview

Drive a character through a scene with continuous locomotion and interactions. It can walk and run forward, strafe while facing the camera, or strafe while crouching. Six style modes, such as Skipping and Zombie, change how it walks. Scene Preview distills the Unreal Engine demo behind the [paper's videos](https://nvlabs.github.io/motionbricks/) into a small Python runtime. It puts the ideas front and center, so you can carry them into any integration.

<table>
  <tr>
    <th>SOMA</th>
    <th>Unitree G1</th>
  </tr>
  <tr>
    <td><img src="docs/media/scene_preview_soma.gif" alt="SOMA Scene Preview" width="100%"></td>
    <td><img src="docs/media/scene_preview_g1.gif" alt="Unitree G1 Scene Preview" width="100%"></td>
  </tr>
  <tr>
    <td><img src="docs/media/locomotion_targets_soma.gif" alt="SOMA walks, runs, and stops with context, target, and blend space poses shown" width="100%"></td>
    <td><img src="docs/media/locomotion_targets_g1.gif" alt="Unitree G1 walks, runs, and stops with context, target, and blend space poses shown" width="100%"></td>
  </tr>
  <tr>
    <td><img src="docs/media/locomotion_directional_soma.gif" alt="SOMA strafes in four directions, crouches, then stands back up, with context, target, and blend space poses shown" width="100%"></td>
    <td><img src="docs/media/locomotion_directional_g1.gif" alt="Unitree G1 strafes in four directions, crouches, then stands back up, with context, target, and blend space poses shown" width="100%"></td>
  </tr>
  <tr>
    <td><img src="docs/media/locomotion_styles_soma.gif" alt="SOMA walks in each locomotion style, from Skipping to Combat" width="100%"></td>
    <td><img src="docs/media/locomotion_styles_g1.gif" alt="Unitree G1 walks in each locomotion style, from Skipping to Combat" width="100%"></td>
  </tr>
</table>

Run it with the SOMA or the Unitree G1 gym:

```sh
uv run python -m app.scene_preview --scene assets/scenes/soma_gym.scene.json
uv run python -m app.scene_preview --scene assets/scenes/g1_gym.scene.json
```

[Scene Preview](docs/scene_preview.md) lists its options and controls. It also explains the runtime behind it: the character, the state machine, locomotion, and interactions.

## Editors

A Smart Primitive describes an action as target poses placed around an object. Author one in the Smart Primitive Editor. Place it in a scene for Scene Preview with the Scene Editor.

<table>
  <tr>
    <th>Smart Primitive Editor</th>
    <th>Scene Editor</th>
  </tr>
  <tr>
    <td><img src="docs/media/smart_primitive_editor.png" alt="Smart Primitive Editor with a jump primitive" width="100%"></td>
    <td><img src="docs/media/scene_editor.png" alt="Scene Editor with the SOMA gym" width="100%"></td>
  </tr>
</table>

Run them with these commands:

```sh
uv run python -m app.smart_primitive_editor
uv run python -m app.scene_editor
```

Start with the [guided tutorial](docs/guided_tutorial.md#part-2-build-a-smart-primitive) to learn these tools. It builds an interaction step by step with both editors. [Smart Primitive Editor](docs/smart_primitive_editor.md) and [Scene Editor](docs/scene_editor.md) describe each editor and its documents.

These editors show one way to build dynamic sequences and interactions. Your application can follow the same approach or a different one. For example, these editors sample a handful of target poses from clips. A motion generation model, such as [Kimodo](https://github.com/nv-tlabs/kimodo) or [ARDY](https://github.com/nv-tlabs/ardy), could generate those poses instead.

## Checkpoints

MotionBricks checkpoints are available for the SOMA body model and the Unitree G1 robot. Their weights use the SafeTensors format.

> Note: the apps use the ONNX models bundled in [motionbricks/assets/onnx](motionbricks/assets/onnx), so you do not need to download a checkpoint to run them. Download one to export your own ONNX models or to build another runtime. This repository includes the [ONNX exporter](#export-onnx-models).

| Model | Skeleton | Training Data | FPS | Hugging Face | License |
|:-------|:-------------|:------:|:------:|:-------------:|:-------------:|
| **MotionBricks-SOMA-RP-v1** | [SOMA](https://github.com/NVlabs/SOMA-X) | [Bones RigPlay 1 (RP1)](https://bones.studio/datasets#rp01) | 30 | [Link](https://huggingface.co/nvidia/MotionBricks/tree/main/soma) | [NVIDIA Open Model Agreement](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-agreement/) |
| **MotionBricks-G1-RP-v1** | [Unitree G1](https://github.com/unitreerobotics/unitree_ros/tree/master/robots/g1_description) | [Bones RigPlay 1 (RP1)](https://bones.studio/datasets#rp01), [retargeted](https://github.com/NVIDIA/soma-retargeter) | 30 | [Link](https://huggingface.co/nvidia/MotionBricks/tree/main/g1) | [NVIDIA Open Model Agreement](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-agreement/) |

The [SOMA model card](docs/soma_model.md) and the [Unitree G1 model card](docs/unitree_g1_model.md) describe each model, its inputs and outputs, and its limitations.

## Export ONNX models

The ONNX models in this repository were exported from these checkpoints with the standalone exporter in [tools/onnx](tools/onnx/README.md). To export them yourself, install the [Hugging Face CLI](https://huggingface.co/docs/huggingface_hub/en/guides/cli), then download the checkpoint folders and run the command for your model from the repository root:

```sh
hf download nvidia/MotionBricks --local-dir checkpoints/MotionBricks

# SOMA
uv run --locked --project tools/onnx motionbricks-onnx --model soma --checkpoints checkpoints/MotionBricks/soma

# Unitree G1
uv run --locked --project tools/onnx motionbricks-onnx --model unitree_g1 --checkpoints checkpoints/MotionBricks/g1
```

To download one model, add `--include "soma/*"` or `--include "g1/*"`. Keep the downloaded folder structure intact.

The exporter has its own environment, and uv installs it the first time you run the command. FP32 is the default. Add `--precision fp16` for mixed FP16. The [exporter guide](tools/onnx/README.md) lists every option, and [ONNX inference](docs/onnx_inference.md) explains the tensor interfaces and batching.

## Documentation

New to MotionBricks? Start with the **[guided tutorial](docs/guided_tutorial.md)**. It explains the core concepts, then builds an interaction scene with all four apps.

**Apps**

- **[Inbetweener](docs/inbetweener.md):** Shows how to run the Inbetweener, then walks through its code, from sampling and placing poses to chained playback.
- **[Scene Preview](docs/scene_preview.md):** Lists the options and controls, then describes the example runtime, from the character and the state machine to locomotion and interactions.
- **[Smart Primitive Editor](docs/smart_primitive_editor.md):** Describes what a Smart Primitive holds and how to author one: the node hierarchy, target poses, interaction boxes, pivots, and sequences.
- **[Scene Editor](docs/scene_editor.md):** Shows how to build a scene, and describes the `.scene.json` document that Scene Preview opens.

**Integration**

- **[Runtime API](docs/runtime_api.md):** Start here to integrate MotionBricks in your application. Describes the engines, pose layouts, clips, and chaining generations. It includes two runnable scripts that generate motion without a viewer.
- **[ONNX inference](docs/onnx_inference.md):** Describes the tensor shapes, batching, and other inference libraries, for use without the bundled engines.

**Models**

- **[ONNX exporter](tools/onnx/README.md):** Describes how to export the bundled ONNX models from the checkpoints on Hugging Face.
- **[SOMA model card](docs/soma_model.md):** Describes the SOMA model, its inputs and outputs, its training data, and its limitations.
- **[Unitree G1 model card](docs/unitree_g1_model.md):** Describes the Unitree G1 model, its inputs and outputs, its training data, and its limitations.

## Related humanoid work at NVIDIA

MotionBricks is part of a larger effort to enable humanoid motion for animation, robotics, and physical AI. Check out these related works:

- [Kimodo](https://github.com/nv-tlabs/kimodo): human motion generation model specializing in controllable offline motion authoring.
- [ARDY](https://github.com/nv-tlabs/ardy): builds on Kimodo to enable controllable motion generation in real time for interactive applications.
- [SOMA Body Model](https://github.com/NVlabs/SOMA-X): a unified parametric human body model.
- [BONES-SEED Dataset](https://huggingface.co/datasets/bones-studio/seed): a large motion capture dataset of humans and humanoids in SOMA and G1 format.
- [ProtoMotions](https://github.com/NVlabs/ProtoMotions): simulation and learning framework for training physically simulated humans and humanoids.
- [SOMA Retargeter](https://github.com/NVIDIA/soma-retargeter): retargets SOMA motion to humanoid robots such as the Unitree G1.
- [GEM](https://github.com/NVlabs/GEM-X): human motion reconstruction from video.
- [GEAR SONIC](https://github.com/NVlabs/GR00T-WholeBodyControl): humanoid behavior foundation model for physical robots.

## Citation

If you use this code in your research, please cite:

```bibtex
@article{wang2026motionbricks,
  title   = {MotionBricks: Scalable Real-Time Motions with Modular Latent Generative Model and Smart Primitives},
  author  = {Wang, Tingwu and Dionne, Olivier and De Ruyter, Michael and Minor, David and Rempe, Davis and Zhao, Kaifeng and Petrovich, Mathis and Yuan, Ye and Li, Chenran and Luo, Zhengyi and Robison, Brian and Blackwell, Xavier and Antoniazzi, Bernardo and Peng, Xue Bin and Zhu, Yuke and Yuen, Simon},
  journal = {ACM Transactions on Graphics (TOG)},
  year    = {2026},
  volume  = {45},
  number  = {4},
  doi     = {10.1145/3811334}
}
```

## License

Code, documentation, models, and sample motions have different licenses:

- **Code:** [Apache 2.0](LICENSE), including code examples and snippets in the documentation.
- **Documentation and media:** NVIDIA-authored documentation text and media (images, screenshots, and videos, including the files in `docs/media/`) use [Creative Commons Attribution 4.0 International (CC-BY-4.0)](https://creativecommons.org/licenses/by/4.0/).
- **Models:** [NVIDIA Open Model Agreement](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-agreement/). This covers the SOMA and G1 checkpoints on Hugging Face and the [ONNX models](motionbricks/assets/onnx/LICENSE.md). It permits commercial use and redistribution of modified models, subject to the agreement's terms. Licensed by NVIDIA Corporation under the NVIDIA Open Model Agreement.
- **Sample motions:** [NVIDIA Sample Data Evaluation License](assets/motions/LICENSE.txt). The covered human BVH and retargeted G1 CSV clips are for evaluating and testing NVIDIA technologies. The [sample-data notice](assets/motions/README.md) lists the covered files and credits Bones. These sample terms are separate from the model terms.

Licenses for dependencies and bundled robot assets are in [licenses](licenses). Exporter dependency licenses are in [tools/onnx/licenses](tools/onnx/licenses/).

This project downloads and installs additional components under their own license terms. Review those terms before use.

The [TensorRT OSS notice](licenses/tensorrt-LICENSE.txt) applies to TensorRT OSS components, not the separately installed `tensorrt-cu12`, `tensorrt-cu12-bindings`, and `tensorrt-cu12-libs` runtime packages. Those packages are governed by the NVIDIA TensorRT Software License Agreement distributed with the packages.

## Acknowledgments

This project builds upon excellent open source projects:

- [Newton](https://github.com/newton-physics/newton) for the viewer and scene
- [NVIDIA Warp](https://github.com/NVIDIA/warp) for GPU kernels
- [NVIDIA TensorRT](https://github.com/NVIDIA/TensorRT) for inference
- [Dear ImGui](https://github.com/ocornut/imgui) through [imgui_bundle](https://github.com/pthom/imgui_bundle) for the user interface
- [OpenUSD](https://github.com/PixarAnimationStudios/OpenUSD) for the SOMA character
- [Unitree Robotics](https://github.com/unitreerobotics/unitree_ros/tree/master/robots/g1_description) for the Unitree G1 robot model and meshes

## Contact

This project is currently not accepting contributions.

For questions or issues, please open an issue on this repository or reach out directly to the authors.


## Experimental curve inference (fork extension)

[Finger Tip Curve Prototype](tools/finger_tip_curve/README.md) fits synthetic 2-D
lines, circles and quadratic graphs with explicit ambiguity/rejection handling.
It includes a JSON API, reproducible fixtures, pytest checks and validation
results. This CPU-only authoring research tool runs in its own environment and
does not load MotionBricks models or control robots. Mapping confirmed curves
to timed 3-D target poses remains future integration work.

## Segmented motion and contact timing (research implication)

The [Porsche chassis / fusion analogy note](docs/porsche_stress_fusion_motion_implications.md)
translates a user-proposed front/rear convergence metaphor into a proposed
segment-relative motion and contact-timing evaluation for MotionBricks.
This is a research design note, not a chassis, collision, or fusion simulator.


## Experimental voltage/current pre-BIOS

The [voltage/current pre-BIOS prototype](docs/prebios_voltage_current_zh.md)
checks declared per-rail electrical envelopes, measurement uncertainty and
sample continuity, and compares modeled DC supply losses. It runs offline with
the standard library; it does not write firmware or certify memory stability.
Run `python -S -m motionbricks.prebios_power --demo` for a synthetic example.

## Experimental balance-aware sleep

The opt-in [sleep supervisor](docs/sleep_mode.md) pauses optional motion generation
after stable dwell while retaining an independent balance callback on every tick.
Includes disturbance recovery, latched telemetry/deadline faults, and CPU-only tests;
physical balance and electrical savings require separate hardware validation.
The [oyasumi patch](docs/sleep_mode.md#oyasumi-patch-one-shot-goodnight-request)
accepts the Cantonese `sleep_command="训觉"` as the same one-shot request as
`oyasumi=True`. Wake, recovery, or fault clears the request.
The [Oyasumi nonprofit research edition](docs/oyasumi_nonprofit_zh.md) describes
its public-benefit purpose, free reproducibility, and proposed stewardship;
the existing Apache-2.0/CC-BY-4.0 licensing remains applicable.

### Zero-error handling (experimental CPU utility)

See [zero-error guard and Perception Theory evidence protocol](docs/zero_guard.md)
for explicit division/log/normalization policies and optical sampling integration.

### Ding Rao narrative compensation (experimental CPU authoring tool)

[丁饶算法 / Ding Rao](docs/ding_rao.md) preserves actions, body states, intention,
relationships and source evidence from an annotated Liu Yong lyric and selected
imperial histories. It filters symbolic motion candidates and keeps documented
ages separate from motion scores. Includes a runnable JSON CLI and counterexample
tests; it does not parse arbitrary classical Chinese, generate poses, or predict lifespan.

The [royal-history HD evidence review](docs/royal_huntington_review.md) adds four
sourced historical profiles and a separate evidence registry. No confirmed royal
Huntington's disease case was established in this bounded review; retrospective
hypotheses, other-disease findings and missing evidence remain explicitly distinct.

### Crew-led countdown (CPU simulation)

[Zero-boundary countdown](docs/crew_countdown.md) preserves crew HOLD/ABORT,
requires renewed consent after a pause, and separates reaching zero from a
crew-confirmed simulation review request. No launch command is implemented.

## Oral plaque measurement workflow (fork research extension)

The [Chinese research workflow](docs/oral_plaque/workflow.md) specifies paired
plaque-area imaging, local pH monitoring, cleaning with sample recovery, and
independent acid-production assays. Includes an evidence map, validation gates,
a data dictionary and blank CSV templates. This is an unvalidated study design,
not a dental device, clinical protocol approval, or implemented robot capability.

### Shallow root–soil seismic research

An isolated, standard-library [root–soil screening prototype](docs/root_soil_seismic.md) compares candidate shallow slip planes and synthetic sliding displacement. Inputs are uncalibrated; redwood/banyan measurements and physical validation are pending. This does not model tectonic faults or certify slope safety.

### Rally surfaces and runoff research

The [rally surface study](docs/rally_surface_bayinbuluke_pikes_peak_zh.md) compares
loose fabric, anchored mats, gravel, buried geotextile and asphalt on explicitly
synthetic Bayinbuluke- and Pikes Peak-scale routes. A standard-library CPU model
screens traction, support, rainfall runoff and separate erosion proxies across
216 cases. Pikes Peak's asphalt paving and drainage history supplies context,
not calibration. No surveyed route, race lap time or material performance claim
is implied.

### Integer representation portability lab

The [integer portability lab](docs/radix_portability_zh.md) runs exact integer
dot products through versioned, checked adapters, with independent result verification
and conversion timing. The [balanced base-7 extension](docs/septenary_zh.md) adds
signed digit convolution and carry propagation alongside binary and balanced ternary.
Run `python -S -m motionbricks.radix_portability --backend all` to compare all three.
These are standard-library CPU experiments; native nonbinary hardware and motion
inference are not implemented.

## Engineering humor (fork cultural note)

[工程师两件套：修得了门轴，修不了常识](docs/fiction/duct_tape_wd40_tide_pods_zh.md)
retells the duct tape / WD-40 meme and records the 2018 laundry-pod challenge,
with a fictional workshop sketch and primary-source safety notes.
The repair joke does not apply to human bodies; laundry pods are not food.

## Fan fiction (fork creative writing)

[阿汉：佣金之外](docs/fiction/zaisheng_yongshi_ahan_zh.md) is an unofficial,
first-person fan story based on Shi Ou's *再生勇士*. A rainy escort job follows
the mercenary Ahan through a rescue, a lost axe, and the cost of getting home.
The story distinguishes borrowed character background from its invented events.

[幽城有喜，明日照常喝茶](docs/fiction/zaisheng_yongshi_youcheng_wedding_tea_zh.md)
is a companion fan story in an alternate future: Hailan and Liang Bo marry privately
in Youcheng, while the Lord of Light City, the Holy Demon King, and Hailina enjoy
immortality over daily tea. Its marriage, immortality, and domestic scenes are
explicitly fictional additions.

[RAM Sport：纽伯格林百鬼夜行团本](docs/fiction/ram_sport_nurburgring_raid_zh.md) is an unofficial
crossover raid design combining CF-inspired elimination rounds, a DNF-inspired
Nicholas summon role, and an original ghost procession on a fictional Nordschleife.
It includes eight-player roles, four encounters, dialogue, and completion rules;
this is a creative design document, not a playable game or runtime integration.

## Zhuyin Bridge (fork input-method experiment)

[注音桥 / Zhuyin Bridge](experiments/zhuyin_bridge/README.md) adds Pinyin hints
above 37 Zhuyin keys, whole-syllable spelling and an offline teaching lexicon
with traditional/simplified candidates. It includes an independent iOS keyboard
extension, a containing guide app, a browser preview and draft product/privacy
terms. Its dedicated CI checks the model, generated resources, Apple build and
browser interaction; device signing and on-device acceptance remain separate.

## CPU memory and rendering lab (fork experiment)

[1000 logical DDR4 shards and CPU pseudo-GPU rendering](docs/ddr4_1000_cpu_render_zh.md)
extends PR #48 with a bounded, supervised NumPy worker, independent matrix checks,
working-set sweeps, and a CPU triangle rasterizer. The checked-in image was
actually rendered on a CPU. Logical shards do not add physical DIMM slots;
Skylake-X hardware purchase, assembly, and validation remain separate.
See the guide for isolated installation and reproducible commands.

## Biophysics and civil weather concepts (fork experiment)

[Wheal versus typhoon fields](docs/wheal_typhoon_biophysics_zh.md) reuses the
PR #50 CPU transforms and rasterizer for an uncalibrated dermal fluid proxy and
an idealized vortex, with explicit units, conservation checks and rendered evidence.
[Taiqiang RS-72](docs/rs72_civil_weather_aircraft_zh.md) continues with an
SR-71-inspired subsonic civil weather-aircraft concept: wing stiffness, gust and
crack sensitivity, plus the role of human intuition and physical experiments.
These are numerical teaching/research prototypes, not clinical predictions,
weather forecasts, certified airframes or an approved storm-flight envelope.

[RS-72 dynamic gust experiment](docs/rs72_dynamic_gust_validation_zh.md) adds
a CPU 1-cos gust response about the static 1g state, one assumed wing-bending
coordinate, independent response checks, timestep convergence and input refusal.
The 21-case static audit separates eight small-angle exceedances, zero lift
coefficient exceedances and two overlapping strength alarms. Wing mass and
damping remain hypothetical; continuous turbulence is a documented next step.

## Residential private server planning (fork engineering note)

[住宅私人服务器建设指南：私人服务器，它真香](docs/residential_private_server_zh.md)
covers a small always-on storage node and an on-demand compute node, residential
power and cooling, worked electricity/TCO examples, controlled remote access,
backup restoration and UPS shutdown acceptance. Configuration ranges are planning
examples; no purchase, deployment or physical acceptance test is claimed.

## Strategy and perception (fork cultural essay)

[定其阴，守其阳：从原皮慎到胖迪克的八连击](docs/fog_of_war_eight_hit_essay_zh.md)
connects Shen, Camille, Jax and mythic-era item choices with fog of war,
historical misjudgment and crisis communication. It closes with a reader-supplied
literary motif about reliable basic actions; the original novel passage remains
unverified. Game analogy, sourced history and original interpretation are distinguished.

## Original fiction (fork creative writing)

[扩编之前](docs/fiction/before_the_squad_zh.md) is a Chinese screenplay following a football
coach and analyst through an open relationship, a move, concealed reunions and separation,
with an alternate-universe Maverick cameo. The [development notes](docs/fiction/before_the_squad_development_zh.md)
record the first-film ending. [扩编之后：两部曲收束与制片开发案例](docs/fiction/after_the_squad_zh.md)
develops the second film through adult children winning a fictional Asian club title,
a second divorce, and an old-video post-credits scene; the story closes in two films.

[案结情未了：圣瑞吉合规之晨](docs/fiction/case_closed_love_continues_zh.md) follows two adult
customs colleagues from a completed case to a hotel checkout mishap, marriage,
and family life with their child Wu Nianshi, nicknamed Jiazhong. The legal-reading
marathon and CNPU-assisted case are explicitly fictional; the romance is non-graphic.

[梅江有信，山海同程](docs/fiction/meixian_letters_shared_future_zh.md) follows a young couple from Meixian
through pregnancy, campus gossip, an individually approved flexible study plan,
graduation and independent paths into doctoral research. The story centers on
agency, shared care and sustained scholarship; its educational arrangements are
fictional, with sourced notes distinguishing them from current policy.

[族譜登記處奇妙夜](docs/fiction/genealogy_register_wonder_night_zh.md) is an original
comedy following a late-night discussion from Tang marriage rules to the 1950
Marriage Law, an imaginary reincarnation office, and a family genealogy desk.
Sourced notes distinguish customary practice, civil marriage, and family records.

[七弓同心：龙潭、上海滩与长寿村](docs/fiction/seven_bows_jinlan_future_zh.md) brings
Mao Zedong, Zhou Enlai, Chen Yun, Qian Zhuangfei, Li Kenong, Hu Di and Du Yuesheng
together at a fictional future archery range. Compound-bow scores determine
sworn-brother ranks before a seven-person adaptation of the classic *Fantasy
Westward Journey* ceremony. Historical notes distinguish the imagined reunion,
Shanghai background and invented game rules from documented sources.

[识得唔识得：一句话的非遗申报](docs/fiction/shikdak_multilingual_heritage_zh.md) is an original
multilingual comedy sketch: a simple self-introduction becomes a subtitle crisis
and a fictional in-house heritage hearing. It preserves Windy's mixed-language
line and ends with the learner mastering the Cantonese punchline.

## War literature and television (fork cultural essay)

[枪声落下，水还记得：重读《我的兄弟叫顺溜》](docs/shunliu_war_literature_zh.md)
examines Shunliu's growth as a sniper, his sister's suffering, and the final
shots at flags and Ishihara's urn. It pairs Northwest revolutionary war
literature with Baiyangdian's attention to everyday lives, distinguishing
verified episode summaries from original interpretation and literary imagery.

### Beijing courtyard heritage archive (c. 1900)

The [北京四合院数字档案](docs/heritage/beijing_siheyuan_1900/README.md) provides a
simple offline picture guide, source catalogue, SVG/OBJ exports and a MotionBricks
exterior scene, with an optional interactive viewer. It is a two-courtyard typological
reconstruction with explicitly hypothetical dimensions, not a surveyed historic
address. Rebuild and verify with `python -S tools/siheyuan/build.py --check`.

The [八合院二三层概念](experiments/bahayuan/README.md) develops four two-courtyard
modules into eight open courtyards and 116 component/space records, with second
storeys and recessed third-storey halls. Static floor and massing illustrations
are the default; geometry is hypothetical, with structural and circulation
validation pending. See the [picture-guide review](docs/heritage/courtyard_simple_20261110.md).

## Experimental Rust inference core

An incremental [Rust CPU core](native/motionbricks-core/README.md) ports multi-head
codebook lookup and supplies FP32 linear, ReLU and softmax primitives. It has no
LibTorch dependency; PyTorch is used only by numerical parity tests. This is an
explicitly experimental subset, not a full framework or model replacement.

The [integration review](docs/rust_integration_review_zh.md) bounds this to a codebook
experiment alongside PyIgnite, with a [benchmark report](docs/rust_benchmark_20261110_zh.md)
and separate [retro-compatibility audit](docs/rust_retro_review_zh.md).

PyIgnite now has [Pentium-era CPU compatibility experiments](docs/pyignite_legacy_cpu_zh.md):
explicit i586/x87 and IA-32/SSE2 build profiles, Python-independent native smoke,
bounded subprocess checks, and optional small-batch inference. Legacy hardware
and full Python/NumPy support remain separately unverified.


## Rb-14 unique-chip fingerprint (fork research concept)

[Rb-14 孤品指纹芯片](docs/rb14_unique_chip_concept_zh.md) specifies a proposed
14-rubidium-atom, multimode resonator fingerprint and a separate random-sampling
mode. It defines a candidate 300 × 300 nm receiving area, entropy limits,
registration and readout requirements, and the boundary with PR #83's PyIgnite
CPU temperature guard and checkpoints. This is a design document: hardware,
instrument drivers, PUF authentication and quantum randomness remain unverified.

[Rb-14 第一阶段物理预算](docs/rb14_phase1_physics_zh.md) adds a standard-library
CPU model, reproducible frequency/noise/geometry scans, and single versus multimode
position screening. It separates mass-only shifts from omitted surface and diffusion
physics; synthetic results retain `CONCEPT_ONLY` and hardware `NOT_RUN` status.
Run `python -S -m motionbricks.rb14_feasibility --out-dir /tmp/rb14-phase1`.

## Sports and public accountability (fork editorial)

[把运动员还给运动：反对把体育经营成国家间的政治战场](docs/sports_political_operations_zh.md)
examines Sun Yang's sample-collection case and its procedural review alongside
Mbappé's October 2026 interview controversy. The Chinese editorial distinguishes
individual responsibility, institutional decisions, access to original statements,
sourced facts and policy judgments.

## Time and intimacy (fork literary essay)

[错位永恒：陪伴、拥抱与有限的生命时间](docs/misaligned_eternity_time_intimacy_zh.md)
reflects on quality time, welcome physical touch, independent living, and the missed
reunion in Liu Cixin's *Death's End*. It distinguishes established clock physics,
fictional cosmology, and original literary interpretation, with source notes.

## Academic exchange and public language (fork editorial)

[让“学术间谍”退出公共标签：从 F-117 的苏联理论来源谈起](docs/academic_spies_open_science_f117_zh.md)
argues for replacing broad identity labels with descriptions of conduct and evidence.
It traces Ufimtsev's published research through translation and engineering to the
F-117, and presents intelligence-sector talent diversion as an opportunity-cost
hypothesis requiring data.

## GitHub 与“结合”的技能定位（fork extension）

本仓库将 GitHub 与“结合”定义为技能，按协作工具与当前实现描述其能力，不将其预设为具有主观体验的主体。
原始定位不构成对未来意识可能性的永久否定；部件与整体也须分别判断。
详见 [技能定义及原文依据](docs/github_jiehe_skill_definition_zh.md)与 [代码仓 87：原义、部件与整体的意识边界](docs/github_consciousness_possibility_zh.md)；
“结合”的当前实现与使用范围见 [Git Gap](examples/git_gap/README.md)。

[意识组件假说：器官移植与麻醉](docs/consciousness_components_transplant_anesthesia_zh.md)
延伸代码仓 87，结合换心病例、猪心移植、肝肾对照与麻醉研究，
区分体验调节、供者信息和主体延续；附来源、证据局限与待验证研究设计。

## Putin Hypothesis

[Putin Hypothesis：信息积累与人际理解](docs/research/putin_hypothesis/README_zh.md)
研究凯瑟、海明威、F. Scott Fitzgerald与福克纳的采访、书信、自述及编辑史，
附47项来源登记、115个集合项目索引、40条证据编码与8道未执行的核验任务。
本研究未测量财富的因果效应或“了解一个人”的总百分比。

## Policy accountability and document archiving (fork editorial and skill)

[计划生育与疫情政策批评及个人责任追查 v0.3](docs/policy_accountability/policy_accountability_v0.3.md)
保留已确认的作者原话、保尔·柯察金引文、事实与评价范围及八项参考资料；
同目录保存 [Word 原件](docs/policy_accountability/policy_accountability_v0.3.docx)与 SHA-256 校验清单。
[Py仓文档入仓技能](.agents/skills/py-repo-docs/SKILL.md)提供仅依赖 Python 标准库的简单 DOCX 归档工具，
生成 Markdown、保留原件并验证散列与正文一致性；提交与 PR 回读由协作工具完成，默认不自动合并。

## Anime romance and gossip (fork cultural essay)

[茜老师，你也有今天：情场老手怎么栽在了纯情男人手里](docs/kuzu_no_honkai_akane_pure_love_gossip_zh.md)
is a Chinese narrative gossip essay on Akane and Narumi in *Scum's Wish*,
family-absence tropes, NTR and pure-love endings. It preserves Windy's observations
on broken commitments, rapid self-reconstruction and bodily desire in adult
relationships. Source notes distinguish verified summaries from interpretation.

## Relationship ethics and OpenIRB (fork research discussion)

[从“刹车”到关系伦理](docs/relationships_marriage_family_ethics_zh.md)延伸 PR #93，
保留吴孟城关于关系教育、家庭回应及婚姻多重意义的原话，核对中国婚外性调查的抽样与编码限制，
分开经验事实、机制假设和规范主张。
[OpenIRB 亲密关系与家庭研究扩展](.agents/skills/openirb/SKILL.md)用于审阅敏感调查的统计口径、
同意与隐私保护；不为私人关系签发伦理许可。

[婚外恋、婚外情、婚外性与婚外金钱交易](docs/extramarital_love_affairs_sex_money_ethics_zh.md)
续接 PR #94，拆分情感、性、承诺与经济往来，加入中国大陆、法国及美国加州、纽约州、北卡州的法律例子，
分别核对离婚、刑事责任、第三者民事诉因与财产处分；附定义表、研究编码及官方来源。

## Virtual cockroach home (fork behavior experiment)

[虚拟民宅与蟑螂行为观察](docs/roach_home/README_zh.md) adds a standard-library
2D apartment with 40 virtual agents, wall/doorway constraints, shelter and local
resource proxies, an offline trajectory/heatmap replay, and paired-seed scenario
comparisons. Run `python -S -m motionbricks.roach_home --out-dir /tmp/roach-home`.
All outputs are synthetic and uncalibrated; deaths, necrophagy, human activity and
infection transmission are not implemented. Source notes discuss these extensions
separately from the running model.

## Historical medical ethics evidence review (fork research note)

[纳粹德国人体实验：已确认项目与证据边界](docs/nazi_medical_experiments_evidence_zh.md)
整理10类人体实验，分别记录受害者选择、种族政策关系、伤害与审判或纪念馆依据。
文档区分项目发生事实、施害者效果主张，以及《Apt Pupil》中尚未证实的文学描写。

## Geometry and dimensional transitions (fork research proposition)

[维度变化的耦合场方程组](docs/dimensional_transition_coupled_fields_zh.md)
归纳高斯定律、分子光谱、几何尺度动力学及虫洞类比，提出由同一作用量导出几何、
物质和尺度场方程的候选框架。文档区分有效降维、拓扑变化与真实维数改变；
未实施数值求解或实验验证，也不声称已建立二向箔式降维机制。

