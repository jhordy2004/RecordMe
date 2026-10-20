"""Punto de ejecución cuando se invoca 'python -m recordme'."""

import sys

from recordme.app import main

if __name__ == "__main__":
    sys.exit(main())
