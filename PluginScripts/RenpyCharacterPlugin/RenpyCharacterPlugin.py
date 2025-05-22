import os
import re
from typing import Dict

from ModuleFolders.Cache.CacheItem import CacheItem, TranslationStatus
from ModuleFolders.Cache.CacheProject import CacheProject, ProjectType
from ModuleFolders.Translator.TranslatorConfig import TranslatorConfig
from ModuleFolders.PromptBuilder.PromptBuilderEnum import PromptBuilderEnum
from ..PluginBase import PluginBase


class RenpyCharacterPlugin(PluginBase):
    """
    Renpy角色辅助翻译插件
    """

    def __init__(self):
        super().__init__()
        self.name = "RenpyCharacterPlugin"
        self.description = "Ren'Py角色辅助翻译插件，提升对话翻译的准确性和人物特征还原度" \
            + "\n" + "自动识别Ren'Py游戏中的角色定义，并在翻译过程中的相关对话中嵌入说话者" \
            + "\n" + "兼容性：仅支持Ren'Py项目,仅推荐强力模型使用"

        self.visibility = True  # 在插件设置中显示
        self.default_enable = False  # 默认禁用状态

        # 注册事件
        self.add_event("text_filter", PluginBase.PRIORITY.LOW)  # 文本预过滤事件，使用LOW优先级，让LanguageFilter先执行
        self.add_event("preproces_text", PluginBase.PRIORITY.NORMAL)  # 文本预处理事件
        self.add_event("postprocess_text", PluginBase.PRIORITY.NORMAL)  # 文本后处理事件
        self.add_event("translation_completed", PluginBase.PRIORITY.NORMAL)  # 翻译完成事件

        # 角色变量映射表
        self.character_map = {}  # 变量名 -> 角色名称
        self.character_variables = set()  # 所有角色变量名集合

        # 统计信息
        self.modified_count = 0  # 修改的文本数量
        self.processed_count = 0  # 处理的文本数量
        self.error_entries = []  # 恢复出错的条目

        # 角色信息标记格式 - 更通用的模式，能够处理各种情况
        self.character_tag_pattern = r'\[角色:([^\]]+?)\]'  # 匹配任何 [角色:xxx] 格式

        # 重置状态变量
        self.reset_state()

    def reset_state(self):
        """重置插件状态"""
        # 重置统计信息
        self.modified_count = 0
        self.processed_count = 0
        self.error_entries = []

    def load(self):
        """插件加载时调用"""
        print(f"[INFO][{self.name}] 插件已加载")

    def on_event(self, event_name, config: TranslatorConfig,event_data: CacheProject ):
        """处理事件"""
        if ProjectType.RENPY not in event_data.file_project_types:
            print(f"[INFO][{self.name}] 非renpy项目不执行")
            return

        # 在文本过滤事件开始时重置状态
        if event_name == "text_filter":
            # 重置插件状态
            self.reset_state()
            self._handle_text_filter(config, event_data)
        elif event_name == "preproces_text":
            self._handle_preprocess_text(config, event_data)
        elif event_name == "postprocess_text":
            self._handle_postprocess_text(config, event_data)
        elif event_name == "translation_completed":
            self._handle_translation_completed(config, event_data)

    def _handle_text_filter(self, config: TranslatorConfig, event_data: CacheProject):
        """处理文本预过滤事件"""
        print(f"[INFO][{self.name}] 开始扫描Ren'Py文件，提取角色定义...")

        # 设置环境变量通知RenpyReader在提取文本时附加角色变量信息
        os.environ["RENPY_CHARACTER_PLUGIN_ACTIVE"] = "1"

        # 扫描所有Ren'Py文件，提取角色定义
        self._scan_renpy_files(config, event_data)

        # 输出扫描结果
        print(f"[INFO][{self.name}] 扫描完成，共找到 {len(self.character_map)} 个角色定义")
        for var_name, char_name in self.character_map.items():
            print(f"[DEBUG][{self.name}] 角色变量: {var_name} -> {char_name}")

    def _handle_preprocess_text(self, config: TranslatorConfig, event_data: CacheProject):
        """处理文本预处理事件"""
        print(f"[INFO][{self.name}] 开始处理源文本，添加角色信息...")

        # 修改系统提示，添加角色信息
        self._enhance_system_prompt(config)

        # 调试信息：检查是否有条目包含角色变量
        has_speaker_var = False
        for file in event_data.files.values():
            for item in file.items:
                speaker_var = item.get_extra("_rcp_speaker_variable", None)
                if not speaker_var:
                    speaker_var = item.get_extra("tag", None)

                if speaker_var and speaker_var in self.character_map:
                    has_speaker_var = True
                    break
            if has_speaker_var:
                break

        if not has_speaker_var:
            print(f"[WARNING][{self.name}] 没有找到任何包含角色变量的条目，请检查RenpyReader.py是否正确提取了角色变量")
            # 打印一些条目的示例，帮助调试
            print(f"[DEBUG][{self.name}] 条目示例:")
            count = 0
            for file in event_data.files.values():
                for item in file.items:
                    if count < 5:  # 只打印前5个条目
                        print(f"[DEBUG][{self.name}] 源文本: {item.source_text}")
                        print(f"[DEBUG][{self.name}] Extra: {item.extra}")
                        count += 1

        # 处理所有文本条目
        for file in event_data.files.values():
            for item in file.items:
                if item.translation_status == TranslationStatus.EXCLUDED:
                    continue  # 跳过已排除的条目

                # 获取角色变量信息
                speaker_var = item.get_extra("_rcp_speaker_variable", None)

                # 如果没有_rcp_speaker_variable，尝试使用tag字段
                if not speaker_var:
                    speaker_var = item.get_extra("tag", None)

                if speaker_var and speaker_var in self.character_map:
                    # 检查源文本是否已经包含角色标签
                    original_text = item.source_text
                    char_name = self.character_map[speaker_var]

                    # 构建更灵活的标签模式，能够处理角色名中包含特殊字符的情况
                    # 使用更通用的方式检测角色标签
                    has_tag = False

                    # 检查是否已经包含角色标签
                    if '[角色:' in original_text:
                        # 尝试提取第一个角色标签
                        tag_match = re.match(r'\[角色:[^\]]+\]', original_text)
                        if tag_match:
                            # 如果已经有角色标签，则不添加新的
                            has_tag = True

                    if not has_tag:
                        # 源文本不包含角色标签，添加角色信息
                        modified_text = f"[角色:{char_name}({speaker_var})] {original_text}"

                        # 更新源文本
                        item.source_text = modified_text

                        # 记录修改信息
                        self.modified_count += 1

                    # 添加_rcp_speaker_variable字段，以便后处理时使用
                    if not item.get_extra("_rcp_speaker_variable", None):
                        item.set_extra("_rcp_speaker_variable", speaker_var)

                self.processed_count += 1

        print(f"[INFO][{self.name}] 源文本处理完成，共处理 {self.processed_count} 个条目，修改 {self.modified_count} 个条目")

    def _handle_postprocess_text(self, config: TranslatorConfig, event_data: CacheProject):
        """处理文本后处理事件"""
        print(f"[INFO][{self.name}] 开始处理翻译文本，恢复原始格式...")

        error_count = 0
        for file in event_data.files.values():
            for item in file.items:
                if item.translation_status != TranslationStatus.TRANSLATED:
                    continue  # 只处理已翻译的条目

                # 获取角色变量信息
                speaker_var = item.get_extra("_rcp_speaker_variable", None)

                # 如果没有_rcp_speaker_variable，尝试使用tag字段
                if not speaker_var:
                    speaker_var = item.get_extra("tag", None)

                if speaker_var and speaker_var in self.character_map:
                    # 检查翻译文本是否包含角色标记
                    translated_text = item.translated_text

                    # 检查是否包含角色标记
                    if '[角色:' in translated_text:
                        # 使用更通用的方式移除所有角色标记
                        # 先找出所有角色标记
                        tags = re.findall(r'\[角色:[^\]]+\]', translated_text)

                        if tags:
                            # 移除所有角色标记
                            clean_text = translated_text
                            for tag in tags:
                                clean_text = clean_text.replace(tag, '')

                            # 去除可能的前导空格
                            clean_text = clean_text.lstrip()

                            # 更新翻译文本
                            item.translated_text = clean_text
                    else:
                        # 角色标记丢失，记录错误
                        error_count += 1
                        self.error_entries.append({
                            "file_name": file.file_name,
                            "storage_path": file.storage_path,
                            "text_index": item.text_index,
                            "source_text": item.source_text,
                            "translated_text": item.translated_text,
                            "speaker_var": speaker_var,
                            "char_name": self.character_map.get(speaker_var, "未知")
                        })

        print(f"[INFO][{self.name}] 翻译文本处理完成，共有 {error_count} 个条目恢复出错")

    def _handle_translation_completed(self, config: TranslatorConfig, event_data: CacheProject):
        """处理翻译完成事件"""
        # 输出统计信息
        print(f"[INFO][{self.name}] 翻译任务完成")
        print(f"[INFO][{self.name}] 共处理 {self.processed_count} 个条目，修改 {self.modified_count} 个条目")

        # 输出错误信息
        if self.error_entries:
            print(f"[WARNING][{self.name}] 共有 {len(self.error_entries)} 个条目恢复出错")

            # 将错误信息写入文件
            self._write_error_report(config)

        # 清理环境变量
        if "RENPY_CHARACTER_PLUGIN_ACTIVE" in os.environ:
            del os.environ["RENPY_CHARACTER_PLUGIN_ACTIVE"]


    def _scan_renpy_files(self, config: TranslatorConfig, event_data: CacheProject):
        """扫描所有Ren'Py文件，提取角色定义"""
        # 获取输入路径
        input_path = config.label_input_path
        if not input_path or not os.path.exists(input_path):
            print(f"[WARNING][{self.name}] 输入路径不存在: {input_path}")
            return

        # 变量名映射表（用于处理变量引用）
        variable_map = {}

        # 扫描所有.rpy文件
        for root, _, files in os.walk(input_path):
            for file in files:
                if file.endswith(".rpy"):
                    file_path = os.path.join(root, file)
                    try:
                        self._extract_character_definitions(file_path, variable_map)
                    except Exception as e:
                        print(f"[ERROR][{self.name}] 处理文件 {file_path} 时出错: {e}")

        # 处理变量引用
        self._resolve_variable_references(variable_map)

    def _extract_character_definitions(self, file_path: str, variable_map: Dict[str, str]):
        """从Ren'Py文件中提取角色定义"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                # 尝试使用其他编码
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
            except Exception as e:
                print(f"[ERROR][{self.name}] 无法读取文件 {file_path}: {e}")
                return

        # 提取角色定义
        # 1. 直接定义角色: define mc = Character("Thomas", color="#FFD700")
        pattern1 = r'define\s+(\w+)\s*=\s*Character\s*\(\s*["\']([^"\']+)["\']'
        for match in re.finditer(pattern1, content):
            var_name = match.group(1)
            char_name = match.group(2)
            self.character_map[var_name] = char_name
            self.character_variables.add(var_name)

        # 2. 定义角色名称变量: define mcN = "Thomas"
        pattern2 = r'define\s+(\w+)\s*=\s*["\']([^"\']+)["\']'
        for match in re.finditer(pattern2, content):
            var_name = match.group(1)
            value = match.group(2)
            variable_map[var_name] = value

        # 3. 使用变量引用: define mc = Character([mcN], color="#FFD700")
        pattern3 = r'define\s+(\w+)\s*=\s*Character\s*\(\s*\[(\w+)\]'
        for match in re.finditer(pattern3, content):
            var_name = match.group(1)
            ref_var = match.group(2)
            # 记录变量引用，稍后解析
            variable_map[var_name] = f"[{ref_var}]"
            self.character_variables.add(var_name)

    def _resolve_variable_references(self, variable_map: Dict[str, str]):
        """解析变量引用"""
        # 处理变量引用
        for var_name, value in variable_map.items():
            if value.startswith("[") and value.endswith("]"):
                # 这是一个变量引用
                ref_var = value[1:-1]
                if ref_var in variable_map:
                    # 引用的变量存在于变量映射表中
                    self.character_map[var_name] = variable_map[ref_var]

    def _enhance_system_prompt(self, config: TranslatorConfig):
        """增强系统提示，添加角色信息"""
        if not self.character_map:
            print(f"[INFO][{self.name}] 没有找到角色定义，不需要增强系统提示")
            return  # 没有角色定义，不需要增强系统提示

        # 构建角色信息提示
        char_info = ["### Ren'Py角色变量对照表", "在翻译过程中，请注意说话者是谁：", ""]

        char_info.extend([
            "当你看到形如 `[角色:Thomas(mc)] I'll come and see you in a bit.` 的文本时，",
            "请理解这是角色 \"Thomas\" 说的话，其变量名为 \"mc\"。",
            "请根据角色的身份和特点，调整翻译风格，使其更符合角色特点。",
            "在翻译结果中，请保持 `[角色:Name(var)]` 格式不变，不要翻译或修改这部分。"
        ])

        # 将角色信息添加到系统提示中
        self.char_info_text = "\n".join(char_info)

        # 直接修改系统提示词内容
        if config.prompt_preset == PromptBuilderEnum.CUSTOM:
            # 如果是自定义提示词，直接添加到系统提示词内容中
            if config.system_prompt_content:
                config.system_prompt_content = f"{config.system_prompt_content}\n\n{self.char_info_text}"
            else:
                config.system_prompt_content = self.char_info_text
        else:
            # 对于非自定义提示词，我们需要修改内存中的提示词变量
            prompt_var_name = None
            prompt_builder_class = None

            # 导入PromptBuilder类
            from ModuleFolders.PromptBuilder.PromptBuilder import PromptBuilder

            if config.prompt_preset == PromptBuilderEnum.COMMON:
                if config.target_language in ("chinese_simplified", "chinese_traditional"):
                    prompt_var_name = "common_system_zh"
                    prompt_builder_class = PromptBuilder
                else:
                    prompt_var_name = "common_system_en"
                    prompt_builder_class = PromptBuilder
            elif config.prompt_preset == PromptBuilderEnum.COT:
                if config.target_language in ("chinese_simplified", "chinese_traditional"):
                    prompt_var_name = "cot_system_zh"
                    prompt_builder_class = PromptBuilder
                else:
                    prompt_var_name = "cot_system_en"
                    prompt_builder_class = PromptBuilder
            elif config.prompt_preset == PromptBuilderEnum.THINK:
                # 导入THINK模式的提示词构建器
                from ModuleFolders.PromptBuilder.PromptBuilderThink import PromptBuilderThink

                # 确保提示词已经加载到内存
                PromptBuilderThink.get_system_default(config)

                if config.target_language in ("chinese_simplified", "chinese_traditional"):
                    prompt_var_name = "think_system_zh"
                    prompt_builder_class = PromptBuilderThink
                else:
                    prompt_var_name = "think_system_en"
                    prompt_builder_class = PromptBuilderThink

            # 如果找到了对应的提示词变量，就修改它
            if prompt_var_name and prompt_builder_class and hasattr(prompt_builder_class, prompt_var_name):
                # 保存原始提示词
                if not hasattr(self, "_original_prompts"):
                    self._original_prompts = {}

                builder_key = f"{prompt_builder_class.__name__}.{prompt_var_name}"
                if builder_key not in self._original_prompts:
                    self._original_prompts[builder_key] = getattr(prompt_builder_class, prompt_var_name)

                # 检查是否已经包含角色信息
                original_prompt = getattr(prompt_builder_class, prompt_var_name)
                if "### Ren'Py角色变量对照表" not in original_prompt:
                    # 添加角色信息
                    new_prompt = f"{original_prompt}\n\n{self.char_info_text}"

                    # 更新内存中的提示词
                    setattr(prompt_builder_class, prompt_var_name, new_prompt)

                    print(f"[INFO][{self.name}] 已更新内存中的系统提示词：{prompt_var_name} (在{prompt_builder_class.__name__}类中)")
            else:
                print(f"[WARNING][{self.name}] 无法更新内存中的系统提示词，变量不存在：{prompt_var_name}")

        # 打印调试信息
        print(f"[INFO][{self.name}] 已添加角色信息到系统提示词中")

        # 保存角色信息到config中，以便后续使用
        config._rcp_char_info_text = self.char_info_text

    def _write_error_report(self, config: TranslatorConfig):
        """将错误信息写入文件"""
        if not self.error_entries:
            return

        # 构建错误报告
        report = ["# Ren'Py角色变量增强插件 - 错误报告", ""]
        report.append(f"共有 {len(self.error_entries)} 个条目恢复出错。")
        report.append("")

        for i, entry in enumerate(self.error_entries, 1):
            report.append(f"## 错误条目 {i}")
            report.append(f"- 文件: {entry['file_name']}")
            report.append(f"- 路径: {entry['storage_path']}")
            report.append(f"- 索引: {entry['text_index']}")
            report.append(f"- 角色变量: {entry['speaker_var']} ({entry['char_name']})")
            report.append(f"- 源文本: {entry['source_text']}")
            report.append(f"- 译文: {entry['translated_text']}")
            report.append("")

        # 写入文件
        output_path = config.label_output_path
        if not output_path:
            output_path = "."

        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)

        report_path = os.path.join(output_path, "renpy_character_plugin_errors.md")
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(report))
            print(f"[INFO][{self.name}] 错误报告已写入: {report_path}")
        except Exception as e:
            print(f"[ERROR][{self.name}] 写入错误报告时出错: {e}")