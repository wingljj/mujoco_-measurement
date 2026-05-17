# mujoco_-measurement

MuJoCo-based KUKA KR20 cup-safe transport simulation for robotic arm motion planning and paper-quality visualization.

Current paper framing: the visual cup is treated as a rigid equivalent payload for a
theodolite mounted at the robot end effector. The paper task is attitude-constrained
planning for satellite-measurement operation, not liquid handling.

## What is included

- `kuka_kr20/`: KUKA KR20 MuJoCo XML models and STL assets.
- `src/`: constrained IK planning, batch simulation, plotting, and animation rendering scripts.
- `docs/theory_and_simulation.md`: theory, method, simulation setup, and result summary.
- `outputs/`: generated experiment results, publication figures, and rendered animations.

## Main workflow

```powershell
conda activate mujoco
python src/simulate_transport.py --model kuka_kr20/kuka_kr20_cup_transport.xml --targets 100 --seed 42 --out outputs/experiment_001
python src/plot_results.py --input outputs/experiment_001/results.csv --out outputs/figures
python src/paper_figures.py --model kuka_kr20/kuka_kr20_cup_transport.xml --results outputs/experiment_001/results.csv --trajectories outputs/experiment_001/trajectories.npz --out outputs/paper_figures
python src/render_animations.py --out outputs/animations/seamless --loop-mode pingpong
```

## Paper experiment workflow

```powershell
conda run -n mujoco python src/simulate_transport.py --model kuka_kr20/kuka_kr20_cup_transport.xml --targets 100 --seed 42 --method proposed --out outputs/paper_runs/proposed_100
conda run -n mujoco python src/simulate_transport.py --model kuka_kr20/kuka_kr20_cup_transport.xml --targets 100 --seed 42 --method position_only --out outputs/paper_runs/position_only_100
conda run -n mujoco python src/simulate_transport.py --model kuka_kr20/kuka_kr20_cup_transport.xml --targets 100 --seed 42 --method joint_linear --out outputs/paper_runs/joint_linear_100
python src/paper_experiment_figures.py --results outputs/paper_runs/proposed_100/results.csv outputs/paper_runs/position_only_100/results.csv outputs/paper_runs/joint_linear_100/results.csv --out outputs/paper_runs/figures_100
```

The paper experiment records terminal accuracy, maximum payload tilt, and
joint-space smoothness metrics. See `docs/theodolite_paper_experiment_report.md`
for the manuscript-oriented method and result summary.

## Result summary

For the saved 100-target experiment:

- IK reachable targets: 99/100
- MuJoCo tracking successes: 98/99 reachable targets
- Maximum successful final error: 0.0168 m
- Mean successful final error: 0.0047 m
- Maximum successful cup tilt: 14.36 deg
- Safety limit: 45 deg
