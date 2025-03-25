import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from ipaddress import ip_network
import socket
import threading
import queue

class PortScannerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("端口扫描工具")
        self.root.resizable(False, False)
        
        # 创建线程安全队列
        self.output_queue = queue.Queue()
        self.scanning = False
        
        # 初始化界面
        self.create_widgets()
        
        # 启动队列检查
        self.process_queue()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 输入区域
        ttk.Label(main_frame, text="IP范围（CIDR格式，如192.168.1.0/24）:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.ip_entry = ttk.Entry(main_frame, width=30)
        self.ip_entry.grid(row=0, column=1, pady=2, padx=5)

        ttk.Label(main_frame, text="起始端口:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.start_port_entry = ttk.Entry(main_frame, width=10)
        self.start_port_entry.grid(row=1, column=1, sticky=tk.W, pady=2, padx=5)

        ttk.Label(main_frame, text="结束端口:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.end_port_entry = ttk.Entry(main_frame, width=10)
        self.end_port_entry.grid(row=2, column=1, sticky=tk.W, pady=2, padx=5)

        ttk.Label(main_frame, text="线程数:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.threads_entry = ttk.Entry(main_frame, width=10)
        self.threads_entry.insert(0, "50")  # 默认线程数
        self.threads_entry.grid(row=3, column=1, sticky=tk.W, pady=2, padx=5)

        # 按钮区域
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=4, columnspan=2, pady=10)
        
        self.start_btn = ttk.Button(btn_frame, text="开始扫描", command=self.start_scan)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="退出", command=self.root.quit).pack(side=tk.LEFT, padx=5)

        # 输出区域
        output_frame = ttk.Frame(main_frame)
        output_frame.grid(row=5, columnspan=2)
        
        self.output_area = scrolledtext.ScrolledText(output_frame, width=60, height=20, wrap=tk.WORD)
        self.output_area.pack()
        self.output_area.configure(state='disabled')

    def validate_inputs(self):
        try:
            # 验证IP格式
            ip_str = self.ip_entry.get().strip()
            if not ip_str:
                raise ValueError("IP范围不能为空")
                
            # 验证端口范围
            start_port = int(self.start_port_entry.get())
            end_port = int(self.end_port_entry.get())
            if not (0 < start_port <= 65535) or not (0 < end_port <= 65535):
                raise ValueError("端口号必须在1-65535之间")
            if start_port > end_port:
                raise ValueError("起始端口不能大于结束端口")
                
            # 验证线程数
            threads = int(self.threads_entry.get())
            if threads <= 0:
                raise ValueError("线程数必须大于0")
                
            return ip_str, start_port, end_port, threads
            
        except ValueError as e:
            messagebox.showerror("输入错误", str(e))
            return None

    def start_scan(self):
        if self.scanning:
            return
            
        inputs = self.validate_inputs()
        if not inputs:
            return
            
        ip_str, start_port, end_port, num_threads = inputs
        
        try:
            network = ip_network(ip_str, strict=False)
        except ValueError:
            messagebox.showerror("错误", "无效的IP地址或CIDR格式")
            return
            
        # 禁用开始按钮
        self.start_btn.config(state=tk.DISABLED)
        self.scanning = True
        
        # 启动扫描线程
        scan_thread = threading.Thread(
            target=self.run_scan,
            args=(network, start_port, end_port, num_threads),
            daemon=True
        )
        scan_thread.start()

    def run_scan(self, network, start_port, end_port, num_threads):
        try:
            # 创建线程池
            threads = []
            for ip in network.hosts():
                if not self.scanning:
                    break
                    
                t = threading.Thread(
                    target=self.scan_ip,
                    args=(str(ip), start_port, end_port),
                    daemon=True
                )
                t.start()
                threads.append(t)
                
                # 控制线程数量
                while len(threads) >= num_threads:
                    t = threads.pop(0)
                    t.join(timeout=0.1)
                    
            # 等待剩余线程
            for t in threads:
                t.join()
                
        except Exception as e:
            self.output_queue.put(f"扫描错误: {str(e)}")
        finally:
            self.output_queue.put("扫描完成")
            self.scanning = False
            self.root.after(100, lambda: self.start_btn.config(state=tk.NORMAL))

    def scan_ip(self, ip, start_port, end_port):
        for port in range(start_port, end_port + 1):
            if not self.scanning:
                return
                
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((ip, port))
                if result == 0:
                    self.output_queue.put(f"发现开放端口: {ip}:{port}")
                sock.close()
            except Exception:
                pass

    def process_queue(self):
        while not self.output_queue.empty():
            msg = self.output_queue.get_nowait()
            self.update_output(msg)
        self.root.after(100, self.process_queue)

    def update_output(self, text):
        self.output_area.configure(state='normal')
        self.output_area.insert(tk.END, text + "\n")
        self.output_area.see(tk.END)
        self.output_area.configure(state='disabled')

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = PortScannerGUI()
    app.run()
