import json
import os
from pathlib import Path
from properties import PropertyParseOptions, parse_export_properties
from blueprint_structure import (
    build_blueprint_structure,
    build_blueprint_variables,
    normalize_blueprint_topology,
    _find_parent_blueprint_paths,
)
from reader import create_archive_with_uexp
from package import FPackageFileSummary
from names import FNameMap
from imports import FImportMap
from exports import FExportMap


class SerializeOptions:
    def __init__(
        self,
        include_object_tree=True,
        include_properties=True,
        include_raw=True,
        raw_limit=64,
        indent="\t",
        blueprint_only=False,
        include_blueprint_structure=True,
    ):
        self.include_object_tree = include_object_tree
        self.include_properties = include_properties
        self.property_options = PropertyParseOptions(
            include_raw=include_raw,
            raw_limit=raw_limit,
        )
        self.indent = indent
        self.blueprint_only = blueprint_only
        self.include_blueprint_structure = include_blueprint_structure


def infer_package_name(summary, name_map, filepath=""):
    if summary.PackageName and summary.PackageName != "None":
        return summary.PackageName

    if filepath:
        stem = os.path.splitext(os.path.basename(filepath))[0]
        suffix = f"/{stem}"
        dotted = f".{stem}"
        for name in name_map.to_list():
            if name.endswith(suffix) or name.endswith(dotted):
                return name.split(".", 1)[0]

    return ""


def resolve_index(summary, import_map, export_map, package_idx):
    if package_idx == 0:
        return {"type": "null", "name": "None"}
    if package_idx > 0:
        idx = package_idx - 1
        if idx < len(export_map):
            return {
                "type": "export",
                "index": idx,
                "name": str(export_map[idx].ObjectName),
            }
    else:
        idx = -package_idx - 1
        if idx < len(import_map):
            imp = import_map[idx]
            return {
                "type": "import",
                "index": idx,
                "name": str(imp.ObjectName),
                "class": str(imp.ClassName),
                "package": str(imp.ClassPackage),
            }
    return {"type": "unknown", "index": package_idx}


def build_object_tree(summary, name_map, import_map, export_map, reader, options):
    exports = export_map.exports
    tree_nodes = []
    export_to_node = {}
    warnings = []

    for i, exp in enumerate(exports):
        obj_name = str(exp.ObjectName)
        class_ref = resolve_index(summary, import_map, export_map, exp.ClassIndex)
        super_ref = resolve_index(summary, import_map, export_map, exp.SuperIndex)
        template_ref = resolve_index(
            summary, import_map, export_map, exp.TemplateIndex
        )
        outer_ref = resolve_index(summary, import_map, export_map, exp.OuterIndex)

        node = {
            "index": i,
            "name": str(exp.ObjectName),
            "class": class_ref,
            "super": super_ref,
            "template": template_ref,
            "outer": outer_ref,
            "objectFlags": exp.ObjectFlags,
            "serialSize": exp.SerialSize,
            "serialOffset": exp.SerialOffset,
            "bIsAsset": exp.bIsAsset,
            "children": [],
        }

        if options.include_properties:
            props = parse_export_properties(reader, exp, i, options.property_options)
            node["properties"] = props["properties"]
            if props.get("warnings"):
                warnings.extend(props["warnings"])

        export_to_node[i] = node

    for i, node in export_to_node.items():
        outer = node["outer"]
        if outer["type"] == "export":
            parent_idx = outer["index"]
            if parent_idx in export_to_node and parent_idx != i:
                export_to_node[parent_idx]["children"].append(node)

    for i, node in export_to_node.items():
        if node["outer"]["type"] != "export":
            tree_nodes.append(node)

    return tree_nodes, warnings


def build_blueprint_structure_with_inheritance(
    tree, name_map, import_map, export_map, filepath, options, visited=None
):
    visited = visited or set()
    if filepath:
        visited.add(str(Path(filepath).resolve()).lower())

    result = {}
    for parent_path in _find_parent_blueprint_paths(
        tree, name_map, import_map, export_map, filepath
    ):
        _merge_blueprint_structure_from_file(parent_path, result, visited, options)

    _merge_component_map(
        result, build_blueprint_structure(tree, import_map, export_map)
    )
    return normalize_blueprint_topology(result)


def _merge_blueprint_structure_from_file(filepath, result, visited, options):
    if not filepath:
        return
    resolved = str(Path(filepath).resolve()).lower()
    if resolved in visited:
        return
    visited.add(resolved)
    if not os.path.exists(filepath):
        return

    archive = create_archive_with_uexp(filepath)
    summary = FPackageFileSummary(archive)
    archive.setSummary(summary)
    name_map = FNameMap(archive)
    import_map = FImportMap(archive)
    export_map = FExportMap(archive)
    tree, _ = build_object_tree(
        summary, name_map, import_map, export_map, archive, options
    )

    parent_structure = build_blueprint_structure_with_inheritance(
        tree, name_map, import_map, export_map, filepath, options, visited
    )
    _merge_component_map(result, parent_structure)


def _merge_component_map(result, incoming):
    for name, entry in incoming.items():
        if name in result:
            result[name] = _merge_component_entry(result[name], entry)
        else:
            result[name] = dict(entry)


def _merge_component_entry(existing, incoming):
    merged = dict(existing)

    if "Class" in incoming and incoming.get("Class") is not None:
        merged["Class"] = incoming["Class"]

    if "Parent" in incoming:
        parent = incoming.get("Parent")
        if parent is not None:
            merged["Parent"] = parent
            merged.pop("IsRoot", None)
        else:
            merged.pop("Parent", None)

    if incoming.get("IsRoot") is True:
        merged["IsRoot"] = True
        merged.pop("Parent", None)
    elif "IsRoot" in incoming:
        if incoming.get("IsRoot") is False:
            merged.pop("IsRoot", None)
        elif incoming.get("IsRoot") is not None:
            merged["IsRoot"] = incoming["IsRoot"]

    if "Socket" in incoming:
        socket = incoming.get("Socket")
        if socket is not None:
            merged["Socket"] = socket
        else:
            merged.pop("Socket", None)

    existing_props = existing.get("Properties")
    incoming_props = incoming.get("Properties")
    if isinstance(existing_props, dict) or isinstance(incoming_props, dict):
        props = dict(existing_props) if isinstance(existing_props, dict) else {}
        if isinstance(incoming_props, dict):
            for prop_name, prop_value in incoming_props.items():
                props[prop_name] = prop_value
        if props:
            merged["Properties"] = props

    for source in (existing, incoming):
        for key, value in source.items():
            if key in {"Class", "Parent", "Socket", "IsRoot", "Properties"}:
                continue
            if value is not None or key not in merged:
                merged[key] = value

    return merged


def serialize_to_dict(summary, name_map, import_map, export_map, reader,
                      filepath="", options=None):
    options = options or SerializeOptions()
    warnings = []

    result = {
        "sourceFile": os.path.basename(filepath) if filepath else "",
        "packageName": infer_package_name(summary, name_map, filepath),
        "summary": summary.to_dict(),
        "nameTable": name_map.to_list(),
        "nameCount": len(name_map),
        "importTable": import_map.to_list(),
        "importCount": len(import_map),
        "exportTable": export_map.to_list(),
        "exportCount": len(export_map),
    }
    if options.include_object_tree:
        tree, warnings = build_object_tree(
            summary, name_map, import_map, export_map, reader, options
        )
        blueprint_structure = build_blueprint_structure_with_inheritance(
            tree, name_map, import_map, export_map, filepath, options
        )
        if options.blueprint_only:
            return blueprint_structure
        blueprint_variables = build_blueprint_variables(
            tree, name_map, import_map, export_map, filepath
        )
        if options.include_blueprint_structure:
            result["blueprintStructure"] = blueprint_structure
            if blueprint_variables:
                result["blueprintVariables"] = blueprint_variables
        result["objectTree"] = tree
    result["_parseWarnings"] = warnings
    return result


def serialize_to_json(summary, name_map, import_map, export_map, reader,
                      filepath="", options=None):
    options = options or SerializeOptions()
    d = serialize_to_dict(summary, name_map, import_map, export_map,
                          reader, filepath, options)
    return json.dumps(d, ensure_ascii=False, indent=options.indent)


def write_json(summary, name_map, import_map, export_map, reader,
               filepath, output_path, options=None):
    json_str = serialize_to_json(summary, name_map, import_map,
                                 export_map, reader, filepath, options)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(json_str)
    return json_str
