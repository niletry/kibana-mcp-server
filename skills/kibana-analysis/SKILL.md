---
name: Kibana Log Analysis
description: 掌握如何使用 Kibana MCP Server 快速搜索、分析和排查线上服务的日志。
---

# Kibana 日志分析技能

此技能指导如何高效利用 Kibana MCP Server 的各种工具来监控服务状态、排查故障并进行日志聚合。

## 场景：故障初查 (Troubleshooting)

当收到线上警报或发现服务异常时，通过以下步骤快速定位：

1. **查找最近的错误日志**
   使用 `kibana_search_errors` 搜索最近 1 小时的错误：
   ```json
   {
     "severity": "all",
     "time_range": "now-1h",
     "size": 20
   }
   ```
   *提示：如果知道具体业务线，可以加上 `service` 参数。*

2. **分析错误分布**
   如果错误散落在多个服务中，可以使用 `kibana_aggregate_logs` 找出哪个服务报错最多：
   ```json
   {
     "aggregation_type": "by_service",
     "time_range": "now-1h",
     "filter": "{\"bool\":{\"should\":[{\"match\":{\"log\":\"error\"}},{\"match\":{\"log\":\"exception\"}}]}}"
   }
   ```

## 场景：日常监控与流量趋势

1. **服务流量统计**
   检查过去 24 小时内各服务的处理量：
   ```json
   {
     "aggregation_type": "by_service",
     "time_range": "now-24h"
   }
   ```

2. **请求高峰监测**
   通过时间轴视图查看流量波动：
   ```json
   {
     "aggregation_type": "by_time",
     "time_range": "now-6h"
   }
   ```

## 核心技巧 (Best Practices)

- **关键词搜索优先级**：先尝试 `kibana_search_logs` 的简单关键词。如果无效，再考虑拼装复杂的 `kibana_raw_query`。
- **限制返回量**：在高频访问的环境下，务必使用 `size` 参数，避免由于数据量过大导致的响应缓慢。
- **时间范围缩放**：
  - 排查即时问题用 `now-15m` 或 `now-1h`。
  - 分析历史趋势用 `now-24h` 或 `now-7d`。

## 工具一览

- `kibana_search_logs`: 通用搜索，支持关键词和 DSL。
- `kibana_get_latest_logs`: 实时流，查看刚发生的日志。
- `kibana_search_errors`: 专注错误排查。
- `kibana_aggregate_logs`: 统计分析利器。
- `kibana_raw_query`: 底层 Elastic 命令，用于最复杂的需求。
