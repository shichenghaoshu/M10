#!/usr/bin/env bash
set -euo pipefail
root_dir="$(cd "$(dirname "$0")/.." && pwd)"
ndk_dir="${ANDROID_NDK_PATH:-${ANDROID_NDK_HOME:-}}"
if [[ -z "$ndk_dir" || ! -f "$ndk_dir/build/cmake/android.toolchain.cmake" ]]; then echo "ANDROID_NDK_PATH must point to an Android NDK" >&2; exit 2; fi
"$root_dir/scripts/prepare_models.sh"
mkdir -p "$root_dir/build/device-libs"
adb pull /vendor/lib64/librknnrt.so "$root_dir/build/device-libs/librknnrt.so"
cmake -S "$root_dir/native/rknn" -B "$root_dir/build/android" -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$ndk_dir/build/cmake/android.toolchain.cmake" -DANDROID_ABI=arm64-v8a \
  -DANDROID_PLATFORM=android-24 -DCMAKE_BUILD_TYPE=Release -DM10_RKNPU_DIR="$root_dir/third_party/rknpu2-v1.0.0" \
  -DM10_RKNNRT_LIB="$root_dir/build/device-libs/librknnrt.so" \
  -DCMAKE_INSTALL_PREFIX="$root_dir/build/android/install"
cmake --build "$root_dir/build/android"
cmake --install "$root_dir/build/android"
