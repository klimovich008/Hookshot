"""Work bounded in what is alive at once (gpu/vk/warm_bounded.h, used by gpu/vk/vk_draw.cpp precompile_warm): the first start
after a preparation with RX_VK_LOAD=create builds every noted pipeline into the pipeline cache and lets each go, instead of
keeping them all ready as the precompile does (which a 16 GB PC cannot hold). Compile and run the rule: every item once, never
more alive than threads, a stop honoured, progress reported. And the source: precompile_warm destroys each pipeline it builds
before it takes the next note, keeps no program, and writes the marker only when it got through. No game or GPU is needed.
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]


def check_source():
    draw = (ROOT / "gpu/vk/vk_draw.cpp").read_text(encoding="utf-8")
    start = draw.index("void precompile_warm(void (*progress)(size_t done, size_t total)) {")
    warm = draw[start:draw.index("\n}\n", start)]
    for needle in ("warm_bounded::run(", "program_cache_borrow(", "vkDestroyPipeline(dev.device, made, nullptr);",
                   "if (done == total && !prepare_stopped())", "precompile_built_write("):
        if needle not in warm:
            raise SystemExit("precompile_warm no longer has: " + needle)
    for kept in ("pipelines.emplace", "pipeline_keep_ready(", "programs[", "program_cache_load_some("):
        if kept in warm:
            raise SystemExit("precompile_warm keeps what it builds: " + kept)
    if warm.index("build_graphics(") > warm.index("vkDestroyPipeline(dev.device, made, nullptr);"):
        raise SystemExit("precompile_warm does not destroy the pipeline it has just built")
    run = draw[draw.index("void precompile_run(void (*progress)(size_t done, size_t total)) {"):]
    run = run[:run.index("const auto t0 = std::chrono::steady_clock::now();")]
    if "if (!precompile_covers_notes()) precompile_warm(progress);" not in run:
        raise SystemExit("precompile_run does not warm the notes before a load at create")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    check_source()
    with tempfile.TemporaryDirectory(prefix="warm-bounded-") as tmp:
        exe = Path(tmp) / "warm-bounded"
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-D_CRT_SECURE_NO_WARNINGS", "-pthread",
                        str(ROOT / "tests/warm_bounded_test.cpp"), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=120)


if __name__ == "__main__":
    main()
