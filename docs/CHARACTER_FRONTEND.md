# Character 前端流程

## 路由与入口

DEV-3.5只新增`/projects/:projectId/characters`和`/projects/:projectId/characters/:characterId`两个React路由。Project详情页的真实“查看角色”链接进入列表，列表项使用Character ID作为稳定key和可区分的编辑链接。Character ID只出现在编辑路径；cursor、ETag、profile和草稿不进入URL。当前没有全局Character路由或历史路由。

## 列表与稳定分页

列表区分`invalid_project`、`loading`、`project_not_found`、`empty`、`ready`和`error`。摘要仅显示Character ID、当前Revision ID、RevisionNumber、ConcurrencyVersion、name、role、created_at和updated_at，故意不读取、下载或显示profile，也不伪造total。一个Project可有多个Character，同名Character合法并保持为独立项。

服务端固定按`created_at DESC, character_id DESC`排序。前端不重排，只在用户点击“加载更多”时使用当前不透明`next_cursor`请求一页，校验Project归属、跨页ID唯一与合并顺序后追加。cursor只驻留hook内存，不解码、预取或自动加载。失败保留已有列表和同cursor；非法cursor只能由用户显式重载第一页清除。

## 创建

表单完整提交name、role和纯文本profile。name必填，name/role规范化后最多120个Unicode代码点，profile最多50000代码点并规范为LF；字段拒绝领域禁止控制字符。非法输入不获取Session或发POST，第一个非法字段获得焦点。同步锁保证一次用户操作最多一个POST，不查询或警告同名Character。

成功时直接采用严格校验的201响应，不额外GET；显式构造不含profile的摘要并插入顶部，保持旧cursor，清空表单并给出“查看新角色”链接。409`CHARACTER_ID_CONFLICT`是服务端ID冲突，不是同名冲突；它保留草稿、不改列表、不自动重试。

网络失败、abort、5xx或不可信成功响应标记“创建结果无法确认”。草稿和列表保持；用户可显式重读第一页后人工核对。由于同名合法，应用不依字段相等猜测原POST结果；只有用户确认重复创建风险后才重新启用提交。

## 编辑基线、完整替换与冲突

编辑页先验证Project/Character ID，再按Character ID执行一次GET并验证Project归属。可信GET或成功PUT的完整响应和共享强ETag构成内存baseline，draft由baseline的name、role、profile初始化。dirty比较领域规范化后的三个文本值，不使用对象引用。

手动保存以PUT完整替换三个字段，发送baseline ETag作为`If-Match`；PUT前不GET，不PATCH、自动保存、重试或合并。成功响应直接替换baseline/ETag并重置draft，不额外GET。确定性失败和保存结果未知都保留draft、旧baseline和ETag；后者要求显式读取服务器当前版本并人工选择。

合法412保留旧baseline、旧ETag、draft及expected/actual version/request ID，不自动GET或PUT。用户必须显式“读取服务器最新版本”；冲突面板只显示版本，不显示latest profile。然后可“采用服务器版本”丢弃草稿，或“保留草稿并重建基线”。后者不合并、不立即PUT；下一次仍必须手动保存并使用latest ETag。

## 隐私、无障碍与限制

profile、创建/编辑草稿、latest profile、ETag/If-Match、cursor、CSRF和Security Session只存在必要的进程/页面内存，不写入浏览器存储、Cookie、URL、history state、隐藏DOM、data属性、诊断文件或日志。表单有真实label、字段错误关联与首错聚焦；加载、成功、错误和冲突使用语义化状态，冲突标题可聚焦。

当前没有Character Revision历史、Diff、回滚/恢复、关系、删除/归档、头像/附件、结构化年龄/阵营/能力或AI生成。DEV-3.6必须由新的编号任务授权，不由本流程预实现。
