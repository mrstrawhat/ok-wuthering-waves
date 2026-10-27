#!/bin/bash
set -euo pipefail

# Build/test only: this script never executes the native capture or input commands.
probe_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mode="${1:-test}"
case "$mode" in
  build|test) ;;
  *) echo 'Usage: bash check.sh [build|test]' >&2; exit 2 ;;
esac
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'The native probe requires macOS and the Swift command line tools.' >&2
  exit 2
fi

build_dir="$probe_dir/.build-native"
module_cache="$build_dir/module-cache"
mkdir -p "$module_cache" "$build_dir/package-cache" "$build_dir/config" "$build_dir/security"
developer_dir="$(xcode-select -p)"
testing_frameworks="$developer_dir/Library/Developer/Frameworks"
extra_flags=()
if [[ -d "$testing_frameworks/Testing.framework" ]]; then
  # The standalone Command Line Tools include Testing, but SwiftPM's native
  # engine does not always add its framework search path automatically.
  extra_flags=(-Xswiftc -F -Xswiftc "$testing_frameworks"
               -Xlinker -rpath -Xlinker "$testing_frameworks")
fi

env CLANG_MODULE_CACHE_PATH="$module_cache" SWIFTPM_MODULECACHE_OVERRIDE="$module_cache" \
  swift "$mode" --build-system native --package-path "$probe_dir" \
  --scratch-path "$build_dir" --cache-path "$build_dir/package-cache" \
  --config-path "$build_dir/config" --security-path "$build_dir/security" \
  --disable-sandbox -Xswiftc -module-cache-path -Xswiftc "$module_cache" "${extra_flags[@]}"
