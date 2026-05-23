# UAssetParser 使用说明

`UAssetParser` 是一个用于解析 UE4.22 `.uasset` 文件的命令行工具，主要面向蓝图和 UMG 资源。工具会读取指定资源文件的包信息、名称表、导入表、导出表和对象层级，并导出为 JSON 文档，方便在不打开 UE4 编辑器的情况下查看资源结构。

本工具只负责读取和导出结构信息，不会修改原始 `.uasset` 文件。

## 快速使用

在 `UAssetParser` 目录下打开命令行，执行：

```bat
UAssetParser.exe D:\vr\ZMKJBS\Content\Blueprints\Global\Module\Character\BP_Character.uasset
```

默认情况下，工具会在输入资源文件旁边生成同名 JSON 文件，例如：

```text
BP_Character.uasset -> BP_Character.json
```

也可以用 `-o` 指定输出路径：

```bat
UAssetParser.exe D:\vr\ZMKJBS\Content\Blueprints\Global\Module\Character\BP_Character.uasset -o output\BP_Character.json
```

## 常用参数

```bat
UAssetParser.exe BP_Character.uasset -o output\BP_Character.json -v
UAssetParser.exe BP_Character.uasset --blueprint-only --no-raw -o output\BP_Character_blueprint.json
UAssetParser.exe BP_Character.uasset --summary-only --compact
UAssetParser.exe BP_Character.uasset --no-raw
UAssetParser.exe BP_Character.uasset --raw-limit 16
UAssetParser.exe Content\Blueprints\Global\Module\Character --batch -o output\batch
```

参数说明：

- `-o`：指定输出 JSON 文件或批量输出目录。
- `-v`：输出更详细的解析过程信息。
- `--summary-only`：只导出摘要信息，不导出完整对象树。
- `--compact`：压缩 JSON 格式，减少文件体积。
- `--no-raw`：不输出未完全识别字段的原始数据。
- `--raw-limit`：限制 raw 数据输出长度。
- `--batch`：批量解析目录下的 `.uasset` 文件。
- `--blueprint-only`：只输出蓝图组件结构，格式更接近 UE 编辑器里看到的组件树。

## 输出内容

导出的 JSON 主要包含：

- `packageName`：资源包路径。
- `summary`：包头摘要信息。
- `nameTable`：名称表。
- `importTable`：导入对象表。
- `exportTable`：导出对象表。
- `objectTree`：根据对象引用关系整理出的树状结构。
- `_parseWarnings`：解析过程中遇到的非致命警告。

需要注意的是，工具会尽力解析蓝图和 UMG 的结构信息，但不会完整反编译蓝图事件图、节点连线或 UE4 私有序列化细节。

如果使用 `--blueprint-only`，输出会变成更精简的蓝图组件结构，例如：

```json
{
  "CollisionCylinder": {
    "Class": "CapsuleComponent",
    "IsRoot": true,
    "Properties": {
      "BodyInstance": {
        "Type": "BodyInstance",
        "Value": {}
      }
    }
  },
  "bp_VRCamera": {
    "Class": "CameraComponent",
    "Parent": "bp_CameraRoot"
  }
}
```

## 验证方式

如果本机有 Python 环境，可以运行以下脚本做基础验证：

```bat
python tests\verify_reader.py
python tests\verify_all.py
python tests\verify_cli_options.py
```

也可以指定自己的测试资源：

```bat
set UASSET_SAMPLE=D:\vr\ZMKJBS\Content\Blueprints\Global\Module\Character\BP_Character.uasset
python tests\verify_cli_options.py
```

## 重新打包

如需重新生成 exe，执行：

```bat
build.bat
```

打包完成后会在 `UAssetParser` 根目录生成：

```text
UAssetParser.exe
```
