from ue_version import UE4Versions


class FObjectImport:
    def __init__(self, f):
        self.ClassPackage = f.readFName()
        self.ClassName = f.readFName()
        self.OuterIndex = f.readInt32()
        self.ObjectName = f.readFName()
        if (f.summary.FileVersionUE4 >=
                UE4Versions.VER_UE4_NON_OUTER_PACKAGE_IMPORT):
            self.PackageName = f.readFName()
        else:
            self.PackageName = ""

    def to_dict(self):
        return {
            "classPackage": str(self.ClassPackage),
            "className": str(self.ClassName),
            "outerIndex": self.OuterIndex,
            "objectName": str(self.ObjectName),
            "packageName": str(self.PackageName) if self.PackageName else "",
        }


class FImportMap:
    def __init__(self, f):
        f.seek(f.summary.ImportOffset)
        self.imports = []
        for _ in range(f.summary.ImportCount):
            self.imports.append(FObjectImport(f))

    def __len__(self):
        return len(self.imports)

    def __getitem__(self, idx):
        return self.imports[idx]

    def to_list(self):
        return [imp.to_dict() for imp in self.imports]

    def resolve_index(self, package_idx):
        """Resolve a negative FPackageIndex to an import entry.
        Positive = export index (1-based), 0 = None,
        Negative = import index (1-based, negated).
        """
        if package_idx >= 0:
            return None
        idx = -package_idx - 1
        if 0 <= idx < len(self.imports):
            return self.imports[idx]
        return None
