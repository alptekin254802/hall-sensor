# Firmware and optional acquisition

## Historical firmware

| Snapshot | Historical build ID | Use |
|---|---|---|
| STM32 0.4.0 | `d938b48619206962` | Four-channel bench acquisition with temperature streams |
| STM32 0.5.0 | `d61d4135045cbd32` | Frozen force-to-mass display conversion for Nextion and later acquisitions |
| HX711_RAW_R1 | Arduino Uno sketch | Signed HX711 bridge counts for the scalar benchmark |

Each STM32 snapshot contains hash-verified historical sources, its BIN/HEX
files and a `historical_build.json`. Original binaries are preserved unchanged.
The portable build entry point changes file locations and therefore generates
a new build identity. A rebuilt binary is not asserted to be bit-identical to
the historical binary. Debug ELF files are not distributed.

From the repository root, with GNU Arm Embedded tools on PATH:

```sh
python firmware/stm32/v0_4_0/build.py --out build/hall_0_4_0
python firmware/stm32/v0_5_0/build.py --out build/hall_0_5_0
```

Alternatively supply `--toolchain` with the compiler's `bin` directory. The
historical compiler was GNU Tools for STM32 14.3.1. Build scripts compile and
link only; they never program or reset a device. The target is STM32F103C8.

The four Hall inputs are PA0, PA1, PA5 and PA6. Acquisition runs at 100 Hz and
uses USART1 at 230400 baud. Two DS18B20 probes share PB7. Nextion uses PA2/PA3
at 9600 baud, with text component `t0`, waveform component 2/channel 0 and the
raw ASCII `T` tare command. The screen's editable HMI/TFT project is not included;
the firmware and readout protocol are included.

The Uno sketch uses D2 for HX711 DOUT, D3 for PD_SCK, channel A/gain 128 and
115200 baud. The experiment used the module's hardware 10 Hz setting. Open
`hx711_reference/hx711_reference.ino` with the Arduino Uno board target to build.
The sketch outputs counts, not calibrated mass. Wire excitation and bridge
signals according to the actual module and transducer pin labels.

## Optional Hall recorder

The exported CLI preserves the serial protocol and recording code, with only
output/model paths adapted for this repository. It is separate from offline
reproduction. Install `requirements-acquisition.txt`, then inspect:

```sh
python -m acquisition.capture --help
```

Recording requires an explicit `--port` (and the physical device), or a
`--replay` byte stream for offline use. Provide `--out recordings` and a duration.
Set specimen and load metadata using the listed options. New recordings are
written to new capture directories and are not added to the publication dataset
automatically. The recorder source is the export-date version; historical
captures need not have used this exact recorder revision.

The HX711 host protocol and recording implementation are in `acquisition/loadcell.py`.
Its `Connection` API requires an explicit port opening and writes new raw captures;
it is provided without the experiment-specific desktop interface.
