#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Launch two independently limited Linux containers on a Docker host.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
image=python:3.13-slim
boxes=()
cleanup() {
    if (( ${#boxes[@]} )); then docker rm -f "${boxes[@]}" >/dev/null; fi
}
trap cleanup EXIT
for role in healthy faulty; do
    id=$(docker run -d --init --network none --read-only --cap-drop ALL \
        --security-opt no-new-privileges --pids-limit 32 --memory 256m \
        --memory-swap 256m --cpus 1 --user 65534:65534 \
        --tmpfs /tmp:rw,noexec,nosuid,nodev,size=8m,mode=1777 \
        --mount "type=bind,src=$root/motionbricks,dst=/src/motionbricks,readonly" \
        --mount "type=bind,src=$root/tests/radix_ipc,dst=/src/tests/radix_ipc,readonly" \
        --workdir /src "$image" sleep 180)
    boxes+=("$id")
    echo "$role $id"
done
healthy=${boxes[0]}
faulty=${boxes[1]}
docker inspect --format '{{.Image}}' "$healthy"
docker exec "$healthy" python -V
for ns in pid mnt net; do
    test "$(docker exec "$healthy" readlink /proc/self/ns/"$ns")" != \
         "$(docker exec "$faulty" readlink /proc/self/ns/"$ns")"
done
docker exec "$healthy" touch /tmp/healthy-only
docker exec "$faulty" test ! -e /tmp/healthy-only
docker exec "$faulty" python -B -S -W error::ResourceWarning -m unittest discover \
    -s tests/radix_ipc -p test_ipc.py -k test_cpu_spin_is_killed_and_session_recovers -v &
fault_run=$!
verify=(python -B -S -c "from motionbricks.radix_ipc import run_mixed_dot; r = run_mixed_dot([1, 2], [3, 4], total_timeout_s=5); assert r['value'] == 11; print(r['status'], r['value'])")
docker exec "$healthy" "${verify[@]}"
wait "$fault_run"
docker exec "$faulty" "${verify[@]}"
docker exec "$healthy" test -f /tmp/healthy-only
