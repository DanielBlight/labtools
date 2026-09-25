"""Non-opening SC10 settings test.

The test exercises mode, timing, repeat and trigger settings while keeping the
controller disabled. Original settings are restored in ``finally``. It does not
verify the physical shutter timing; use suitable instrumentation for that.
"""

from __future__ import annotations

import argparse

from labtools.devices.sc10 import (
    SC10,
    SC10ExternalTriggerMode,
    SC10Mode,
    SC10TriggerMode,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM4")
    parser.add_argument("--baud", type=int, default=9600)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with SC10(port=args.port, baud_rate=args.baud) as shutter:
        original = shutter.get_state()
        print("Initial state:")
        print(original)
        shutter.set_enabled(False)
        try:
            for mode in SC10Mode:
                shutter.set_mode(mode)
                reported = shutter.get_mode()
                print(f"Mode {mode.name}: {reported.name}")
                if reported != mode:
                    raise RuntimeError(f"Mode readback mismatch for {mode.name}")

            for milliseconds in (10, 50, 100):
                shutter.set_open_time_ms(milliseconds)
                shutter.set_close_time_ms(milliseconds + 10)
                reported_open = shutter.get_open_time_ms()
                reported_close = shutter.get_close_time_ms()
                print(
                    f"Timing request open={milliseconds} ms, close={milliseconds + 10} ms; "
                    f"readback open={reported_open} ms, close={reported_close} ms"
                )
                if reported_open != milliseconds or reported_close != milliseconds + 10:
                    raise RuntimeError("Timing readback mismatch")

            for repeat in (1, 4, 8):
                shutter.set_repeat_count(repeat)
                reported = shutter.get_repeat_count()
                print(f"Repeat request={repeat}; readback={reported}")
                if reported != repeat:
                    raise RuntimeError("Repeat-count readback mismatch")

            for trigger in SC10TriggerMode:
                shutter.set_trigger_mode(trigger)
                if shutter.get_trigger_mode() != trigger:
                    raise RuntimeError("Trigger-mode readback mismatch")

            for output_mode in SC10ExternalTriggerMode:
                shutter.set_external_trigger_mode(output_mode)
                if shutter.get_external_trigger_mode() != output_mode:
                    raise RuntimeError("External-trigger-mode readback mismatch")

            print("All non-opening mode and timing checks passed.")
        finally:
            shutter.set_enabled(False)
            shutter.set_mode(original.mode)
            shutter.set_trigger_mode(original.trigger_mode)
            shutter.set_external_trigger_mode(original.external_trigger_mode)
            shutter.set_open_time_ms(original.open_time_ms)
            shutter.set_close_time_ms(original.close_time_ms)
            shutter.set_repeat_count(original.repeat_count)
            print("Original settings restored; controller left disabled.")


if __name__ == "__main__":
    main()
