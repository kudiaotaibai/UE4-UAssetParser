import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from package import FPackageFileSummary
from reader import MAGIC_TAG, create_archive


filepath = r"D:\vr\ZMKJBS\Content\Blueprints\Global\Module\Character\BP_Character.uasset"
ar = create_archive(filepath)
summary = FPackageFileSummary(ar)

print(f"Tag: 0x{summary.Tag:08X} (expected: 0x{MAGIC_TAG:08X})")
print(f"LegacyFileVersion: {summary.LegacyFileVersion}")
print(f"LegacyUE3Version: {summary.LegacyUE3Version}")
print(f"FileVersionUE4: {summary.FileVersionUE4}")
print(f"FileVersionLicenseeUE4: {summary.FileVersionLicenseeUE4}")
print(f"CustomVersion count: {len(summary.CustomVersions)}")
print(f"TotalHeaderSize: {summary.TotalHeaderSize}")
print(f"PackageName: {summary.PackageName}")
print(f"PackageFlags: {summary.PackageFlags}")
print(f"NameCount: {summary.NameCount}, NameOffset: {summary.NameOffset}")
print(
    "GatherableTextData: "
    f"count={summary.GatherableTextDataCount}, "
    f"offset={summary.GatherableTextDataOffset}"
)
print(f"ExportCount: {summary.ExportCount}, ExportOffset: {summary.ExportOffset}")
print(f"ImportCount: {summary.ImportCount}, ImportOffset: {summary.ImportOffset}")

assert summary.Tag == MAGIC_TAG, "Tag mismatch"
assert summary.LegacyFileVersion == -7, "LegacyFileVersion mismatch"
assert summary.FileVersionUE4 == 517, "FileVersionUE4 mismatch"
assert summary.FileVersionLicenseeUE4 == 0, "Licensee version mismatch"
assert summary.TotalHeaderSize == 346026, "TotalHeaderSize mismatch"
assert summary.NameCount == 709, "NameCount mismatch"
assert summary.ImportCount == 198, "ImportCount mismatch"
assert summary.ExportCount == 499, "ExportCount mismatch"

print("=== Reader verified OK ===")
