import os
import re
import time
import glob
import requests
import threading
from queue import Queue
from threading import Thread
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed


def should_run():
    time_file = 'update_time.txt'
    if not os.path.exists(time_file):
        return True
    
    with open(time_file, 'r') as f:
        last_time = datetime.strptime(f.read().strip(), '%Y-%m-%d %H:%M:%S')
    return (datetime.now() - last_time).days >= 0


def update_run_time():
    with open('update_time.txt', 'w') as f:
        f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


def check_ip(ip, port):
    try:
        url = f"http://{ip}:{port}/stat"
        resp = requests.get(url, timeout=2)
        if resp.status_code == 200 and 'Multi stream daemon' in resp.text:
            print(f"[有效IP] {ip}:{port}")
            return f"{ip}:{port}"
    except Exception:
        return None


def generate_ips(ip_part, scan_type):
    a, b, c, d = map(int, ip_part.split('.'))
    if scan_type == 0:  # D段扫描
        return [f"{a}.{b}.{c}.{x}" for x in range(1, 256)]
    else:  # C+D段扫描
        return [f"{a}.{b}.{x}.{y}" for x in range(256) for y in range(256)]


def read_config(config_path):
    configs = []
    try:
        with open(config_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(',')
                if len(parts) != 2:
                    print(f"格式错误 行{line_num}: 需要'IP:端口,扫描类型'格式 -> {line}")
                    continue
                configs.append(parts)
        return configs
    except Exception as e:
        print(f"配置文件错误: {e}")
        return []


def scan_ips(ip_part, port, scan_type):
    print(f"\n开始扫描 {ip_part} 端口 {port} 类型 {scan_type}")
    valid_ips = []
    ips = generate_ips(ip_part, scan_type)
    total = len(ips)
    checked = [0]
    
    def show_progress():
        while checked[0] < total:
            print(f"进度: {checked[0]}/{total} 有效: {len(valid_ips)}")
            time.sleep(10)
    
    Thread(target=show_progress, daemon=True).start()
    
    with ThreadPoolExecutor(max_workers=200 if scan_type==0 else 100) as executor:
        futures = {executor.submit(check_ip, ip, port): ip for ip in ips}
        for future in as_completed(futures):
            result = future.result()
            if result:
                valid_ips.append(result)
            checked[0] += 1
    
    print(f"扫描完成，有效IP数量: {len(valid_ips)}\n")
    return valid_ips


def process_province(config_path):
    filename = os.path.basename(config_path)
    if not filename.endswith("_config.txt"):
        return
    
    province, operator = filename.split('_')[:2]
    print(f"\n{'='*30}\n处理: {province} {operator}\n{'='*30}")
    
    # 扫描IP
    configs = read_config(config_path)
    all_ips = []
    for entry in configs:
        try:
            ip_port, scan_type = entry
            ip_part, port = ip_port.split(':', 1)
            all_ips.extend(scan_ips(ip_part, port, int(scan_type)))
        except Exception as e:
            print(f"配置错误: {entry} -> {e}")
    
    # 生成组播
    tmpl_file = os.path.join('zubo', f"{province}_{operator}.txt")
    if not os.path.exists(tmpl_file):
        print(f"缺少模板文件: {tmpl_file}")
        return
    
    with open(tmpl_file, 'r', encoding='utf-8') as f:
        channels = [line.strip() for line in f if line.strip()]
    
    output = []
    for ip in all_ips:
        output.extend([c.replace("udp://", f"http://{ip}/udp/") for c in channels])
    
    with open(f"{province}_{operator}_组播.txt", 'w', encoding='utf-8') as f:
        f.write('\n'.join(output))


def speed_test():
    speed_queue = Queue()
    results = []
    
    # 加载所有组播频道
    for file in glob.glob("*_组播.txt"):
        with open(file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and ',' in line:
                    name, url = line.split(',', 1)
                    speed_queue.put((name, url))
    
    # 测速线程
    def worker():
        while True:
            try:
                name, url = speed_queue.get(timeout=10)
                start = time.time()
                size = 0
                try:
                    with requests.get(url, stream=True, timeout=5) as r:
                        for chunk in r.iter_content(1024):
                            size += len(chunk)
                            if time.time() - start > 5:
                                break
                    speed = size / (time.time() - start) / 1024 / 1024
                except:
                    speed = 0
                
                if speed > 0.1:
                    results.append((speed, name, url))
                print(f"[测速] {'✓' if speed>0.1 else '✗'} {name[:20]:<20} {speed:.2f}MB/s")
                speed_queue.task_done()
            except:
                break
    
    print("\n开始测速...")
    threads = [Thread(target=worker) for _ in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    
    # 排序保存
    results.sort(reverse=True, key=lambda x: x[0])
    with open("speed.txt", "w", encoding='utf-8') as f:
        f.write('\n'.join([f"{name},{url},{speed:.2f}" for speed, name, url in results]))


def classify_channel(name):
    """智能分类频道"""
    name = name.lower()
    if 'cctv' in name or '央视' in name or '中央' in name:
        return "央视频道,#genre#"
    elif '卫视' in name or '凤凰' in name or '翡翠' in name or '星空' in name:
        return "卫视频道,#genre#"
    elif re.search(r'(湖南|长沙|株洲|湘潭|衡阳|岳阳|常德|张家界|郴州|永州)', name):
        return "湖南频道,#genre#"
    else:
        return "其他频道,#genre#"


def natural_sort_key(s):
    """自然排序算法"""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', s)]


def merge_files():
    # ================= 第一部分：处理分类内容 =================
    category_map = {
        "央视频道,#genre#": [],
        "卫视频道,#genre#": [],
        "湖南频道,#genre#": [],
        "其他频道,#genre#": []
    }

    # 处理测速文件
    if os.path.exists("speed.txt"):
        with open("speed.txt", 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.count(',') >= 2:
                    name, url, _ = line.split(',', 2)
                    category = classify_channel(name)
                    category_map[category].append(f"{name},{url}")

    # 处理组播文件
    for file in glob.glob("*_组播.txt"):
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and ',' in line:
                        name, url = line.split(',', 1)
                        category = classify_channel(name)
                        category_map[category].append(f"{name},{url}")

    # 生成分类内容
    final_content = []
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    final_content.append(f"更新时间,#genre#\n{current_time},url\n")
    
    # 分类区块处理
    for category in ["央视频道,#genre#", "卫视频道,#genre#", "湖南频道,#genre#", "其他频道,#genre#"]:
        channels = category_map[category]
        
        # 去重逻辑
        unique_channels = {}
        for chan in channels:
            name, url = chan.split(',', 1)
            if name not in unique_channels:
                unique_channels[name] = []
            if len(unique_channels[name]) < 10:
                unique_channels[name].append(url)
        
        # 排序处理
        sorted_channels = []
        for name in sorted(unique_channels.keys(), key=natural_sort_key):
            for url in unique_channels[name][:10]:
                sorted_channels.append(f"{name},{url}")
        
        # 添加分类头
        if sorted_channels:
            final_content.append(f"{category}\n" + "\n".join(sorted_channels))

    # ================= 第二部分：追加特殊文件 =================
    special_files = ["AKTV.txt", "hnyd.txt"]
    for file in special_files:
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                # 保持原文件完整结构
                content = []
                current_category = ""
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if line.endswith("#genre#"):
                        current_category = line
                        content.append(f"\n{current_category}")
                    else:
                        content.append(line)
                
                if content:
                    final_content.append("\n".join(content))
                    print(f"已追加文件: {file} (共{len(content)}行)")

    # ================= 写入最终文件 =================
    with open("iptv_list.txt", "w", encoding='utf-8') as f:
        f.write("\n\n".join(final_content))


def main():
    if not should_run():
        print("未达到执行时间间隔")
        return
    
    update_run_time()
    
    # 处理所有省份配置
    for conf in glob.glob(os.path.join('zubo', '*_config.txt')):
        process_province(conf)
    
    # 测速和合并
    speed_test()
    merge_files()
    
    print("\n任务完成! 最终列表已保存至 iptv_list.txt")


if __name__ == "__main__":
    main()
