import csv

for variant in ["full_method", "no_tilt_barrier", "position_only", "position_orientation"]:
    rows = list(csv.DictReader(open(f"outputs/ablation_study/{variant}_results.csv")))
    sim_ok = sum(1 for r in rows if r["sim_success"].strip() == "True")
    plan_ok = sum(1 for r in rows if r["planned_success"].strip() == "True")
    errors = [float(r["final_error_m"]) for r in rows if r["sim_success"].strip() == "True"]
    tilts = [float(r["max_tilt_deg"]) for r in rows if r["sim_success"].strip() == "True"]
    print(f"=== {variant} ===")
    print(f"  Total: {len(rows)}, Plan OK: {plan_ok}, Sim OK: {sim_ok}")
    if errors:
        print(f"  Mean error: {sum(errors)/len(errors)*1000:.1f}mm, Max: {max(errors)*1000:.1f}mm")
    if tilts:
        print(f"  Mean tilt: {sum(tilts)/len(tilts):.2f}deg, Max: {max(tilts):.2f}deg")
