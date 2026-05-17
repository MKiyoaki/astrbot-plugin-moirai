# TODO

## 🚧 进行中：Persona 隔离 + 配置拆分 + WebUI 主架构升级

Plan 文件：`C:\Users\Drgar\.claude\plans\1-bug-2-streamed-abelson.md`

### 📋 大计划：整体架构（交接必读）

**目标**：让 Moirai 支持多 Bot Persona（AstrBot 端可以配多个 bot 人格）下的**数据隔离**。每个 persona 在 WebUI 中看到独立的事件 / 印象 / 关系，但**设置全部共享**（plugin_config.json 还是同一份）。同时支持"All Personas"汇总视图把所有 persona 的数据放到一张图。**绝不破坏旧版本数据**。

**核心方案 — 行级隔离**（不是分库）：
- DB 表 `events` / `impressions` / `personas` 各加一列 `bot_persona_name TEXT`
- `NULL` 语义 = "遗留 / 默认 persona"（迁移前的所有数据自动是 NULL）
- 写入：事件归属由 `core/extractor/extractor.py:_get_bot_persona()` 推断当前 AstrBot 激活的 persona name（扫 `personas` 表中 `platform="internal"` 的 primary_name），然后透传到下游 Impression 写入
- 读取：repository 的 `list_*` 方法加 `bot_persona_name=` / `include_legacy=True` 参数；SQL 拼接为 `(bot_persona_name = ? OR bot_persona_name IS NULL)`，默认带遗留行，让选了 Alice 的人也能看到迁移前的数据
- API：所有 `/api/events` `/api/graph` `/api/archived_events` 等接受 `?persona=Alice` query；不带 = 汇总视图
- 新端点 `GET /api/personas/bots` 返回所有出现过的 bot_persona_name + 事件计数，给前端 selector 用

**核心方案 — Impression 表 unique key 修复**：
- 旧 `UNIQUE(observer_uid, subject_uid, scope)` 升级为 `UNIQUE(observer, subject, scope, ifnull(bot_persona_name, ''))`
- SQLite 的 inline UNIQUE 对 NULL 视为不同，所以**必须**用 `CREATE UNIQUE INDEX ... ifnull(...)` 表达式索引（migration 010 已经做了）
- `ON CONFLICT(observer, subject, scope, ifnull(bot_persona_name, ''))` 用同样的表达式匹配索引

**核心方案 — 数据流**：

```
AstrBot 消息 → MessageRouter → MessageWindow
                                    ↓ 关窗
                       Extractor 提取 Event
                                    ↓ event.bot_persona_name = _get_bot_persona()
                                Event 写入 DB
                                    ↓
            SocialOrientationAnalyzer.analyze(..., bot_persona_name=event.bot_persona_name)
                                    ↓
                       Impression 写入 DB（带 bot_persona_name）
                                    ↓
                       WebUI ?persona=Alice → repo.list_*(bot_persona_name='Alice')
                                    ↓
                       前端 store.currentPersonaName 决定查哪个 scope
```

**前端架构**：
- store 加 `currentPersonaName: string | null` + `scopeMode: 'single' | 'all'`，localStorage 持久化
- Sidebar 顶部 PersonaSelector 全局可切
- 首次启动弹 FirstLaunchPersonaPicker（受 `persona_default_view_mode` 配置控制）
- 每个 page 在 useEffect 依赖 store 的 persona 状态，变化时重新 fetch

**Persona 合并 (Phase 4)**：
- 后端 `POST /api/personas/{src}/merge/{target}` 用事务 UPDATE 把 events/impressions/personas 的 bot_persona_name 从 src 改为 target
- 难点：impressions 的 unique index 可能在合并时冲突（如果 src 和 target 都有 (obs, subj, scope) 同 tuple 的行）。采用"target wins"策略：先 DELETE src 中和 target 冲突的行，再 UPDATE 剩余
- 审计日志（可关）：`data_dir/audit/persona_merge.jsonl`

**关键决策（用户已确认）**：
- 隔离键采用复用已有的 `bot_persona_name` 字符串（不引入新的 UID）
- 首次进入：localStorage 记上次 + 首次弹窗
- 登录 UI：仅 polish 保留布局

**主动 defer（明确不做）**：
- Partitioner 按 persona 拆窗（窗口本就单 persona）
- 每 persona 独立 sqlite db（与"汇总视图"冲突）
- Personas 表实际填 `bot_persona_name`（persona 是共享实体；只在 impressions/events 上做隔离即可）
- 多用户 / 协作 / 权限

**关键文件总览**：
- 配置：`_conf_schema.json`、`core/config.py`、`web/frontend/app/config/page.tsx`、`web/frontend/lib/i18n.ts`
- 后端 DB：`migrations/010_persona_isolation_scope.sql`、`core/domain/models.py`、`core/repository/{base,sqlite,memory}.py`
- 后端业务：`core/extractor/extractor.py`、`core/social/orientation_analyzer.py`
- 后端 API：`web/plugin_routes.py`（生产路径）、`web/server.py`（dev/tests 路径）
- 前端：`web/frontend/lib/{store,api,i18n}.ts`、`web/frontend/components/{layout,shared,library}/*.tsx`

---

### Phase 1 — 配置拆分 + 4 个新配置键
- [x] `_conf_schema.json` 把 `relation`（19 字段）拆为 `relation` / `scheduled` / `debug_display` 三组
- [x] `relation` 组内新增 `persona_isolation_legacy_visible` / `persona_merge_audit_enabled` / `persona_default_view_mode` 三键，`persona_isolation_enabled` 默认改为 `true`
- [x] `core/config.py` 加 3 个新 getter property
- [x] `web/frontend/app/config/page.tsx` 同步拆 SECTIONS + 加 FIELD_DEPENDENCIES 联动禁用
- [x] `web/frontend/lib/i18n.ts` 三语 (zh/ja/en) 全部加 section / field 标签

### Phase 2 — 后端 Persona 隔离骨架（向前兼容）
- [x] `migrations/010_persona_isolation_scope.sql` — personas 加列；impressions 重建表 + `CREATE UNIQUE INDEX ... ifnull(bot_persona_name, '')`；events 加索引
- [x] `core/domain/models.py` — `Persona.bot_persona_name` / `Impression.bot_persona_name` 字段，默认 None
- [x] `core/repository/sqlite.py` — read/write 路径都处理 bot_persona_name；`ON CONFLICT(...,ifnull(bot_persona_name,''))` 配合新索引；`_safe_get` 兼容旧 row factory
- [x] Smoke test：全 10 migration 干净跑通；Upsert NULL→NULL 覆盖；NULL/Alice/Bob 三行并存；现有 455 tests 全过

### Phase 3 — WebUI Persona 上下文 + API 透传 + 写路径 wiring（进行中）

**Phase 3a — 后端写路径 wiring**
- [x] `core/social/orientation_analyzer.py` — `analyze()` / `_upsert_impression()` 接受 `bot_persona_name`，传给 Impression
- [x] `core/extractor/extractor.py` — 调 analyzer 时透传 `event.bot_persona_name`
- [ ] `core/adapters/identity.py` — 创建 Persona 时填 `bot_persona_name`（**defer**：persona 是共享实体，不必按 bot 隔离；视后续 UI 需求再决定）
- [ ] `core/sync/parser.py` / `core/sync/syncer.py` — Impression 构造传 `bot_persona_name=None`（**defer**：MD 同步是旁路，先不动）

**Phase 3b — 后端 repository 过滤 + API 透传**
- [x] `core/repository/base.py` — `ImpressionRepository.get/list_by_observer/list_by_subject` + `EventRepository.list_all/list_by_group/list_by_status` 加 `bot_persona_name` / `include_legacy` 参数
- [x] `core/repository/sqlite.py` — SQL 用 `(bot_persona_name = ? OR bot_persona_name IS NULL)` 过滤；`_persona_where` helper；`get` 用 `ifnull(bot_persona_name, '') = ifnull(?, '')` 精确匹配
- [x] `core/repository/memory.py` — In-memory 实现 4-tuple key；`_persona_matches` helper
- [x] `web/plugin_routes.py` — `events_data` / `graph_data` 加 `bot_persona_name` kwarg；`_handle_events` / `_handle_graph_guarded` 读 `?persona=` 透传
- [x] `web/plugin_routes.py` — 新增 `_handle_bot_personas_list` + `GET /api/personas/bots` 路由
- [x] `web/server.py` — 同步上述改动（dev/tests 路径）
- [x] 测试：150 tests pass（含 test_webui, test_graph_scope, test_sqlite_repo 等）

**Phase 3c — 前端 store + API + UI 组件（待办）**
- [ ] `web/frontend/lib/store.tsx` — `currentPersonaName: string | null` + `scopeMode: 'single' \| 'all'`，localStorage 持久化
- [ ] `web/frontend/lib/api.ts` — list/get 加可选 `persona?: string | null` query；加 `personas.listBots()`
- [ ] `web/frontend/components/shared/persona-selector.tsx` — 新建，sidebar 顶部下拉
- [ ] `web/frontend/components/shared/first-launch-persona-picker.tsx` — 新建，首次弹窗
- [ ] `web/frontend/components/layout/app-shell.tsx` — 挂 first-launch modal
- [ ] `web/frontend/components/layout/app-sidebar.tsx` — 顶部嵌入 selector
- [ ] events/library/graph/recall/stats 各 page — 在 loadXxx 里读 store 的 persona 透传给 api
- [ ] `web/frontend/lib/i18n.ts` — picker / "All Personas" / "Default" 文案三语

#### Phase 3c 技术实现（交接细节）

**1. Store 扩展** — [`web/frontend/lib/store.tsx`](web/frontend/lib/store.tsx)

```ts
// AppState 加：
currentPersonaName: string | null   // 选中的 bot persona；null 仅在 scopeMode='all' 时合法
scopeMode: 'single' | 'all'         // 区分 "选了具体 persona" vs "选了汇总"
firstLaunchDone: boolean             // 是否已经过过首次 picker

// AppActions 加：
setCurrentPersona: (name: string | null, mode: 'single' | 'all') => void
setFirstLaunchDone: (done: boolean) => void
```

localStorage keys（沿用 `getStored` / `setStored` 工具）：
- `em_current_persona_name` — string 或 ""（空 = null）
- `em_persona_scope_mode` — `'single'` / `'all'`
- `em_first_launch_done` — `'1'`

初始化：在 AppProvider 顶部 `useState(() => getStored(...))` 三个 state；setter 同步写 localStorage。
**重要**：把这三个 state 纳入 `ctx` 的 useMemo 依赖，否则切换时不会触发下游 useEffect。

**2. API 层** — [`web/frontend/lib/api.ts`](web/frontend/lib/api.ts)

```ts
// 工具：拼 persona query
function withPersona(url: string, persona: string | null | undefined): string {
  if (!persona) return url
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}persona=${encodeURIComponent(persona)}`
}

// 改造 events.list（保持向后兼容签名）：
events.list = (limit = 500, persona?: string | null) =>
  request<EventsResponse>(withPersona(`/api/events?limit=${limit}`, persona))

// 同样改：events.listArchived(persona?) / events.recycleBin(persona?) / graph.get(persona?)

// 新增：
personas.listBots = () =>
  request<{ items: { name: string | null; event_count: number }[] }>('/api/personas/bots')
```

**3. PersonaSelector** — `web/frontend/components/shared/persona-selector.tsx`（新建）

用 shadcn `Select`（不需要搜索）。Props 接受 `compact?: boolean` 控制 sidebar vs page header 样式。

```tsx
export function PersonaSelector({ compact = false }: { compact?: boolean }) {
  const { i18n, currentPersonaName, scopeMode, setCurrentPersona } = useApp()
  const [bots, setBots] = useState<{ name: string | null; event_count: number }[]>([])
  
  useEffect(() => {
    api.personas.listBots().then(r => setBots(r.items))
  }, [])
  
  const value = scopeMode === 'all' ? '__all__' : (currentPersonaName ?? '__legacy__')
  
  const handleChange = (v: string) => {
    if (v === '__all__') setCurrentPersona(null, 'all')
    else if (v === '__legacy__') setCurrentPersona(null, 'single')
    else setCurrentPersona(v, 'single')
  }
  
  return (
    <Select value={value} onValueChange={handleChange}>
      <SelectTrigger className={compact ? 'h-8 text-xs' : ''}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__all__">{i18n.persona.allPersonas}</SelectItem>
        <SelectItem value="__legacy__">{i18n.persona.defaultLegacy}</SelectItem>
        {bots.filter(b => b.name).map(b => (
          <SelectItem key={b.name!} value={b.name!}>{b.name} ({b.event_count})</SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
```

**4. FirstLaunchPersonaPicker** — `web/frontend/components/shared/first-launch-persona-picker.tsx`（新建）

```tsx
export function FirstLaunchPersonaPicker({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { i18n, setCurrentPersona, setFirstLaunchDone } = useApp()
  const [bots, setBots] = useState<...>([])
  useEffect(() => { if (open) api.personas.listBots().then(r => setBots(r.items)) }, [open])
  
  const pick = (name: string | null, mode: 'single' | 'all') => {
    setCurrentPersona(name, mode)
    setFirstLaunchDone(true)
    onClose()
  }
  
  return (
    <Dialog open={open} onOpenChange={() => {/* 不允许 esc 关闭 */}}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{i18n.persona.firstLaunchTitle}</DialogTitle>
          <DialogDescription>{i18n.persona.firstLaunchDesc}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          {bots.filter(b => b.name).map(b => (
            <Button key={b.name!} variant="outline" onClick={() => pick(b.name!, 'single')}>
              {b.name} <Badge variant="secondary">{b.event_count}</Badge>
            </Button>
          ))}
          <Separator />
          <Button variant="ghost" onClick={() => pick(null, 'all')}>{i18n.persona.viewAll}</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
```

**5. AppShell 挂 modal** — [`web/frontend/components/layout/app-shell.tsx`](web/frontend/components/layout/app-shell.tsx)

```tsx
const { authenticated, firstLaunchDone, /* persona_default_view_mode from /api/config */ } = useApp()
const [pickerOpen, setPickerOpen] = useState(false)

useEffect(() => {
  if (!authenticated) return
  if (firstLaunchDone) return
  const mode = pluginConfigValues.persona_default_view_mode || 'remember'
  if (mode === 'all') {
    setCurrentPersona(null, 'all')
    setFirstLaunchDone(true)  // 不弹窗，直接进入
  } else if (mode === 'force_pick' || mode === 'remember') {
    setPickerOpen(true)  // 弹
  }
}, [authenticated, firstLaunchDone])

// 渲染：
<FirstLaunchPersonaPicker open={pickerOpen} onClose={() => setPickerOpen(false)} />
```

注意 `force_pick` 模式下每次启动都弹（不 setFirstLaunchDone）。`remember` + 已有 currentPersonaName 时跳过弹窗。

**6. Sidebar 嵌入** — [`web/frontend/components/layout/app-sidebar.tsx`](web/frontend/components/layout/app-sidebar.tsx)

在品牌 logo 下方加 `<PersonaSelector compact />`，建议放在 sidebar header / `SidebarGroup` 顶部 padding 区域。

**7. Page 级 useEffect wiring**

每个 page 改造模式（以 events 为例）：

```tsx
const { currentPersonaName, scopeMode, ... } = useApp()
const personaParam = scopeMode === 'all' ? null : currentPersonaName

const loadEvents = useCallback(async () => {
  const data = await api.events.list(1000, personaParam)
  setRawEvents(data.items)
}, [setRawEvents, appToast, i18n.events.loadError, personaParam])  // ← 关键：加入依赖

useEffect(() => { loadEvents() }, [loadEvents])
```

需要改的 page：
- [`web/frontend/app/events/page.tsx`](web/frontend/app/events/page.tsx) — events.list / listArchived / recycleBin
- [`web/frontend/app/library/page.tsx`](web/frontend/app/library/page.tsx) — events.list
- [`web/frontend/app/graph/page.tsx`](web/frontend/app/graph/page.tsx) — graph.get
- [`web/frontend/app/recall/page.tsx`](web/frontend/app/recall/page.tsx) — events.list（作为补充检索）
- [`web/frontend/app/stats/page.tsx`](web/frontend/app/stats/page.tsx) — stats 暂不带 persona（先确认 stats 是否需要隔离；本期 defer）

**8. i18n 文案** — [`web/frontend/lib/i18n.ts`](web/frontend/lib/i18n.ts) — 三个 locale 各加：

```ts
persona: {
  allPersonas: '全部 Persona' / 'All Personas' / 'すべてのペルソナ',
  defaultLegacy: '默认 (旧数据)' / 'Default (Legacy)' / 'デフォルト (旧データ)',
  firstLaunchTitle: '选择要查看的 Bot Persona',
  firstLaunchDesc: '不同的 Bot Persona 拥有独立的记忆视图。可随时在 Sidebar 顶部切换。',
  viewAll: '先看全部记忆',
  currentScope: '当前作用域',
}
```

**9. 陷阱 / 注意事项**

- **app context 引用稳定性**：因为 stats 轮询每次都会让 `ctx` object 引用变（参见 `commit af0c3e4`），page 里写 `useCallback(..., [app, ...])` 会导致每次轮询都重 fetch。**必须**解构出稳定回调和稳定值：`const { currentPersonaName, scopeMode, setRawEvents, toast: appToast } = useApp()`，依赖里只列这些原子值。
- **PersonaSelector 自身的 listBots 调用**：仅在 mount 时调一次；切换 persona 后不需要 refetch 列表（除非用户合并了 persona — 那是 Phase 4 的责任）。
- **API 层向后兼容**：persona 参数永远是可选第二个参数；旧调用点不传等同于 `null = 不过滤`。
- **首次 picker 显示时机**：必须等 `authenticated === true && !authLoading`，否则会闪一下登录 → picker → 内容。
- **"汇总视图"和"遗留视图"的区分**：
  - `scopeMode='all'` → 不带 `?persona=` → 后端返回所有数据（包括所有 bot persona 的 + NULL 的）
  - `scopeMode='single'` + `currentPersonaName=null` → 带 `?persona=`？这里有歧义。建议：`single + null` 表示"只看 legacy NULL 行"，对应"默认 (旧数据)"选项。前端在 query 里发 `?persona=` 不带值或专门拼一个特殊 token？**最安全做法**：API 层把 `null` 的 persona 翻译成不带 query（=后端返汇总），由前端 `scopeMode` 决定语义。Phase 4 加合并后这里要重看。

**10. 验证步骤**

1. `npm install && npm run build && python tools/sync_frontend.py -f`
2. 启动后端，打开 WebUI
3. 首次进入：弹 picker → 选一个 persona → 进入只显示该 persona 数据的视图
4. Sidebar 顶部切到"全部 Persona" → 数据汇总显示
5. devtools Network 面板：选了 persona 时 `/api/events` 带 `?persona=Alice`
6. 刷新页面：选项保持不变（localStorage 起效）
7. 配置页关闭 `persona_isolation_enabled`：刷新后**不**弹 picker，全部使用汇总视图（**TODO 待落实**：当前 store 没有读这个开关，要在 store 初始化时读 `/api/config` 的 values；可放到 Phase 3c 末尾或推迟到 Phase 4）

### Phase 4 — Persona 合并 / 转移
- [ ] 后端 `POST /api/personas/{src}/merge/{target}` — 事务内更新 events/impressions/personas，可选写 `audit/persona_merge.jsonl`
- [ ] 后端 `GET /api/personas/{src}/merge/{target}/preview` — 返回影响行数
- [ ] `web/frontend/components/library/merge-persona-dialog.tsx` — 新建对话框（带预览 + 二次确认 + sudo 限制）
- [ ] `web/frontend/components/library/persona-row.tsx` — 加 "🔀 转移到…" 按钮
- [ ] 合并后自动把 store 的 `currentPersonaName` 切到 target

#### Phase 4 技术实现（交接细节）

**1. URL 设计取舍**

合并的 src / target 是**字符串**（bot_persona_name），可能含中文、空格、特殊字符。`POST /api/personas/{src}/merge/{target}` 这种 path 参数对 URL-encode 友好但容易出问题。**推荐**：

```
POST /api/personas/merge        body: { src: "Alice", target: "Bob" }
GET  /api/personas/merge/preview?src=Alice&target=Bob
```

更易传非 ASCII，也更符合"动作"语义。

**2. 后端 — 关键 SQL** ([`web/plugin_routes.py`](web/plugin_routes.py))

合并 impressions 的难点：`UNIQUE(observer, subject, scope, ifnull(bot_persona_name, ''))` 索引会在 src→target 改名时和 target 已有的行冲突。

策略：**target wins**（保留 target 已有的行，丢弃 src 中冲突的行）

```sql
-- Step 1: 删除 src 中和 target 已有行冲突的 impressions
DELETE FROM impressions
WHERE bot_persona_name = :src
  AND EXISTS (
    SELECT 1 FROM impressions t
    WHERE t.observer_uid = impressions.observer_uid
      AND t.subject_uid = impressions.subject_uid
      AND t.scope = impressions.scope
      AND ifnull(t.bot_persona_name, '') = ifnull(:target, '')
  );

-- Step 2: 把剩余的 src 行改名为 target
UPDATE impressions SET bot_persona_name = :target WHERE bot_persona_name = :src;

-- Step 3: events 不存在冲突（PK 是 event_id），直接 update
UPDATE events SET bot_persona_name = :target WHERE bot_persona_name = :src;

-- Step 4: personas 同上（PK 是 uid）
UPDATE personas SET bot_persona_name = :target WHERE bot_persona_name = :src;
```

整个流程必须在**单个事务**内，用 `_txn(self._db, self._lock)` 包住。

**3. 后端 handler 模板**

```python
async def _handle_persona_merge_preview(self, request):
    src = request.rel_url.query.get('src') or ''
    target = request.rel_url.query.get('target') or ''
    if not src or not target:
        return _json({'error': 'src/target required'}, 400)
    
    db = self._event_repo._db  # type: ignore
    async with db.execute("SELECT COUNT(*) FROM events WHERE bot_persona_name = ?", (src,)) as cur:
        events_n = (await cur.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM impressions WHERE bot_persona_name = ?", (src,)) as cur:
        imps_total = (await cur.fetchone())[0]
    async with db.execute("""
        SELECT COUNT(*) FROM impressions s WHERE s.bot_persona_name = ?
        AND EXISTS (SELECT 1 FROM impressions t WHERE t.observer_uid=s.observer_uid
            AND t.subject_uid=s.subject_uid AND t.scope=s.scope
            AND ifnull(t.bot_persona_name,'') = ifnull(?, ''))
    """, (src, target)) as cur:
        imps_conflicts = (await cur.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM personas WHERE bot_persona_name = ?", (src,)) as cur:
        personas_n = (await cur.fetchone())[0]
    
    return _json({
        'events_moved': events_n,
        'impressions_moved': imps_total - imps_conflicts,
        'impressions_dropped': imps_conflicts,
        'personas_moved': personas_n,
    })

async def _handle_persona_merge(self, request):
    body = await _request_json(request)
    src, target = body.get('src'), body.get('target')
    if not src or not target or src == target:
        return _json({'error': 'invalid src/target'}, 400)
    
    db = self._event_repo._db  # type: ignore
    async with _txn(db, _get_db_lock(db)):
        # ... 上面那四条 SQL
    
    # 审计日志
    if self._cfg.persona_merge_audit_enabled:
        audit_path = self._data_dir / 'audit' / 'persona_merge.jsonl'
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps({
                'ts': time.time(), 'src': src, 'target': target,
                'events_moved': ..., 'impressions_moved': ..., 'personas_moved': ...,
            }, ensure_ascii=False) + '\n')
    
    return _json({...})
```

**注意**：在 dev 环境 `_event_repo._db` 可能是 None（in-memory repo）。Production 始终是 SQLite。建议加 isinstance 检查或在 repository base 暴露一个 `execute_raw()` 方法。

**4. 路由注册**（plugin_routes.py 第 ~228 行附近）

```python
(f"/api/personas/merge",            self._handle_persona_merge_guarded,   ["POST"], "Merge persona A → B"),
(f"/api/personas/merge/preview",    self._handle_persona_merge_preview,   ["GET"],  "Preview merge impact"),
```

合并要 sudo 模式，包 `self._wrap("sudo", ...)`。

**5. 前端 API**

```ts
// web/frontend/lib/api.ts
personas.mergePreview = (src: string, target: string) =>
  request<{ events_moved: number; impressions_moved: number; impressions_dropped: number; personas_moved: number }>(
    `/api/personas/merge/preview?src=${encodeURIComponent(src)}&target=${encodeURIComponent(target)}`
  )

personas.merge = (src: string, target: string) =>
  request<...>('/api/personas/merge', { method: 'POST', body: JSON.stringify({ src, target }) })
```

**6. MergePersonaDialog 组件** — `web/frontend/components/library/merge-persona-dialog.tsx`（新建）

```tsx
export function MergePersonaDialog({
  open, src, allPersonas, onClose, onMerged,
}: {
  open: boolean
  src: string
  allPersonas: { name: string }[]
  onClose: () => void
  onMerged: (target: string) => void
}) {
  const [target, setTarget] = useState<string>('')
  const [preview, setPreview] = useState<MergePreview | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [loading, setLoading] = useState(false)
  
  useEffect(() => {
    if (target && target !== src) {
      api.personas.mergePreview(src, target).then(setPreview)
    } else {
      setPreview(null)
    }
  }, [src, target])
  
  const handleMerge = async () => {
    setLoading(true)
    try {
      await api.personas.merge(src, target)
      onMerged(target)
      onClose()
    } finally { setLoading(false) }
  }
  
  return (
    <Dialog ...>
      <Select value={target} onValueChange={setTarget}>
        {allPersonas.filter(p => p.name !== src).map(p => <SelectItem ...>{p.name}</SelectItem>)}
      </Select>
      {preview && (
        <div className="text-sm space-y-1">
          <p>events 将转移：<b>{preview.events_moved}</b></p>
          <p>impressions 将转移：<b>{preview.impressions_moved}</b></p>
          {preview.impressions_dropped > 0 && (
            <p className="text-destructive">impressions 因冲突丢弃：<b>{preview.impressions_dropped}</b>（target 已有同 (obs, subj, scope) 行胜出）</p>
          )}
          <p>personas 将转移：<b>{preview.personas_moved}</b></p>
        </div>
      )}
      {!confirming ? (
        <Button variant="destructive" disabled={!target} onClick={() => setConfirming(true)}>
          继续
        </Button>
      ) : (
        <Button variant="destructive" disabled={loading} onClick={handleMerge}>
          {loading ? <Spinner /> : '确认合并'}
        </Button>
      )}
    </Dialog>
  )
}
```

**7. PersonaRow 加按钮** — [`web/frontend/components/library/persona-row.tsx`](web/frontend/components/library/persona-row.tsx)

在已有 "编辑 / 删除" 按钮旁加：

```tsx
{app.sudo && (
  <Button variant="ghost" size="icon" onClick={() => onMerge(persona)}>
    <GitMerge className="size-3" />  {/* lucide-react */}
  </Button>
)}
```

`onMerge` prop 从父组件（library/page.tsx）传入，打开 dialog。

**8. 合并后状态切换**

```tsx
const handleMerged = (target: string) => {
  if (app.currentPersonaName === src) {
    app.setCurrentPersona(target, 'single')  // 自动切到 target
  }
  // 刷新 personas 列表 + events
  loadAll()
}
```

**9. 陷阱 / 注意**

- **src / target 校验**：必须不相等、必须非空、必须都在 `/api/personas/bots` 返回列表里
- **AstrBot 端 personas 表的 `(platform="internal", physical_id="bot")` 绑定**：合并 personas 表中的 bot persona 后，相应的 identity_binding 也要 reattach 到 target uid。否则后续 `_get_bot_persona()` 可能找不到 bot
- **审计日志位置**：`data_dir/audit/`，确保 `parent.mkdir(parents=True, exist_ok=True)`
- **回滚**：当前方案无回滚（事务提交后不可逆）。如果担心，可以在事务前先备份 db 文件
- **测试**：写 `tests/test_persona_merge.py`：
  - happy path：src→target，事件 / 印象 / 人格行数符合预期
  - src=target 拒绝（400）
  - 冲突 impressions 数量正确报告
  - 审计日志生成 / 关闭开关时不生成

### Phase 5 — 登录界面 polish（保留布局）
- [ ] 右侧表单加 `radial-gradient` 背景光晕
- [ ] 密码 input 聚焦时丝线动画提速 1.5×
- [ ] 错误提示加 `slide-in-from-top-2 fade-in` + 红色脉冲
- [ ] 提交加载态加渐进文案 `login.verifying`（三语 i18n）
- [ ] 品牌 logo 微悬浮（仅桌面）

### Phase 6 —"全 Persona 主界面"图谱（可选 / 后续）
- [ ] graph 在 `scopeMode === 'all'` 时把每个 bot persona 渲染为超级节点
- [ ] 点击超级节点下钻到该 persona 的子图

### 主动 defer / 不在范围
- ❌ Partitioner 按 bot_persona 拆窗（实测窗口本就单 persona，价值低，不做）
- ❌ 每 persona 独立 sqlite db（与"汇总主界面"诉求冲突，本次走行级方案）
- ❌ 多用户 / 协作 / 权限模型

---

### 插件多语言支持（i18n）
在 `.astrbot-plugin/i18n/` 下创建 `zh-CN.json` 和 `en-US.json`，覆盖：
- `metadata.yaml` 的 `display_name`、`desc`
- `_conf_schema.json` 所有字段的 `description`、`hint`、`labels`

不动源码，只新增两个 JSON 文件。

### 前端对于archieved事件的相关管理显示和支持功能

---

## 后端架构优化与演进 (Refinement & Evolution)

### ✅ [设计] 叙事轴摘要向量化与分层 RAG（已实现）
- `events.event_type` 列区分 `episode` / `narrative`
- 每日摘要生成后自动写入 narrative Event 并向量化
- `RecallManager` 按关键词分类器（macro/micro/both）分层检索，`formatter.py` 按类型分段输出

### ✅ [性能] 周期性维护任务合并（已实现）
- `run_consolidated_maintenance()` 合并两个任务，共享一次全量 Persona 扫描和事件预加载
- 当 `persona_synthesis_enabled` 和 `relation_enabled` 均为 true 时，自动注册合并任务

### ✅ [质量] 语义提取策略预筛选（已实现）
- `core/extractor/noise_filter.py`：规则过滤纯表情包、极短消息、复读消息
- 在 `semantic` 策略的 DBSCAN 分段后、LLM 蒸馏前应用

### ✅ [架构] SSOT 边界（部分，待持续维护）
- DB 是唯一事实源；MD 文件是只读投影
- 仅 `IMPRESSIONS.md` 允许反向同步，其他文件禁止反向同步

---

## 待讨论的功能方向（Feature Discussions）

### [设计] 用户预设关系（Preset Impressions）

**背景**：目前 Impression 完全由 LLM 从对话中自动提取。希望支持管理员/用户为 bot 预设对某人的先验态度（如"朋友""仇人""亲人"），在 LLM 提取功能关闭时也能对 agent 行为生效。

**讨论中的分歧**：
- 预设关系使用枚举模板（朋友/仇人/亲人），由系统映射到 benevolence × power 双轴数值，`confidence` 设低（约 0.2）标记为先验；随真实对话积累会被更高置信度数据覆盖
- 担忧：双轴数值是从真实行为拟合来的，手动填入破坏数据来源一致性；且先验关系在 agent 判断中的权重理应很低

**两个待决定的子问题**：

1. **是否注入 system prompt？**
   - 仅可视化：出现在关系图中，不影响 agent 行为，完全安全
   - 注入 prompt：用弱化语气（"据初始设定，与 TA 关系为朋友"），对 agent 有实际影响，但权重难以精确控制
   - 折中：作为独立字段注入，与自动提取的 impression 分开，prompt 里明确区分两者来源

2. **数据存储位置**
   - 方案 A：写入现有 `Impression` 表，加 `is_pinned` flag 区分人工 vs 自动，extractor upsert 时跳过 pinned 记录
   - 方案 B：独立的 `PresetRelation` 表，完全不混入自动提取数据，判断结构无污染，但需要新增 repo/schema

**倾向**：方案 B + 仅可视化作为 MVP，后续视需求再开启 prompt 注入开关。

---

### [设计] 关系图管理操作（Graph CRUD）

**背景**：目前缺少对关系数据的精细化管理入口。

**合理的操作（待实现）**：
- 删除单条 impression：`DELETE /api/impressions/{observer}/{subject}/{scope}`
- 按 group 批量清除 impression（加确认弹窗）
- WebUI Library 页面对 impression 的直接删除入口

**不合理的操作（不做）**：
- 手动新建 persona（无行为依据，产生"无根"节点）
- 手动拖拽/重排关系图拓扑（破坏事件驱动的数据一致性）

---

## 待确认的设计决策（Deferred Decisions）

### [设计] narrative Event 的 inherit_from 下钻
当前 narrative Events 的 `inherit_from` 为空列表，不指向当天的 episode events。
待评估：向 `inherit_from` 写入当天所有 episode event_id 的 payload 开销（每天数十个 ID），
以及是否对”宏观→微观”上下文展开有实际价值。

### [架构] IMPRESSIONS.md 反向同步的长期去向
当前：FileWatcher（30s 轮询）+ 正则解析器，维护成本较高。
待评估：是否在 WebUI 新增直接的 impression 表单提交 API，将 FileWatcher 降级为”离线备份”入口。

### [设计] 分层 RAG 查询分类器精度提升
当前实现：关键词计数投票（`_MACRO_KWS` / `_MICRO_KWS`）。
待评估：接入轻量 embedding 相似度或 LLM 分类提升精度，但需权衡延迟开销。

### [可选优化] `run_memory_cleanup` 返回值 double-counting
`core/tasks/cleanup.py` 中 `total += archived` + `total += deleted` 会对同一次运行中
先被归档、后被永久删除的事件计数两次（测试失败：`test_memory_cleanup.py::test_cleanup_locked_event_not_deleted`）。
数据安全不受影响（`is_locked` 保护正常），仅影响返回值统计语义。
修复方案：只 `return deleted`，或改为返回 `{"archived": archived, "deleted": deleted}`。

