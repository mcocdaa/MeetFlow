# 项目概览卡片对齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让项目详情概览页桌面两列中同一行的卡片保持相同外框高度，同时保留单列移动端的内容自适应高度。

**Architecture:** 仅修改项目概览 Grid 容器的交叉轴对齐方式。浏览器依据同一行最高的卡片确定行高，并拉伸较短卡片；组件结构、数据流和响应式单列断点保持不变。Vitest 默认跳过 CSS，故在测试配置中仅为 `styles.css` 启用 CSS 处理，再通过 JSDOM 的 computed style 断言保护该规则；浏览器/容器复测确认实际渲染。

**Tech Stack:** Vue 3、CSS Grid、Vitest、Testing Library、Vite。

---

### Task 1: 为项目概览网格写失败的样式回归测试

**Files:**
- Modify: `frontend/vite.config.ts:11-17`
- Modify: `frontend/src/tests/project-workspace.test.ts:1-90`

- [x] **Step 1: 加载全局样式并写入失败断言**

在 `frontend/vite.config.ts` 的 `test` 中加入：

```ts
css: { include: [/styles\.css$/] },
```

并在现有 import 区加入：

```ts
import '../styles.css'
```

在 `keeps overview focused on project state and actionable summaries` 用例之后加入：

```ts
  it('stretches dashboard cards within each overview row', async () => {
    const { container } = render(ProjectDetailView)

    await screen.findByRole('heading', { name: '项目状态' })
    const grid = container.querySelector<HTMLElement>('.project-overview-grid')

    expect(grid).not.toBeNull()
    expect(getComputedStyle(grid as HTMLElement).alignItems).toBe('stretch')
  })
```

- [x] **Step 2: 确认测试在旧样式下失败**

Run:

```bash
npm --prefix frontend test -- --run src/tests/project-workspace.test.ts
```

Expected: 新用例失败，实际 `alignItems` 为 `start`，证明测试覆盖了截图中的网格收缩原因。

### Task 2: 拉伸同一网格行的项目概览卡片

**Files:**
- Modify: `frontend/src/styles.css:362`
- Test: `frontend/src/tests/project-workspace.test.ts`

- [x] **Step 1: 以最小 CSS 改动修复交叉轴对齐**

将项目概览规则中的：

```css
.project-overview-grid { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(18rem, .9fr); gap: 18px; align-items: start; }
```

改为：

```css
.project-overview-grid { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(18rem, .9fr); gap: 18px; align-items: stretch; }
```

不要增加固定高度、`min-height`、组件包装层或断点规则。

- [x] **Step 2: 确认针对性测试变绿**

Run:

```bash
npm --prefix frontend test -- --run src/tests/project-workspace.test.ts
```

Expected: 所有项目工作台测试通过，新的 computed-style 断言返回 `stretch`。

- [x] **Step 3: 运行完整前端验证**

Run:

```bash
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: Vitest 全部通过；生产构建 exit code 为 0。Vite 已知的主包体积告警可记录，但不能视为构建失败。

- [x] **Step 4: 重建并验证本地 Docker 页面**

Run:

```bash
docker compose build
docker compose up -d --force-recreate
curl --fail --silent --show-error http://127.0.0.1:18000/api/health
```

Expected: `meetflow:local` 重建完成，容器为 healthy，健康接口返回 `{\"status\":\"ok\"}`；在桌面两列项目概览中，同一行卡片底边对齐。

- [x] **Step 5: 提交实现**

```bash
git add frontend/src/styles.css frontend/src/tests/project-workspace.test.ts docs/superpowers/plans/2026-08-01-project-overview-card-alignment.md
git commit -m "fix: align project overview cards"
```
