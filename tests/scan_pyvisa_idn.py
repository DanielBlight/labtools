"""Scan all PyVISA-visible instruments and print their IDN responses."""

import argparse

import pyvisa


def scan_resources(timeout_ms: int = 2000) -> int:
    resource_manager = pyvisa.ResourceManager()
    resources = resource_manager.list_resources()

    if not resources:
        print("No VISA resources found.")
        return 0

    print(f"Found {len(resources)} VISA resource(s).")

    for address in resources:
        instrument = None
        try:
            instrument = resource_manager.open_resource(address)
            instrument.timeout = timeout_ms
            idn = instrument.query("*IDN?").strip()
            print(f"{address}: {idn}")
        except Exception as exc:  # pragma: no cover - hardware/environment dependent
            print(f"{address}: ERROR: {exc}")
        finally:
            if instrument is not None:
                try:
                    instrument.close()
                except Exception:
                    pass

    resource_manager.close()
    return 0


def main():
    parser = argparse.ArgumentParser(description="List PyVISA resources and query *IDN? on each one.")
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=2000,
        help="VISA timeout in milliseconds for each IDN query (default: 2000).",
    )
    args = parser.parse_args()
    raise SystemExit(scan_resources(timeout_ms=args.timeout_ms))


if __name__ == "__main__":
    main()
