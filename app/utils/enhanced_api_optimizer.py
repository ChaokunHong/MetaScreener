#!/usr/bin/env python3
"""
Enhanced API Optimizer for MetaScreener
实现熔断器、自适应速率限制、智能负载均衡等高级优化功能
"""

import time
import random
import logging
import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque, defaultdict
import hashlib
import json

# Setup logging
optimizer_logger = logging.getLogger("api_optimizer")

class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"      # 正常状态
    OPEN = "open"          # 熔断状态
    HALF_OPEN = "half_open"  # 半开状态

@dataclass
class APIMetrics:
    """API性能指标"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rate_limit_errors: int = 0
    timeout_errors: int = 0
    avg_response_time: float = 0.0
    last_success_time: float = 0.0
    last_failure_time: float = 0.0
    consecutive_failures: int = 0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests
    
    @property
    def failure_rate(self) -> float:
        """失败率"""
        return 1.0 - self.success_rate

@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""
    failure_threshold: int = 5          # 失败阈值
    recovery_timeout: int = 60          # 恢复超时(秒)
    success_threshold: int = 3          # 成功阈值
    timeout: int = 30                   # 请求超时(秒)
    enable_fallback: bool = True        # 启用降级
    
class CircuitBreaker:
    """熔断器实现"""
    
    def __init__(self, provider_name: str, model_id: str, config: CircuitBreakerConfig):
        self.provider_name = provider_name
        self.model_id = model_id
        self.config = config
        self.state = CircuitState.CLOSED
        self.metrics = APIMetrics()
        self.last_failure_time = 0.0
        self.half_open_success_count = 0
        self._lock = threading.Lock()
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """执行API调用，带熔断保护"""
        with self._lock:
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time < self.config.recovery_timeout:
                    raise CircuitBreakerOpenError(f"Circuit breaker is OPEN for {self.provider_name}-{self.model_id}")
                else:
                    # 尝试半开状态
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_success_count = 0
                    optimizer_logger.info(f"Circuit breaker entering HALF_OPEN state for {self.provider_name}-{self.model_id}")
        
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            self._record_success(time.time() - start_time)
            return result
        except Exception as e:
            self._record_failure(time.time() - start_time, e)
            raise
    
    def _record_success(self, response_time: float):
        """记录成功调用"""
        with self._lock:
            self.metrics.total_requests += 1
            self.metrics.successful_requests += 1
            self.metrics.last_success_time = time.time()
            self.metrics.consecutive_failures = 0
            
            # 更新平均响应时间
            if self.metrics.avg_response_time == 0:
                self.metrics.avg_response_time = response_time
            else:
                self.metrics.avg_response_time = (self.metrics.avg_response_time * 0.9) + (response_time * 0.1)
            
            if self.state == CircuitState.HALF_OPEN:
                self.half_open_success_count += 1
                if self.half_open_success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    optimizer_logger.info(f"Circuit breaker CLOSED for {self.provider_name}-{self.model_id}")
    
    def _record_failure(self, response_time: float, error: Exception):
        """记录失败调用"""
        with self._lock:
            self.metrics.total_requests += 1
            self.metrics.failed_requests += 1
            self.metrics.last_failure_time = time.time()
            self.metrics.consecutive_failures += 1
            
            # 分类错误类型
            error_str = str(error).lower()
            if "rate limit" in error_str or "429" in error_str:
                self.metrics.rate_limit_errors += 1
            elif "timeout" in error_str:
                self.metrics.timeout_errors += 1
            
            # 检查是否需要打开熔断器
            if (self.state == CircuitState.CLOSED and 
                self.metrics.consecutive_failures >= self.config.failure_threshold):
                self.state = CircuitState.OPEN
                self.last_failure_time = time.time()
                optimizer_logger.warning(f"Circuit breaker OPENED for {self.provider_name}-{self.model_id} after {self.metrics.consecutive_failures} failures")
            elif self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.last_failure_time = time.time()
                optimizer_logger.warning(f"Circuit breaker returned to OPEN from HALF_OPEN for {self.provider_name}-{self.model_id}")

class CircuitBreakerOpenError(Exception):
    """熔断器开启异常"""
    pass

class AdaptiveRateLimiter:
    """自适应速率限制器"""
    
    def __init__(self, provider_name: str, model_id: str, initial_rpm: int = 60):
        self.provider_name = provider_name
        self.model_id = model_id
        self.current_rpm = initial_rpm
        self.request_times = deque()
        self.recent_errors = deque()
        self.last_rate_limit_time = 0.0
        self._lock = threading.Lock()
        
        # 自适应参数
        self.min_rpm = max(10, initial_rpm // 10)  # 最小速率
        self.max_rpm = initial_rpm * 2             # 最大速率
        self.adjustment_factor = 0.1               # 调整因子
    
    def acquire(self) -> bool:
        """获取请求许可"""
        with self._lock:
            now = time.time()
            
            # 清理过期的请求记录
            cutoff_time = now - 60.0  # 保留最近1分钟的记录
            while self.request_times and self.request_times[0] < cutoff_time:
                self.request_times.popleft()
            
            # 检查当前速率
            current_requests = len(self.request_times)
            if current_requests >= self.current_rpm:
                return False  # 超过速率限制
            
            # 记录请求时间
            self.request_times.append(now)
            return True
    
    def record_rate_limit_error(self):
        """记录速率限制错误"""
        with self._lock:
            now = time.time()
            self.recent_errors.append(now)
            self.last_rate_limit_time = now
            
            # 清理过期错误记录
            cutoff_time = now - 300.0  # 保留最近5分钟的错误
            while self.recent_errors and self.recent_errors[0] < cutoff_time:
                self.recent_errors.popleft()
            
            # 降低速率
            old_rpm = self.current_rpm
            self.current_rpm = max(self.min_rpm, int(self.current_rpm * (1 - self.adjustment_factor)))
            optimizer_logger.warning(f"Rate limit hit for {self.provider_name}-{self.model_id}, reducing RPM from {old_rpm} to {self.current_rpm}")
    
    def record_success(self):
        """记录成功请求，可能提高速率"""
        with self._lock:
            now = time.time()
            
            # 如果最近没有速率限制错误，尝试提高速率
            if now - self.last_rate_limit_time > 120.0:  # 2分钟内没有速率限制错误
                if len(self.recent_errors) == 0:  # 最近5分钟内没有错误
                    old_rpm = self.current_rpm
                    self.current_rpm = min(self.max_rpm, int(self.current_rpm * (1 + self.adjustment_factor / 2)))
                    if old_rpm != self.current_rpm:
                        optimizer_logger.info(f"Increasing RPM for {self.provider_name}-{self.model_id} from {old_rpm} to {self.current_rpm}")

class LoadBalancer:
    """智能负载均衡器"""
    
    def __init__(self):
        self.provider_metrics: Dict[str, APIMetrics] = defaultdict(APIMetrics)
        self.provider_weights: Dict[str, float] = defaultdict(lambda: 1.0)
        self._lock = threading.Lock()
    
    def select_provider(self, available_providers: List[str], exclude_providers: List[str] = None) -> Optional[str]:
        """选择最优的提供商"""
        if exclude_providers is None:
            exclude_providers = []
        
        candidates = [p for p in available_providers if p not in exclude_providers]
        if not candidates:
            return None
        
        with self._lock:
            # 计算每个提供商的得分
            scores = {}
            for provider in candidates:
                metrics = self.provider_metrics[provider]
                weight = self.provider_weights[provider]
                
                # 综合评分：成功率 * 权重 / 平均响应时间
                if metrics.avg_response_time > 0:
                    score = (metrics.success_rate * weight) / metrics.avg_response_time
                else:
                    score = metrics.success_rate * weight
                
                # 惩罚最近有失败的提供商
                if time.time() - metrics.last_failure_time < 60.0:
                    score *= 0.5
                
                scores[provider] = score
            
            # 选择得分最高的提供商
            if scores:
                return max(scores.keys(), key=lambda k: scores[k])
            else:
                return random.choice(candidates)
    
    def record_result(self, provider: str, success: bool, response_time: float):
        """记录提供商的调用结果"""
        with self._lock:
            metrics = self.provider_metrics[provider]
            metrics.total_requests += 1
            
            if success:
                metrics.successful_requests += 1
                metrics.last_success_time = time.time()
                metrics.consecutive_failures = 0
                
                # 更新平均响应时间
                if metrics.avg_response_time == 0:
                    metrics.avg_response_time = response_time
                else:
                    metrics.avg_response_time = (metrics.avg_response_time * 0.9) + (response_time * 0.1)
                
                # 提高权重
                self.provider_weights[provider] = min(2.0, self.provider_weights[provider] * 1.01)
            else:
                metrics.failed_requests += 1
                metrics.last_failure_time = time.time()
                metrics.consecutive_failures += 1
                
                # 降低权重
                self.provider_weights[provider] = max(0.1, self.provider_weights[provider] * 0.95)

class ResponseCache:
    """响应缓存"""
    
    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        self.max_size = max_size
        self.ttl = ttl
        self.cache: Dict[str, Dict] = {}
        self._lock = threading.Lock()
    
    def _generate_key(self, provider: str, model: str, prompt: str, params: Dict) -> str:
        """生成缓存键"""
        key_data = {
            'provider': provider,
            'model': model,
            'prompt': prompt,
            'params': sorted(params.items())
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, provider: str, model: str, prompt: str, params: Dict) -> Optional[Dict]:
        """获取缓存的响应"""
        key = self._generate_key(provider, model, prompt, params)
        
        with self._lock:
            if key in self.cache:
                entry = self.cache[key]
                if time.time() - entry['timestamp'] < self.ttl:
                    optimizer_logger.debug(f"Cache hit for {provider}-{model}")
                    return entry['response']
                else:
                    # 过期，删除
                    del self.cache[key]
        
        return None
    
    def put(self, provider: str, model: str, prompt: str, params: Dict, response: Dict):
        """缓存响应"""
        key = self._generate_key(provider, model, prompt, params)
        
        with self._lock:
            # 如果缓存已满，删除最旧的条目
            if len(self.cache) >= self.max_size:
                oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]['timestamp'])
                del self.cache[oldest_key]
            
            self.cache[key] = {
                'response': response,
                'timestamp': time.time()
            }
            optimizer_logger.debug(f"Cached response for {provider}-{model}")

class EnhancedAPIOptimizer:
    """增强的API优化器"""
    
    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.rate_limiters: Dict[str, AdaptiveRateLimiter] = {}
        self.load_balancer = LoadBalancer()
        self.response_cache = ResponseCache()
        self._lock = threading.Lock()
        
        # 从配置加载熔断器设置
        from config.config import CIRCUIT_BREAKER_CONFIG
        self.circuit_config = CircuitBreakerConfig(**CIRCUIT_BREAKER_CONFIG)
    
    def get_circuit_breaker(self, provider: str, model: str) -> CircuitBreaker:
        """获取或创建熔断器"""
        key = f"{provider}-{model}"
        if key not in self.circuit_breakers:
            with self._lock:
                if key not in self.circuit_breakers:
                    self.circuit_breakers[key] = CircuitBreaker(provider, model, self.circuit_config)
        return self.circuit_breakers[key]
    
    def get_rate_limiter(self, provider: str, model: str) -> AdaptiveRateLimiter:
        """获取或创建速率限制器"""
        key = f"{provider}-{model}"
        if key not in self.rate_limiters:
            with self._lock:
                if key not in self.rate_limiters:
                    # 从配置获取初始RPM
                    from config.config import get_model_specific_config
                    config = get_model_specific_config(provider, model)
                    initial_rpm = config.get('rate_limit', {}).get('requests_per_minute', 60)
                    self.rate_limiters[key] = AdaptiveRateLimiter(provider, model, initial_rpm)
        return self.rate_limiters[key]
    
    def optimized_api_call(self, provider: str, model: str, api_func: Callable, 
                          prompt: str, params: Dict, *args, **kwargs) -> Dict:
        """执行优化的API调用"""
        
        # 1. 检查缓存
        cached_response = self.response_cache.get(provider, model, prompt, params)
        if cached_response:
            return cached_response
        
        # 2. 检查速率限制
        rate_limiter = self.get_rate_limiter(provider, model)
        if not rate_limiter.acquire():
            # 等待或使用备用提供商
            fallback_providers = self.circuit_config.fallback_providers.get(provider, [])
            if fallback_providers:
                alternative = self.load_balancer.select_provider(fallback_providers)
                if alternative:
                    optimizer_logger.info(f"Rate limit hit for {provider}-{model}, using fallback {alternative}")
                    return self.optimized_api_call(alternative, model, api_func, prompt, params, *args, **kwargs)
            
            # 等待速率限制恢复
            time.sleep(60.0 / rate_limiter.current_rpm)
        
        # 3. 使用熔断器执行调用
        circuit_breaker = self.get_circuit_breaker(provider, model)
        
        start_time = time.time()
        try:
            response = circuit_breaker.call(api_func, *args, **kwargs)
            response_time = time.time() - start_time
            
            # 记录成功
            rate_limiter.record_success()
            self.load_balancer.record_result(provider, True, response_time)
            
            # 缓存响应
            if response.get('label') in ['INCLUDE', 'EXCLUDE', 'MAYBE']:  # 只缓存有效响应
                self.response_cache.put(provider, model, prompt, params, response)
            
            return response
            
        except CircuitBreakerOpenError:
            # 熔断器开启，尝试备用提供商
            fallback_providers = self.circuit_config.fallback_providers.get(provider, [])
            if fallback_providers:
                alternative = self.load_balancer.select_provider(fallback_providers, [provider])
                if alternative:
                    optimizer_logger.warning(f"Circuit breaker open for {provider}-{model}, using fallback {alternative}")
                    return self.optimized_api_call(alternative, model, api_func, prompt, params, *args, **kwargs)
            raise
            
        except Exception as e:
            response_time = time.time() - start_time
            
            # 记录失败
            error_str = str(e).lower()
            if "rate limit" in error_str or "429" in error_str:
                rate_limiter.record_rate_limit_error()
            
            self.load_balancer.record_result(provider, False, response_time)
            raise
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """获取优化统计信息"""
        stats = {
            'circuit_breakers': {},
            'rate_limiters': {},
            'load_balancer': {},
            'cache': {
                'size': len(self.response_cache.cache),
                'max_size': self.response_cache.max_size,
                'hit_rate': 0.0  # 需要实现命中率统计
            }
        }
        
        # 熔断器统计
        for key, cb in self.circuit_breakers.items():
            stats['circuit_breakers'][key] = {
                'state': cb.state.value,
                'success_rate': cb.metrics.success_rate,
                'avg_response_time': cb.metrics.avg_response_time,
                'consecutive_failures': cb.metrics.consecutive_failures
            }
        
        # 速率限制器统计
        for key, rl in self.rate_limiters.items():
            stats['rate_limiters'][key] = {
                'current_rpm': rl.current_rpm,
                'recent_requests': len(rl.request_times),
                'recent_errors': len(rl.recent_errors)
            }
        
        # 负载均衡器统计
        for provider, metrics in self.load_balancer.provider_metrics.items():
            stats['load_balancer'][provider] = {
                'success_rate': metrics.success_rate,
                'avg_response_time': metrics.avg_response_time,
                'weight': self.load_balancer.provider_weights[provider]
            }
        
        return stats

# 全局优化器实例
api_optimizer = EnhancedAPIOptimizer()

def get_api_optimizer() -> EnhancedAPIOptimizer:
    """获取全局API优化器实例"""
    return api_optimizer 