# Hul 的 Agent 深色工程控制台改造实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有功能型三栏页面改造成中文深色工程控制台，同时保持会话、聊天、Citation 与 Trace 的既有功能和 API 契约。

**Architecture:** 仅调整 Next.js 展示层。`globals.css` 提供颜色、表面、间距和动效 token；`ConsolePage` 负责整体框架；聊天、引用和 Trace 组件分别承担自己的信息密度与交互呈现。Zustand、TanStack Query、BFF 和 Python API 均不修改。

**Tech Stack:** Next.js App Router、React、TypeScript、Tailwind CSS、Radix UI、TanStack Query、Zustand、Vitest、React Testing Library。

## 全局约束

- 保持浏览器仅访问 `/api/...`，不修改 Python 后端和 API 字段。
- 保持中文用户文案、严格 TypeScript，禁止新增 UI 动画依赖。
- 使用深色工程控制台配色；动态数值使用等宽数字；按钮最小可点击区域为 40px。
- 不改变会话隔离、ChatTurn 绑定、Citation 与 Trace 的行为。

---

### Task 1: 深色视觉基础与顶部框架

**Files:**
- Modify: `frontend/app/globals.css`
- Modify: `frontend/components/console-page.tsx`
- Test: `frontend/tests/console-page.test.tsx`

**Interfaces:**
- Consumes: `useConversationStore` 的 `currentSessionId`、`turnsBySessionId`、`addSession`。
- Produces: 包含品牌栏、连接状态、会话栏、聊天主区与调试栏的 `ConsolePage`。

- [ ] **Step 1: 写入失败测试，断言深色控制台的关键可访问区域存在。**

```tsx
render(<ConsolePage />);
expect(screen.getByRole("banner", { name: "Hul 的 Agent 控制台" })).toBeTruthy();
expect(screen.getByRole("complementary", { name: "会话列表" })).toBeTruthy();
expect(screen.getByRole("complementary", { name: "调试面板" })).toBeTruthy();
```

- [ ] **Step 2: 运行失败测试。**

Run: `npx.cmd vitest run tests/console-page.test.tsx`

Expected: FAIL，缺少品牌栏或命名区域。

- [ ] **Step 3: 实现深色 token 和整体框架。**

```tsx
<main className="console-shell">
  <header aria-label="Hul 的 Agent 控制台" className="console-header">…</header>
  <div className="console-layout">…</div>
</main>
```

`globals.css` 定义 `--console-bg`、`--console-surface`、`--console-border`、`--console-accent` 和 `--console-muted`，并为按钮限定 `transition-property: transform, background-color, border-color, color` 与 `:active { scale: .96; }`。

- [ ] **Step 4: 运行测试确认通过。**

Run: `npx.cmd vitest run tests/console-page.test.tsx`

Expected: PASS。

### Task 2: 聊天、引用与 Trace 的信息密度改造

**Files:**
- Modify: `frontend/components/chat-workspace.tsx`
- Modify: `frontend/components/citation-panel.tsx`
- Modify: `frontend/components/trace-panel.tsx`
- Test: `frontend/tests/chat-workspace.test.tsx`
- Test: `frontend/tests/citation-panel.test.tsx`
- Test: `frontend/tests/trace-panel.test.tsx`

**Interfaces:**
- Consumes: 既有 `ChatTurn`、`Citation`、`RetrievalTrace` 与 `agentApi`。
- Produces: 样式化消息卡片、Citation 卡片、紧凑中文 Trace Tabs；不改变 props 和返回数据。

- [ ] **Step 1: 写入失败测试，断言聊天与检索轨迹拥有中文语义区域。**

```tsx
expect(screen.getByRole("region", { name: "聊天记录" })).toBeTruthy();
expect(screen.getByRole("region", { name: "检索阶段摘要" })).toBeTruthy();
```

- [ ] **Step 2: 运行对应失败测试。**

Run: `npx.cmd vitest run tests/chat-workspace.test.tsx tests/trace-panel.test.tsx`

Expected: FAIL，缺少语义区域。

- [ ] **Step 3: 实现卡片与数据样式。**

```tsx
<section aria-label="聊天记录" className="chat-timeline">…</section>
<section aria-label="检索阶段摘要" className="trace-summary">…</section>
```

消息、引用和 Trace 都使用 `console-surface`，耗时与数量使用 `tabular-nums`，表格保留横向滚动而不截断 Chunk ID。

- [ ] **Step 4: 运行组件测试确认通过。**

Run: `npx.cmd vitest run tests/chat-workspace.test.tsx tests/citation-panel.test.tsx tests/trace-panel.test.tsx`

Expected: PASS。

### Task 3: 响应式复核与完整验证

**Files:**
- Modify: `frontend/components/console-page.tsx`
- Test: `frontend/tests/console-page.test.tsx`

**Interfaces:**
- Consumes: 既有 Sheet、TracePanel、SessionList。
- Produces: 桌面三栏与小屏会话/调试抽屉保持一致的中文界面。

- [ ] **Step 1: 写入失败测试，断言小屏抽屉入口中文化。**

```tsx
expect(screen.getByRole("button", { name: "会话" })).toBeTruthy();
expect(screen.getByRole("button", { name: "调试信息" })).toBeTruthy();
```

- [ ] **Step 2: 运行失败测试。**

Run: `npx.cmd vitest run tests/console-page.test.tsx`

Expected: FAIL，若入口缺失或未使用中文名称。

- [ ] **Step 3: 完成响应式 class 与 aria-label 调整。**

```tsx
<aside aria-label="会话列表" className="hidden lg:block">…</aside>
<aside aria-label="调试面板" className="hidden lg:block">…</aside>
```

- [ ] **Step 4: 运行完整前端验证。**

Run: `npm.cmd run test; npm.cmd run typecheck; npm.cmd run lint; npm.cmd run build`

Expected: Vitest 全绿，TypeScript、ESLint 和生产构建均成功。
