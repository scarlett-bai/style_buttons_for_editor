# Style Buttons for Editor — 配置说明

修改配置后，**重新打开编辑器窗口**（关闭并重新打开"添加/编辑"窗口，或切换笔记类型）即可生效。

## 全局设置 `global`

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled` | 布尔 | `true` | 插件总开关。关闭后不再显示任何样式按钮 |
| `default_tag` | 字符串 | `"span"` | 默认包裹标签。未单独指定 `tag` 的 class 使用此标签 |
| `button_overflow_mode` | 字符串 | `"dropdown"` | 按钮过多时的处理方式：`dropdown`（更多下拉菜单）/ `newline`（换行）/ `scroll`（横向滚动） |
| `button_overflow_threshold` | 整数 | `8` | 触发溢出处理的按钮数量阈值 |
| `show_css_preview_tooltip` | 布尔 | `true` | 鼠标悬停按钮时，tooltip 中是否显示该 class 的 CSS 属性摘要 |
| `show_button_style_preview` | 布尔 | `true` | 是否让按钮本身应用对应 CSS 的安全属性（如加粗、颜色）作为预览 |
| `ignored_classes` | 字符串数组 | 见下 | 全局忽略、不生成按钮的 class 列表 |
| `language` | 字符串 | `"auto"` | 界面语言：`auto`（跟随 Anki）/ `zh` / `en` |
| `debug` | 布尔 | `false` | 调试模式。开启后，样式应用失败时会把原因写入日志，并在编辑器内弹出提示（toast），便于排查"标签没添加上"等问题 |

默认忽略列表：`card, card1, card2, card3, cloze, nightMode, night_mode, replay-button, typepad, typeBad, typeGood, typeMissed`

> 注意：按钮预览仅应用 `color`、`background-color`、`font-weight`、`font-style`、`text-decoration`、`text-transform`、`letter-spacing`、`font-family` 等安全属性，不会应用 `display`、`transform` 等可能破坏按钮布局的属性。

## 按笔记类型配置 `note_types`

结构为 `note_types -> "<笔记类型名称>" -> "<class 名>" -> { 配置项 }`。
未列出的 class 将使用下列默认值。

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `visible` | 布尔 | `true` | 是否显示为按钮 |
| `display_name` | 字符串 | `""` | 按钮显示文字（空则用 class 名） |
| `order` | 整数 | （解析顺序） | 排列顺序，数字越小越靠前 |
| `tag` | 字符串 | `""` | 该 class 的包裹标签（空则用全局 `default_tag`） |
| `shortcut` | 字符串 | `""` | 快捷键，如 `"Ctrl+Shift+1"`、`"Ctrl+Shift+H"`（默认不分配） |
| `color` | 字符串 | `""` | 按钮上的小圆点标记颜色，用于快速视觉区分（如 `"#ff0000"`） |

### 示例

```json
{
  "note_types": {
    "基础模板": {
      "highlight": { "display_name": "高亮", "order": 1, "tag": "mark", "shortcut": "Ctrl+Shift+H" },
      "bold":      { "display_name": "粗体", "order": 2, "shortcut": "Ctrl+Shift+B" },
      "container": { "visible": false }
    }
  }
}
```

## 已知限制

- 仅解析模板 Styling 文本框中的 CSS，不支持 `@import` 导入的外部样式。
- 仅支持 class 选择器（`.class`），不支持 ID 选择器（`#id`）。
