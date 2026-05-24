class FNameEntry:
    def __init__(self, f):
        self.Name = f.readFString()
        self.NonCasePreservingHash = f.readUInt16()
        self.CasePreservingHash = f.readUInt16()

    def __repr__(self):
        return f"FName('{self.Name}')"

    def __str__(self):
        return self.Name


class FNameMap:
    def __init__(self, f):
        f.seek(f.summary.NameOffset)
        self.names = []
        for _ in range(f.summary.NameCount):
            self.names.append(FNameEntry(f))
        f.setNameMap(self.names)

    def __getitem__(self, idx):
        return self.names[idx]

    def __len__(self):
        return len(self.names)

    def to_list(self):
        return [entry.Name for entry in self.names]
