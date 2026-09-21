#!/usr/bin/env python3
"""Recompute the sensor-node power budget with a part swapped in.

Usage:
    python tools/what_if.py                      # baseline budget
    python tools/what_if.py --imu imu-b          # swap the IMU
    python tools/what_if.py --imu imu-c --uplink can-xcvr
    python tools/what_if.py --imu imu-b --markdown > outputs/what-if-imu-b.md

Reads only example-system/parts/*.json. Standard library only.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / "example-system" / "parts"

BATTERY_MAH = 2000
TARGET_DAYS = 30
LIMIT_MA = 2.7  # SN-REQ-020
PERIOD_MS = 10.0
UART_TX_MS_PER_S = 16 * 10 / 115200 * 1000  # 16 bytes, 10 bits each


def load_part(part_id: str) -> dict:
    if not part_id.replace("-", "").isalnum():
        raise SystemExit(f"invalid part id: {part_id!r}")
    path = PARTS / f"{part_id}.json"
    if not path.exists():
        raise SystemExit(f"unknown part {part_id!r}; available: {', '.join(p.stem for p in sorted(PARTS.glob('*.json')))}")
    return json.loads(path.read_text())


def budget(mcu: dict, imu: dict, temp: dict, uplink: dict | None, mcu_active_duty: float) -> list[dict]:
    rows = []

    def add(name, part, active_ma, duty):
        rows.append({"consumer": name, "part": part["id"], "active_ma": active_ma, "duty": duty, "avg_ma": active_ma * duty})

    add("MCU active", mcu, mcu["active_current_ma"], mcu_active_duty)
    add("MCU sleep", mcu, mcu["sleep_current_ma"], 1 - mcu_active_duty)
    add(f"IMU ({imu['interface'].upper()})", imu, imu["active_current_ma"], 1.0)
    temp_duty = temp["conversion_time_ms"] / 1000.0
    add("Temp sensor conversion", temp, temp["conversion_current_ma"], temp_duty)
    add("Temp sensor idle", temp, temp["idle_current_ma"], 1 - temp_duty)
    if uplink is None:
        add("UART transmit", mcu, mcu["uart_tx_current_ma"], UART_TX_MS_PER_S / 1000.0)
    else:
        add(f"{uplink['interface'].upper()} transceiver", uplink, uplink["active_current_ma"], 1.0)
    return rows


def compatibility(imu: dict, baseline: dict, temp: dict) -> list[str]:
    issues = []
    if imu["interface"] != baseline["interface"]:
        issues.append(f"Interface changes {baseline['interface'].upper()} -> {imu['interface'].upper()}: ICD section 1-2 pins and driver change.")
        if imu["interface"] == "i2c" and imu.get("i2c_address") == temp.get("i2c_address"):
            issues.append("I2C address collides with the temperature sensor.")
    if 100 not in imu["odr_hz"] and not any(abs(o - 100) / 100 <= 0.05 for o in imu["odr_hz"]):
        issues.append(f"No ODR within 5 % of 100 Hz (available: {imu['odr_hz']}); SN-REQ-001 needs a timing waiver or decimation.")
    for key, label in (("accel_lsb_per_g", "accelerometer"), ("gyro_lsb_per_dps", "gyro")):
        if imu[key] != baseline[key]:
            issues.append(f"{label} scale factor {baseline[key]} -> {imu[key]} LSB: packet units change (ICD section 4) or firmware must rescale.")
    if imu["who_am_i"] != baseline["who_am_i"]:
        issues.append(f"WHO_AM_I {baseline['who_am_i']} -> {imu['who_am_i']}: update init check (SN-REQ-008 reinit path).")
    if imu["read_bytes_per_sample"] != baseline["read_bytes_per_sample"]:
        issues.append(f"Burst read {baseline['read_bytes_per_sample']} -> {imu['read_bytes_per_sample']} bytes: re-check TIMING.md IMU read row.")
    if imu["package"] != baseline["package"]:
        issues.append(f"Package {baseline['package']} -> {imu['package']}: board layout change.")
    if imu["supply_v"][0] > 3.3 or imu["supply_v"][1] < 3.3:
        issues.append("Supply range excludes 3.3 V.")
    return issues


def render(rows, title, issues, markdown):
    total = sum(r["avg_ma"] for r in rows)
    life_days = BATTERY_MAH / total / 24
    ok = total <= LIMIT_MA
    if markdown:
        print(f"# What-if: {title}\n")
        print("| Consumer | Part | Active (mA) | Duty | Average (mA) |\n| --- | --- | --- | --- | --- |")
        for r in rows:
            print(f"| {r['consumer']} | {r['part']} | {r['active_ma']:.3f} | {r['duty']*100:.2f} % | {r['avg_ma']:.3f} |")
        print(f"| **Total** | | | | **{total:.3f}** |\n")
        print(f"- Limit (SN-REQ-020): {LIMIT_MA} mA -> **{'PASS' if ok else 'FAIL'}** ({(total/LIMIT_MA-1)*100:+.1f} %)")
        print(f"- Estimated life: {life_days:.1f} days (target {TARGET_DAYS})\n")
        print("## Compatibility impacts\n")
        print("\n".join(f"- {i}" for i in issues) if issues else "- None detected from part data.")
    else:
        print(f"{title}")
        for r in rows:
            print(f"  {r['consumer']:<26} {r['part']:<9} {r['active_ma']:8.3f} mA x {r['duty']*100:6.2f} % = {r['avg_ma']:.3f} mA")
        print(f"  {'TOTAL':<26} {total:.3f} mA  limit {LIMIT_MA} mA  {'PASS' if ok else 'FAIL'}  life {life_days:.1f} days")
        for i in issues:
            print(f"  ! {i}")
    return 0 if ok else 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mcu", default="mcu-m0")
    ap.add_argument("--imu", default="imu-a")
    ap.add_argument("--temp", default="temp-x")
    ap.add_argument("--uplink", default=None, help="transceiver part id, e.g. can-xcvr (default: MCU UART)")
    ap.add_argument("--mcu-duty", type=float, default=0.40, help="MCU active duty cycle (0.40 today, 0.25 with sleep)")
    ap.add_argument("--markdown", action="store_true")
    a = ap.parse_args(argv)

    mcu, imu, temp = load_part(a.mcu), load_part(a.imu), load_part(a.temp)
    uplink = load_part(a.uplink) if a.uplink else None
    baseline_imu = load_part("imu-a")
    rows = budget(mcu, imu, temp, uplink, a.mcu_duty)
    issues = compatibility(imu, baseline_imu, temp) if imu["id"] != baseline_imu["id"] else []
    if uplink is not None:
        issues.append(f"{uplink['name']} needs {uplink['supply_v'][0]}-{uplink['supply_v'][1]} V; current board is 3.3 V only (ADR-0002).")
    title = f"mcu={mcu['id']} imu={imu['id']} temp={temp['id']} uplink={uplink['id'] if uplink else 'uart'} mcu_duty={a.mcu_duty:.2f}"
    return render(rows, title, issues, a.markdown)


if __name__ == "__main__":
    sys.exit(main())
