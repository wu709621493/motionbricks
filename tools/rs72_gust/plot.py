"""Plot an existing report/history pair after verifying its checksum."""
import argparse
import hashlib
import json
from pathlib import Path


def render(report_dir, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from motionbricks.rs72_gust import Case, one_cos

    target = Path(out)
    if target.exists():
        raise FileExistsError('output plot already exists')
    root = Path(report_dir)
    report = json.loads((root/'report.json').read_text(encoding='utf-8'))
    history = root/'history.csv'
    if hashlib.sha256(history.read_bytes()).hexdigest() != report['history_sha256']:
        raise ValueError('history checksum mismatch')
    case = Case(**report['results'][-1]['case'])
    time, eta, _, static = np.loadtxt(history, delimiter=',', skiprows=1).T
    gust = np.array([one_cos(float(t), case) for t in time])
    duration = 2*case.gradient_m/case.tas_m_s
    plt.rcParams.update({'font.size':10, 'axes.spines.top':False, 'axes.spines.right':False})
    fig, axes = plt.subplots(2, 1, figsize=(9,6), sharex=True, layout='constrained')
    axes[0].plot(time, gust, color='#267f8c', lw=2)
    axes[0].set_ylabel('Vertical gust (m/s)')
    axes[1].plot(time, static*1000, color='#ad7831', ls='--', lw=2, label='Quasi-static increment')
    axes[1].plot(time, eta*1000, color='#274e86', lw=2, label='One-coordinate dynamic increment')
    axes[1].set_ylabel('Wing-tip increment (mm)')
    axes[1].set_xlabel('Time (s)')
    axes[1].legend(frameon=False, loc='upper right')
    for ax in axes:
        ax.axvline(duration, color='#888888', ls=':', lw=1)
        ax.set_xlim(0, min(time[-1], max(2.2, 2*duration)))
        ax.grid(alpha=.15)
    fig.suptitle('RS-72 | 1-cos gust, fixed-root elastic response\nSynthetic parameters; no flight validation', fontsize=14)
    axes[0].text(.98, .88,
                 f'TAS {case.tas_m_s:g} m/s | Gust {case.gust_peak_m_s:+g} m/s | H {case.gradient_m:g} m\n'
                 f'Half-wing mass {case.wing_half_mass_kg:g} kg | Damping {case.damping_ratio:.0%}',
                 transform=axes[0].transAxes, ha='right', va='top')
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open('xb') as handle:
            fig.savefig(handle, format='png', dpi=180)
    finally:
        plt.close(fig)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-dir', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        print(render(args.report_dir, args.out))
    except (ValueError, OSError) as exc:
        parser.exit(1, f'RS-72 plot refused: {exc}\n')
