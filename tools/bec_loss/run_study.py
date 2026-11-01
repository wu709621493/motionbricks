"""Run reproducible BEC loss study; write results only to the requested directory."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from motionbricks.bec_dynamics import Parameters
from motionbricks.bec_loss import study
from motionbricks.hopfield_reference import ablation_study

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, required=True)
args = parser.parse_args()
result = study(Parameters())
args.output_dir.mkdir(parents=True, exist_ok=True)
(args.output_dir / 'bec_loss_results.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
hopfield = ablation_study()
(args.output_dir / 'hopfield_ablation_results.json').write_text(json.dumps(hopfield, indent=2, allow_nan=False)+'\n')
print(json.dumps({'evidence': result['evidence'], 'accuracy':result['accuracy'], 'hopfield':hopfield['rows']}, indent=2))
