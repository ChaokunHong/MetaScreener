#!/usr/bin/env python3
"""
Optimized API Integration for MetaScreener
将增强的API优化器集成到现有的API调用中，提供无缝的性能优化
"""

import logging
from typing import Dict, Optional, Any
from functools import wraps
import time

# Import existing API functions
from app.utils.utils import (
    _call_openai_compatible_api, _call_claude_api, _call_gemini_api,
    get_optimized_parameters, get_retry_strategy
)

# Import enhanced optimizer
from app.utils.enhanced_api_optimizer import get_api_optimizer, CircuitBreakerOpenError

# Setup logging
integration_logger = logging.getLogger("api_integration")

class OptimizedAPIWrapper:
    """优化的API包装器"""
    
    def __init__(self):
        self.optimizer = get_api_optimizer()
        self.call_count = 0
        self.cache_hits = 0
        self.fallback_count = 0
    
    def call_llm_api_optimized(self, prompt_data: Dict[str, str], provider_name: str, 
                              model_id: str, api_key: str, base_url: Optional[str] = None) -> Dict[str, str]:
        """
        优化的LLM API调用，集成所有性能优化功能
        
        Args:
            prompt_data: 包含system_prompt和main_prompt的字典
            provider_name: AI提供商名称
            model_id: 模型ID
            api_key: API密钥
            base_url: 基础URL（可选）
        
        Returns:
            包含label和justification的响应字典
        """
        self.call_count += 1
        
        # 提取prompt信息
        system_prompt = prompt_data.get("system_prompt", "")
        main_prompt = prompt_data.get("main_prompt", "")
        full_prompt = f"{system_prompt}\n\n{main_prompt}" if system_prompt else main_prompt
        
        # 获取优化参数
        optimized_params = get_optimized_parameters(provider_name, model_id, "screening")
        
        # 定义API调用函数
        def api_call_func():
            if provider_name in ["DeepSeek", "OpenAI_ChatGPT"]:
                return _call_openai_compatible_api(
                    main_prompt, system_prompt, model_id, api_key, base_url, provider_name
                )
            elif provider_name == "Anthropic_Claude":
                return _call_claude_api(
                    main_prompt, system_prompt, model_id, api_key, base_url
                )
            elif provider_name == "Google_Gemini":
                return _call_gemini_api(full_prompt, model_id, api_key)
            else:
                raise ValueError(f"Unsupported provider: {provider_name}")
        
        try:
            # 使用优化器执行API调用
            response = self.optimizer.optimized_api_call(
                provider=provider_name,
                model=model_id,
                api_func=api_call_func,
                prompt=full_prompt,
                params=optimized_params
            )
            
            integration_logger.debug(f"Optimized API call successful for {provider_name}-{model_id}")
            return response
            
        except CircuitBreakerOpenError as e:
            integration_logger.error(f"Circuit breaker open: {e}")
            return {
                "label": "CIRCUIT_BREAKER_OPEN",
                "justification": f"Service temporarily unavailable due to circuit breaker: {str(e)}"
            }
        except Exception as e:
            integration_logger.error(f"Optimized API call failed: {e}")
            return {
                "label": "API_ERROR",
                "justification": f"API call failed: {str(e)}"
            }
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        optimizer_stats = self.optimizer.get_optimization_stats()
        
        return {
            "wrapper_stats": {
                "total_calls": self.call_count,
                "cache_hits": self.cache_hits,
                "fallback_count": self.fallback_count,
                "cache_hit_rate": self.cache_hits / max(1, self.call_count)
            },
            "optimizer_stats": optimizer_stats
        }

# 全局优化API包装器实例
optimized_api_wrapper = OptimizedAPIWrapper()

def call_llm_api_with_optimization(prompt_data: Dict[str, str], provider_name: str, 
                                  model_id: str, api_key: str, base_url: Optional[str] = None) -> Dict[str, str]:
    """
    使用优化功能的LLM API调用入口函数
    
    这个函数可以直接替换现有的call_llm_api函数，提供完全向后兼容的接口
    """
    return optimized_api_wrapper.call_llm_api_optimized(
        prompt_data, provider_name, model_id, api_key, base_url
    )

def get_api_performance_report() -> Dict[str, Any]:
    """获取API性能报告"""
    return optimized_api_wrapper.get_performance_stats()

# 装饰器：为现有函数添加优化功能
def with_api_optimization(func):
    """
    装饰器：为现有的API调用函数添加优化功能
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # 如果是支持的API调用函数，使用优化版本
        if func.__name__ in ['call_llm_api', '_perform_screening_on_abstract']:
            # 提取参数
            if len(args) >= 4:
                prompt_data = args[0] if isinstance(args[0], dict) else {"main_prompt": str(args[0])}
                provider_name = args[1] if len(args) > 1 else kwargs.get('provider_name')
                model_id = args[2] if len(args) > 2 else kwargs.get('model_id')
                api_key = args[3] if len(args) > 3 else kwargs.get('api_key')
                base_url = args[4] if len(args) > 4 else kwargs.get('base_url')
                
                return call_llm_api_with_optimization(
                    prompt_data, provider_name, model_id, api_key, base_url
                )
        
        # 对于其他函数，正常执行
        return func(*args, **kwargs)
    
    return wrapper

# 批处理优化函数
def optimized_batch_processing(items: list, process_func: callable, provider_name: str, 
                              model_id: str, max_workers: int = None) -> list:
    """
    优化的批处理函数，集成速率限制和负载均衡
    
    Args:
        items: 要处理的项目列表
        process_func: 处理函数
        provider_name: AI提供商名称
        model_id: 模型ID
        max_workers: 最大并发数（可选）
    
    Returns:
        处理结果列表
    """
    from config.config import get_model_specific_config
    
    # 获取模型配置
    model_config = get_model_specific_config(provider_name, model_id)
    rate_limit = model_config.get('rate_limit', {})
    
    # 计算最优并发数
    if max_workers is None:
        max_workers = min(
            rate_limit.get('batch_size', 10),
            len(items),
            50  # 硬限制
        )
    
    # 获取速率限制器
    rate_limiter = optimized_api_wrapper.optimizer.get_rate_limiter(provider_name, model_id)
    
    results = []
    batch_size = max_workers
    
    integration_logger.info(f"Starting optimized batch processing: {len(items)} items, batch_size={batch_size}")
    
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        batch_results = []
        
        for item in batch:
            # 检查速率限制
            while not rate_limiter.acquire():
                time.sleep(1.0)  # 等待1秒后重试
            
            try:
                result = process_func(item)
                batch_results.append(result)
                rate_limiter.record_success()
            except Exception as e:
                integration_logger.error(f"Batch processing error: {e}")
                # 记录错误但继续处理
                batch_results.append({
                    "label": "BATCH_ERROR",
                    "justification": f"Batch processing error: {str(e)}"
                })
                
                # 如果是速率限制错误，记录到速率限制器
                if "rate limit" in str(e).lower() or "429" in str(e):
                    rate_limiter.record_rate_limit_error()
        
        results.extend(batch_results)
        
        # 批次间延迟（如果需要）
        if i + batch_size < len(items):
            delay = 60.0 / rate_limiter.current_rpm
            if delay > 0.1:  # 只有当延迟大于100ms时才等待
                time.sleep(delay)
    
    integration_logger.info(f"Completed optimized batch processing: {len(results)} results")
    return results

# 健康检查函数
def check_api_health(provider_name: str, model_id: str) -> Dict[str, Any]:
    """
    检查API健康状态
    
    Args:
        provider_name: AI提供商名称
        model_id: 模型ID
    
    Returns:
        健康状态信息
    """
    optimizer = get_api_optimizer()
    
    # 获取熔断器状态
    circuit_breaker = optimizer.get_circuit_breaker(provider_name, model_id)
    
    # 获取速率限制器状态
    rate_limiter = optimizer.get_rate_limiter(provider_name, model_id)
    
    # 获取负载均衡器中的提供商权重
    provider_weight = optimizer.load_balancer.provider_weights.get(provider_name, 1.0)
    provider_metrics = optimizer.load_balancer.provider_metrics.get(provider_name)
    
    health_status = {
        "provider": provider_name,
        "model": model_id,
        "circuit_breaker": {
            "state": circuit_breaker.state.value,
            "success_rate": circuit_breaker.metrics.success_rate,
            "consecutive_failures": circuit_breaker.metrics.consecutive_failures,
            "avg_response_time": circuit_breaker.metrics.avg_response_time
        },
        "rate_limiter": {
            "current_rpm": rate_limiter.current_rpm,
            "recent_requests": len(rate_limiter.request_times),
            "recent_errors": len(rate_limiter.recent_errors)
        },
        "load_balancer": {
            "weight": provider_weight,
            "success_rate": provider_metrics.success_rate if provider_metrics else 0.0,
            "avg_response_time": provider_metrics.avg_response_time if provider_metrics else 0.0
        },
        "overall_health": "healthy"  # 默认健康
    }
    
    # 评估整体健康状态
    if circuit_breaker.state.value == "open":
        health_status["overall_health"] = "unhealthy"
    elif circuit_breaker.metrics.success_rate < 0.8:
        health_status["overall_health"] = "degraded"
    elif len(rate_limiter.recent_errors) > 5:
        health_status["overall_health"] = "degraded"
    
    return health_status

# 性能监控函数
def monitor_api_performance() -> Dict[str, Any]:
    """
    监控API性能并生成报告
    
    Returns:
        性能监控报告
    """
    stats = get_api_performance_report()
    
    # 分析性能趋势
    performance_analysis = {
        "cache_efficiency": "good" if stats["wrapper_stats"]["cache_hit_rate"] > 0.2 else "poor",
        "circuit_breaker_activations": len([
            cb for cb in stats["optimizer_stats"]["circuit_breakers"].values()
            if cb["state"] != "closed"
        ]),
        "rate_limit_issues": len([
            rl for rl in stats["optimizer_stats"]["rate_limiters"].values()
            if rl["recent_errors"] > 0
        ]),
        "recommendations": []
    }
    
    # 生成优化建议
    if stats["wrapper_stats"]["cache_hit_rate"] < 0.1:
        performance_analysis["recommendations"].append(
            "缓存命中率较低，考虑增加缓存大小或调整TTL"
        )
    
    if performance_analysis["circuit_breaker_activations"] > 0:
        performance_analysis["recommendations"].append(
            "检测到熔断器激活，建议检查API提供商状态"
        )
    
    if performance_analysis["rate_limit_issues"] > 0:
        performance_analysis["recommendations"].append(
            "检测到速率限制问题，建议降低并发数或升级API套餐"
        )
    
    return {
        "timestamp": time.time(),
        "performance_stats": stats,
        "analysis": performance_analysis
    }

# 导出主要函数
__all__ = [
    'call_llm_api_with_optimization',
    'optimized_batch_processing', 
    'check_api_health',
    'monitor_api_performance',
    'get_api_performance_report',
    'with_api_optimization'
] 