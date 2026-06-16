/*
 * Style Buttons for Editor — 前端运行时 (F2 / F3 + 拖拽排序)
 *
 * 在 Anki 编辑器 webview 中注入,负责:
 *   - render(payload): 在工具栏渲染样式按钮(含溢出下拉、样式预览、tooltip)
 *   - apply(spec):     对当前字段选区执行包裹 / Toggle 取消
 *   - 拖拽排序:        指针拖拽调整按钮顺序(支持工具栏内、下拉内、两区互拖),
 *                      松手后即时本地重排并通过 pycmd 回传 Python 持久化
 *   - 键盘快捷键分发
 *
 * 设计要点:
 *   - 包裹用 document.execCommand("insertHTML") 对捕获到的 DOM 选区操作(即 Anki
 *     内部 x6 的底层机制),不依赖 window.wrap / focusedInput —— 后者在字段内容变化
 *     后会被清空,导致只能生效一次。
 *   - 选区位于字段的 shadow DOM 中,通过 getRootNode().getSelection() 获取;并在
 *     mousedown 时(字段仍持有选区)就捕获,应用时重新聚焦并恢复,杜绝焦点漂移。
 *   - 用指针(mousedown/move/up)而非 HTML5 拖拽:这样可在 mousedown 时
 *     preventDefault 以保住字段焦点/选区(供“点击=应用样式”使用),同时不影响拖拽。
 *     移动超过阈值才进入拖拽,否则视为点击。
 *   - 所有操作 try/catch 包裹,任何异常都不影响编辑器(PRD 4.3)。
 */
(function () {
    "use strict";

    if (window.__sbfe && window.__sbfe._ready) {
        return; // 已初始化:核心函数保持不变,仅由 render() 刷新数据
    }

    const ns = (window.__sbfe = window.__sbfe || {});
    ns._ready = true;
    ns.shortcuts = []; // [{combo:{...}, spec:{...}}]
    ns.i18n = {};
    ns.noteType = ""; // 当前笔记类型名,用于保存排序
    ns._payload = null; // 最近一次渲染数据,拖拽后本地重排复用
    ns._dragThreshold = 5; // 进入拖拽的位移阈值(px)

    // ---- 选区与可编辑区 -------------------------------------------------

    function deepActiveElement() {
        let el = document.activeElement;
        while (el && el.shadowRoot && el.shadowRoot.activeElement) {
            el = el.shadowRoot.activeElement;
        }
        return el;
    }

    function getSelectionInfo() {
        const active = deepActiveElement();
        if (!active) return null;
        const root = active.getRootNode();
        const sel = root && root.getSelection ? root.getSelection() : document.getSelection();
        if (!sel || sel.rangeCount === 0) return null;

        let editable = active;
        while (
            editable &&
            !(editable.nodeType === 1 && editable.getAttribute && editable.getAttribute("contenteditable") !== null)
        ) {
            editable = editable.parentNode;
        }
        if (!editable) editable = active;

        // 克隆 range,使其在选区/焦点变化后仍可用(供 mousedown 时捕获、应用时恢复)
        return {
            sel: sel,
            range: sel.getRangeAt(sel.rangeCount - 1).cloneRange(),
            editable: editable,
        };
    }

    function escapeAttr(value) {
        return String(value).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
    }

    // ---- Toggle:查找并移除既有包裹 -------------------------------------

    function findWrapper(range, className, editable) {
        let node = range.commonAncestorContainer;
        if (node && node.nodeType === 3) node = node.parentNode;
        while (node && node !== editable) {
            if (node.nodeType === 1 && node.classList && node.classList.contains(className)) {
                return node;
            }
            node = node.parentNode;
        }
        return null;
    }

    function unwrap(el, className) {
        const others = Array.prototype.slice.call(el.classList).filter(function (c) {
            return c !== className;
        });
        let replacement;
        if (others.length === 0) {
            replacement = el.innerHTML;
        } else {
            const clone = el.cloneNode(false);
            clone.classList.remove(className);
            clone.innerHTML = el.innerHTML;
            replacement = clone.outerHTML;
        }
        const root = el.getRootNode();
        const sel = root && root.getSelection ? root.getSelection() : document.getSelection();
        const r = document.createRange();
        r.selectNode(el);
        sel.removeAllRanges();
        sel.addRange(r);
        document.execCommand("insertHTML", false, replacement);
    }

    function selectedHtml(range) {
        const div = document.createElement("div");
        div.appendChild(range.cloneContents());
        return div.innerHTML;
    }

    function rootSelection(node) {
        const root = node && node.getRootNode ? node.getRootNode() : document;
        return root && root.getSelection ? root.getSelection() : document.getSelection();
    }

    // 把光标定位到刚插入的空标签内部(无选区场景)
    function insertEmpty(info, tag, className) {
        const html =
            "<" + tag + ' class="' + escapeAttr(className) + '" data-sbfe-caret="1"></' + tag + ">";
        document.execCommand("insertHTML", false, html);
        let el = null;
        try {
            el = info.editable.querySelector && info.editable.querySelector("[data-sbfe-caret]");
        } catch (e) {
            el = null;
        }
        if (el) {
            el.removeAttribute("data-sbfe-caret");
            try {
                const sel = rootSelection(el);
                const nr = document.createRange();
                nr.setStart(el, 0);
                nr.collapse(true);
                sel.removeAllRanges();
                sel.addRange(nr);
            } catch (e) {
                /* 忽略光标定位失败 */
            }
        }
    }

    // ---- 应用样式(包裹 / Toggle) ------------------------------------
    //
    // 不依赖 Anki 的 window.wrap / focusedInput(其在内容变化后会被清空导致失效),
    // 而是直接对捕获到的 DOM 选区执行 document.execCommand("insertHTML")
    // —— 这正是 Anki 内部 x6 的底层机制,且会正确触发字段保存。

    function applyWithInfo(spec, info) {
        try {
            if (!info || !info.editable) return;

            // 重新聚焦字段并恢复捕获到的选区(防止点击/重渲染导致焦点漂移)
            try {
                if (info.editable.focus) info.editable.focus();
                const sel = rootSelection(info.editable);
                if (sel && info.range) {
                    sel.removeAllRanges();
                    sel.addRange(info.range);
                }
            } catch (e) {
                /* 恢复失败则尽力而为 */
            }

            const sel = rootSelection(info.editable);
            if (!sel || sel.rangeCount === 0) return;
            const range = sel.getRangeAt(sel.rangeCount - 1);

            const wrapper = findWrapper(range, spec.name, info.editable);
            if (wrapper) {
                unwrap(wrapper, spec.name);
                return;
            }

            const tag = spec.tag || "span";
            if (range.collapsed) {
                insertEmpty(info, tag, spec.name);
            } else {
                const open = "<" + tag + ' class="' + escapeAttr(spec.name) + '">';
                const close = "</" + tag + ">";
                document.execCommand("insertHTML", false, open + selectedHtml(range) + close);
            }
        } catch (e) {
            console.error("[StyleButtons] apply failed", e);
        }
    }

    function apply(spec) {
        applyWithInfo(spec, getSelectionInfo());
    }

    ns.apply = apply;

    // ---- 快捷键 ----------------------------------------------------------

    function parseCombo(str) {
        if (!str) return null;
        const combo = { ctrl: false, shift: false, alt: false, meta: false, key: "" };
        str.split("+").forEach(function (part) {
            const p = part.trim().toLowerCase();
            if (p === "ctrl" || p === "control") combo.ctrl = true;
            else if (p === "shift") combo.shift = true;
            else if (p === "alt" || p === "option") combo.alt = true;
            else if (p === "cmd" || p === "meta" || p === "command") combo.meta = true;
            else if (p) combo.key = p;
        });
        return combo.key ? combo : null;
    }

    function matchesCombo(e, combo) {
        return (
            !!e.ctrlKey === combo.ctrl &&
            !!e.shiftKey === combo.shift &&
            !!e.altKey === combo.alt &&
            !!e.metaKey === combo.meta &&
            (e.key || "").toLowerCase() === combo.key
        );
    }

    if (!ns._kbBound) {
        ns._kbBound = true;
        document.addEventListener(
            "keydown",
            function (e) {
                if (!ns.shortcuts || ns.shortcuts.length === 0) return;
                for (let i = 0; i < ns.shortcuts.length; i++) {
                    const sc = ns.shortcuts[i];
                    if (matchesCombo(e, sc.combo)) {
                        e.preventDefault();
                        e.stopPropagation();
                        apply(sc.spec);
                        return;
                    }
                }
            },
            true
        );
    }

    // 点击下拉之外时关闭“更多”菜单(全局只绑定一次,避免随重渲染泄漏)
    if (!ns._menuCloserBound) {
        ns._menuCloserBound = true;
        document.addEventListener(
            "click",
            function (e) {
                const bar = document.getElementById("sbfe-bar");
                if (!bar) return;
                const menu = bar.querySelector(".sbfe-menu");
                const wrap = bar.querySelector(".sbfe-more-wrap");
                if (menu && menu.classList.contains("open") && wrap && !wrap.contains(e.target)) {
                    menu.classList.remove("open");
                }
            },
            true
        );
    }

    // ---- 拖拽排序 --------------------------------------------------------

    function pointInRect(e, r) {
        return e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
    }

    // 在 container 中,根据光标位置把 el 插入到合适处。
    //   orientation: 'h' 按 X 比较(工具栏),'v' 按 Y 比较(下拉)
    function insertInto(container, el, e, orientation) {
        const sibs = Array.prototype.slice.call(container.children).filter(function (c) {
            return c !== el && c.nodeType === 1 && c.hasAttribute && c.hasAttribute("data-sbfe-class");
        });
        for (let i = 0; i < sibs.length; i++) {
            const r = sibs[i].getBoundingClientRect();
            const mid = orientation === "h" ? r.left + r.width / 2 : r.top + r.height / 2;
            const pos = orientation === "h" ? e.clientX : e.clientY;
            if (pos < mid) {
                if (el.nextSibling !== sibs[i] && el !== sibs[i]) container.insertBefore(el, sibs[i]);
                return;
            }
        }
        // 落在最后:工具栏需保持“更多”包裹在末尾
        if (orientation === "h") {
            const moreWrap = container.querySelector(".sbfe-more-wrap");
            if (moreWrap) {
                container.insertBefore(el, moreWrap);
                return;
            }
        }
        container.appendChild(el);
    }

    // 收集当前 DOM 中按钮的全局顺序(工具栏内 -> 下拉内)
    function collectOrder() {
        const bar = document.getElementById("sbfe-bar");
        const order = [];
        if (!bar) return order;
        Array.prototype.slice.call(bar.children).forEach(function (c) {
            if (c.nodeType === 1 && c.hasAttribute && c.hasAttribute("data-sbfe-class")) {
                order.push(c.getAttribute("data-sbfe-class"));
            }
        });
        const menu = bar.querySelector(".sbfe-menu");
        if (menu) {
            menu.querySelectorAll("[data-sbfe-class]").forEach(function (c) {
                order.push(c.getAttribute("data-sbfe-class"));
            });
        }
        return order;
    }

    function persistAndRerender(menuWasOpen) {
        const order = collectOrder();
        if (typeof window.pycmd === "function" && ns.noteType) {
            window.pycmd(
                "sbfe_save_order:" + JSON.stringify({ noteType: ns.noteType, order: order })
            );
        }
        // 本地按新顺序重排 payload 并干净重渲染(修正可见/下拉划分与样式)
        if (ns._payload && ns._payload.classes) {
            const map = {};
            ns._payload.classes.forEach(function (c) {
                map[c.name] = c;
            });
            const reordered = [];
            order.forEach(function (name) {
                if (map[name]) reordered.push(map[name]);
            });
            // 保留未在 order 中的(理论上不会有)
            ns._payload.classes.forEach(function (c) {
                if (order.indexOf(c.name) === -1) reordered.push(c);
            });
            ns._payload.classes = reordered;
            ns._reopenMenu = !!menuWasOpen;
            render(ns._payload);
            ns._reopenMenu = false;
        }
    }

    // 为按钮/菜单项绑定“拖拽或点击”行为
    function wireDragOrClick(el, spec) {
        let pending = false;
        let dragging = false;
        let startX = 0;
        let startY = 0;
        let menuWasOpen = false;
        let capturedInfo = null; // mousedown 时捕获的选区(此刻字段仍持有选区)

        function onMove(e) {
            if (!pending) return;
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;
            if (!dragging && Math.sqrt(dx * dx + dy * dy) > ns._dragThreshold) {
                dragging = true;
                el.classList.add("sbfe-dragging");
                const bar = document.getElementById("sbfe-bar");
                const menu = bar && bar.querySelector(".sbfe-menu");
                menuWasOpen = !!(menu && menu.classList.contains("open"));
            }
            if (!dragging) return;
            e.preventDefault();

            const bar = document.getElementById("sbfe-bar");
            if (!bar) return;
            const menu = bar.querySelector(".sbfe-menu");

            if (menu && menu.classList.contains("open") && pointInRect(e, menu.getBoundingClientRect())) {
                insertInto(menu, el, e, "v");
            } else {
                insertInto(bar, el, e, "h");
            }
        }

        function onUp() {
            document.removeEventListener("mousemove", onMove, true);
            document.removeEventListener("mouseup", onUp, true);
            pending = false;
            if (dragging) {
                dragging = false;
                el.classList.remove("sbfe-dragging");
                persistAndRerender(menuWasOpen);
            } else {
                applyWithInfo(spec, capturedInfo);
            }
            capturedInfo = null;
        }

        el.addEventListener("mousedown", function (e) {
            if (e.button !== 0) return;
            // 先捕获选区(此刻焦点仍在字段),再 preventDefault 保住焦点
            capturedInfo = getSelectionInfo();
            e.preventDefault();
            pending = true;
            dragging = false;
            startX = e.clientX;
            startY = e.clientY;
            document.addEventListener("mousemove", onMove, true);
            document.addEventListener("mouseup", onUp, true);
        });
    }

    // ---- 样式表(只注入一次) -------------------------------------------

    function ensureStyle() {
        if (document.getElementById("sbfe-style")) return;
        const style = document.createElement("style");
        style.id = "sbfe-style";
        style.textContent =
            ".sbfe-bar{display:inline-flex;align-items:center;gap:2px;flex-wrap:var(--sbfe-wrap,nowrap);max-width:var(--sbfe-maxw,none);overflow-x:var(--sbfe-overflow,visible)}" +
            ".sbfe-sep{display:inline-block;width:1px;align-self:stretch;min-height:1.2em;margin:0 6px;background:var(--border-subtle,#ccc);opacity:.6}" +
            ".sbfe-btn{min-width:auto;padding:0 8px;white-space:nowrap;cursor:grab}" +
            ".sbfe-btn:active{cursor:grabbing}" +
            ".sbfe-btn .sbfe-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;vertical-align:middle}" +
            ".sbfe-dragging{opacity:.45}" +
            ".sbfe-more-wrap{position:relative;display:inline-block}" +
            ".sbfe-menu{position:absolute;top:100%;right:0;z-index:1000;min-width:140px;max-height:60vh;overflow-y:auto;margin-top:2px;padding:4px;background:var(--canvas,#fff);border:1px solid var(--border-subtle,#ccc);border-radius:5px;box-shadow:0 2px 8px rgba(0,0,0,.25);display:none}" +
            ".sbfe-menu.open{display:block}" +
            ".sbfe-menu-item{display:block;width:100%;text-align:left;padding:4px 8px;border:none;background:transparent;color:var(--fg,inherit);cursor:grab;border-radius:3px;white-space:nowrap}" +
            ".sbfe-menu-item:active{cursor:grabbing}" +
            ".sbfe-menu-item:hover{background:var(--highlight-bg,rgba(0,0,0,.08))}";
        document.head.appendChild(style);
    }

    // ---- 渲染按钮 --------------------------------------------------------

    function makeButton(cls, showPreview) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.tabIndex = -1;
        btn.className = "sbfe-btn linkb";
        btn.title = cls.tooltip || cls.label || cls.name;
        btn.setAttribute("data-sbfe-class", cls.name);

        if (cls.color) {
            const dot = document.createElement("span");
            dot.className = "sbfe-dot";
            dot.style.backgroundColor = cls.color;
            btn.appendChild(dot);
        }
        const label = document.createElement("span");
        label.textContent = cls.label || cls.name;
        if (showPreview && cls.previewStyle) label.setAttribute("style", cls.previewStyle);
        btn.appendChild(label);

        wireDragOrClick(btn, { name: cls.name, tag: cls.tag });
        return btn;
    }

    function makeMenuItem(cls, showPreview) {
        const item = document.createElement("button");
        item.type = "button";
        item.tabIndex = -1;
        item.className = "sbfe-menu-item";
        item.title = cls.tooltip || cls.label || cls.name;
        item.setAttribute("data-sbfe-class", cls.name);

        if (cls.color) {
            const dot = document.createElement("span");
            dot.className = "sbfe-dot";
            dot.style.backgroundColor = cls.color;
            item.appendChild(dot);
        }
        const label = document.createElement("span");
        label.textContent = cls.label || cls.name;
        if (showPreview && cls.previewStyle) label.setAttribute("style", cls.previewStyle);
        item.appendChild(label);

        wireDragOrClick(item, { name: cls.name, tag: cls.tag });
        return item;
    }

    function render(payload) {
        try {
            ensureStyle();

            const old = document.getElementById("sbfe-bar");
            if (old) old.remove();

            ns.i18n = (payload && payload.i18n) || {};
            ns.noteType = (payload && payload.noteType) || "";
            ns._payload = payload || null;

            const classes = (payload && payload.classes) || [];
            if (classes.length === 0) {
                ns.shortcuts = [];
                return; // 无可显示 class:不渲染任何元素(E1 / 场景 6)
            }

            // 工具栏由 Svelte 异步渲染,首次加载时可能尚未挂载 -> 重试
            const toolbar = document.querySelector(".editor-toolbar");
            if (!toolbar) {
                const tries = (render._tries = (render._tries || 0) + 1);
                if (tries <= 40) {
                    setTimeout(function () {
                        render(payload);
                    }, 50);
                }
                return;
            }
            render._tries = 0;

            const bar = document.createElement("div");
            bar.id = "sbfe-bar";
            bar.className = "sbfe-bar";

            const sep = document.createElement("span");
            sep.className = "sbfe-sep";
            bar.appendChild(sep);

            const mode = (payload && payload.overflowMode) || "dropdown";
            const threshold = (payload && payload.overflowThreshold) || 8;
            const showPreview = !!(payload && payload.showPreview);

            if (mode === "newline") {
                bar.style.setProperty("--sbfe-wrap", "wrap");
            } else if (mode === "scroll") {
                bar.style.setProperty("--sbfe-overflow", "auto");
                bar.style.setProperty("--sbfe-maxw", "40vw");
            }

            const useDropdown = mode === "dropdown" && classes.length > threshold;
            const inlineCount = useDropdown ? threshold : classes.length;

            for (let i = 0; i < inlineCount; i++) {
                bar.appendChild(makeButton(classes[i], showPreview));
            }

            if (useDropdown) {
                const wrap = document.createElement("div");
                wrap.className = "sbfe-more-wrap";

                const moreBtn = document.createElement("button");
                moreBtn.type = "button";
                moreBtn.tabIndex = -1;
                moreBtn.className = "sbfe-btn linkb";
                moreBtn.style.cursor = "pointer";
                moreBtn.textContent = (ns.i18n.more || "More") + " ▾";

                const menu = document.createElement("div");
                menu.className = "sbfe-menu";
                for (let j = inlineCount; j < classes.length; j++) {
                    menu.appendChild(makeMenuItem(classes[j], showPreview));
                }

                moreBtn.addEventListener("mousedown", function (e) {
                    e.preventDefault();
                });
                moreBtn.addEventListener("click", function (e) {
                    e.preventDefault();
                    menu.classList.toggle("open");
                });

                wrap.appendChild(moreBtn);
                wrap.appendChild(menu);
                bar.appendChild(wrap);

                if (ns._reopenMenu) menu.classList.add("open");
            }

            toolbar.appendChild(bar);

            // 刷新快捷键映射
            ns.shortcuts = [];
            classes.forEach(function (cls) {
                const combo = parseCombo(cls.shortcut);
                if (combo) {
                    ns.shortcuts.push({ combo: combo, spec: { name: cls.name, tag: cls.tag } });
                }
            });
        } catch (e) {
            console.error("[StyleButtons] render failed", e);
        }
    }

    ns.render = render;
})();
