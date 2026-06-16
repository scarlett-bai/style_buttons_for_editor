# Style Buttons for Editor

根据当前笔记类型（Note Type）模板 CSS 中定义的样式，自动在 Anki 卡片编辑器工具栏生成快捷按钮。选中文本后点击按钮，即可将其包裹进对应的 HTML 标签，无需手写代码。

![示意](docs/screenshot.png)

## 功能

- **CSS 自动解析**：读取当前笔记类型的 Styling，提取所有自定义 class（支持逗号分隔、嵌套/组合选择器、伪类、`@media`、中文/连字符 class 名等）。
- **动态按钮**：在工具栏原生按钮之后显示样式按钮；切换笔记类型时自动刷新。无自定义 class 时不显示任何按钮。
- **拖拽排序**：直接按住工具栏按钮左右拖动即可调整顺序，松手即保存；「更多 ▾」下拉内的项可上下拖动排序，下拉打开时还能在工具栏与下拉之间互拖。
- **一键包裹**：
  - 有选区 → 包裹为 `<span class="xxx">选中文本</span>`
  - 无选区 → 插入空标签并把光标定位到标签内
  - 已被同 class 包裹 → 再次点击取消（Toggle）；若该标签还有其它 class，则仅移除当前 class
  - 不同 class → 在外层再嵌套一层（样式叠加）
- **按钮样式预览**：按钮本身应用对应 CSS 的安全属性（加粗、颜色等）。
- **Tooltip**：显示 class 名、快捷键与 CSS 属性摘要。
- **快捷键**：可为每个 class 绑定快捷键（默认不分配，避免冲突）。
- **溢出处理**：按钮过多时支持"更多"下拉菜单 / 换行 / 横向滚动。
- **中英文界面**：跟随 Anki 语言设置。

## 安装

将本插件文件夹放入 Anki 插件目录（`Tools → Add-ons → View Files`），重启 Anki。

## 使用

1. 在某个笔记类型的 **Styling** 中定义样式，例如：
   ```css
   .vocab { color: blue; font-weight: bold; }
   .grammar { color: green; font-style: italic; }
   ```
2. 打开"添加/编辑"窗口，工具栏右侧会出现 `vocab`、`grammar` 按钮。
3. 选中文本 → 点击按钮即可包裹。

## 配置

- `Tools → Style Buttons 设置…`，或
- `Tools → Add-ons → 选中本插件 → Config`

配置项说明见 [config.md](config.md)。

## 兼容性

- Anki 2.1.55+（Qt6），已在 Anki 25.09 上开发验证。
- 支持 添加（Add）/ 编辑（Edit）/ 浏览器（Browser）三种编辑场景。

## 已知限制

- 仅解析模板内的 CSS，不支持 `@import` 外部样式。
- 仅支持 class 选择器，不支持 ID 选择器。

## 许可

MIT
