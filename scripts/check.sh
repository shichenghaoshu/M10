#!/usr/bin/env bash
set -euo pipefail
root_dir="$(cd "$(dirname "$0")/.." && pwd)"
python_bin="${PYTHON:-python3}"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

"$python_bin" "$root_dir/scripts/check_publication.py"
(cd "$root_dir/m10-robot-core" && "$python_bin" -m pytest tests -q)
(cd "$root_dir/m10-face-ui" && "$python_bin" -m pytest tests -q)
(cd "$root_dir/m10-hardware-test" && "$python_bin" -m pytest tests -q)

for test_name in test_motor_control_core test_m10_protocol_core; do
  c++ -std=c++17 -Wall -Wextra -pedantic \
    "$root_dir/m10-hardware-test/tests/$test_name.cpp" -o "$tmp_dir/$test_name"
  "$tmp_dir/$test_name"
done

cmake -S "$root_dir/m10-vision" -B "$tmp_dir/vision" -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build "$tmp_dir/vision"
ctest --test-dir "$tmp_dir/vision" --output-on-failure
echo "PASS host checks (no physical motor control performed)"
