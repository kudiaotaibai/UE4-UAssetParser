import struct
import io
from errors import MagicMismatchError, UnsupportedVersionError

MAGIC_TAG = 0x9E2A83C1


class Archive:
    def __init__(self, data, filename=""):
        self.data = data
        self.stream = io.BytesIO(data)
        self.size = len(data)
        self.filename = filename
        self.summary = None
        self.name_map = None

    def tell(self):
        return self.stream.tell()

    def seek(self, pos):
        self.stream.seek(pos)

    def remaining(self):
        return self.size - self.tell()

    def read(self, n):
        return self.stream.read(n)

    def setSummary(self, summary):
        self.summary = summary

    def setNameMap(self, name_map):
        self.name_map = name_map

    def readByte(self):
        return struct.unpack("<B", self.stream.read(1))[0]

    def readBool(self):
        return self.readByte() != 0

    def readArchiveBool(self):
        return self.readUInt32() != 0

    def readUInt16(self):
        return struct.unpack("<H", self.stream.read(2))[0]

    def readInt32(self):
        return struct.unpack("<i", self.stream.read(4))[0]

    def readUInt32(self):
        return struct.unpack("<I", self.stream.read(4))[0]

    def readInt64(self):
        return struct.unpack("<q", self.stream.read(8))[0]

    def readUInt64(self):
        return struct.unpack("<Q", self.stream.read(8))[0]

    def readFloat(self):
        return struct.unpack("<f", self.stream.read(4))[0]

    def readDouble(self):
        return struct.unpack("<d", self.stream.read(8))[0]

    def readGuid(self):
        return self.stream.read(16)

    def readBytes(self, n):
        return self.stream.read(n)

    def readFString(self):
        length = self.readInt32()
        if length == 0:
            return ""
        if length < 0:
            text = self.stream.read(-length * 2)
            return text.decode("utf-16-le", errors="replace").rstrip("\x00")
        else:
            text = self.stream.read(length)
            return text.decode("ascii", errors="replace").rstrip("\x00")

    def readTArray(self, element_reader):
        count = self.readInt32()
        result = []
        for _ in range(count):
            result.append(element_reader())
        return result

    def readFName(self):
        index = self.readInt32()
        number = self.readInt32()
        if self.name_map is None:
            return f"<index={index}, number={number}>"
        if index < 0 or index >= len(self.name_map):
            return "None"
        base_name = self.name_map[index]
        if number == 0:
            return base_name
        return f"{base_name}_{number - 1}"

    def readFPackageIndex(self):
        return self.readInt32()

    def readFSoftObjectPath(self):
        asset_path = self.readFName()
        sub_path = self.readFString()
        return {"assetPath": asset_path, "subPath": sub_path}


def create_archive(filepath):
    with open(filepath, "rb") as f:
        data = f.read()
    return Archive(data, filepath)


def create_archive_with_uexp(filepath):
    data = bytearray()
    with open(filepath, "rb") as f:
        data.extend(f.read())

    uexp_path = filepath.replace(".uasset", ".uexp")
    try:
        with open(uexp_path, "rb") as f:
            data.extend(f.read())
    except FileNotFoundError:
        pass

    return Archive(bytes(data), filepath)
