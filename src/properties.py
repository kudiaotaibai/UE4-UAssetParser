class PropertyParseOptions:
    def __init__(self, include_raw=True, raw_limit=64):
        self.include_raw = include_raw
        self.raw_limit = raw_limit


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
        self._reader = reader

    def is_none(self):
        return self.Name == "None"

    def read_value(self, reader, export_offset, export_end, options):
        return read_tagged_value(reader, self, export_offset, export_end, options)


def read_tagged_value(reader, tag, export_offset, export_end, options):
    t = tag.Type
    size = tag.Size

    if t == "BoolProperty":
        return reader.readByte() != 0

    elif t == "IntProperty":
        return reader.readInt32()

    elif t == "Int64Property":
        return reader.readInt64()

    elif t == "FloatProperty":
        return reader.readFloat()

    elif t == "StrProperty":
        return reader.readFString()

    elif t == "NameProperty":
        return str(reader.readFName())

    elif t == "TextProperty":
        return read_text_property(reader)

    elif t == "ByteProperty":
        return read_byte_property(reader)

    elif t == "EnumProperty":
        return str(reader.readFName())

    elif t == "ObjectProperty":
        idx = reader.readFPackageIndex()
        return {"type": "ObjectRef", "index": idx}

    elif t == "SoftObjectProperty":
        return reader.readFSoftObjectPath()

    elif t == "StructProperty":
        return read_struct_property(reader, export_offset, export_end, options)

    elif t == "ArrayProperty":
        return read_array_property(reader, export_end, options)

    elif t == "MapProperty":
        return read_map_property(reader, export_end, options)

    elif t == "SetProperty":
        return read_set_property(reader, export_end, options)

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


def read_text_property(reader):
    flags = reader.readUInt32()
    if flags & 0x00000001:
        return {"textType": "Immutable", "value": reader.readFString()}
    result = {"textType": "Transient"}
    if flags & 0x00000002:
        result["textCultureInvariant"] = True
    if flags & 0x00000004:
        result["textIsCultureInvariant"] = False
    namespace = reader.readFString()
    key = reader.readFString()
    source = reader.readFString()
    result["namespace"] = namespace
    result["key"] = key
    result["source"] = source
    return result


def read_byte_property(reader):
    enum_type = reader.readFName()
    if str(enum_type) != "None":
        enum_value = reader.readFName()
        return {"enumType": str(enum_type), "value": str(enum_value)}
    else:
        return reader.readByte()


def read_struct_property(reader, export_offset, export_end, options):
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
        rot = read_struct_property(reader, export_offset, export_end, options)
        trans = read_struct_property(reader, export_offset, export_end, options)
        scale = read_struct_property(reader, export_offset, export_end, options)
        result["rotation"] = rot
        result["translation"] = trans
        result["scale3D"] = scale
        return result
    if struct_type == "Box":
        result["Min"] = read_struct_property(reader, export_offset, export_end, options)
        result["Max"] = read_struct_property(reader, export_offset, export_end, options)
        result["IsValid"] = reader.readByte()
        return result
    if struct_type == "SoftObjectPath":
        result["assetPath"] = str(reader.readFName())
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
        if tag.Size <= 0:
            reader.seek(export_end)
            break
        if reader.tell() + tag.Size > export_end:
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
            reader.seek(min(export_end, reader.tell() + max(0, tag.Size)))
    return fields, warnings


def read_array_property(reader, export_end, options):
    element_type = reader.readFName()
    count = reader.readInt32()
    items = []
    for _ in range(count):
        dummy_tag = FPropertyTag.__new__(FPropertyTag)
        dummy_tag.Name = f"_elem"
        dummy_tag.Type = str(element_type)
        dummy_tag.Size = 0
        dummy_tag.ArrayIndex = 0
        items.append(dummy_tag.read_value(reader, 0, export_end, options))
    return {
        "elementType": str(element_type),
        "count": count,
        "items": items,
    }


def read_map_property(reader, export_end, options):
    key_type = reader.readFName()
    value_type = reader.readFName()
    count = reader.readInt32()
    entries = []
    for _ in range(count):
        key_tag = FPropertyTag.__new__(FPropertyTag)
        key_tag.Name = "key"
        key_tag.Type = str(key_type)
        key_tag.Size = 0
        key_tag.ArrayIndex = 0
        val_tag = FPropertyTag.__new__(FPropertyTag)
        val_tag.Name = "value"
        val_tag.Type = str(value_type)
        val_tag.Size = 0
        val_tag.ArrayIndex = 0
        key = key_tag.read_value(reader, 0, export_end, options)
        value = val_tag.read_value(reader, 0, export_end, options)
        entries.append({"key": key, "value": value})
    return {
        "keyType": str(key_type),
        "valueType": str(value_type),
        "count": count,
        "entries": entries,
    }


def read_set_property(reader, export_end, options):
    element_type = reader.readFName()
    count = reader.readInt32()
    items = []
    for _ in range(count):
        dummy_tag = FPropertyTag.__new__(FPropertyTag)
        dummy_tag.Name = "_elem"
        dummy_tag.Type = str(element_type)
        dummy_tag.Size = 0
        dummy_tag.ArrayIndex = 0
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
