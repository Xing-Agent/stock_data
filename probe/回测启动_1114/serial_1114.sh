#!/usr/bin/env bash
# one job at a time: three in parallel got OOM-killed (exit 137) on this 8GB box
cd "$(dirname "$0")/../.." || exit 1
for d in probe/流动性池_1114/跑技术面换池_1114.py probe/大波段闸四道_1114/跑大波段闸_1114.py probe/分批离场_1114/跑分批离场_1114.py; do
  python3 "$d" >> "$(dirname "$d")/run_log_serial.txt" 2>&1
done
echo SERIAL_DONE
