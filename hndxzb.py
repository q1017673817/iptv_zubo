# main.py
import os
import re
import time
import aiohttp
import asyncio
from datetime import datetime, timedelta
from ratelimit import limits, sleep_and_retry
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('iptv_scanner.log'),
        logging.StreamHandler()
    ]
)

# 常量配置
CONFIG_PATH = 'config.txt'
OUTPUT_DIR = 'output'
SAFE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'en-US,en;q=0.9'
}
MAX_WORKERS = 50  # 异步并发数
TEST_DURATION = 5  # 测速时长(秒)

class ConfigManager:
    @staticmethod
    def should_run():
        """检查是否达到执行间隔"""
        if not os.path.exists('update_time.txt'):
            return True
        with open('update_time.txt', 'r') as f:
            last_run = datetime.strptime(f.read().strip(), '%Y-%m-%d %H:%M:%S')
        return datetime.now() - last_run >= timedelta(hours=6)

    @staticmethod
    def update_timestamp():
        with open('update_time.txt', 'w') as f:
            f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

class IPScanner:
    def __init__(self):
        self.valid_ips = set()
    
    @sleep_and_retry
    @limits(calls=100, period=60)
    async def check_ip(self, session, ip, port):
        """异步检查单个IP有效性"""
        try:
            url = f"http://{ip}:{port}/stat"
            async with session.get(url, headers=SAFE_HEADERS, timeout=3) as response:
                if response.status == 200:
                    text = await response.text()
                    if 'msd' in response.headers.get('Server', '').lower():
                        return f"{ip}:{port}"
        except Exception as e:
            logging.debug(f"IP检查失败 {ip}:{port} - {str(e)}")
        return None

    async def scan_range(self, ip_base, port, scan_type):
        """扫描指定IP段"""
        base_parts = list(map(int, ip_base.split('.')))
        tasks = []
        
        async with aiohttp.ClientSession() as session:
            # 生成扫描IP列表
            if scan_type == 0:
                ips = [f"{'.'.join(map(str, base_parts[:3]))}.{d}" for d in range(1,256)]
            else:
                ips = [f"{'.'.join(map(str, base_parts[:2]))}.{c}.{d}" 
                      for c in range(256) for d in range(1,256)]
            
            # 创建异步任务
            for ip in ips:
                tasks.append(self.check_ip(session, ip, port))
            
            # 分批处理结果
            for i in range(0, len(tasks), MAX_WORKERS):
                batch = tasks[i:i+MAX_WORKERS]
                results = await asyncio.gather(*batch)
                for result in results:
                    if result:
                        self.valid_ips.add(result)
                        logging.info(f"发现有效IP: {result}")

class SpeedTester:
    async def test_speed(self, session, name, url):
        """异步测速"""
        try:
            start = time.time()
            async with session.get(url, headers=SAFE_HEADERS, timeout=TEST_DURATION+2) as response:
                response.raise_for_status()
                downloaded = 0
                async for chunk in response.content.iter_chunked(1024):
                    downloaded += len(chunk)
                    if time.time() - start > TEST_DURATION:
                        break
                duration = time.time() - start
                return (name, url, downloaded/duration/1024/1024)  # MB/s
        except Exception as e:
            logging.debug(f"测速失败 {url} - {str(e)}")
            return (name, url, 0)

class ChannelProcessor:
    @staticmethod
    def categorize_channels(channels):
        """分类处理频道"""
        categories = {
            '央视频道,#genre#': [],
            '卫视频道,#genre#': [],
            '湖南频道,#genre#': [],
            '其他频道,#genre#': []
        }
        
        for name, url, speed in channels:
            name_lower = name.lower()
            if 'cctv' in name_lower or '央视' in name:
                key = '央视频道,#genre#'
            elif '卫视' in name or '凤凰' in name:
                key = '卫视频道,#genre#'
            elif re.search(r'(湖南|长沙|株洲|湘潭|衡阳)', name):
                key = '湖南频道,#genre#'
            else:
                key = '其他频道,#genre#'
            
            categories[key].append((name, url, speed))
        
        # 排序和过滤
        for cat in categories.values():
            cat.sort(key=lambda x: (-x[2], x[0]))  # 按速度降序，名称升序
            # 去重逻辑
            seen = set()
            filtered = []
            for item in cat:
                if item[0] not in seen:
                    seen.add(item[0])
                    filtered.append(item)
                if len(filtered) >= 15:  # 每类最多保留15个
                    break
            cat[:] = filtered
        
        return categories

async def main():
    if not ConfigManager.should_run():
        logging.info("未达到执行间隔，跳过本次运行")
        return

    # 阶段1：IP扫描
    scanner = IPScanner()
    configs = []
    try:
        with open(CONFIG_PATH) as f:
            for line in f:
                ip_port, scan_type = line.strip().rsplit(',', 1)
                ip, port = ip_port.split(':')
                configs.append((ip, int(port), int(scan_type)))
    except Exception as e:
        logging.error(f"配置文件错误: {str(e)}")
        return

    for ip_base, port, scan_type in configs:
        logging.info(f"开始扫描 {ip_base}:{port} 类型{scan_type}")
        await scanner.scan_range(ip_base, port, scan_type)
    
    # 保存有效IP
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(f'{OUTPUT_DIR}/valid_ips.txt', 'w') as f:
        f.write('\n'.join(scanner.valid_ips))

    # 阶段2：频道测速
    tester = SpeedTester()
    speed_results = []
    async with aiohttp.ClientSession() as session:
        tasks = []
        # 读取原始频道列表
        with open('zubo/湖南_电信.txt') as f:
            for line in f:
                if line.strip():
                    name, url = line.strip().split(',', 1)
                    for ip in scanner.valid_ips:
                        new_url = url.replace("udp://", f"http://{ip}/udp/")
                        tasks.append(tester.test_speed(session, name, new_url))
        
        # 分批处理测速任务
        for i in range(0, len(tasks), MAX_WORKERS):
            batch = tasks[i:i+MAX_WORKERS]
            results = await asyncio.gather(*batch)
            speed_results.extend(results)
            logging.info(f"完成测速批次 {i//MAX_WORKERS+1}/{(len(tasks)+MAX_WORKERS-1)//MAX_WORKERS}")

    # 阶段3：频道处理
    processor = ChannelProcessor()
    categorized = processor.categorize_channels([r for r in speed_results if r[2] > 0.1])
    
    # 生成最终文件
    with open(f'{OUTPUT_DIR}/iptv_list.txt', 'w') as f:
        f.write(f"更新时间,#genre#\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')},url\n\n")
        for category, channels in categorized.items():
            f.write(f"{category}:\n")
            for name, url, speed in channels:
                f.write(f"{name},{url}\n")
            f.write("\n")
    
    ConfigManager.update_timestamp()
    logging.info("任务执行完成")

if __name__ == "__main__":
    asyncio.run(main())
