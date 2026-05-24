class UAssetError(Exception):
    pass


class MagicMismatchError(UAssetError):
    def __init__(self, found_tag):
        self.found_tag = found_tag
        super().__init__(
            "invalid .uasset file: magic tag mismatch "
            f"(expected 0x9E2A83C1, found 0x{found_tag:08X})"
        )


class UnsupportedVersionError(UAssetError):
    def __init__(self, ver_ue4, ver_ue5):
        self.ver_ue4 = ver_ue4
        self.ver_ue5 = ver_ue5
        super().__init__(
            f"unsupported package version: UE4={ver_ue4}, UE5={ver_ue5}"
        )


class FileNotFoundError2(UAssetError):
    def __init__(self, path):
        self.path = path
        super().__init__(f"file not found: {path}")


class ParseError(UAssetError):
    def __init__(self, message):
        super().__init__(message)


class ExportParseWarning:
    def __init__(self, export_index, export_name, level, message):
        self.export_index = export_index
        self.export_name = export_name
        self.level = level
        self.message = message

    def to_dict(self):
        return {
            "exportIndex": self.export_index,
            "exportName": self.export_name,
            "level": self.level,
            "message": self.message,
        }
