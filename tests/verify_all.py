import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reader import create_archive
from package import FPackageFileSummary
from names import FNameMap
from imports import FImportMap
from exports import FExportMap

filepath = r"D:\vr\ZMKJBS\Content\Blueprints\Global\Module\Character\BP_Character.uasset"
ar = create_archive(filepath)

# Parse summary
summary = FPackageFileSummary(ar)
ar.setSummary(summary)
print(f"Tag: 0x{summary.Tag:08X}")
print(f"LegacyFileVersion: {summary.LegacyFileVersion}")
print(f"FileVersionUE4: {summary.FileVersionUE4}")
print(f"FileVersionLicenseeUE4: {summary.FileVersionLicenseeUE4}")
print(f"PackageName: {summary.PackageName}")
print(f"NameCount: {summary.NameCount}, NameOffset: {summary.NameOffset}")
print(f"ImportCount: {summary.ImportCount}, ImportOffset: {summary.ImportOffset}")
print(f"ExportCount: {summary.ExportCount}, ExportOffset: {summary.ExportOffset}")
print(f"bUnversioned: {summary.bUnversioned}")
print(f"TotalHeaderSize: {summary.TotalHeaderSize}")
if summary.SavedByEngineVersion:
    print(f"Engine: {summary.SavedByEngineVersion}")

# Parse name map
name_map = FNameMap(ar)
print(f"\nName map size: {len(name_map)}")
print("First 10 name entries:")
for i in range(min(10, len(name_map))):
    print(f"  [{i}] {name_map[i]}")

# Parse import map
import_map = FImportMap(ar)
print(f"\nImport map size: {len(import_map)}")
print("First 5 imports:")
for i in range(min(5, len(import_map))):
    imp = import_map[i]
    print(f"  [{i}] {imp.ObjectName} (class={imp.ClassName})")

# Parse export map
export_map = FExportMap(ar)
print(f"\nExport map size: {len(export_map)}")
print("First 5 exports:")
for i in range(min(5, len(export_map))):
    exp = export_map[i]
    print(f"  [{i}] {exp.ObjectName} serialSize={exp.SerialSize} serialOffset={exp.SerialOffset}")

print("\n=== VERIFIED: All tables parsed OK ===")

# Check expected values
assert summary.Tag == 0x9E2A83C1, "Tag mismatch"
assert summary.LegacyFileVersion == -7, "LegacyFileVersion mismatch"
assert summary.FileVersionUE4 == 517, "FileVersionUE4 mismatch"
assert len(name_map) == 709, f"NameCount mismatch: {len(name_map)} != 709"
assert len(import_map) == 198, f"ImportCount mismatch: {len(import_map)} != 198"
assert len(export_map) == 499, f"ExportCount mismatch: {len(export_map)} != 499"
print("All assertions passed!")
