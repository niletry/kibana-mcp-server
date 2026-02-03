# Kibana MCP Server - 使用示例

## 场景 1: 调查生产环境错误

### 步骤 1: 设置凭证
```json
{
  "tool": "kibana_set_credentials",
  "arguments": {
    "username": "engineer",
    "password": "your_password"
  }
}
```

### 步骤 2: 查找最近的错误
```json
{
  "tool": "kibana_search_errors",
  "arguments": {
    "service": "api-server",
    "severity": "exception",
    "time_range": "now-2h",
    "size": 20
  }
}
```

### 步骤 3: 查看具体服务的最新日志
```json
{
  "tool": "kibana_get_latest_logs",
  "arguments": {
    "service": "api-server",
    "size": 50
  }
}
```

---

## 场景 2: 监控服务健康状态

### 步骤 1: 统计各服务日志量
```json
{
  "tool": "kibana_aggregate_logs",
  "arguments": {
    "aggregation_type": "by_service",
    "time_range": "now-1h"
  }
}
```

**预期输出:**
```
📈 服务日志统计（时间范围: now-1h）:

  • app-server: 8,234 条
  • auth-module: 7,621 条
  • proxy-gateway: 2,845 条
  • api-server: 692 条
  ...
```

### 步骤 2: 检查异常增长的服务
如果某个服务日志量异常，深入查看：
```json
{
  "tool": "kibana_search_errors",
  "arguments": {
    "service": "异常服务名",
    "time_range": "now-1h",
    "size": 30
  }
}
```

---

## 场景 3: 追踪特定业务流程

### 步骤 1: 搜索 user_id
```json
{
  "tool": "kibana_search_logs",
  "arguments": {
    "query": "user_id:12345",
    "time_range": "now-24h",
    "size": 100
  }
}
```

### 步骤 2: 使用高级 DSL 查询
```json
{
  "tool": "kibana_search_logs",
  "arguments": {
    "query": "{\"query\":{\"bool\":{\"must\":[{\"match\":{\"log\":\"user_id\"}},{\"match\":{\"log\":\"12345\"}}],\"filter\":[{\"range\":{\"@timestamp\":{\"gte\":\"now-24h\"}}}]}},\"size\":100,\"sort\":[{\"@timestamp\":{\"order\":\"asc\"}}]}",
    "time_range": "now-24h"
  }
}
```

---

## 场景 4: 性能分析

### 按时间统计请求量
```json
{
  "tool": "kibana_aggregate_logs",
  "arguments": {
    "aggregation_type": "by_time",
    "time_range": "now-6h"
  }
}
```

**预期输出:**
```
📈 时间序列日志统计（时间范围: now-6h）:

  • 2026-02-03T12:00:00: 15,234 条
  • 2026-02-03T12:05:00: 14,892 条
  • 2026-02-03T12:10:00: 16,445 条
  ...
```

---

## 场景 5: 高级自定义查询

### 自定义聚合 - 统计 HTTP 状态码
```json
{
  "tool": "kibana_aggregate_logs",
  "arguments": {
    "aggregation_type": "custom",
    "time_range": "now-1h",
    "custom_aggregation": "{\"status_codes\":{\"terms\":{\"script\":{\"source\":\"if (doc['log.keyword'].size() > 0) { def log = doc['log.keyword'].value; def matcher = /\\\\\\\" (\\\\d{3}) /.matcher(log); if (matcher.find()) { return matcher.group(1); } } return 'unknown';\",\"lang\":\"painless\"},\"size\":10}}}"
  }
}
```

### 原始 Elasticsearch 查询
```json
{
  "tool": "kibana_raw_query",
  "arguments": {
    "path": "/logstash-*/_search",
    "query": "{\"query\":{\"bool\":{\"must\":[{\"match\":{\"kubernetes.container_name\":\"proxy-gateway\"}}],\"filter\":[{\"range\":{\"@timestamp\":{\"gte\":\"now-30m\"}}}]}},\"size\":0,\"aggs\":{\"response_codes\":{\"terms\":{\"script\":{\"source\":\"if (doc['log.keyword'].size() > 0) { def log = doc['log.keyword'].value; def matcher = /\\\\\\\" (\\\\d{3}) /.matcher(log); if (matcher.find()) { return matcher.group(1); } } return 'unknown';\",\"lang\":\"painless\"},\"size\":10}}}}"
  }
}
```

---

## 场景 6: 实时监控告警

### 监控最近的致命错误
```json
{
  "tool": "kibana_search_errors",
  "arguments": {
    "severity": "critical",
    "time_range": "now-5m",
    "size": 10
  }
}
```

### 针对特定服务的错误监控
```json
{
  "tool": "kibana_search_errors",
  "arguments": {
    "service": "billing-module",
    "severity": "all",
    "time_range": "now-15m",
    "size": 20
  }
}
```

---

## 常用查询模板

### 1. 查找包含特定关键词的日志
```json
{
  "tool": "kibana_search_logs",
  "arguments": {
    "query": "your_keyword",
    "time_range": "now-1h",
    "size": 50
  }
}
```

### 2. 查找多个服务的日志
使用原始查询:
```json
{
  "tool": "kibana_raw_query",
  "arguments": {
    "query": "{\"query\":{\"bool\":{\"should\":[{\"match\":{\"kubernetes.container_name\":\"service1\"}},{\"match\":{\"kubernetes.container_name\":\"service2\"}}],\"minimum_should_match\":1}},\"size\":50,\"sort\":[{\"@timestamp\":{\"order\":\"desc\"}}]}"
  }
}
```

### 3. 统计错误率
```json
{
  "tool": "kibana_aggregate_logs",
  "arguments": {
    "aggregation_type": "custom",
    "time_range": "now-1h",
    "custom_aggregation": "{\"total_logs\":{\"value_count\":{\"field\":\"@timestamp\"}},\"error_logs\":{\"filter\":{\"bool\":{\"should\":[{\"match\":{\"log\":\"error\"}},{\"match\":{\"log\":\"ERROR\"}}]}}}}"
  }
}
```

---

## 时间范围参考

| 范围 | 表达式 | 适用场景 |
|------|--------|----------|
| 最近 5 分钟 | `now-5m` | 实时监控 |
| 最近 30 分钟 | `now-30m` | 快速排查 |
| 最近 1 小时 | `now-1h` | 常规查询 |
| 最近 6 小时 | `now-6h` | 趋势分析 |
| 最近 24 小时 | `now-24h` | 日常回顾 |
| 最近 7 天 | `now-7d` | 周报分析 |

---

## 性能优化建议

1. **控制返回数量** - 使用 `size` 参数限制结果
2. **缩小时间范围** - 避免查询过长的时间段
3. **使用聚合** - 对于统计分析，使用聚合而不是获取所有结果
4. **选择必要字段** - 使用 `fields` 参数只返回需要的字段

---

## 故障排查流程

### 当服务出现问题时：

1. **查看最新日志** - `kibana_get_latest_logs`
2. **搜索错误** - `kibana_search_errors`
3. **统计服务状态** - `kibana_aggregate_logs` (by_service)
4. **查看时间趋势** - `kibana_aggregate_logs` (by_time)
5. **深入调查** - 使用 `kibana_search_logs` 或 `kibana_raw_query`

---

## 更多示例

查看 `test_server.py` 文件了解更多编程示例。
