"""Compatibility entry point. Maintained command: python -m scripts.update_crashes."""
import runpy

if __name__ == "__main__":
    runpy.run_module("scripts.update_crashes", run_name="__main__")
