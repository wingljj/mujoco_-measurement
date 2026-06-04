"""Analyze gaps between planned and simulated metrics."""
import csv, numpy as np, os

os.chdir(r'C:\study\自动化精测\mujoco_-measurement')

with open(r'outputs\experiment_001\results.csv', newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

reachable = [r for r in rows if r['planned_success'] == 'True']
sim_success = [r for r in reachable if r['sim_success'] == 'True']
sim_fail = [r for r in reachable if r['sim_success'] == 'False']

print(f'Total targets: {len(rows)}')
print(f'IK reachable: {len(reachable)}')
print(f'Sim success: {len(sim_success)}')
print(f'Sim failures (planned OK but sim failed): {len(sim_fail)}')

for r in sim_fail:
    print(f'  target_id={r["target_id"]}: planned_err={float(r["planned_error_m"]):.4f}, '
          f'planned_tilt={float(r["planned_max_tilt_deg"]):.2f}, '
          f'sim_err={float(r["final_error_m"]):.4f}, sim_tilt={float(r["max_tilt_deg"]):.2f}')

success_tilts = np.array([float(r['max_tilt_deg']) for r in sim_success])
success_planned_tilts = np.array([float(r['planned_max_tilt_deg']) for r in sim_success])
success_errors = np.array([float(r['final_error_m']) for r in sim_success])
success_planned_errors = np.array([float(r['planned_error_m']) for r in sim_success])

tilt_gap = success_tilts - success_planned_tilts
error_gap = success_errors - success_planned_errors

print(f'\n--- Gap analysis ({len(sim_success)} samples) ---')
print(f'Tilt gap (sim - planned): max={np.max(tilt_gap):.2f}deg, mean={np.mean(tilt_gap):.2f}deg, median={np.median(tilt_gap):.2f}deg')
print(f'Error gap (sim - planned): max={np.max(error_gap)*1000:.2f}mm, mean={np.mean(error_gap)*1000:.2f}mm')
print(f'Max sim tilt: {np.max(success_tilts):.2f}deg')
print(f'Max planned tilt: {np.max(success_planned_tilts):.2f}deg')
print(f'Mean sim tilt: {np.mean(success_tilts):.2f}deg')
print(f'Mean planned tilt: {np.mean(success_planned_tilts):.2f}deg')
print(f'Max sim error: {np.max(success_errors)*1000:.2f}mm')
print(f'Max planned error: {np.max(success_planned_errors)*1000:.2f}mm')

high_gap = [(i, g) for i, g in enumerate(tilt_gap) if g > 5]
print(f'\nHigh tilt-gap samples (>5deg): {len(high_gap)}')
for idx, gap in high_gap:
    r = sim_success[idx]
    print(f'  target_id={r["target_id"]}: planned_tilt={float(r["planned_max_tilt_deg"]):.2f}deg, '
          f'sim_tilt={float(r["max_tilt_deg"]):.2f}deg, gap={gap:.2f}deg')

for r in rows:
    if r['planned_success'] == 'False':
        print(f'\nIK FAILURE target_id={r["target_id"]}: msg={r["message"]}')
        print(f'  target=({float(r["target_x"]):.3f}, {float(r["target_y"]):.3f}, {float(r["target_z"]):.3f})')
        print(f'  planned_error={float(r["planned_error_m"]):.4f}, planned_tilt={float(r["planned_max_tilt_deg"]):.2f}deg')
