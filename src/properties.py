import re


class PropertyParseOptions:
    def __init__(self, include_raw=True, raw_limit=64):
        self.include_raw = include_raw
        self.raw_limit = raw_limit


def normalize_path_string(value, field_name=""):
    if not isinstance(value, str):
        return value

    text = value.strip()
    if not text or text in {"None", "null"}:
        return value

    wrapper = re.match(r"^([A-Za-z0-9_]+)\'(.+)\'$", text)
    if wrapper:
        prefix = wrapper.group(1)
        inner = wrapper.group(2)
        normalized_inner = normalize_path_string(inner, field_name)
        if normalized_inner != inner:
            return f"{prefix}'{normalized_inner}'"
        return value

    if not _looks_path_like(text, field_name):
        return value

    normalized = text.replace("\\", "/")
    lower = normalized.lower()

    if lower.startswith("content/"):
        rel = normalized[len("Content/"):].lstrip("/")
        if rel:
            return f"/Game/{rel}"

    plugin_idx = lower.rfind("/plugins/")
    if plugin_idx != -1:
        content_idx = lower.find("/content/", plugin_idx)
        if content_idx != -1:
            plugin_root = normalized[plugin_idx + len("/plugins/"):content_idx]
            plugin_name = plugin_root.split("/", 1)[0]
            rel = normalized[content_idx + len("/content/"):].lstrip("/")
            if rel:
                return f"/{plugin_name}/{rel}"

    content_idx = lower.rfind("/content/")
    if content_idx != -1:
        rel = normalized[content_idx + len("/content/"):].lstrip("/")
        if rel:
            return f"/Game/{rel}"

    if normalized.startswith("./"):
        return normalized[2:]

    return normalized


def _looks_path_like(text, field_name=""):
    lower_text = text.lower()
    lower_name = (field_name or "").lower()

    if lower_text.startswith(("/game/", "/engine/", "/script/")):
        return False

    if re.match(r"^[a-z]:[\\/]", text) or text.startswith("\\\\"):
        return True

    if "/content/" in lower_text or "\\content\\" in lower_text:
        return True

    if lower_text.startswith("content/") or lower_text.startswith("content\\"):
        return True

    if lower_text.startswith("./") or lower_text.startswith("../"):
        return True

    if lower_text.endswith((".lua", ".uasset", ".umap")):
        return True

    if any(key in lower_name for key in ("path", "file", "lua", "script")):
        return any(sep in text for sep in ("/", "\\")) or lower_text.endswith((
            ".lua", ".uasset", ".umap"
        ))

    return False


class FPropertyTag:
    def __init__(self, reader):
        key_fname = reader.readFName()
        self.Name = str(key_fname)
        if self.Name == "None":
            self.Type = "None"
            self.Size = 0
            self.ArrayIndex = 0
            return
        type_fname = reader.readFName()
        self.Type = str(type_fname)
        self.Size = reader.readInt32()
        self.ArrayIndex = reader.readInt32()
        self.StructName = None
        self.StructGuid = None
        self.BoolValue = None
        self.EnumName = None
        self.InnerType = None
        self.ValueType = None
        self.HasPropertyGuid = False
        self.PropertyGuid = None

        if self.Type == "StructProperty":
            self.StructName = str(reader.readFName())
            self.StructGuid = reader.readGuid().hex()
        elif self.Type == "BoolProperty":
            self.BoolValue = reader.readBool()
        elif self.Type in ("ByteProperty", "EnumProperty"):
            self.EnumName = str(reader.readFName())
        elif self.Type in ("ArrayProperty", "SetProperty"):
            self.InnerType = str(reader.readFName())
        elif self.Type == "MapProperty":
            self.InnerType = str(reader.readFName())
            self.ValueType = str(reader.readFName())

        self.HasPropertyGuid = reader.readBool()
        if self.HasPropertyGuid:
            self.PropertyGuid = reader.readGuid().hex()
        self._reader = reader

    def is_none(self):
        return self.Name == "None"

    def read_value(self, reader, export_offset, export_end, options):
        return read_tagged_value(reader, self, export_offset, export_end, options)


def read_tagged_value(reader, tag, export_offset, export_end, options):
    t = tag.Type
    size = tag.Size

    if t == "BoolProperty":
        return tag.BoolValue

    elif t == "IntProperty":
        return reader.readInt32()

    elif t == "Int64Property":
        return reader.readInt64()

    elif t == "FloatProperty":
        return reader.readFloat()

    elif t == "StrProperty":
        return normalize_path_string(reader.readFString(), tag.Name)

    elif t == "NameProperty":
        return str(reader.readFName())

    elif t == "TextProperty":
        return read_text_property(reader, tag, export_end, options)

    elif t == "ByteProperty":
        return read_byte_property(reader, tag)

    elif t == "EnumProperty":
        return str(reader.readFName())

    elif t == "ObjectProperty":
        idx = reader.readFPackageIndex()
        return {"type": "ObjectRef", "index": idx}

    elif t == "SoftObjectProperty":
        return reader.readFSoftObjectPath()

    elif t == "StructProperty":
        return read_struct_property(
            reader,
            export_offset,
            export_end,
            options,
            tag.StructName,
        )

    elif t == "ArrayProperty":
        return read_array_property(reader, export_end, options, tag.InnerType)

    elif t == "MapProperty":
        return read_map_property(
            reader,
            export_end,
            options,
            tag.InnerType,
            tag.ValueType,
        )

    elif t == "SetProperty":
        return read_set_property(reader, export_end, options, tag.InnerType)

    else:
        result = {
            "unsupported": True,
            "type": t,
            "size": size,
        }
        result.update(read_raw_blob(reader, size, export_end, options))
        return result


def read_raw_blob(reader, size, export_end, options):
    available = max(0, min(size, export_end - reader.tell()))
    raw = reader.readBytes(available)
    result = {"rawSize": size}
    if available < size:
        result["rawReadSize"] = available
        result["rawDataTruncated"] = True
    if not options.include_raw:
        return result
    if options.raw_limit is not None and len(raw) > options.raw_limit:
        result["rawData"] = raw[:options.raw_limit].hex()
        result["rawDataTruncated"] = True
    else:
        result["rawData"] = raw.hex()
    return result


def read_text_property(reader, tag, export_end, options):
    start = reader.tell()
    raw = reader.readBytes(max(0, min(tag.Size, export_end - start)))
    result = {"textType": "Raw", "size": tag.Size}
    try:
        text = raw.decode("utf-16-le", errors="ignore").replace("\x00", "")
        text = "".join(ch for ch in text if ch.isprintable()).strip()
        if text:
            result["value"] = normalize_path_string(text, tag.Name)
    except Exception:
        pass
    if options.include_raw:
        if options.raw_limit is not None and len(raw) > options.raw_limit:
            result["rawData"] = raw[:options.raw_limit].hex()
            result["rawDataTruncated"] = True
        else:
            result["rawData"] = raw.hex()
    return result


def read_byte_property(reader, tag=None):
    enum_type = tag.EnumName if tag else str(reader.readFName())
    if enum_type and enum_type != "None":
        enum_value = reader.readFName()
        return {"enumType": enum_type, "value": str(enum_value)}
    else:
        return reader.readByte()


def read_struct_property(reader, export_offset, export_end, options,
                         struct_type=None):
    if struct_type is None:
        struct_type = str(reader.readFName())
    result = {"structType": struct_type}
    if struct_type == "Guid":
        raw = reader.readBytes(16)
        result["value"] = raw.hex()
        return result
    if struct_type == "Vector":
        result["X"] = reader.readFloat()
        result["Y"] = reader.readFloat()
        result["Z"] = reader.readFloat()
        return result
    if struct_type == "Rotator":
        result["Roll"] = reader.readFloat()
        result["Pitch"] = reader.readFloat()
        result["Yaw"] = reader.readFloat()
        return result
    if struct_type == "Vector2D":
        result["X"] = reader.readFloat()
        result["Y"] = reader.readFloat()
        return result
    if struct_type == "LinearColor":
        result["R"] = reader.readFloat()
        result["G"] = reader.readFloat()
        result["B"] = reader.readFloat()
        result["A"] = reader.readFloat()
        return result
    if struct_type == "Color":
        result["R"] = reader.readByte()
        result["G"] = reader.readByte()
        result["B"] = reader.readByte()
        result["A"] = reader.readByte()
        return result
    if struct_type == "Transform":
        result["rotation"] = {
            "X": reader.readFloat(),
            "Y": reader.readFloat(),
            "Z": reader.readFloat(),
            "W": reader.readFloat(),
        }
        result["translation"] = {
            "X": reader.readFloat(),
            "Y": reader.readFloat(),
            "Z": reader.readFloat(),
        }
        result["scale3D"] = {
            "X": reader.readFloat(),
            "Y": reader.readFloat(),
            "Z": reader.readFloat(),
        }
        return result
    if struct_type == "Box":
        result["Min"] = read_struct_property(reader, export_offset, export_end, options)
        result["Max"] = read_struct_property(reader, export_offset, export_end, options)
        result["IsValid"] = reader.readByte()
        return result
    if struct_type == "SoftObjectPath":
        result["assetPath"] = normalize_path_string(str(reader.readFName()), struct_type)
        result["subPath"] = reader.readFString()
        return result
    try:
        inner, warnings = _read_nested_tags(reader, export_offset, export_end, options)
        result["fields"] = inner
    except Exception:
        result["unsupported"] = True
    return result


def _read_nested_tags(reader, export_offset, export_end, options):
    fields = {}
    warnings = []
    while reader.tell() + 8 <= export_end:
        try:
            tag = FPropertyTag(reader)
        except Exception as e:
            warnings.append({
                "tag": "<header>",
                "type": "<unknown>",
                "error": f"failed to read property tag header: {e}",
            })
            reader.seek(export_end)
            break
        if tag.is_none():
            break
        payload_start = reader.tell()
        payload_end = payload_start + max(0, tag.Size)
        if payload_end > export_end:
            fields[tag.Name] = {
                "type": tag.Type,
                "arrayIndex": tag.ArrayIndex,
                "unsupported": True,
                "error": "property payload exceeds export bounds",
            }
            warnings.append({
                "tag": tag.Name,
                "type": tag.Type,
                "error": "property payload exceeds export bounds",
            })
            reader.seek(export_end)
            break
        try:
            fields[tag.Name] = {
                "type": tag.Type,
                "arrayIndex": tag.ArrayIndex,
                "value": tag.read_value(reader, export_offset, export_end, options),
            }
            if tag.StructName:
                fields[tag.Name]["structType"] = tag.StructName
            if tag.EnumName:
                fields[tag.Name]["enumType"] = tag.EnumName
            if tag.InnerType:
                fields[tag.Name]["innerType"] = tag.InnerType
            if tag.ValueType:
                fields[tag.Name]["valueType"] = tag.ValueType
            if tag.PropertyGuid:
                fields[tag.Name]["propertyGuid"] = tag.PropertyGuid
            if reader.tell() < payload_end:
                reader.seek(payload_end)
        except Exception as e:
            fields[tag.Name] = {
                "type": tag.Type,
                "unsupported": True,
                "error": str(e),
            }
            warnings.append({
                "tag": tag.Name,
                "type": tag.Type,
                "error": str(e),
            })
            reader.seek(min(export_end, payload_end))
    return fields, warnings


def read_array_property(reader, export_end, options, element_type=None):
    element_type = element_type or str(reader.readFName())
    count = reader.readInt32()
    items = []
    for _ in range(count):
        dummy_tag = FPropertyTag.__new__(FPropertyTag)
        dummy_tag.Name = f"_elem"
        dummy_tag.Type = str(element_type)
        dummy_tag.Size = 0
        dummy_tag.ArrayIndex = 0
        dummy_tag.StructName = None
        dummy_tag.BoolValue = None
        dummy_tag.EnumName = None
        dummy_tag.InnerType = None
        dummy_tag.ValueType = None
        items.append(dummy_tag.read_value(reader, 0, export_end, options))
    return {
        "elementType": str(element_type),
        "count": count,
        "items": items,
    }


def read_map_property(reader, export_end, options, key_type=None, value_type=None):
    key_type = key_type or str(reader.readFName())
    value_type = value_type or str(reader.readFName())
    count = reader.readInt32()
    entries = []
    for _ in range(count):
        key_tag = FPropertyTag.__new__(FPropertyTag)
        key_tag.Name = "key"
        key_tag.Type = str(key_type)
        key_tag.Size = 0
        key_tag.ArrayIndex = 0
        key_tag.StructName = None
        key_tag.BoolValue = None
        key_tag.EnumName = None
        key_tag.InnerType = None
        key_tag.ValueType = None
        val_tag = FPropertyTag.__new__(FPropertyTag)
        val_tag.Name = "value"
        val_tag.Type = str(value_type)
        val_tag.Size = 0
        val_tag.ArrayIndex = 0
        val_tag.StructName = None
        val_tag.BoolValue = None
        val_tag.EnumName = None
        val_tag.InnerType = None
        val_tag.ValueType = None
        key = key_tag.read_value(reader, 0, export_end, options)
        value = val_tag.read_value(reader, 0, export_end, options)
        entries.append({"key": key, "value": value})
    return {
        "keyType": str(key_type),
        "valueType": str(value_type),
        "count": count,
        "entries": entries,
    }


def read_set_property(reader, export_end, options, element_type=None):
    element_type = element_type or str(reader.readFName())
    count = reader.readInt32()
    items = []
    for _ in range(count):
        dummy_tag = FPropertyTag.__new__(FPropertyTag)
        dummy_tag.Name = "_elem"
        dummy_tag.Type = str(element_type)
        dummy_tag.Size = 0
        dummy_tag.ArrayIndex = 0
        dummy_tag.StructName = None
        dummy_tag.BoolValue = None
        dummy_tag.EnumName = None
        dummy_tag.InnerType = None
        dummy_tag.ValueType = None
        items.append(dummy_tag.read_value(reader, 0, export_end, options))
    return {
        "elementType": str(element_type),
        "count": count,
        "items": items,
    }


def parse_export_properties(reader, export_entry, export_index, options=None):
    options = options or PropertyParseOptions()
    offset = export_entry.SerialOffset
    size = export_entry.SerialSize
    if size <= 0 or offset <= 0:
        return {"properties": {}, "warnings": []}
    try:
        reader.seek(offset)
        fields, warnings = _read_nested_tags(reader, offset, offset + size, options)
        return {"properties": fields, "warnings": warnings}
    except Exception as e:
        w = [{"exportIndex": export_index, "level": "corrupt", "message": str(e)}]
        return {"properties": {}, "warnings": w}
