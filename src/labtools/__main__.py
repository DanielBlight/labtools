"""Support python -m labtools without importing Qt or device drivers."""
from labtools.cli import main

if __name__ == "__main__":
    main()
