# UAsset Parser 需求规格文档

## 1. 项目目标

开发一个命令行工具，解析 UE4.22 的 `.uasset` 文件（蓝图/UMG），导出为树状结构的 JSON 文档。

本工具面向笔试任务交付，重点是能独立运行、能读取指定 `.uasset`、能输出可读的资产结构 JSON。工具不以完整反编译蓝图逻辑图为目标，不依赖 UE4 Editor 或 UE4 引擎 DLL。

## 2. 功能需求

### 2.1 核心解析能力

MVP 必须支持：
- 解析 UE4.22 **FPackageFileSummary** 二进制头部
- 读取 Name Table（FName 表，字符串池）
- 读取 Import Table（导入对象引用）
- 读取 Export Table（导出对象定义）
- 根据 OuterIndex / ClassIndex / SuperIndex / TemplateIndex 建立对象引用关系
- 对 Export 序列化数据做 best-effort 属性解析；遇到未知属性类型时保留原始元信息并继续导出

增强目标：
- 识别常见 Blueprint 资产导出对象，例如 `Blueprint`、`BlueprintGeneratedClass`、`SimpleConstructionScript`、`SCS_Node`
- 识别常见 UMG 资产导出对象，例如 `WidgetBlueprint`、`WidgetTree`、`Widget` 节点
- 尽量还原组件树、Widget 树、变量定义和默认值

### 2.2 输出格式

导出 JSON 必须是树状层级结构：

```json
{
  "packageName": "/Game/Blueprints/Global/Module/Character/BP_Character",
  "engineVersion": "++UE4+Release-4.22",
  "packageGuid": "ED68B0E4-E942-94F4-0BDA-31A241BB462E",
  "packageFlags": 0,
  "nameTable": ["None", "BP_Character", "BP_Character_C", "..."],
  "importTable": [
    {
      "name": "Plane",
      "class": "StaticMesh",
      "outer": "/Engine/BasicShapes",
      "package": "/Engine/BasicShapes"
    }
  ],
  "exportTable": [
    {
      "name": "BP_Character_C",
      "class": "BlueprintGeneratedClass",
      "super": "CharacterBase_C",
      "outer": "/Game/.../BP_Character",
      "properties": {},
      "children": [...]
    }
  ]
}
```

### 2.3 输出粒度

MVP 输出必须包含：
- 包基础信息：文件路径、包名、版本、GUID、PackageFlags
- Name Table
- Import Table
- Export Table
- Export 对象之间的父子层级树
- 每个节点的名称、类、父对象、父类、模板对象、序列化大小和偏移
- 已成功解析的 UObject 属性；未知属性要在 JSON 中标记为 `unsupported` 或 `raw`

增强输出尽量包含：
- 蓝图内的组件层级（Actor Component Hierarchy）
- UMG 内的 Widget 节点树
- 变量定义（Blueprint Variables）及其类型、默认值

非目标：
- 不要求完整反编译蓝图事件图、函数图、节点连线和本地变量
- 不要求还原所有 UE4 私有序列化类型

### 2.4 CLI 接口

```bat
UAssetParser.exe <input.uasset> [options]

参数:
  <input>        必填，.uasset 文件路径
  -o, --output   可选，指定输出 JSON 路径（默认与输入同目录同名 .json）
  -v, --verbose  可选，输出详细解析日志

示例:
  UAssetParser.exe BP_Character.uasset
  UAssetParser.exe Content\Blueprints\Global\Module\Character\BP_Character.uasset -o output.json
  UAssetParser.exe BP_Character.uasset -v
```

### 2.5 批量模式

```bat
UAssetParser.exe <input_dir> --batch

示例:
  UAssetParser.exe Content\Blueprints\GameThree --batch
  # 遍历目录下所有 .uasset 文件，默认在各自文件同目录生成同名 .json
```

## 3. 技术规格

### 3.1 目标 UE 版本

UE4.22。不同工程保存的资产可能带有不同的 Licensee Version，不能写死为 0。

本项目样例 `Content\Blueprints\Global\Module\Character\BP_Character.uasset` 实测头部：
- Tag: `0x9E2A83C1`
- LegacyFileVersion: `-7`
- FileVersionUE4: `864`
- FileVersionLicenseeUE4: `517`

### 3.2 .uasset 文件格式（FPackageFileSummary）

UE4.22 的 `FPackageFileSummary` 字段顺序需要按 UE4.22 源码中的 `FPackageFileSummary::Serialize` 实现解析，不能用固定猜测偏移硬读全部字段。基础读取顺序如下：

| 顺序 | 字段 | 大小 | 说明 |
|------|------|------|------|
| 1 | Tag | 4 bytes | 魔数 `0x9E2A83C1` |
| 2 | LegacyFileVersion | 4 bytes | 常见为 `-7` |
| 3 | FileVersionUE4 | 4 bytes | UE4 文件版本 |
| 4 | FileVersionLicenseeUE4 | 4 bytes | 项目/授权方版本 |
| 5 | CustomVersionContainer | 可变 | 自定义版本列表 |
| 6 | TotalHeaderSize | 4 bytes | 头部总大小 |
| 7 | FolderName | FString | 包路径 |
| 8 | PackageFlags | 4 bytes | 包标志位 |
| 9 | NameCount / NameOffset | 8 bytes | Name Table 数量与偏移 |
| 10 | GatherableTextDataCount / Offset | 8 bytes | 文本采集数据 |
| 11 | ExportCount / ExportOffset | 8 bytes | 导出表 |
| 12 | ImportCount / ImportOffset | 8 bytes | 导入表 |
| 13 | DependsOffset 等后续字段 | 可变 | 依赖、缩略图、GUID、版本信息等 |

解析器应优先使用 Summary 中的 Count/Offset 跳转读取 Name/Import/Export，而不是依赖固定绝对偏移。

### 3.3 Import Table Entry

```c
FObjectImport {
    FName ClassPackage;    // 类所在包名
    FName ClassName;       // 类名
    FPackageIndex OuterIndex; // 外部对象索引
    FName ObjectName;      // 对象名
}
```

### 3.4 Export Table Entry

```c
FObjectExport {
    FPackageIndex ClassIndex;   // 类索引
    FPackageIndex SuperIndex;   // 父类索引
    FPackageIndex TemplateIndex; // 模板索引
    FPackageIndex OuterIndex;   // 外部对象索引
    FName ObjectName;           // 对象名
    uint32 ObjectFlags;         // 对象标志
    int64 SerialSize;           // 序列化数据大小
    int64 SerialOffset;         // 序列化数据偏移
    bool bForcedExport;         // 强制导出
    bool bNotForClient;         // 非客户端
    bool bNotForServer;         // 非服务器
    GUID PackageGuid;           // 包 GUID
    uint32 PackageFlags;        // 包标志
    bool bNotAlwaysLoadedForEditorGame; // 编辑器/游戏加载标志
    bool bIsAsset;              // 是否资产
    bool bFirstExportDependency;// 首次导出依赖
    bool bSerializationBeforeSerializationDependencies; // 序列化顺序标志
    bool bCreateBeforeSerializationDependencies;        // 创建顺序标志
    bool bSerializationBeforeCreateDependencies;         // 依赖序列化才创建标志
    bool bCreateBeforeCreateDependencies;                // 依赖创建才创建标志
}
```

以上结构只作为字段参考。实际实现必须按 UE4.22 `FObjectExport::Serialize` 的版本条件读取，避免因为版本差异造成字段错位。

### 3.5 UObject 属性序列化格式

导出对象之后是序列化的 UObject 属性数据。使用 FArchive 序列化格式：
- 属性由 `FPropertyTag` 标识（Name, Type, Size）
- 嵌套属性（Struct, Array, Map）递归序列化
- 组件嵌套通过 `FObjectProperty` 引用（`FPackageIndex`）

#### 3.5.1 属性类型枚举表

MVP 必须支持以下属性类型。解析顺序为先解析 Tag（Name + Type），再按类型读取值：

| 属性类型 | TypeName | 值格式 | 说明 |
|----------|----------|--------|------|
| BoolProperty | BoolProperty | 1 byte (0/1) | 布尔值 |
| IntProperty | IntProperty | 4 bytes (int32) | 整数 |
| Int64Property | Int64Property | 8 bytes (int64) | 长整数 |
| FloatProperty | FloatProperty | 4 bytes (float) | 浮点数 |
| StrProperty | StrProperty | FString | 字符串 |
| NameProperty | NameProperty | FName (index + number) | FName 引用 |
| TextProperty | TextProperty | FText (flags + namespace + key + value) | 本地化文本 |
| ByteProperty | ByteProperty | FName typeName + 1~8 bytes | 枚举或字节 |
| EnumProperty | EnumProperty | FName enumType + FName value | 枚举值 |
| ObjectProperty | ObjectProperty | FPackageIndex | 对象引用 |
| SoftObjectProperty | SoftObjectProperty | FSoftObjectPath | 软对象路径 |
| StructProperty | StructProperty | FName structType + 嵌套 Tag 序列 + None 终止 | 结构体（含 Vector, Rotator, Transform, Guid 等内建类型） |
| ArrayProperty | ArrayProperty | FName elementType + int32 count + 逐个元素 | 数组 |
| MapProperty | MapProperty | FName keyType + FName valueType + int32 count + 逐个 key-value 对 | 字典 |
| SetProperty | SetProperty | FName elementType + int32 count + 逐个元素 | 集合 |

**Tag 序列化格式**:
```
FPropertyTag {
    FName  TagName      // 属性名，None 表示终止
    FName  TagType      // 属性类型（上表 TypeName 列）
    int32  Size         // 数据大小
    int32  ArrayIndex   // 数组索引（0 = 非数组）
    // ... 之后是 Size 字节的属性值
}
```

**各项目属性解析覆盖率对比**:

| 能力 | UAssetAPI (C#) | uasset-rs (Rust) | uasset-reader-js | 本项目目标 |
|------|---------------|------------------|------------------|-----------|
| 属性 Tag 解析 | 100+ 类型 | 泛型 Parseable trait | 完整 | MVP 支持上表14种 |
| 嵌套 Struct | 递归 | 递归 | 递归 | 递归（遇到嵌套 Struct 创建子节点） |
| Array/Map/Set | 完整 | 完整 | 只读 | 完整解析 |
| FObjectProperty 组件引用 | 完整 | 有 | 有 | 解析为 `{ref: "ExportIndex_n"}` |
| 未知属性类型 | 跳过 Size 字节 | 跳过 | 跳过 | 读 Size，标记 `unsupported`，跳过 |

#### 3.5.2 FPropertyTag 类型解析与 usmap 依赖

UE4.22 中属性 Tag 的类型字段有两种编码方式：

**有版本号映射（Versioned / usmap）**: 属性的 `TagType` 存储的是类型名 FName（如 `StrProperty`, `IntProperty`），直接可读。这种情况常见于未 Cooked 的 Editor 资产。

**无版本号映射（Unversioned / Cooked）**: 属性的 `TagType` 存储的是类型 GUID（16 byte），**无法直接翻译为可读类型名**，必须依赖 `.usmap` 映射文件。UE4.22 项目如果资产经过 Cook，通常是此模式。

**策略**:
1. 优先尝试从 Tag 的 Name 字符串判定是否为类型名（命中上表 → 直接解析）
2. 如果 Name 不是已知类型字符串（是16字节 GUID），尝试加载同目录的 `.usmap` 文件反查类型
3. 无 usmap 时：输出中 `tagType` 字段输出为 `"<GUID:xxxx>"` 占位，继续解析 Size 和值（未知类型按 raw 处理）
4. 如果读 `BP_Character.uasset` 时发现属性 Tags 全部可读，说明此文件为 versioned 模式，取消 usmap 查找

**实测**: 本项目 `BP_Character.uasset` 是 Editor 未 Cook 资产，预期使用 versioned（FName）类型，可直接解析。此判断需在解析第一个属性 Tag 时确认。

#### 3.5.3 属性解析降级策略

遵循"尽力解析、逐步降级"原则：

```
Level 1: 正常解析 → 输出结构化数据（tagName, tagType, value）
Level 2: Struct 内部字段解析失败 → 该 Struct 节点标记为 partial，失败字段标记 unsupported
Level 3: 属性类型未知 → 读取 Size 字节保留为 base64 raw 字符串，标记 unsupported
Level 4: 属性 Tag 头部损坏 → 记录错误，标记为 corrupt，跳过剩余序列化数据
```

| 降级级别 | 行为 | JSON 标记 |
|----------|------|-----------|
| 正常 | 完整解析 | 无额外标记 |
| Struct 部分失败 | 已完成字段保留，失败字段降级 | `"partial": true` |
| 类型未知 | 保留 raw base64 + 已知 Size | `"unsupported": true, "rawSize": N, "rawData": "<base64>"` |
| Tag 损坏 | 停止当前 Export 属性解析，已解析的属性保留 | `"corrupt": true` |
| 整个 Export 解析失败 | 保留 Export 元信息（类名、序列化大小等） | `"parseError": "error message"` |

**关键规则**:
- 单个 Export 解析失败不影响其他 Export
- 同一 Export 内，一个属性失败不影响之前的属性
- 所有降级情况均在 stderr 输出 warning（`-v` 模式下也输出到 stdout）
- JSON 顶层增加 `"_parseWarnings": [...]` 数组汇总所有警告

### 3.6 .uexp 拆分文件处理

UE4 Cooked 资产如果序列化数据超过阈值，会将 Export 数据拆分到同名的 `.uexp` 文件：

- `.uasset` 文件包含 FPackageFileSummary + Name/Import/Export Table，Export 的 SerialOffset 指向 `.uexp`
- `.uexp` 文件包含纯粹的序列化 Export 数据（无单独头部）

**策略**:
1. 读取 `.uasset` 后，检查同级目录是否存在同名 `.uexp` 文件
2. 若存在，合并两个文件进行解析（uasset 提供结构和表，uexp 提供 Export 序列化数据）
3. 若不存在，所有数据均在 `.uasset` 内读取（非 Cooked 资产的常见情况）
4. 不存在 `.uexp` 时，Export 的 SerialOffset 和 SerialSize 直接在 uasset 文件内读取即可

### 3.7 版本兼容策略

参考 [uasset-parser-py](https://github.com/ay27/uasset-parser-py) 的 `ue_version.py`，使用 `EUnrealEngineObjectUE4Version` 版本常量进行条件字段解析：

```python
# 核心模式：根据包文件版本决定是否读取某字段
if self.file_version >= VER_UE4_SOMETHING:
    field = reader.readInt32()
```

FPackageFileSummary 的字段顺序和是否存在取决于 LegacyFileVersion 和 FileVersionUE4 的组合。不应假设固定偏移。参考 uasset-parser-py 的 `FPackageFileSummary.__init__` 处理了 10+ 个版本变体，按需参考。

### 3.8 实现技术栈

- **语言**: Python 3.10+（跨平台、易打包）
- **运行时核心依赖**:
  - `struct` — 二进制解析
  - `json` — JSON 序列化
  - 运行 exe 时不依赖第三方 Python 包
- **开发/打包依赖**:
  - PyInstaller（打包为独立 exe）
- **编码**: UTF-8

## 4. 非功能需求

### 4.1 性能
- 单个 1MB 以内 .uasset 文件解析耗时 < 2 秒
- 内存占用 < 100MB

### 4.2 错误处理
- 非法 .uasset 文件（魔数不匹配）报错并退出
- 不支持 UE5/UE4.25+ 的新版本格式报错并提示版本号
- 文件不存在报 FileNotFound
- 单个 Export 属性解析失败时，不应导致整个文件导出失败；应记录错误节点并继续
- CLI 返回码：成功为 0，参数错误为 2，文件/格式错误为 3，未预期异常为 1

### 4.3 可维护性
- 模块化结构：Reader → Parser → Serializer
- 可扩展新的属性类型解析器
- 独立于 UE 引擎运行，不需要 UE4 Editor 或引擎 DLL

## 5. 项目结构

```
D:\vr\UAssetParser\
├── src/
│   ├── main.py          # 入口，CLI 参数解析
│   ├── reader.py         # 二进制流读取器（FArchive）
│   ├── package.py        # FPackageFileSummary 解析
│   ├── names.py          # FName Table 解析
│   ├── imports.py        # Import Table 解析
│   ├── exports.py        # Export Table 解析
│   ├── properties.py     # UObject 属性序列化解析
│   ├── serializer.py     # 树状 JSON 输出
│   └── errors.py         # 错误处理与版本检查
├── tests/
│   ├── test_reader.py
│   ├── test_package.py
│   └── fixtures/         # 测试用 .uasset 样本
├── output/               # 测试输出目录，不作为 CLI 默认输出目录
├── build.bat             # PyInstaller 打包脚本
└── requirements.txt      # Python 依赖
```

## 6. 验收用例

### 6.1 指定文件解析

命令：

```bat
UAssetParser.exe D:\vr\ZMKJBS\Content\Blueprints\Global\Module\Character\BP_Character.uasset
```

期望：
- 进程返回码为 0
- 生成 `D:\vr\ZMKJBS\Content\Blueprints\Global\Module\Character\BP_Character.json`
- JSON 可被标准 JSON 解析器读取
- JSON 至少包含 `packageName`、`summary`、`nameTable`、`importTable`、`exportTable`、`objectTree`
- `nameTable` 中能看到 `BP_Character` 或 `BP_Character_C`
- `exportTable` 中能看到主要 Blueprint / GeneratedClass 相关导出对象

### 6.2 指定输出路径

命令：

```bat
UAssetParser.exe D:\vr\ZMKJBS\Content\Blueprints\Global\Module\Character\BP_Character.uasset -o D:\vr\UAssetParser\output\BP_Character.json
```

期望：
- 进程返回码为 0
- JSON 输出到 `D:\vr\UAssetParser\output\BP_Character.json`

### 6.3 错误文件

命令：

```bat
UAssetParser.exe not_exists.uasset
```

期望：
- 进程返回码非 0
- 控制台输出清晰错误信息

## 7. 交付物

1. Python 源码（`src/`）
2. 单元测试（`tests/`）
3. 打包脚本 `build.bat`，一键生成 `UAssetParser.exe`
4. 使用示例 bat 文件 `example.bat`

## 8. 版本记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-05-19 | 初稿定稿 |
| v1.1 | 2026-05-19 | 收敛实现边界，修正 UE4.22 头部说明，补充验收用例 |
