#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Log Eye 日志获取脚本
支持用户传入 appCode、content、startTime、traceId 参数
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime

try:
    import requests
except ImportError:
    print("错误: 请先安装 requests 库 (pip install requests)")
    sys.exit(1)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class LogEyeFetcher:
    """Log Eye 日志获取器"""

    API_URL = "https://log-eye.souche-inc.com/query/logs"

    DEFAULT_HEADERS = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'zh,en-US;q=0.9,en;q=0.8,zh-TW;q=0.7,zh-CN;q=0.6',
        'content-type': 'application/json;charset=UTF-8',
        'origin': 'https://logplatform.souche-inc.com',
        'priority': 'u=1, i',
        'referer': 'https://logplatform.souche-inc.com/',
        'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    }

    # 固定请求参数
    DEFAULT_PARAMS = {
        "namespace": "souche",
        "env": "prod",
        "level": "INFO ,WARN ,ERROR",
        "thread": "",
        "sort": "asc",
        "pageSize": 100,
        "nodeName": "",
        "clazz": "",
    }

    MAX_RETRIES = 3
    BASE_DELAY = 1
    REQUEST_TIMEOUT = 30
    REQUEST_DELAY = 0.5

    def __init__(self, cookie: str):
        """
        初始化获取器
        :param cookie: 认证Cookie
        """
        self.headers = self.DEFAULT_HEADERS.copy()
        self.headers['Cookie'] = cookie

    def fetch_logs(self, page_num: int = 0, **kwargs) -> dict:
        """
        获取日志数据
        :param page_num: 页码
        :param kwargs: 用户传入的参数 (appCode, content, startTime, traceId)
        :return: 响应数据
        """
        # 构建请求参数
        payload = self.DEFAULT_PARAMS.copy()
        payload['pageNum'] = page_num
        payload['appCode'] = kwargs.get('appCode', '')
        payload['content'] = kwargs.get('content', '')
        payload['startTime'] = kwargs.get('startTime', 0)
        
        trace_id = kwargs.get('traceId', '')
        if trace_id:
            payload['traceId'] = trace_id

        retry_count = 0

        while retry_count <= self.MAX_RETRIES:
            try:
                logger.info(f"正在获取第 {page_num} 页数据 (尝试 {retry_count + 1}/{self.MAX_RETRIES + 1})...")
                
                response = requests.post(
                    self.API_URL,
                    headers=self.headers,
                    data=json.dumps(payload),
                    timeout=self.REQUEST_TIMEOUT
                )

                if response.status_code == 429:
                    retry_count += 1
                    if retry_count > self.MAX_RETRIES:
                        logger.error(f"获取第 {page_num} 页数据失败：请求过于频繁，已达到最大重试次数")
                        return None

                    delay = self.BASE_DELAY * (2 ** (retry_count - 1))
                    logger.warning(f"请求过于频繁，将在 {delay:.2f} 秒后重试...")
                    time.sleep(delay)
                    continue

                elif 500 <= response.status_code < 600:
                    retry_count += 1
                    if retry_count > self.MAX_RETRIES:
                        logger.error(f"获取第 {page_num} 页数据失败：服务器错误 {response.status_code}，已达到最大重试次数")
                        return None

                    delay = self.BASE_DELAY * (2 ** (retry_count - 1))
                    logger.warning(f"服务器错误 {response.status_code}，将在 {delay:.2f} 秒后重试...")
                    time.sleep(delay)
                    continue

                response.raise_for_status()

                try:
                    return response.json()
                except json.JSONDecodeError:
                    logger.error(f"获取第 {page_num} 页数据失败：响应不是有效的JSON格式")
                    return None

            except requests.exceptions.Timeout:
                retry_count += 1
                if retry_count > self.MAX_RETRIES:
                    logger.error(f"获取第 {page_num} 页数据失败：请求超时，已达到最大重试次数")
                    return None

                delay = self.BASE_DELAY * (2 ** (retry_count - 1))
                logger.warning(f"请求超时，将在 {delay:.2f} 秒后重试...")
                time.sleep(delay)

            except requests.exceptions.ConnectionError:
                retry_count += 1
                if retry_count > self.MAX_RETRIES:
                    logger.error(f"获取第 {page_num} 页数据失败：连接错误，已达到最大重试次数")
                    return None

                delay = self.BASE_DELAY * (2 ** (retry_count - 1))
                logger.warning(f"连接错误，将在 {delay:.2f} 秒后重试...")
                time.sleep(delay)

            except requests.exceptions.RequestException as e:
                logger.error(f"获取第 {page_num} 页数据失败：{str(e)}")
                return None

        return None

    def is_empty_data(self, data: dict) -> bool:
        """判断返回的数据是否为空"""
        if not data:
            return True
        if 'success' in data and not data['success']:
            return True
        if 'data' not in data:
            return True
        if 'logs' not in data['data']:
            return True
        if isinstance(data['data']['logs'], list) and len(data['data']['logs']) == 0:
            return True
        return False

    def parse_log_entry(self, log_str: str) -> dict:
        """解析日志条目"""
        try:
            return json.loads(log_str)
        except json.JSONDecodeError:
            logger.warning(f"无法解析日志条目: {log_str[:100]}...")
            return None

    def run(self, app_code: str, content: str, start_time: int, trace_id: str = None, output_file: str = None):
        """
        运行日志获取
        :param app_code: 应用代码
        :param content: 日志内容关键字
        :param start_time: 开始时间 (毫秒时间戳)
        :param trace_id: 追踪ID (可选)
        :param output_file: 输出文件路径
        """
        page_num = 0
        total_count = 0
        parsed_count = 0
        parse_error_count = 0
        success_pages = 0
        failed_pages = 0
        start_time_ts = time.time()

        # 确定输出文件
        if output_file is None:
            current_time = datetime.now()
            output_file = f"logs_{current_time.strftime('%Y%m%d_%H%M%S')}.txt"

        logger.info(f"开始获取日志数据")
        logger.info(f"  appCode: {app_code}")
        logger.info(f"  content: {content}")
        logger.info(f"  startTime: {start_time}")
        logger.info(f"  traceId: {trace_id or '(未指定)'}")
        logger.info(f"  输出文件: {output_file}")

        try:
            while True:
                data = self.fetch_logs(
                    page_num,
                    appCode=app_code,
                    content=content,
                    startTime=start_time,
                    traceId=trace_id or ''
                )

                if self.is_empty_data(data):
                    logger.info(f"第 {page_num} 页没有数据或获取失败，结束循环")
                    if not data:
                        failed_pages += 1
                    break

                if 'data' in data and 'logs' in data['data'] and isinstance(data['data']['logs'], list):
                    logs_list = data['data']['logs']
                    page_log_count = len(logs_list)
                    page_parsed_count = 0

                    # 解析并保存每条日志
                    with open(output_file, 'a', encoding='utf-8') as f:
                        for log_str in logs_list:
                            parsed_log = self.parse_log_entry(log_str)
                            if parsed_log:
                                f.write(json.dumps(parsed_log, ensure_ascii=False) + '\n')
                                parsed_count += 1
                                page_parsed_count += 1
                            else:
                                parse_error_count += 1

                    total_count += page_log_count
                    success_pages += 1

                    logger.info(f"成功获取第 {page_num} 页，共 {page_log_count} 条原始日志，解析成功 {page_parsed_count} 条")

                    # 获取总页数信息
                    if 'data' in data and 'totalNum' in data['data']:
                        total_num = data['data']['totalNum']
                        logger.info(f"总记录数: {total_num}, 已获取: {total_count}/{total_num}")

                    # 检查是否还有更多数据
                    if page_log_count < self.DEFAULT_PARAMS['pageSize']:
                        logger.info("数据已获取完毕")
                        break
                else:
                    logger.warning(f"第 {page_num} 页数据格式不符合预期")
                    failed_pages += 1

                page_num += 1
                time.sleep(self.REQUEST_DELAY)

        except KeyboardInterrupt:
            logger.info("程序被用户中断")
        except Exception as e:
            logger.error(f"程序运行出错: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")

        end_time_ts = time.time()
        elapsed_time = end_time_ts - start_time_ts

        logger.info("=" * 60)
        logger.info("数据获取完成！")
        logger.info(f"总计耗时: {elapsed_time:.2f} 秒")
        logger.info(f"成功获取页面数: {success_pages}")
        logger.info(f"失败页面数: {failed_pages}")
        logger.info(f"总共获取原始日志条数: {total_count}")
        logger.info(f"成功解析日志条数: {parsed_count}")
        logger.info(f"解析失败日志条数: {parse_error_count}")
        logger.info(f"数据已保存到: {output_file}")


def main():
    # 从环境变量读取Cookie
    cookie = os.environ.get('sc_inc_cookie')
    
    if not cookie:
        print("错误: 请设置环境变量 sc_inc_cookie")
        print("示例: export sc_inc_cookie='_security_token_inc=9177210962036881; acw_tc=...'")
        sys.exit(1)
    
    parser = argparse.ArgumentParser(description='Log Eye 日志获取工具')
    parser.add_argument('--cookie', '-c', help='认证Cookie (已废弃，请使用环境变量 sc_inc_cookie)')
    parser.add_argument('--app-code', '-a', required=True, help='应用代码 (appCode)')
    parser.add_argument('--content', '-k', default='', help='日志内容关键字 (可选，为空时查询所有日志)')
    parser.add_argument('--start-time', '-s', required=True, type=int, help='开始时间 (毫秒时间戳)')
    parser.add_argument('--trace-id', '-t', default=None, help='追踪ID (traceId, 可选)')
    parser.add_argument('--output', '-o', default=None, help='输出文件路径 (可选)')

    args = parser.parse_args()

    fetcher = LogEyeFetcher(cookie=cookie)
    fetcher.run(
        app_code=args.app_code,
        content=args.content,
        start_time=args.start_time,
        trace_id=args.trace_id,
        output_file=args.output
    )


if __name__ == "__main__":
    main()
