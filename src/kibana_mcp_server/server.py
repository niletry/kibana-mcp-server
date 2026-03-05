#!/usr/bin/env python3
"""
Kibana MCP Server
提供 Kibana 日志查询功能，自动处理认证和会话管理
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import quote

import httpx
from mcp.server import Server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)
from pydantic import BaseModel, Field


# 配置
KIBANA_URL = os.getenv("KIBANA_URL", "https://logs.example.com")
KIBANA_VERSION = os.getenv("KIBANA_VERSION", "8.17.1")
KIBANA_USERNAME = os.getenv("KIBANA_USERNAME")
KIBANA_PASSWORD = os.getenv("KIBANA_PASSWORD")
SESSION_TIMEOUT = timedelta(hours=23)  # sid cookie 通常 24 小时过期


class KibanaSession:
    """管理 Kibana 会话和认证"""
    
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.sid_cookie: Optional[str] = None
        self.session_created_at: Optional[datetime] = None
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def ensure_authenticated(self) -> None:
        """确保当前会话已认证，如果未认证或过期则重新登录"""
        if self._is_session_valid():
            return
        
        await self.login()
    
    def _is_session_valid(self) -> bool:
        """检查会话是否有效"""
        if not self.sid_cookie or not self.session_created_at:
            return False
        
        # 检查是否超时
        if datetime.now() - self.session_created_at > SESSION_TIMEOUT:
            return False
        
        return True
    
    async def login(self) -> None:
        """登录 Kibana 获取 sid cookie"""
        login_url = f"{KIBANA_URL}/internal/security/login"
        
        payload = {
            "providerType": "basic",
            "providerName": "cloud-basic",
            "currentURL": f"{KIBANA_URL}/login?msg=LOGGED_OUT",
            "params": {
                "username": self.username,
                "password": self.password
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "kbn-version": KIBANA_VERSION,
            "kbn-xsrf": "kibana"
        }
        
        try:
            print(f"DEBUG: Attempting login to {login_url} with user {self.username}", file=sys.stderr)
            response = await self.client.post(
                login_url,
                json=payload,
                headers=headers
            )
            
            if response.status_code == 200:
                # 提取 sid cookie
                set_cookie = response.headers.get("set-cookie", "")
                if "sid=" in set_cookie:
                    # 提取 sid 值
                    sid_start = set_cookie.find("sid=") + 4
                    sid_end = set_cookie.find(";", sid_start)
                    self.sid_cookie = set_cookie[sid_start:sid_end]
                    self.session_created_at = datetime.now()
                else:
                    raise Exception("登录成功但未获取到 sid cookie")
            else:
                raise Exception(f"登录失败: {response.status_code} - {response.text}")
        
        except Exception as e:
            raise Exception(f"Kibana 登录错误: {str(e)}")
    
    async def request(self, path: str, query: dict) -> dict:
        """
        发送请求到 Kibana proxy 端点
        自动处理 401 错误并重新登录
        """
        await self.ensure_authenticated()
        
        encoded_path = quote(path, safe='')
        url = f"{KIBANA_URL}/api/console/proxy?path={encoded_path}&method=POST"
        
        headers = {
            "Cookie": f"sid={self.sid_cookie}",
            "kbn-xsrf": "kibana",
            "kbn-version": KIBANA_VERSION,
            "Content-Type": "application/json",
            "x-elastic-internal-origin": "Kibana"
        }
        
        try:
            response = await self.client.post(
                url,
                json=query,
                headers=headers
            )
            
            # 如果遇到 401，重新登录后重试
            if response.status_code == 401:
                await self.login()
                
                # 更新 headers 中的 cookie
                headers["Cookie"] = f"sid={self.sid_cookie}"
                
                # 重试请求
                response = await self.client.post(
                    url,
                    json=query,
                    headers=headers
                )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"请求失败: {response.status_code} - {response.text}")
        
        except Exception as e:
            raise Exception(f"Kibana 请求错误: {str(e)}")
    
    async def close(self):
        """关闭 HTTP 客户端"""
        await self.client.aclose()


# 全局会话管理器
_session: Optional[KibanaSession] = None


def get_session() -> KibanaSession:
    """获取当前会话，如果未初始化则根据环境变量自动初始化"""
    global _session
    if _session is None:
        if not KIBANA_USERNAME or not KIBANA_PASSWORD:
            raise Exception("Kibana 凭证未配置。请设置 KIBANA_USERNAME 和 KIBANA_PASSWORD 环境变量。")
        _session = KibanaSession(KIBANA_USERNAME, KIBANA_PASSWORD)
    return _session


# 创建 MCP Server
app = Server("kibana")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """列出所有可用的工具"""
    return [
        Tool(
            name="kibana_search_logs",
            description="搜索 Kibana 日志。支持自定义 Elasticsearch DSL 查询或简单的关键词搜索",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词（简单搜索）或完整的 Elasticsearch DSL 查询 JSON 字符串"
                    },
                    "time_range": {
                        "type": "string",
                        "description": "时间范围，如 'now-1h', 'now-24h', 'now-7d' 等",
                        "default": "now-1h"
                    },
                    "size": {
                        "type": "integer",
                        "description": "返回结果数量",
                        "default": 20,
                        "minimum": 1,
                        "maximum": 1000
                    },
                    "index_pattern": {
                        "type": "string",
                        "description": "索引模式",
                        "default": "logstash-*"
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要返回的字段列表",
                        "default": ["@timestamp", "kubernetes.container_name", "log"]
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="kibana_aggregate_logs",
            description="聚合统计 Kibana 日志。可以按服务、时间等维度统计",
            inputSchema={
                "type": "object",
                "properties": {
                    "aggregation_type": {
                        "type": "string",
                        "enum": ["by_service", "by_time", "custom"],
                        "description": "聚合类型: by_service(按服务统计), by_time(按时间统计), custom(自定义聚合)"
                    },
                    "time_range": {
                        "type": "string",
                        "description": "时间范围，如 'now-1h', 'now-24h' 等",
                        "default": "now-1h"
                    },
                    "filter": {
                        "type": "string",
                        "description": "可选的过滤条件（Elasticsearch DSL JSON 字符串）"
                    },
                    "custom_aggregation": {
                        "type": "string",
                        "description": "自定义聚合查询（仅当 aggregation_type 为 'custom' 时使用）"
                    },
                    "index_pattern": {
                        "type": "string",
                        "description": "索引模式",
                        "default": "logstash-*"
                    }
                },
                "required": ["aggregation_type"]
            }
        ),
        Tool(
            name="kibana_get_latest_logs",
            description="快速获取最新的日志记录",
            inputSchema={
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "服务名称（kubernetes.container_name），为空则返回所有服务"
                    },
                    "size": {
                        "type": "integer",
                        "description": "返回数量",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 100
                    },
                    "index_pattern": {
                        "type": "string",
                        "description": "索引模式",
                        "default": "logstash-*"
                    }
                }
            }
        ),
        Tool(
            name="kibana_search_errors",
            description="搜索错误日志（包含 error、exception、fail 等关键词）",
            inputSchema={
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "服务名称（kubernetes.container_name），为空则搜索所有服务"
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["error", "exception", "critical", "all"],
                        "description": "错误严重程度",
                        "default": "all"
                    },
                    "time_range": {
                        "type": "string",
                        "description": "时间范围",
                        "default": "now-1h"
                    },
                    "size": {
                        "type": "integer",
                        "description": "返回数量",
                        "default": 20,
                        "minimum": 1,
                        "maximum": 100
                    },
                    "index_pattern": {
                        "type": "string",
                        "description": "索引模式",
                        "default": "logstash-*"
                    }
                }
            }
        ),
        Tool(
            name="kibana_raw_query",
            description="执行原始的 Elasticsearch DSL 查询（高级用户）",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Elasticsearch 路径，如 '/logstash-*/_search'",
                        "default": "/logstash-*/_search"
                    },
                    "query": {
                        "type": "string",
                        "description": "完整的 Elasticsearch DSL 查询 JSON 字符串"
                    }
                },
                "required": ["query"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """处理工具调用"""
    
    # 获取会话（如果未认证则自动认证）
    session = get_session()
    
    if name == "kibana_search_logs":
        return await handle_search_logs(session, arguments)
    
    elif name == "kibana_aggregate_logs":
        return await handle_aggregate_logs(session, arguments)
    
    elif name == "kibana_get_latest_logs":
        return await handle_get_latest_logs(session, arguments)
    
    elif name == "kibana_search_errors":
        return await handle_search_errors(session, arguments)
    
    elif name == "kibana_raw_query":
        return await handle_raw_query(session, arguments)
    
    else:
        raise ValueError(f"未知工具: {name}")


async def handle_search_logs(session: KibanaSession, args: dict) -> list[TextContent]:
    """处理日志搜索"""
    query_str = args["query"]
    time_range = args.get("time_range", "now-1h")
    size = args.get("size", 20)
    index_pattern = args.get("index_pattern", "logstash-*")
    fields = args.get("fields", ["@timestamp", "kubernetes.container_name", "log"])
    
    # 尝试解析为 JSON（完整的 DSL 查询）
    try:
        query_dsl = json.loads(query_str)
    except json.JSONDecodeError:
        # 简单关键词搜索
        query_dsl = {
            "query": {
                "bool": {
                    "must": [
                        {"match": {"log": query_str}}
                    ],
                    "filter": [
                        {"range": {"@timestamp": {"gte": time_range}}}
                    ]
                }
            },
            "size": size,
            "_source": fields,
            "sort": [{"@timestamp": {"order": "desc"}}]
        }
    
    # 确保有 size 和 _source
    if "size" not in query_dsl:
        query_dsl["size"] = size
    if "_source" not in query_dsl:
        query_dsl["_source"] = fields
    
    path = f"/{index_pattern}/_search"
    result = await session.request(path, query_dsl)
    
    # 格式化输出
    hits = result.get("hits", {}).get("hits", [])
    total = result.get("hits", {}).get("total", {}).get("value", 0)
    
    output = f"📊 找到 {total} 条日志，显示前 {len(hits)} 条：\n\n"
    
    for i, hit in enumerate(hits, 1):
        source = hit.get("_source", {})
        timestamp = source.get("@timestamp", "N/A")
        service = source.get("kubernetes", {}).get("container_name", "N/A")
        log = source.get("log", "N/A")
        
        output += f"{i}. [{timestamp}] {service}\n"
        output += f"   {log[:200]}{'...' if len(log) > 200 else ''}\n\n"
    
    return [TextContent(type="text", text=output)]


async def handle_aggregate_logs(session: KibanaSession, args: dict) -> list[TextContent]:
    """处理日志聚合"""
    agg_type = args["aggregation_type"]
    time_range = args.get("time_range", "now-1h")
    index_pattern = args.get("index_pattern", "logstash-*")
    
    # 基础查询
    base_query = {
        "range": {"@timestamp": {"gte": time_range}}
    }
    
    # 添加过滤条件
    filter_query = args.get("filter")
    if filter_query:
        try:
            filter_dsl = json.loads(filter_query)
            base_query = {"bool": {"must": [base_query, filter_dsl]}}
        except json.JSONDecodeError:
            pass
    
    if agg_type == "by_service":
        query_dsl = {
            "size": 0,
            "query": base_query,
            "aggs": {
                "services": {
                    "terms": {
                        "field": "kubernetes.container_name.keyword",
                        "size": 20,
                        "order": {"_count": "desc"}
                    }
                }
            }
        }
    elif agg_type == "by_time":
        query_dsl = {
            "size": 0,
            "query": base_query,
            "aggs": {
                "logs_over_time": {
                    "date_histogram": {
                        "field": "@timestamp",
                        "fixed_interval": "5m"
                    }
                }
            }
        }
    elif agg_type == "custom":
        custom_agg = args.get("custom_aggregation")
        if not custom_agg:
            raise ValueError("custom 聚合类型需要提供 custom_aggregation 参数")
        try:
            agg_dsl = json.loads(custom_agg)
            query_dsl = {
                "size": 0,
                "query": base_query,
                "aggs": agg_dsl
            }
        except json.JSONDecodeError as e:
            raise ValueError(f"custom_aggregation 不是有效的 JSON: {str(e)}")
    else:
        raise ValueError(f"未知的聚合类型: {agg_type}")
    
    path = f"/{index_pattern}/_search"
    result = await session.request(path, query_dsl)
    
    # 格式化输出
    aggs = result.get("aggregations", {})
    
    if agg_type == "by_service":
        buckets = aggs.get("services", {}).get("buckets", [])
        output = f"📈 服务日志统计（时间范围: {time_range}）:\n\n"
        for bucket in buckets:
            service = bucket["key"]
            count = bucket["doc_count"]
            output += f"  • {service}: {count:,} 条\n"
    elif agg_type == "by_time":
        buckets = aggs.get("logs_over_time", {}).get("buckets", [])
        output = f"📈 时间序列日志统计（时间范围: {time_range}）:\n\n"
        for bucket in buckets:
            timestamp = bucket["key_as_string"]
            count = bucket["doc_count"]
            output += f"  • {timestamp}: {count:,} 条\n"
    else:
        output = f"📈 自定义聚合结果:\n\n{json.dumps(aggs, indent=2, ensure_ascii=False)}"
    
    return [TextContent(type="text", text=output)]


async def handle_get_latest_logs(session: KibanaSession, args: dict) -> list[TextContent]:
    """获取最新日志"""
    service = args.get("service")
    size = args.get("size", 10)
    index_pattern = args.get("index_pattern", "logstash-*")
    
    query_dsl = {
        "query": {"match_all": {}},
        "size": size,
        "sort": [{"@timestamp": {"order": "desc"}}],
        "_source": ["@timestamp", "kubernetes.container_name", "log"]
    }
    
    # 添加服务过滤
    if service:
        query_dsl["query"] = {
            "match": {
                "kubernetes.container_name": service
            }
        }
    
    path = f"/{index_pattern}/_search"
    result = await session.request(path, query_dsl)
    
    hits = result.get("hits", {}).get("hits", [])
    
    output = f"📝 最新 {len(hits)} 条日志"
    if service:
        output += f"（服务: {service}）"
    output += ":\n\n"
    
    for i, hit in enumerate(hits, 1):
        source = hit.get("_source", {})
        timestamp = source.get("@timestamp", "N/A")
        svc = source.get("kubernetes", {}).get("container_name", "N/A")
        log = source.get("log", "N/A")
        
        output += f"{i}. [{timestamp}] {svc}\n"
        output += f"   {log[:200]}{'...' if len(log) > 200 else ''}\n\n"
    
    return [TextContent(type="text", text=output)]


async def handle_search_errors(session: KibanaSession, args: dict) -> list[TextContent]:
    """搜索错误日志"""
    service = args.get("service")
    severity = args.get("severity", "all")
    time_range = args.get("time_range", "now-1h")
    size = args.get("size", 20)
    index_pattern = args.get("index_pattern", "logstash-*")
    
    # 构建错误关键词
    error_keywords = {
        "error": ["error", "Error", "ERROR"],
        "exception": ["exception", "Exception", "EXCEPTION"],
        "critical": ["critical", "Critical", "CRITICAL", "fatal", "Fatal", "FATAL"],
        "all": ["error", "Error", "ERROR", "exception", "Exception", "fail", "Fail", "FAIL"]
    }
    
    keywords = error_keywords.get(severity, error_keywords["all"])
    
    # 构建查询
    must_clauses = [
        {
            "bool": {
                "should": [
                    {"match": {"log": keyword}} for keyword in keywords
                ],
                "minimum_should_match": 1
            }
        }
    ]
    
    if service:
        must_clauses.append({
            "match": {"kubernetes.container_name": service}
        })
    
    query_dsl = {
        "query": {
            "bool": {
                "must": must_clauses,
                "filter": [
                    {"range": {"@timestamp": {"gte": time_range}}}
                ]
            }
        },
        "size": size,
        "sort": [{"@timestamp": {"order": "desc"}}],
        "_source": ["@timestamp", "kubernetes.container_name", "log"]
    }
    
    path = f"/{index_pattern}/_search"
    result = await session.request(path, query_dsl)
    
    hits = result.get("hits", {}).get("hits", [])
    total = result.get("hits", {}).get("total", {}).get("value", 0)
    
    output = f"🚨 找到 {total} 条错误日志"
    if service:
        output += f"（服务: {service}）"
    output += f"，显示前 {len(hits)} 条:\n\n"
    
    for i, hit in enumerate(hits, 1):
        source = hit.get("_source", {})
        timestamp = source.get("@timestamp", "N/A")
        svc = source.get("kubernetes", {}).get("container_name", "N/A")
        log = source.get("log", "N/A")
        
        output += f"{i}. [{timestamp}] {svc}\n"
        output += f"   {log[:300]}{'...' if len(log) > 300 else ''}\n\n"
    
    return [TextContent(type="text", text=output)]


async def handle_raw_query(session: KibanaSession, args: dict) -> list[TextContent]:
    """执行原始查询"""
    path = args.get("path", "/logstash-*/_search")
    query_str = args["query"]
    
    try:
        query_dsl = json.loads(query_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"查询不是有效的 JSON: {str(e)}")
    
    result = await session.request(path, query_dsl)
    
    # 格式化 JSON 输出
    output = json.dumps(result, indent=2, ensure_ascii=False)
    
    return [TextContent(type="text", text=output)]


async def main():
    """启动 MCP server"""
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

def run():
    """同步入口点，用于 console_scripts"""
    asyncio.run(main())

if __name__ == "__main__":
    run()
