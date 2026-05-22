# 竞品调研与需求不足分析

## 调研范围

调查了 17 个开源 .uasset 解析项目，覆盖 C#（6个）、Python（4个）、Rust（2个）、JavaScript（1个）、C++（1个）。

## 关键发现：唯一 Python 竞品

**[uasset-parser-py](https://github.com/ay27/uasset-parser-py)** — 21 stars，唯一 Python 原生 .uasset 解析库。

| 维度 | uasset-parser-py | 我们的需求 | 差距 |
|------|-----------------|-----------|------|
| FPackageFileSummary | 完整 | 完整 | 持平 |
| Name/Import/Export Table | 完整 | 完整 | 持平 |
| UObject 属性解析 | **无** | MVP 要求 best-effort 属性解析 | **欠缺** |
| JSON 输出 | 无（只有 `__repr__`） | 核心需求 | **欠缺** |
| CLI 接口 | 无 | 核心需求 | **欠缺** |
| Blueprint/UMG 类型识别 | 无 | 增强目标 | **欠缺** |
| 错误容错 | 无 | MVP 要求失败继续 | **欠缺** |
| 打包 exe | 无 | 核心需求 | **欠缺** |

直接复用 uasset-parser-py 只能覆盖约 40% 的 MVP 范围。它的优势在 `FPackageFileSummary.__init__` 的版本条件读取逻辑（处理了所有 LegacyFileVersion -2 到 -8+ 的变体），这个可以作为参考但不建议直接 fork——因为它的属性解析完全空白，而我们需求 MVP 就要求 best-effort 属性解析。

## 本项目需求 vs 成熟项目能力对比

### 1. UObject 属性解析不足

| 能力 | UAssetAPI (C#) | uasset-rs (Rust) | uasset-reader-js | 本需求当前 |
|------|---------------|------------------|------------------|-----------|
| 属性 Tag 解析 | 100+ 类型 | 泛型 Parseable trait | 完整 | 仅提了 `FPropertyTag` 概念 |
| 嵌套 Struct | 递归 | 递归 | 递归 | 一句带过 |
| Array/Map/Set | 完整 | 完整 | 只读 | 一句带过 |
| FObjectProperty（组件引用）| 完整 | 有 | 有 | 提了但无细节 |
| UStruct 序列化 | 完整 | 泛型 | 不完整 | **未提及** |
| 属性类型枚举表 | 列出了 `EPropertyType` | 有 enums | 有 | **缺失** |

**不足**: 需求文档没有列出要支持的属性类型（`IntProperty`, `FloatProperty`, `BoolProperty`, `StrProperty`, `NameProperty`, `ObjectProperty`, `StructProperty`, `ArrayProperty`, `MapProperty`, `SetProperty`, `TextProperty`, `ByteProperty`, `EnumProperty` 等）。开发时容易遗漏。

### 2. Blueprint/UMG 特化解析缺失

| 能力 | UAssetAPI | CUE4Parse | uasset-rs | 本需求 |
|------|-----------|-----------|-----------|--------|
| BlueprintGeneratedClass 识别 | 有 | 有 | 有 | 提了 |
| SimpleConstructionScript 解析 | Export Type | 有 | 无 | 提了名称 |
| SCS_Node 组件层级 | 有 | 有 | 无 | 提了 |
| WidgetTree 解析 | 间接 | 间接 | 无 | 提了 |
| Widget 节点父子关系 | 间接 | 间接 | 无 | 提了 |
| Kismet 字节码 | **有** | 部分 | 无 | 明确不做 |
| FPropertyTag GUID→类型映射 | **usmap 支持** | 有 | 无 | **未提及** |

**关键不足**: UE4.22 的蓝图属性如果没有 `.usmap` 映射文件，`FPropertyTag` 的 Type GUID 无法解析为可读类型名。UAssetAPI 支持 usmap，我们的需求文档完全没有提及这个依赖关系。

### 3. .uasset 可能拆分问题

**重要发现**: UE4 中，Cooked 的 .uasset 文件如果超过一定大小，序列化数据会被拆分到同名的 `.uexp` 文件。本项目实测 `BP_Character.uasset`（630KB）没有 .uexp 文件，说明当前测试文件未拆分。但需求文档应该提到这个边界情况。

| 项目 | 是否处理 .uexp |
|------|---------------|
| UAssetAPI | 是，自动检测并读取配对 .uexp |
| CUE4Parse | 是 |
| uasset-rs | 未明确 |
| uasset-parser-py | 未处理 |
| 本需求 | **未提及** |

### 4. 版本兼容策略不够具体

所有竞品都实现了**条件字段读取**模式：

```
if version >= VER_UE4_SOMETHING:
    read field
```

uasset-parser-py 甚至处理了 10+ 个 LegacyFileVersion 变体。我们的需求只说了"不能写死偏移"，但没有具体说明如何实现版本兼容——应该参考 `EUnrealEngineObjectUE4Version` 枚举。

### 5. 属性解析容错策略

所有成熟项目在属性解析时都实现了：
- 遇到未知类型 → 跳过 Size 字节，继续下一个 Tag
- 不因一个属性解析失败而终止整个文件

需求文档提到了"应记录错误节点并继续"，但没有定义降级策略：
- 属性名能否解析？如果不能，怎么标记？
- 属性值类型未知时，是保留原始 hex 还是跳过？
- Struct 嵌套解析失败时，是否回退到 raw bytes？

---

## 需求改进建议

### 高优先级（MVP 必须补）

| # | 改进 | 理由 |
|---|------|------|
| 1 | **补属性类型枚举表** | 无此表开发时无法系统实现属性解析，至少列出 10+ 常见类型 |
| 2 | **明确 .uexp 文件处理策略** | 虽然当前测试文件未拆分，但需要制定检查逻辑 |
| 3 | **定义属性解析降级策略** | 未知类型跳过 Size 字节、Struct 失败回退 raw、失败节点标记 `unsupported` |

### 中优先级（增强质量）

| # | 改进 | 理由 |
|---|------|------|
| 4 | **引用 UE4 ObjectVersion 版本常量** | 参考 uasset-parser-py 的 `ue_version.py`，明确哪些版本号对应哪些条件字段 |
| 5 | **usmap 依赖说明** | 文档应说明：如果属性 Type GUID 无法解析（无 usmap），输出中将用 GUID 字符串代替类型名 |
| 6 | **SCS_Node 组件树解析策略** | Blueprint 的组件层级实际是从 SCS_Node 的 Export 序列化数据中解析，不是从属性 Tags 直接拿 |

### 低优先级（可选）

| # | 改进 | 理由 |
|---|------|------|
| 7 | WidgetTree 特殊处理 | UMG 的 Widget 树有专用的序列化格式 `FWidgetTree`，不同于普通 Actor 组件 |
| 8 | 参考 uasset-parser-py 的版本处理 | 后续扩展 UE5 支持时参考 |

---

## 总结

当前需求文档的 MVP 范围定义基本合理（不做完整反编译），但以下三点必须在开发前补上：

1. **属性类型枚举表** — 否则属性解析无法系统实现
2. **属性解析降级策略** — 否则遇到未知类型就崩
3. **FPropertyTag GUID/Type 解析策略** — 说明有/无 usmap 时的行为差异

建议在 REQUIREMENTS.md 中追加上述三点后即可开始编码。
