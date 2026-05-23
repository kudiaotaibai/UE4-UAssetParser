import sys
import os

_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import json
import argparse
import traceback

from reader import create_archive_with_uexp
from package import FPackageFileSummary
from names import FNameMap
from imports import FImportMap
from exports import FExportMap
from serializer import SerializeOptions, write_json
from errors import UAssetError


EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_BAD_ARGS = 2
EXIT_FILE_ERROR = 3


def parse_single(filepath, output_path=None, verbose=False, options=None):
    if not os.path.exists(filepath):
        print(f"Error: file not found: {filepath}", file=sys.stderr)
        sys.exit(EXIT_FILE_ERROR)

    archive = create_archive_with_uexp(filepath)
    name = os.path.basename(filepath)

    if verbose:
        print(f"Parsing: {name} ({archive.size / 1024:.1f} KB)")

    summary = FPackageFileSummary(archive)
    archive.setSummary(summary)

    if verbose:
        eng = summary.SavedByEngineVersion
        print(f"  Version: UE4={summary.FileVersionUE4}, "
              f"LicenseeUE4={summary.FileVersionLicenseeUE4}")
        if eng:
            print(f"  Engine: {eng}")
        print(f"  Names: {summary.NameCount}, "
              f"Imports: {summary.ImportCount}, "
              f"Exports: {summary.ExportCount}")

    name_map = FNameMap(archive)
    import_map = FImportMap(archive)
    export_map = FExportMap(archive)

    if output_path is None:
        base = os.path.splitext(filepath)[0]
        output_path = base + ".json"

    write_json(summary, name_map, import_map, export_map, archive,
               filepath, output_path, options)

    if verbose:
        out_name = os.path.basename(output_path)
        json_size = os.path.getsize(output_path) / 1024
        print(f"  Output: {out_name} ({json_size:.1f} KB)")

    return output_path


def parse_batch(input_dir, output_dir=None, verbose=False, options=None):
    if not os.path.isdir(input_dir):
        print(f"Error: directory not found: {input_dir}", file=sys.stderr)
        sys.exit(EXIT_FILE_ERROR)

    uasset_files = []
    for root, dirs, files in os.walk(input_dir):
        for f in files:
            if f.endswith(".uasset"):
                uasset_files.append(os.path.join(root, f))

    if not uasset_files:
        print(f"Warning: no .uasset files found in directory: {input_dir}")
        return

    print(f"Found {len(uasset_files)} .uasset files")
    count = 0
    errors = 0
    for fp in uasset_files:
        try:
            output_path = None
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(
                    output_dir,
                    os.path.splitext(os.path.basename(fp))[0] + ".json"
                )
            out = parse_single(
                fp,
                output_path=output_path,
                verbose=verbose,
                options=options,
            )
            count += 1
            if verbose:
                print(f"  [{count}/{len(uasset_files)}] OK: "
                      f"{os.path.basename(out)}")
        except Exception as e:
            errors += 1
            if verbose:
                print(f"  ERROR: {os.path.basename(fp)}: {e}",
                      file=sys.stderr)

    print(f"Done. {count} parsed, {errors} errors.")


def main():
    parser = argparse.ArgumentParser(
        description="UAsset Parser - Parse UE4 .uasset files to JSON",
    )
    parser.add_argument(
        "input", help=".uasset file path or directory (with --batch)"
    )
    parser.add_argument(
        "-o", "--output",
        help=(
            "Output JSON path for single-file mode, or output directory "
            "for --batch (default: same as input)"
        )
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--batch", action="store_true",
        help="Batch mode: parse all .uasset in a directory"
    )
    parser.add_argument(
        "--summary-only", action="store_true",
        help="Skip objectTree/property parsing; output summary/name/import/export tables only"
    )
    parser.add_argument(
        "--no-properties", action="store_true",
        help="Build objectTree but skip per-export property parsing"
    )
    parser.add_argument(
        "--no-raw", action="store_true",
        help="Do not include rawData hex for unsupported properties"
    )
    parser.add_argument(
        "--raw-limit", type=int, default=64,
        help="Maximum rawData bytes to include per unsupported property (default: 64)"
    )
    parser.add_argument(
        "--full-raw", action="store_true",
        help="Include full rawData hex for unsupported properties"
    )
    parser.add_argument(
        "--compact", action="store_true",
        help="Write compact JSON instead of pretty-printed JSON"
    )
    parser.add_argument(
        "--blueprint-only", action="store_true",
        help="Output an editor-friendly Blueprint component structure only"
    )

    args = parser.parse_args()
    raw_limit = None if args.full_raw else max(0, args.raw_limit)
    options = SerializeOptions(
        include_object_tree=not args.summary_only,
        include_properties=not args.no_properties and not args.summary_only,
        include_raw=not args.no_raw,
        raw_limit=raw_limit,
        indent=None if args.compact else 2,
        blueprint_only=args.blueprint_only,
    )

    try:
        if args.batch:
            parse_batch(args.input, args.output, args.verbose, options)
        else:
            out = parse_single(args.input, args.output, args.verbose, options)
            if args.verbose:
                print(f"Done: {out}")
            else:
                print(out)
    except UAssetError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(EXIT_FILE_ERROR)
    except Exception as e:
        if args.verbose:
            traceback.print_exc()
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(EXIT_UNEXPECTED)


if __name__ == "__main__":
    main()
