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

        result[name] = entry

    return result


def _build_scs_info(all_nodes, export_nodes):
    result = {}
    for node in all_nodes:
        if _class_name(node) != "SCS_Node":
            continue
        props = node.get("properties", {})
        template_idx = _object_ref_index(props.get("ComponentTemplate"))
        if not template_idx or template_idx <= 0:
            continue

        info = {}
        internal_name = _property_value(props.get("InternalVariableName"))
        if internal_name:
            info["name"] = internal_name

        parent_name = _property_value(props.get("ParentComponentOrVariableName"))
        if parent_name:
            info["parent"] = parent_name

        result[template_idx - 1] = info
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


def _object_ref_index(prop):
    if not isinstance(prop, dict):
        return None
    value = prop.get("value", {})
    if not isinstance(value, dict):
        return None
    return value.get("index")


def _property_value(prop):
    if not isinstance(prop, dict):
        return None
    return prop.get("value")


def _convert_properties(properties, import_map, export_map):
    result = {}
    for name, prop in properties.items():
        if name == "AttachParent":
            continue
        if not isinstance(prop, dict):
            continue
        if prop.get("unsupported"):
            continue

        converted = _convert_property(prop, import_map, export_map)
        if converted is not None and not _contains_parse_garbage(converted):
            result[name] = converted
    return result


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
            "Value": value.get("value"),
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
