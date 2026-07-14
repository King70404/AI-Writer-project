# AIWebNovel 后端

本目录包含 DEV-0.2 建立的最小 Python 后端工程。目前仅提供 FastAPI 应用工厂、类型化配置、标准输出 JSON 日志、请求 ID、统一 API 错误格式，以及存活和就绪健康检查。

当前尚未实现数据库、小说业务模块、Codex 调用、工作流或前端。健康检查成功只表示基础后端进程能够响应且应用初始化完成，不表示小说系统已经完成。

## 环境要求

- Windows 11；
- Python 3.12.10；
- 默认只监听 `127.0.0.1`。

## 创建虚拟环境并安装

在仓库根目录执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e "backend[dev]"
```

## 启动

```powershell
.\.venv\Scripts\python.exe -m aiwebnovel
```

默认健康检查地址：

- `http://127.0.0.1:8000/api/v1/health/live`
- `http://127.0.0.1:8000/api/v1/health/ready`

## 测试

在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/backend -q
.\.venv\Scripts\python.exe -m pip check
```
