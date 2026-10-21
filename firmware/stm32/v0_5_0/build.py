"""Compile/link the existing STM32 project. No programmer/flash commands."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT
DRIVERS = PROJECT / "Drivers"

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--toolchain", type=Path, help="Directory containing arm-none-eabi-gcc")
    ap.add_argument("--channels", type=int, choices=[2,4], default=4)
    ap.add_argument("--out", type=Path, help="New output directory, never overwrite a previous build")
    ap.add_argument("--rate-hz", type=int)
    ap.add_argument("--baud", type=int, default=230400)
    args = ap.parse_args(argv)
    if args.channels != 4 or args.rate_hz not in (None,100) or args.baud != 230400:
        ap.error("This display release requires 4 channels, 100 Hz and 230400 baud")
    if args.rate_hz is None: args.rate_hz = 100 if args.channels == 4 else 200
    if args.rate_hz not in range(20,1001) or 1000000 % args.rate_hz or args.baud <= 0:
        ap.error("Invalid integer period/rate/baud")
    record_bytes = 96 + 5*(args.channels-2)
    if (record_bytes*args.rate_hz+300)*10 > args.baud*.85:
        ap.error("Worst-case records exceed 85 percent of UART capacity")
    suffix = ".exe" if sys.platform == "win32" else ""
    name = "arm-none-eabi-gcc" + suffix
    gcc = args.toolchain / name if args.toolchain else None
    if gcc is None:
        found = shutil.which(name)
        if found:
            gcc = Path(found)
        elif Path("C:/ST").exists():
            found = sorted(Path("C:/ST").rglob(name))
            if found:
                gcc = found[-1]
    if gcc is None or not gcc.is_file():
        ap.error("arm-none-eabi-gcc not found. Supply --toolchain BIN_DIRECTORY. Nothing was flashed.")
    out = args.out or PROJECT / f"Debug/pilot_{args.channels}ch"
    out.mkdir(parents=True, exist_ok=False)
    driver = DRIVERS / "STM32F1xx_HAL_Driver"
    sources = sorted((PROJECT / "Core/Src").glob("*.c")) + sorted((driver / "Src").glob("*.c"))
    sources += list((PROJECT / "Core/Startup").glob("*.s"))
    includes = [PROJECT / "Core/Inc", driver / "Inc", driver / "Inc/Legacy",
                DRIVERS / "CMSIS/Device/ST/STM32F1xx/Include", DRIVERS / "CMSIS/Include"]
    linker = PROJECT / "STM32F103C8TX_FLASH.ld"
    version = subprocess.check_output([str(gcc), "--version"], text=True).splitlines()[0]
    hashes = {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest()
              for f in sorted(set(sources + list((PROJECT / "Core/Inc").glob("*.h")) +
                                  list(DRIVERS.rglob("*.h")) + [linker]))}
    header = (PROJECT / "Core/Inc/pilot_config.h").read_text(encoding="utf-8")
    def setting(name):
        return int(re.search(r"^#define " + name + r" (\d+)U$", header, re.M)[1])
    config = {"temperature": {"type": "DS18B20", "pin": "PB7", "supply_v": 3.3, "max_probes": 2, "period_ms": 1000, "resolution_bits": 12, "physical_tested": False}, "nextion": {"enabled": True, "pins": ["PA2", "PA3"],
                          "baud": setting("PILOT_NEXTION_BAUD"),
                          "period_ms": setting("PILOT_NEXTION_PERIOD_MS"),
                          "tare": "display_only", "hmi_contract": "t0; waveform 2/0; raw T",
                          "physical_link_tested": False}, "compiler": version, "rate_hz": args.rate_hz, "baud": args.baud,
              "channels": args.channels, "record_max_bytes": record_bytes,
              "uart_worst_case_fraction": (record_bytes*args.rate_hz+300)*10/args.baud,
              "pins": ["PA0","PA1"] + (["PA5","PA6"] if args.channels==4 else []),
              "optimization": "O2", "sources_sha256": hashes,
              "build_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    config["nextion"].update(mode="mass_g", window_samples=100, tare="unloaded_zero_only", model_id="497c5c8fbd85a4ef4284da84ff57cb27144c7f28b633eb0435fdb7966894c42d", negative_zero_extension="first segment to -50 g, display only")
    build_id = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
    flags = ["-mcpu=cortex-m3", "-mthumb", "-O2", "-g3", "-ffunction-sections", "-fdata-sections",
             "-fstack-usage", "-Wall", "-Wextra", "-Wno-unused-function", "-std=gnu11",
             "-DUSE_HAL_DRIVER", "-DSTM32F103xB", f'-DPILOT_BUILD_ID="{build_id}"',
             f"-DPILOT_RATE_HZ={args.rate_hz}U", f"-DPILOT_BAUD={args.baud}U",
             f"-DPILOT_CHANNEL_COUNT={args.channels}U"]
    incflags = ["-I" + str(f) for f in includes]
    commands = []
    logpath = out / "build.log"
    with logpath.open("w", encoding="utf-8") as log:
        def run(command):
            commands.append(command)
            r = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            log.write(r.stdout); log.flush()
            if r.returncode:
                print(r.stdout, file=sys.stderr)
                raise SystemExit(f"Build failed ({r.returncode}); see {logpath}. No flash operation.")
            return r.stdout
        objects = []
        for i, source in enumerate(sources):
            obj = out / f"{i:02d}_{source.stem}.o"
            run([str(gcc), *flags, *incflags, "-c", str(source), "-o", str(obj)])
            objects.append(str(obj))
        elf = out / "hall_pilot.elf"
        print(run([str(gcc), "-mcpu=cortex-m3", "-mthumb", "--specs=nano.specs", "--specs=nosys.specs",
                   "-T" + str(linker), "-Wl,--gc-sections,--print-memory-usage",
                   "-Wl,-Map=" + str(out / "hall_pilot.map"), *objects, "-Wl,--start-group", "-lc", "-lm",
                   "-Wl,--end-group", "-o", str(elf)]))
        for fmt, ext in [("ihex", "hex"), ("binary", "bin")]:
            run([str(gcc.with_name("arm-none-eabi-objcopy" + suffix)), "-O", fmt, str(elf), str(out / ("hall_pilot." + ext))])
        size = run([str(gcc.with_name("arm-none-eabi-size" + suffix)), str(elf)])
        print(size)
    config.update(build_id=build_id, commands=commands, size_output=size,
                  artifacts_sha256={f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                                    for f in out.glob("hall_pilot.*") if f.suffix in {".elf", ".hex", ".bin"}},
                  device_tested=False, flashed=False)
    (out / "build_manifest.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"Build ID {build_id}\n{elf}\nNot flashed. Not verified on hardware.")

if __name__ == "__main__":
    main()
