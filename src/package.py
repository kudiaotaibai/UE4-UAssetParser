import struct
from uuid import UUID
from reader import MAGIC_TAG
from errors import MagicMismatchError
from ue_version import UE4Versions, UE5Versions


class FGuid:
    def __init__(self, f):
        self.A, self.B, self.C, self.D = struct.unpack("<IIII", f.read(16))

    def to_hex(self):
        return (f"{self.A:08X}{self.B:08X}{self.C:08X}"
                f"{self.D:08X}")

    def to_uuid(self):
        return UUID(self.to_hex())


class FEngineVersion:
    def __init__(self, f):
        self.Major = f.readUInt16()
        self.Minor = f.readUInt16()
        self.Patch = f.readUInt16()
        self.Changelist = f.readUInt32()
        self.Branch = f.readFString()

    def __str__(self):
        return (f"{self.Major}.{self.Minor}.{self.Patch} "
                f"cl={self.Changelist} branch={self.Branch}")


class FCustomVersion:
    def __init__(self, f):
        self.Key = FGuid(f)
        self.Version = f.readInt32()


class FGenerationInfo:
    def __init__(self, f):
        self.ExportCount = f.readInt32()
        self.NameCount = f.readInt32()


class FCompressedChunk:
    def __init__(self, f):
        self.UncompressedOffset = f.readInt64()
        self.UncompressedSize = f.readInt64()
        self.CompressedOffset = f.readInt64()
        self.CompressedSize = f.readInt64()


class FPackageFileSummary:
    def __init__(self, f):
        self.Tag = f.readUInt32()
        if self.Tag != MAGIC_TAG:
            raise MagicMismatchError(self.Tag)

        self.LegacyFileVersion = f.readInt32()

        if self.LegacyFileVersion != -4:
            self.LegacyUE3Version = f.readInt32()

        self.FileVersionUE4 = f.readInt32()

        if self.LegacyFileVersion <= -8:
            self.FileVersionUE5 = f.readInt32()
        else:
            self.FileVersionUE5 = 0

        self.FileVersionLicenseeUE4 = f.readInt32()

        if self.LegacyFileVersion <= -2:
            self.CustomVersions = self._read_custom_versions(f)

        self.bUnversioned = (
            not self.FileVersionUE4
            and not self.FileVersionUE5
            and not self.FileVersionLicenseeUE4
        )

        self.TotalHeaderSize = f.readInt32()
        self.PackageName = f.readFString()
        self.PackageFlags = f.readUInt32()

        self.NameCount = f.readInt32()
        self.NameOffset = f.readInt32()

        if self.FileVersionUE5 >= UE5Versions.ADD_SOFTOBJECTPATH_LIST:
            self.SoftObjectPathsCount = f.readInt32()
            self.SoftObjectPathsOffset = f.readInt32()
        else:
            self.SoftObjectPathsCount = 0
            self.SoftObjectPathsOffset = 0

        if self.FileVersionUE4 >= UE4Versions.VER_UE4_ADDED_PACKAGE_SUMMARY_LOCALIZATION_ID:
            self.LocalizationId = f.readFString()
        else:
            self.LocalizationId = ""

        self.GatherableTextDataCount = 0
        self.GatherableTextDataOffset = 0
        if self.FileVersionUE4 >= UE4Versions.VER_UE4_SERIALIZE_TEXT_IN_PACKAGES:
            self.GatherableTextDataCount = f.readInt32()
            self.GatherableTextDataOffset = f.readInt32()

        self.ExportCount = f.readInt32()
        self.ExportOffset = f.readInt32()
        self.ImportCount = f.readInt32()
        self.ImportOffset = f.readInt32()
        self.DependsOffset = f.readInt32()

        if self.FileVersionUE4 >= UE4Versions.VER_UE4_ADD_STRING_ASSET_REFERENCES_MAP:
            self.SoftPackageReferencesCount = f.readInt32()
            self.SoftPackageReferencesOffset = f.readInt32()

        if self.FileVersionUE4 >= UE4Versions.VER_UE4_ADDED_SEARCHABLE_NAMES:
            self.SearchableNamesOffset = f.readInt32()

        self.ThumbnailTableOffset = f.readInt32()
        self.Guid = FGuid(f)

        if self.FileVersionUE4 >= UE4Versions.VER_UE4_ADDED_PACKAGE_OWNER:
            self.PersistentGuid = FGuid(f)

        self.Generations = []
        self.GenerationCount = f.readInt32()
        if self.GenerationCount > 0:
            for _ in range(self.GenerationCount):
                self.Generations.append(FGenerationInfo(f))

        if self.FileVersionUE4 >= UE4Versions.VER_UE4_ENGINE_VERSION_OBJECT:
            self.SavedByEngineVersion = FEngineVersion(f)
            self.EngineChangelist = 0
        else:
            self.SavedByEngineVersion = None
            self.EngineChangelist = f.readInt32()

        if self.FileVersionUE4 >= UE4Versions.VER_UE4_PACKAGE_SUMMARY_HAS_COMPATIBLE_ENGINE_VERSION:
            self.CompatibleWithEngineVersion = FEngineVersion(f)
        else:
            self.CompatibleWithEngineVersion = None

        self.CompressionFlags = f.readUInt32()
        self.CompressedChunks = f.readTArray(FCompressedChunk)

        self.PackageSource = f.readUInt32()
        self.AdditionalPackagesToCook = f.readTArray(f.readFString)

        if self.LegacyFileVersion > -7:
            self.NumTextureAllocations = f.readInt32()
        else:
            self.NumTextureAllocations = 0

        self.AssetRegistryDataOffset = f.readInt32()
        self.BulkDataStartOffset = f.readInt64()

        if self.FileVersionUE4 >= UE4Versions.VER_UE4_WORLD_LEVEL_INFO:
            self.WorldTileInfoDataOffset = f.readInt32()
        else:
            self.WorldTileInfoDataOffset = 0

        if self.FileVersionUE4 >= UE4Versions.VER_UE4_CHANGED_CHUNKID_TO_BE_AN_ARRAY_OF_CHUNKIDS:
            self.ChunkIDs = f.readTArray(f.readInt32)
        else:
            self.ChunkIDs = []

        self.PreloadDependencyCount = f.readInt32()
        self.PreloadDependencyOffset = f.readInt32()

    def _read_custom_versions(self, f):
        if self.LegacyFileVersion == -2:
            return f.readTArray(lambda: _EnumCustomVersion_DEPRECATED(f))
        elif self.LegacyFileVersion >= -5 and self.LegacyFileVersion < -2:
            return f.readTArray(lambda: _GuidCustomVersion_DEPRECATED(f))
        else:
            return f.readTArray(lambda: FCustomVersion(f))

    def to_dict(self):
        d = {
            "Tag": f"0x{self.Tag:08X}",
            "LegacyFileVersion": self.LegacyFileVersion,
            "LegacyUE3Version": self.LegacyUE3Version,
            "FileVersionUE4": self.FileVersionUE4,
            "FileVersionUE5": self.FileVersionUE5,
            "FileVersionLicenseeUE4": self.FileVersionLicenseeUE4,
            "bUnversioned": self.bUnversioned,
            "TotalHeaderSize": self.TotalHeaderSize,
            "PackageName": self.PackageName,
            "PackageFlags": self.PackageFlags,
            "NameCount": self.NameCount,
            "NameOffset": self.NameOffset,
            "ExportCount": self.ExportCount,
            "ExportOffset": self.ExportOffset,
            "ImportCount": self.ImportCount,
            "ImportOffset": self.ImportOffset,
            "DependsOffset": self.DependsOffset,
            "Guid": self.Guid.to_hex(),
            "ThumbnailTableOffset": self.ThumbnailTableOffset,
            "GenerationCount": self.GenerationCount,
            "CompressionFlags": self.CompressionFlags,
            "AssetRegistryDataOffset": self.AssetRegistryDataOffset,
            "BulkDataStartOffset": self.BulkDataStartOffset,
            "PreloadDependencyCount": self.PreloadDependencyCount,
        }
        if self.SavedByEngineVersion:
            d["EngineVersion"] = str(self.SavedByEngineVersion)
        if self.CustomVersions:
            d["CustomVersionCount"] = len(self.CustomVersions)
        return d


class _EnumCustomVersion_DEPRECATED:
    def __init__(self, f):
        self.Tag = f.readUInt32()
        self.Version = f.readInt32()


class _GuidCustomVersion_DEPRECATED:
    def __init__(self, f):
        self.Key = FGuid(f)
        self.Version = f.readInt32()
        self.FriendlyName = f.readFString()
