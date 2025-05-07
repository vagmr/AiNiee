# Ren'Py角色变量增强插件

## 功能介绍

这个插件用于改善Ren'Py游戏的翻译质量，特别是对话部分。在Ren'Py游戏中，角色对话通常使用变量来表示说话者，例如：

```renpy
define mc = Character("Thomas", color="#FFD700")
define nn = Character("Allison", color="#7f32a8")

# 游戏中的对话
mc "I'll come and see you in a bit."
nn "Thank you!"
```

在这个例子中，`mc`和`nn`是变量，而"Thomas"和"Allison"是实际的角色名称。

当这些对话被提取用于翻译时，AI翻译模型只能看到双引号内的文本（如"I'll come and see you in a bit."），而不知道这些文本是由哪个角色说的。这可能导致翻译质量下降，因为AI无法根据角色的身份和特点来调整翻译风格。

本插件通过以下步骤解决这个问题：

1. 在翻译开始前，扫描所有Ren'Py文件，提取角色定义（`define`语句）
2. 设置标志通知`RenpyReader`在提取文本时附加角色变量信息
3. 直接在`text_filter`事件中修改源文本，添加角色信息
4. 将角色信息添加到系统提示中，进一步帮助AI理解角色关系
5. 在翻译完成后，恢复原始格式，移除添加的角色信息

这种方法与`RenpyReader`紧密集成，确保角色信息能够正确地传递给AI模型，提供更符合角色特点的翻译。

## 使用方法

1. 将插件文件夹放入`PluginScripts`目录
2. 在AiNiee的插件设置页面中启用"RenpyCharacterPlugin"
3. 正常进行翻译操作

## 支持的角色定义格式

插件支持以下几种常见的Ren'Py角色定义格式：

1. 直接定义角色：`define mc = Character("Thomas", color="#FFD700")`
2. 定义角色名称变量：`define mcN = "Thomas"`
3. 使用变量引用：`define mc = Character([mcN], color="#FFD700")`

## 文本转换示例

原始文本：
```
mc "I'll come and see you in a bit."
```

转换后的文本（发送给AI翻译）：
```
[角色:Thomas(mc)] I'll come and see you in a bit.
```

AI翻译结果：
```
[角色:Thomas(mc)] 我一会儿来看你。
```

最终输出（恢复原始格式）：
```
mc "我一会儿来看你。"
```

## 系统提示增强

插件还会在系统提示中添加角色信息，进一步提高翻译质量：

```
### Ren'Py角色变量对照表
在翻译过程中，请注意以下角色变量与实际名称的对应关系：

- mc = "Thomas"
- nn = "Allison"
- a = "Amelia"
- l = "Elizabeth"
...

当你看到形如 `[角色:Thomas(mc)] I'll come and see you in a bit.` 的文本时，
请理解这是角色 "Thomas" 说的话，其变量名为 "mc"。
请根据角色的身份和特点，调整翻译风格，使其更符合角色特点。
在翻译结果中，请保持 `[角色:Name(var)]` 格式不变，不要翻译或修改这部分。
```

## 与RenpyReader的集成

本插件与`RenpyReader`紧密集成，通过以下方式工作：

1. 在`text_filter`事件中设置`config.renpy_character_plugin_active = True`标志
2. `RenpyReader`检测到这个标志后，会在提取文本时附加`_rcp_speaker_variable`字段
3. 插件使用这个字段来识别角色变量，并添加角色信息
4. 在翻译完成后，插件使用这个字段来恢复原始格式

这种集成方式确保了角色信息能够正确地传递给AI模型，提供更符合角色特点的翻译。

## 错误检查与报告

如果在处理过程中发现一些条目无法正确恢复原始格式（例如，AI翻译结果中丢失了角色标记），插件会生成一个错误报告文件`renpy_character_plugin_errors.md`，列出所有出现问题的条目，以便手动修复。

## 注意事项

- 插件只会处理在Ren'Py文件中明确定义的角色变量
- 插件会临时修改待翻译的文本，但最终输出的格式与原始文件相同
- 插件默认是禁用的，需要在设置中手动启用
- 这种方法需要与最新版本的`RenpyReader`配合使用

## 调试信息

插件在运行过程中会输出以下调试信息：

- 扫描到的角色定义列表
- 识别的角色对话数量
- 修改的源文本数量
- 处理的翻译结果数量

如果遇到问题，可以查看这些信息来帮助排查。