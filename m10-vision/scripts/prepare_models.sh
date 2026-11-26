#!/usr/bin/env bash
set -euo pipefail
root_dir="$(cd "$(dirname "$0")/.." && pwd)"
commit="1346f96"
base="https://api.github.com/repos/airockchip/rknpu2/contents"
asset_dir="$root_dir/third_party/rknpu2-v1.0.0"
mkdir -p "$root_dir/models/checksums" "$asset_dir/include" "$asset_dir/ssd"
fetch() {
  local repo_file="$1" dest="$2" part="$2.part"
  if [[ ! -s "$dest" ]]; then
    curl -fL --retry 3 -H 'Accept: application/vnd.github.raw+json' -o "$part" "$base/$repo_file?ref=$commit"
    mv "$part" "$dest"
  fi
}
fetch "examples/rknn_ssd_demo/model/ssd_inception_v2.rknn" "$root_dir/models/ssd_inception_v2_rknn_1.0.0.rknn"
fetch "examples/rknn_ssd_demo/model/road.bmp" "$root_dir/models/road.bmp"
fetch "examples/rknn_ssd_demo/model/box_priors.txt" "$root_dir/models/box_priors.txt"
fetch "examples/rknn_ssd_demo/model/coco_labels_list.txt" "$root_dir/models/coco_labels_list.txt"
fetch "Android/librknn_api/include/rknn_api.h" "$asset_dir/include/rknn_api.h"
fetch "examples/rknn_ssd_demo/src/ssd.h" "$asset_dir/ssd/ssd.h"
fetch "examples/rknn_ssd_demo/src/ssd.cc" "$asset_dir/ssd/ssd.cc"
fetch "LICENSE" "$asset_dir/LICENSE"
(cd "$root_dir" && shasum -a 256 models/ssd_inception_v2_rknn_1.0.0.rknn models/road.bmp > models/checksums/rknpu2-v1.0.0.sha256)
echo "Prepared official RKNPU2 1.0.0 assets from commit $commit"
