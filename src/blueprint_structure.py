import os
import re
from pathlib import Path

from exports import FExportMap
from imports import FImportMap
from package import FPackageFileSummary
from names import FNameMap
from properties import PropertyParseOptions, parse_export_properties
from reader import create_archive_with_uexp


def build_blueprint_structure(tree_nodes, import_map, export_map):
    """Build an editor-friendly component map from parsed export nodes."""
    all_nodes = []
    export_nodes = {}

    def visit(node):
        all_nodes.append(node)
        idx = node.get("index")
        if isinstance(idx, int):
            export_nodes[idx] = node
        for child in node.get("children", []):
            visit(child)

    for root in tree_nodes:
        visit(root)

    scs_info = _build_scs_info(all_nodes, export_nodes)

    component_nodes = []
    for node in all_nodes:
        cls = _class_name(node)
        name = node.get("name", "")
        if (
            _is_component_class(cls)
            and not name.startswith("NODE_")
            and not name.startswith("K2Node_")
        ):
            component_nodes.append(node)

    result = {}
    for node in component_nodes:
        info = scs_info.get(node.get("index"), {})
        name = info.get("name") or _clean_component_name(node.get("name", ""))
        entry = {
            "Class": _class_name(node),
        }

        parent = info.get("parent") or _find_attach_parent(node, export_nodes)
        if parent:
            entry["Parent"] = _clean_component_name(parent)
        else:
            entry["IsRoot"] = True

        properties = _convert_properties(
            node.get("properties", {}),
            import_map,
            export_map,
        )
        if properties:
            entry["Properties"] = properties

        socket = info.get("socket") or _find_attach_socket(node)
        if socket:
            entry["Socket"] = socket

        result[name] = entry

    return normalize_blueprint_topology(result)


def build_blueprint_variables(
    tree_nodes, name_map, import_map, export_map, source_file=""
):
    result = {}
    visited = set()
    if source_file:
        visited.add(str(Path(source_file).resolve()).lower())

    for parent_path in _find_parent_blueprint_paths(
        tree_nodes, name_map, import_map, export_map, source_file
    ):
        _merge_variables_from_file(parent_path, result, visited)

    for name, entry in _extract_declared_variables_from_exports(
        None, import_map, export_map
    ).items():
        _merge_variable_entry(result, name, entry)

    _merge_variables_from_tree(tree_nodes, import_map, export_map, result)

    return result


def _merge_variables_from_tree(tree_nodes, import_map, export_map, result):
    all_nodes = []

    def visit(node):
        all_nodes.append(node)
        for child in node.get("children", []):
            visit(child)

    for root in tree_nodes:
        visit(root)

    for node in all_nodes:
        if not _is_cdo_node(node):
            continue
        for name, entry in _extract_cdo_variables(
            node.get("properties", {}),
            import_map,
            export_map,
        ).items():
            _merge_variable_entry(result, name, entry)


def _merge_variables_from_file(filepath, result, visited):
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

    for parent_path in _find_parent_blueprint_paths(
        [], name_map, import_map, export_map, filepath
    ):
        _merge_variables_from_file(parent_path, result, visited)

    declared_variables = _extract_declared_variables_from_exports(
        summary, import_map, export_map
    )
    for name, entry in declared_variables.items():
        _merge_variable_entry(result, name, entry)

    cdo_props = _extract_cdo_props_from_file(archive, name_map, export_map)
    for name, entry in _extract_cdo_variables(
        cdo_props, import_map, export_map
    ).items():
        _merge_variable_entry(result, name, entry)


def _merge_variable_entry(result, name, entry):
    existing = result.get(name, {})
    merged = dict(existing)
    for key, value in entry.items():
        if value is not None or key not in merged:
            merged[key] = value
    result[name] = merged


def _extract_cdo_props_from_file(reader, name_map, export_map):
    for i, exp in enumerate(export_map.exports):
        object_name = str(exp.ObjectName)
        if not object_name.startswith("Default__"):
            continue
        props = parse_export_properties(
            reader,
            exp,
            i,
            PropertyParseOptions(include_raw=True, raw_limit=64),
        )
        return props.get("properties", {})
    return {}


def _fname_index(value):
    if isinstance(value, int):
        return value
    text = str(value)
    match = re.search(r"<index=(\d+),\s*number=\d+>", text)
    if match:
        return int(match.group(1))
    try:
        return int(text)
    except Exception:
        return -1


def _is_cdo_node(node):
    name = node.get("name", "")
    return isinstance(name, str) and name.startswith("Default__")


def _extract_cdo_variables(properties, import_map, export_map):
    result = {}
    for name, prop in properties.items():
        if name != "LuaFilePath" and not name.startswith("bp_"):
            continue
        if not isinstance(prop, dict) or prop.get("unsupported"):
            continue
        converted = _convert_property(prop, import_map, export_map)
        if converted is not None:
            result[name] = converted
    return result


def _extract_declared_variables_from_exports(summary, import_map, export_map):
    result = {}
    component_names = _component_names_from_exports(summary, import_map, export_map)
    for exp in export_map.exports:
        name = str(exp.ObjectName)
        if name not in {"LuaFilePath"} and not name.startswith("bp_"):
            continue
        if name in component_names:
            continue
        cls_ref = _resolve_package_index(summary, import_map, export_map, exp.ClassIndex)
        cls = cls_ref.get("name", "")
        if cls not in {
            "BoolProperty",
            "ByteProperty",
            "IntProperty",
            "Int64Property",
            "FloatProperty",
            "StrProperty",
            "TextProperty",
            "NameProperty",
            "ObjectProperty",
            "SoftObjectProperty",
            "EnumProperty",
            "ArrayProperty",
            "MapProperty",
            "SetProperty",
            "StructProperty",
        }:
            continue
        outer_ref = _resolve_package_index(summary, import_map, export_map, exp.OuterIndex)
        if not isinstance(outer_ref, dict):
            continue
        if outer_ref.get("type") != "export" or not str(outer_ref.get("name", "")).endswith("_C"):
            continue
        result[name] = {
            "Type": cls[:-8] if cls.endswith("Property") else cls,
            "Value": None,
        }
    return result


def _component_names_from_exports(summary, import_map, export_map):
    result = set()
    for exp in export_map.exports:
        cls_ref = _resolve_package_index(summary, import_map, export_map, exp.ClassIndex)
        cls = cls_ref.get("name", "")
        if not _is_component_class(cls):
            continue
        result.add(_clean_component_name(str(exp.ObjectName)))
    return result


def _resolve_package_index(summary, import_map, export_map, package_idx):
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


def _find_parent_blueprint_paths(
    tree_nodes, name_map, import_map, export_map, source_file
):
    all_nodes = []

    if tree_nodes:
        def visit(node):
            all_nodes.append(node)
            for child in node.get("children", []):
                visit(child)

        for root in tree_nodes:
            visit(root)
    else:
        for exp in export_map.exports:
            super_ref = {"type": "null", "index": None}
            if exp.SuperIndex < 0:
                super_ref = {
                    "type": "import",
                    "index": -exp.SuperIndex - 1,
                }
            all_nodes.append({
                "name": str(exp.ObjectName),
                "super": super_ref,
            })

    parent_paths = []
    for node in all_nodes:
        name = node.get("name", "")
        if not isinstance(name, str) or not name.endswith("_C"):
            continue
        super_ref = node.get("super", {})
        if not isinstance(super_ref, dict) or super_ref.get("type") != "import":
            continue
        idx = super_ref.get("index")
        if not isinstance(idx, int):
            continue
        imp = import_map.resolve_index(-(idx + 1))
        if not imp:
            continue
        path = _resolve_package_to_uasset_path(
            _resolve_blueprint_package_name(str(imp.ObjectName), name_map),
            source_file,
        )
        if path:
            parent_paths.append(path)
    return parent_paths


def _resolve_blueprint_package_name(object_name, name_map):
    if not object_name or not name_map:
        return ""
    idx = _fname_index(object_name)
    if 0 <= idx < len(name_map):
        resolved_name = str(name_map[idx])
    else:
        resolved_name = str(object_name)
    stem = resolved_name
    if stem.endswith("_C"):
        stem = stem[:-2]
    candidates = []
    for name in name_map.to_list():
        if name.endswith(f"/{stem}") or name.endswith(f".{stem}"):
            candidates.append(name)
    for candidate in candidates:
        if candidate.startswith("/Game/"):
            return candidate
    return candidates[0] if candidates else ""


def _resolve_package_to_uasset_path(package_name, source_file):
    if not package_name or package_name == "None":
        return ""
    if not package_name.startswith("/Game/"):
        return ""

    content_root = _find_content_root(source_file)
    if not content_root:
        return ""

    rel = package_name[len("/Game/"):].lstrip("/").replace("/", os.sep)
    path = Path(content_root) / rel
    if path.suffix.lower() != ".uasset":
        path = path.with_suffix(".uasset")
    return str(path)


def _find_content_root(source_file):
    try:
        current = Path(source_file).resolve()
    except Exception:
        return ""
    for parent in current.parents:
        if parent.name.lower() == "content":
            return str(parent)
    return ""


def _build_scs_info(all_nodes, export_nodes):
    result = {}
    scs_nodes = []
    for node in all_nodes:
        if _class_name(node) != "SCS_Node":
            continue
        scs_nodes.append(node)
        props = node.get("properties", {})
        template_idx = _object_ref_index(props.get("ComponentTemplate"))
        if not template_idx or template_idx <= 0:
            continue

        info = result.setdefault(template_idx - 1, {})
        name = _scs_component_name(node, export_nodes)
        if name:
            info["name"] = name

        parent_name = _property_value(props.get("ParentComponentOrVariableName"))
        if parent_name:
            info["parent"] = parent_name

        socket = _property_value(props.get("AttachToName"))
        if not socket:
            socket = _property_value(props.get("AttachSocketName"))
        if socket and socket != "None":
            info["socket"] = socket

    for node in scs_nodes:
        parent_name = _scs_component_name(node, export_nodes)
        if not parent_name:
            continue
        for child_idx in _object_ref_array_indices(
            node.get("properties", {}).get("ChildNodes")
        ):
            child_scs_node = export_nodes.get(child_idx - 1)
            if not child_scs_node:
                continue
            child_template_idx = _object_ref_index(
                child_scs_node.get("properties", {}).get("ComponentTemplate")
            )
            if not child_template_idx or child_template_idx <= 0:
                continue
            child_info = result.setdefault(child_template_idx - 1, {})
            child_info.setdefault("parent", parent_name)
    return result


def _class_name(node):
    ref = node.get("class", {})
    if isinstance(ref, dict):
        return ref.get("name", "")
    return ""


def _is_component_class(cls):
    if not cls:
        return False
    return cls.endswith("Component") and cls not in {
        "ActorComponent",
    }


def _clean_component_name(name):
    suffix = "_GEN_VARIABLE"
    if name.endswith(suffix):
        return name[:-len(suffix)]
    return name


def _find_attach_parent(node, export_nodes):
    props = node.get("properties", {})
    attach_parent = props.get("AttachParent")
    if not attach_parent:
        return ""
    idx = _object_ref_index(attach_parent)
    if not isinstance(idx, int) or idx <= 0:
        return ""
    parent = export_nodes.get(idx - 1)
    if not parent:
        return ""
    return parent.get("name", "")


def _find_attach_socket(node):
    props = node.get("properties", {})
    for key in ("AttachSocketName", "AttachToName", "SocketName"):
        socket = _property_value(props.get(key))
        if socket and socket != "None":
            return socket
    return ""


def _object_ref_index(prop):
    if not isinstance(prop, dict):
        return None
    value = prop.get("value", {})
    if not isinstance(value, dict):
        return None
    return value.get("index")


def _object_ref_array_indices(prop):
    if not isinstance(prop, dict):
        return []
    value = prop.get("value", {})
    if not isinstance(value, dict):
        return []
    result = []
    for item in value.get("items", []):
        if isinstance(item, dict) and isinstance(item.get("index"), int):
            result.append(item["index"])
    return result


def _property_value(prop):
    if not isinstance(prop, dict):
        return None
    return prop.get("value")


def _scs_component_name(node, export_nodes):
    props = node.get("properties", {})
    internal_name = _property_value(props.get("InternalVariableName"))
    if internal_name:
        return internal_name

    template_idx = _object_ref_index(props.get("ComponentTemplate"))
    if isinstance(template_idx, int) and template_idx > 0:
        template = export_nodes.get(template_idx - 1)
        if template:
            return _clean_component_name(template.get("name", ""))
    return ""


def _convert_properties(properties, import_map, export_map):
    result = {}
    for name, prop in properties.items():
        if name in {"AttachParent", "AttachSocketName", "AttachToName", "SocketName"}:
            continue
        if not isinstance(prop, dict):
            continue
        if prop.get("unsupported"):
            continue

        converted = _convert_property(prop, import_map, export_map)
        if converted is not None and not _contains_parse_garbage(converted):
            result[name] = converted
    return result


def normalize_blueprint_topology(components):
    if not isinstance(components, dict) or not components:
        return components

    child_counts = {name: 0 for name in components}
    for node in components.values():
        parent = node.get("Parent")
        if parent in child_counts:
            child_counts[parent] += 1

    root_candidates = [
        name for name, node in components.items()
        if (
            not node.get("Parent")
            and _is_attachable_component_class(node.get("Class", ""))
        )
    ]
    if not root_candidates:
        for node in components.values():
            node.pop("IsRoot", None)
        return components

    root = max(
        root_candidates,
        key=lambda name: _root_score(name, components[name], child_counts),
    )
    for name, node in components.items():
        if name == root:
            node.pop("Parent", None)
            node["IsRoot"] = True
            continue
        if node.get("Parent"):
            node.pop("IsRoot", None)
            continue
        node.pop("IsRoot", None)
        if _is_attachable_component_class(node.get("Class", "")):
            node["Parent"] = root
    return components


def _root_score(name, node, child_counts):
    return (
        child_counts.get(name, 0),
        1 if name != "DefaultSceneRoot" else 0,
        1 if node.get("Class") != "SceneComponent" else 0,
        1 if name in {"bp_Body", "CollisionCylinder", "bp_BaseRoot"} else 0,
    )


def _is_attachable_component_class(cls):
    if not cls:
        return False
    if cls in {"ActorComponent", "CharacterMovementComponent"}:
        return False
    if cls.endswith("MovementComponent"):
        return False
    return cls.endswith("Component")


def _convert_property(prop, import_map, export_map):
    prop_type = prop.get("type", "")
    value = prop.get("value")

    if prop_type.endswith("Property"):
        prop_type_name = prop_type[:-len("Property")]
    else:
        prop_type_name = prop_type

    if prop_type == "StructProperty" and isinstance(value, dict):
        struct_type = prop.get("structType") or value.get("structType", "Struct")
        struct_value = _convert_struct(value, import_map, export_map)
        result = {
            "Type": struct_type,
            "Value": struct_value,
        }
        return result

    if prop_type == "ObjectProperty" and isinstance(value, dict):
        return {
            "Type": "Object",
            "Value": _resolve_object_ref(value.get("index"), import_map, export_map),
        }

    if prop_type == "SoftObjectProperty" and isinstance(value, dict):
        asset_path = value.get("assetPath", "")
        sub_path = value.get("subPath", "")
        return {
            "Type": "SoftObject",
            "Value": asset_path + (f":{sub_path}" if sub_path else ""),
        }

    if prop_type == "ByteProperty" and isinstance(value, dict):
        return {
            "Type": "Byte",
            "Value": _normalize_enum_value(value.get("value")),
        }

    if prop_type == "ArrayProperty" and isinstance(value, dict):
        return {
            "Type": "Array",
            "Value": value.get("items", []),
        }

    if prop_type == "MapProperty" and isinstance(value, dict):
        return {
            "Type": "Map",
            "Value": value.get("entries", []),
        }

    return {
        "Type": prop_type_name,
        "Value": value,
    }


def _convert_struct(value, import_map, export_map):
    struct_type = value.get("structType")
    if struct_type in {"Vector", "Vector2D", "Rotator", "LinearColor", "Color"}:
        return {
            k: v
            for k, v in value.items()
            if k != "structType"
        }
    if struct_type == "Transform":
        return {
            "Rotation": value.get("rotation"),
            "Translation": value.get("translation"),
            "Scale3D": value.get("scale3D"),
        }
    if "fields" in value:
        converted = {}
        for field_name, field_prop in value.get("fields", {}).items():
            field_value = _convert_property(field_prop, import_map, export_map)
            if field_value is None or _contains_parse_garbage(field_value):
                continue
            converted[_lower_first(field_name)] = field_value.get("Value")
        if struct_type == "BodyInstance":
            converted = _normalize_body_instance(converted)
        return converted
    return {
        k: v
        for k, v in value.items()
        if k != "structType"
    }


def _contains_parse_garbage(value):
    if isinstance(value, dict):
        if value.get("unsupported") is True:
            return True
        if "rawData" in value or "rawSize" in value or "error" in value:
            return True
        return any(_contains_parse_garbage(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_parse_garbage(v) for v in value)
    return False


def _lower_first(name):
    if not name:
        return name
    return name[:1].lower() + name[1:]


def _normalize_enum_value(value):
    if not isinstance(value, str):
        return value
    text = value.strip()
    if "::" in text:
        return text.split("::", 1)[1]
    return text


def _normalize_body_instance(value):
    if not isinstance(value, dict):
        return value

    result = dict(value)
    defaults = {
        "sleepFamily": "Normal",
        "dOFMode": "Default",
        "bUseCCD": False,
        "bIgnoreAnalyticCollisions": False,
        "bNotifyRigidBodyCollision": False,
        "bLockTranslation": False,
        "bLockRotation": False,
        "bLockXTranslation": False,
        "bLockYTranslation": False,
        "bLockZTranslation": False,
        "bLockXRotation": False,
        "bLockYRotation": False,
        "bLockZRotation": False,
        "bOverrideMaxAngularVelocity": False,
        "bOverrideMaxDepenetrationVelocity": False,
        "bOverrideWalkableSlopeOnInstance": False,
        "bInterpolateWhenSubStepping": False,
        "positionSolverIterationCount": 8,
        "velocitySolverIterationCount": 1,
        "maxDepenetrationVelocity": 0,
        "massInKgOverride": 0,
        "linearDamping": 0,
        "angularDamping": 0,
        "massScale": 1,
        "physicsBlendWeight": 0,
        "bSimulatePhysics": False,
        "bOverrideMass": False,
        "bEnableGravity": True,
        "bAutoWeld": True,
        "bStartAwake": True,
        "bGenerateWakeEvents": False,
        "bUpdateMassWhenScaleChanges": False,
    }

    for key, default in defaults.items():
        result.setdefault(key, default)

    if "collisionEnabled" not in result:
        result["collisionEnabled"] = _default_collision_enabled(
            result.get("collisionProfileName", "")
        )

    if "collisionEnabled" in result:
        result["collisionEnabled"] = _normalize_enum_value(result["collisionEnabled"])

    result.setdefault(
        "walkableSlopeOverride",
        {
            "walkableSlopeBehavior": "WalkableSlope_Default",
            "walkableSlopeAngle": 0,
        },
    )
    result.setdefault("customDOFPlaneNormal", {"x": 0, "y": 0, "z": 0})
    result.setdefault("cOMNudge", {"x": 0, "y": 0, "z": 0})
    result.setdefault("inertiaTensorScale", {"x": 1, "y": 1, "z": 1})

    collision = result.get("collisionResponses")
    if not _is_valid_collision_responses(collision):
        result["collisionResponses"] = _default_collision_responses(
            result.get("collisionProfileName", "")
        )

    return result


def _default_collision_enabled(profile_name):
    if profile_name in {"NoCollision", "ForAttackOverlap"}:
        return "NoCollision"
    if profile_name in {"ForBody"}:
        return "QueryAndPhysics"
    if profile_name in {"ForDamageOverlap", "ForMeshOverlap"}:
        return "QueryOnly"
    return "QueryOnly"


def _is_valid_collision_responses(value):
    if not isinstance(value, dict):
        return False
    response_array = value.get("responseArray")
    if not isinstance(response_array, list) or not response_array:
        return False
    first = response_array[0]
    return isinstance(first, dict) and "channel" in first and "response" in first


def _default_collision_responses(profile_name):
    if profile_name == "ForAttackOverlap":
        return {
            "responseArray": [
                {"channel": "Pawn", "response": "ECR_Ignore"},
                {"channel": "Visibility", "response": "ECR_Ignore"},
                {"channel": "Camera", "response": "ECR_Ignore"},
                {"channel": "PhysicsBody", "response": "ECR_Ignore"},
                {"channel": "Vehicle", "response": "ECR_Ignore"},
                {"channel": "Destructible", "response": "ECR_Ignore"},
                {"channel": "SightMesh", "response": "ECR_Overlap"},
                {"channel": "BlockVolume", "response": "ECR_Block"},
            ]
        }
    return {"responseArray": []}


def _resolve_object_ref(index, import_map, export_map):
    if index is None:
        return "None"
    if index == 0:
        return "None"
    if index > 0:
        exp = export_map.resolve_index(index)
        if exp:
            return str(exp.ObjectName)
        return f"<export:{index}>"

    imp = import_map.resolve_index(index)
    if not imp:
        return f"<import:{index}>"

    package_name = str(imp.PackageName) if imp.PackageName else ""
    object_name = str(imp.ObjectName)
    class_name = str(imp.ClassName)
    if package_name and package_name != "None":
        if object_name and not package_name.endswith(object_name):
            path = f"{package_name}.{object_name}"
        else:
            path = package_name
    else:
        path = object_name

    if class_name and class_name not in {"None", "Package"}:
        return f"{class_name}'{path}'"
    return path
