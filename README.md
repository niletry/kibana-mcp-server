# Kibana MCP Server

🔍 **Kibana 日志查询 MCP Server** - 提供自动认证、会话管理和多种日志查询工具

## 功能特性

✅ **自动认证管理**
- 自动登录并获取 `sid` cookie
- 会话过期自动续期
- 401 错误自动重新登录

✅ **智能会话保持**
- 会话有效期 23 小时（避免 24 小时超时）
- 自动检测会话失效
- 透明的重新认证

✅ **丰富的查询工具**
- 日志搜索（关键词查询 + DSL 查询）
- 聚合统计（按服务、按时间）
- 错误日志快速搜索
- 原始 Elasticsearch DSL 查询

## 安装

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 或使用 uv (推荐)
uv pip install -r requirements.txt
```

## 运行方式 (推荐使用 uvx)

你可以直接使用 `uvx` 从本地目录运行：

```bash
uvx --from /tmp/kibana-mcp-server kibana-mcp-server
```

## 配置 MCP

### Claude Desktop / OpenCode 配置

```json
{
  "mcpServers": {
    "kibana": {
      "command": "uvx",
      "args": [
        "--from",
        "/tmp/kibana-mcp-server",
        "kibana-mcp-server"
      ],
      "env": {
        "KIBANA_URL": "https://logs.example.com",
        "KIBANA_VERSION": "8.17.1"
      }
    }
  }
}
```

## 可用工具

### 1. `kibana_set_credentials`
设置登录凭证（必须首先调用）

**参数:**
- `username` - Kibana 用户名
- `password` - Kibana 密码

**示例:**
```json
{
  "username": "your_username",
  "password": "your_password"
}
```

---

### 2. `kibana_search_logs`
搜索日志（支持关键词搜索和完整 DSL 查询）

**参数:**
- `query` - 搜索关键词或完整 Elasticsearch DSL JSON
- `time_range` - 时间范围，默认 "now-1h"
- `size` - 返回数量，默认 20
- `index_pattern` - 索引模式，默认 "logstash-*"
- `fields` - 返回字段列表

**示例 1: 关键词搜索**
```json
{
  "query": "user_id",
  "time_range": "now-30m",
  "size": 10
}
```

**示例 2: DSL 查询**
```json
{
  "query": "{\"query\":{\"bool\":{\"must\":[{\"match\":{\"kubernetes.container_name\":\"api-server\"}}]}}}",
  "time_range": "now-1h",
  "size": 50
}
```

---

### 3. `kibana_aggregate_logs`
聚合统计日志

**参数:**
- `aggregation_type` - 聚合类型: "by_service" | "by_time" | "custom"
- `time_range` - 时间范围，默认 "now-1h"
- `filter` - 可选过滤条件（DSL JSON）
- `custom_aggregation` - 自定义聚合（仅 custom 类型）
- `index_pattern` - 索引模式

**示例 1: 按服务统计**
```json
{
  "aggregation_type": "by_service",
  "time_range": "now-24h"
}
```

**示例 2: 按时间统计**
```json
{
  "aggregation_type": "by_time",
  "time_range": "now-6h"
}
```

---

### 4. `kibana_get_latest_logs`
快速获取最新日志

**参数:**
- `service` - 服务名称（可选）
- `size` - 返回数量，默认 10
- `index_pattern` - 索引模式

**示例:**
```json
{
  "service": "proxy-gateway",
  "size": 20
}
```

---

### 5. `kibana_search_errors`
搜索错误日志

**参数:**
- `service` - 服务名称（可选）
- `severity` - 严重程度: "error" | "exception" | "critical" | "all"
- `time_range` - 时间范围，默认 "now-1h"
- `size` - 返回数量，默认 20
- `index_pattern` - 索引模式

**示例:**
```json
{
  "service": "api-server",
  "severity": "exception",
  "time_range": "now-2h",
  "size": 30
}
```

---

### 6. `kibana_raw_query`
执行原始 Elasticsearch DSL 查询（高级）

**参数:**
- `path` - Elasticsearch 路径，默认 "/logstash-*/_search"
- `query` - 完整的 Elasticsearch DSL JSON 字符串

**示例:**
```json
{
  "path": "/logstash-*/_search",
  "query": "{\"query\":{\"match_all\":{}},\"size\":5}"
}
```

---

## 使用流程

### 1. 首次使用 - 设置凭证
```
使用工具: kibana_set_credentials
参数:
  username: "engineer"
  password: "your_password"
```

### 2. 查询日志
```
使用工具: kibana_search_logs
参数:
  query: "error"
  time_range: "now-1h"
  size: 20
```

### 3. 统计分析
```
使用工具: kibana_aggregate_logs
参数:
  aggregation_type: "by_service"
  time_range: "now-24h"
```

## 技术细节

### 认证机制
1. 用户调用 `kibana_set_credentials` 设置凭证
2. 首次请求时自动登录 Kibana
3. 获取并保存 `sid` cookie（Iron 加密格式）
4. 后续请求自动携带 cookie
5. 遇到 401 错误时自动重新登录

### 会话管理
- **会话超时**: 23 小时（避免 24 小时边界问题）
- **自动检测**: 每次请求前检查会话有效性
- **透明续期**: 用户无需关心会话状态

### 错误处理
- ✅ 401 Unauthorized → 自动重新登录
- ✅ 网络超时 → 30 秒超时配置
- ✅ JSON 解析错误 → 友好错误提示
- ✅ 参数验证 → Pydantic 模型验证

## 常见时间范围

| 表达式 | 含义 |
|--------|------|
| `now-5m` | 最近 5 分钟 |
| `now-30m` | 最近 30 分钟 |
| `now-1h` | 最近 1 小时 |
| `now-6h` | 最近 6 小时 |
| `now-24h` | 最近 24 小时 |
| `now-7d` | 最近 7 天 |
| `now-30d` | 最近 30 天 |

## 常见字段

- `@timestamp` - 日志时间戳
- `log` - 日志内容
- `kubernetes.container_name` - Kubernetes 容器名（服务名）
- `kubernetes.namespace_name` - Kubernetes 命名空间
- `kubernetes.pod_name` - Pod 名称
- `stream` - 输出流（stdout/stderr）

## 故障排查

### 问题: "Kibana 会话未初始化"
**解决**: 先调用 `kibana_set_credentials` 设置凭证

### 问题: "登录失败: 401"
**解决**: 检查用户名和密码是否正确

### 问题: "请求超时"
**解决**: 
1. 检查网络连接
2. 减小查询范围（`size` 参数）
3. 缩短时间范围

### 问题: 查询返回空结果
**解决**:
1. 检查索引模式是否正确
2. 扩大时间范围
3. 检查查询语法

## 开发

### 运行测试
```bash
python server.py
```

### 调试模式
设置环境变量启用详细日志:
```bash
export DEBUG=1
python server.py
```

## 许可证

MIT License
