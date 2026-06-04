"""Quick verification of experiment results consistency."""
import csv
import numpy as np

rows = list(csv.DictReader(open("outputs/experiment_001/results.csv")))

total = len(rows)
reachable = sum(1 for r in rows if r["reachable"].lower() == "true")
sim_success = sum(1 for r in rows if r["sim_success"].lower() == "true")

errors = []
tilts = []
for r in rows:
    if r["sim_success"].lower() == "true":
        e = float(r["final_error_m"])
        t = float(r["max_tilt_deg"])
        if np.isfinite(e):
            errors.append(e)
        if np.isfinite(t):
            tilts.append(t)

print(f"=== Results Verification ===")
print(f"Total targets: {total}")
print(f"Reachable (IK): {reachable}")
print(f"Sim success: {sim_success}")
print(f"Success rate (of reachable): {100*sim_success/reachable:.2f}%")
print(f"Max final error (success): {max(errors):.4f} m")
print(f"Mean final error (success): {np.mean(errors):.4f} m")
print(f"Max tilt (success): {max(tilts):.2f} deg")
print(f"Mean tilt (success): {np.mean(tilts):.2f} deg")

# Check consistency with README claims
print(f"\n=== Claims vs Raw Data Check ===")
print(f"README claims: 99/100 reachable, 98/99 sim success")
print(f"Raw data: {reachable}/{total} reachable, {sim_success}/{reachable} sim success")

print(f"\nREADME claims: max error 0.0168m, mean error 0.0047m")
print(f"Raw data: max error {max(errors):.4f}m, mean error {np.mean(errors):.4f}m")

print(f"\nREADME claims: max tilt 14.36deg, safety limit 45deg")
print(f"Raw data: max tilt {max(tilts):.2f}deg")
