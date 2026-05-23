import json
import os
from properties import PropertyParseOptions, parse_export_properties
from blueprint_structure import build_blueprint_structure


class SerializeOptions:
    def __init__(
        self,
        include_object_tree=True,
        include_properties=True,
        include_raw=True,
        raw_limit=64,
        indent=2,
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
        blueprint_structure = build_blueprint_structure(
            tree, import_map, export_map
        )
        if options.blueprint_only:
            return blueprint_structure
        if options.include_blueprint_structure:
            result["blueprintStructure"] = blueprint_structure
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
