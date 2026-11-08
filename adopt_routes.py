"""Compatibility entry point. Maintained command: python -m scripts.adopt_routes."""
import runpy

if __name__ == "__main__":
    runpy.run_module("scripts.adopt_routes", run_name="__main__")
