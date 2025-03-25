import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from ipaddress import ip_network
import socket
import threading
import queue
import time

class PortScannerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("端口扫描工具 by luoye")
        self.root.resizable(False, False)
        
        # 初始化变量
        self.output_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        self.scanning = False
        self.total_tasks = 0
        self.completed_tasks = 0
        
        self.create_widgets()
        self.process_queues()

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
        self.threads_entry.insert(0, "200")
        self.threads_entry.grid(row=3, column=1, sticky=tk.W, pady=2, padx=5)

        # 按钮区域
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=4, columnspan=2, pady=10)
        self.start_btn = ttk.Button(btn_frame, text="开始扫描", command=self.start_scan)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="退出", command=self.root.quit).pack(side=tk.LEFT, padx=5)

        # 进度条区域
        ttk.Label(main_frame, text="扫描进度:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.progress_bar = ttk.Progressbar(main_frame, orient=tk.HORIZONTAL, length=300, mode='determinate')
        self.progress_bar.grid(row=5, column=1, pady=5, sticky=tk.W)
        self.progress_label = ttk.Label(main_frame, text="准备就绪")
        self.progress_label.grid(row=6, columnspan=2, pady=2)

        # 输出区域
        output_frame = ttk.Frame(main_frame)
        output_frame.grid(row=7, columnspan=2)
        self.output_area = scrolledtext.ScrolledText(output_frame, width=60, height=20, wrap=tk.WORD)
        self.output_area.pack()
        self.output_area.configure(state='disabled')

    def validate_inputs(self):
        try:
            ip_str = self.ip_entry.get().strip()
            if not ip_str:
                raise ValueError("IP范围不能为空")
                
            start_port = int(self.start_port_entry.get())
            end_port = int(self.end_port_entry.get())
            if not (0 < start_port <= 65535) or not (0 < end_port <= 65535):
                raise ValueError("端口号必须在1-65535之间")
            if start_port > end_port:
                raise ValueError("起始端口不能大于结束端口")
                
            threads = int(self.threads_entry.get())
            if threads <= 0:
                raise ValueError("线程数必须大于0")
                
            return ip_str, start_port, end_port, threads
            
        except ValueError as e:
            messagebox.showerror("输入错误", str(e))
            return None

    def calculate_total_tasks(self, network, start_port, end_port):
        try:
            ip_count = sum(1 for _ in network.hosts())
            port_count = end_port - start_port + 1
            return ip_count * port_count
        except:
            return 0

    def start_scan(self):
        if self.scanning:
            return
            
        inputs = self.validate_inputs()
        if not inputs:
            return
            
        ip_str, start_port, end_port, num_threads = inputs
        
        try:
            network = ip_network(ip_str, strict=False)
            self.total_tasks = self.calculate_total_tasks(network, start_port, end_port)
            if self.total_tasks == 0:
                raise ValueError("无效的扫描范围")
                
            self.completed_tasks = 0
            self.progress_bar['value'] = 0
            self.progress_label.config(text="0/0 (0.00%)")
            self.output_area.configure(state='normal')
            self.output_area.delete(1.0, tk.END)
            self.output_area.configure(state='disabled')
            
        except ValueError as e:
            messagebox.showerror("错误", str(e))
            return
            
        self.start_btn.config(state=tk.DISABLED)
        self.scanning = True
        
        scan_thread = threading.Thread(
            target=self.run_scan,
            args=(network, start_port, end_port, num_threads),
            daemon=True
        )
        scan_thread.start()

    def run_scan(self, network, start_port, end_port, num_threads):
        try:
            threads = []
            for ip in network.hosts():
                if not self.scanning:
                    break
                    
                port_count = end_port - start_port + 1
                self.progress_queue.put(port_count)  # 预增进度
                
                t = threading.Thread(
                    target=self.scan_ip,
                    args=(str(ip), start_port, end_port),
                    daemon=True
                )
                t.start()
                threads.append(t)
                
                while len(threads) >= num_threads:
                    t = threads.pop(0)
                    t.join(timeout=0.1)
                    
            for t in threads:
                t.join()
                
        except Exception as e:
            self.output_queue.put(f"扫描错误: {str(e)}")
        finally:
            self.progress_queue.put(None)
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
            finally:
                self.progress_queue.put(1)

    def process_queues(self):
        # 处理输出队列
        while not self.output_queue.empty():
            msg = self.output_queue.get_nowait()
            self.update_output(msg)
            
        # 处理进度队列
        while not self.progress_queue.empty():
            increment = self.progress_queue.get_nowait()
            if increment is None:
                self.progress_label.config(text="扫描完成！")
                break
                
            self.completed_tasks += increment
            if self.total_tasks > 0:
                progress = self.completed_tasks / self.total_tasks * 100
                self.progress_bar['value'] = progress
                self.progress_label.config(
                    text=f"{self.completed_tasks}/{self.total_tasks} ({progress:.2f}%)"
                )

        self.root.after(200, self.process_queues)

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
