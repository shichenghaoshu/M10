#!/usr/bin/env bash
set -euo pipefail
root_dir="$(cd "$(dirname "$0")/.." && pwd)"
cmake -S "$root_dir" -B "$root_dir/build/host" -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build "$root_dir/build/host"
ctest --test-dir "$root_dir/build/host" --output-on-failure

