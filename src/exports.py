from ue_version import UE4Versions
from package import FGuid


class FObjectExport:
    def __init__(self, f):
        self.ClassIndex = f.readInt32()
        self.SuperIndex = f.readInt32()

        if (f.summary.FileVersionUE4 >=
                UE4Versions.VER_UE4_TemplateIndex_IN_COOKED_EXPORTS):
            self.TemplateIndex = f.readInt32()
        else:
            self.TemplateIndex = 0

        self.OuterIndex = f.readInt32()
        self.ObjectName = f.readFName()
        self.ObjectFlags = f.readUInt32()

        if (f.summary.FileVersionUE4 <
                UE4Versions.VER_UE4_64BIT_EXPORTMAP_SERIALSIZES):
            self.SerialSize = f.readInt32()
            self.SerialOffset = f.readInt32()
        else:
            self.SerialSize = f.readInt64()
            self.SerialOffset = f.readInt64()

        self.bForcedExport = f.readArchiveBool()
        self.bNotForClient = f.readArchiveBool()
        self.bNotForServer = f.readArchiveBool()

        self.PackageGuid = FGuid(f)
        self.PackageFlags = f.readUInt32()

        if (f.summary.FileVersionUE4 >=
                UE4Versions.VER_UE4_LOAD_FOR_EDITOR_GAME):
            self.bNotAlwaysLoadedForEditorGame = f.readArchiveBool()
        else:
            self.bNotAlwaysLoadedForEditorGame = False

        if (f.summary.FileVersionUE4 >=
                UE4Versions.VER_UE4_COOKED_ASSETS_IN_EDITOR_SUPPORT):
            self.bIsAsset = f.readArchiveBool()
        else:
            self.bIsAsset = False

        if (f.summary.FileVersionUE4 >=
                UE4Versions.VER_UE4_PRELOAD_DEPENDENCIES_IN_COOKED_EXPORTS):
            self.FirstExportDependency = f.readInt32()
            self.SerializationBeforeSerializationDependencies = f.readInt32()
            self.CreateBeforeSerializationDependencies = f.readInt32()
            self.SerializationBeforeCreateDependencies = f.readInt32()
            self.CreateBeforeCreateDependencies = f.readInt32()

    def to_dict(self):
        return {
            "objectName": str(self.ObjectName),
            "classIndex": self.ClassIndex,
            "superIndex": self.SuperIndex,
            "templateIndex": self.TemplateIndex,
            "outerIndex": self.OuterIndex,
            "objectFlags": self.ObjectFlags,
            "serialSize": self.SerialSize,
            "serialOffset": self.SerialOffset,
            "bForcedExport": self.bForcedExport,
            "bNotForClient": self.bNotForClient,
            "bNotForServer": self.bNotForServer,
            "packageFlags": self.PackageFlags,
            "bIsAsset": self.bIsAsset,
        }


class FExportMap:
    def __init__(self, f):
        f.seek(f.summary.ExportOffset)
        self.exports = []
        for _ in range(f.summary.ExportCount):
            self.exports.append(FObjectExport(f))

    def __len__(self):
        return len(self.exports)

    def __getitem__(self, idx):
        return self.exports[idx]

    def to_list(self):
        return [exp.to_dict() for exp in self.exports]

    def resolve_index(self, package_idx):
        """Resolve a positive FPackageIndex to an export entry."""
        if package_idx <= 0:
            return None
        idx = package_idx - 1
        if 0 <= idx < len(self.exports):
            return self.exports[idx]
        return None
