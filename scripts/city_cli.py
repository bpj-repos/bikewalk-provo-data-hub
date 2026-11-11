"""JSON results for the city commands, with existing human output preserved."""
from contextlib import redirect_stdout
import io
import json
import sys
from zipfile import BadZipFile

from jsonschema import ValidationError


def run(parser, action):
    parser.add_argument("--json", action="store_true", help="Emit one JSON result or error, without progress text")
    args = parser.parse_args()
    try:
        with redirect_stdout(io.StringIO() if args.json else sys.stdout):
            result = action(args)
    except (ValueError, OSError, KeyError, ImportError, BadZipFile, ValidationError) as error:
        if not args.json:
            parser.error(str(error))
        print(json.dumps({"status": "error", "error": str(error), "nextCommand": None}))
        raise SystemExit(2) from None
    if args.json:
        print(json.dumps({"status": "ok", **result}, ensure_ascii=False))


def package_result(package, digest, *, inputs, coverage=None, excluded=None, next_command=None):
    return dict(
        inputs=inputs,
        outputs={"package": str(package.resolve()), "manifest": str((package / "datapackage.json").resolve()),
                 "sha256": digest},
        coverage=coverage or {},
        excluded=excluded or {},
        nextCommand=next_command,
    )
