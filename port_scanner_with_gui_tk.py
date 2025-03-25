# port_scanner_with_gui_tk.py
import tkinter as tk
from tkinter import ttk, scrolledtext

class PortScannerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("端口扫描工具")
        
        # GUI组件
        self.create_widgets()
        
    def create_widgets(self):
        frame = ttk.Frame(self.root, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # 输入区域
        ttk.Label(frame, text="IP范围（如 192.168.1.0/24）:").grid(row=0, column=0, sticky=tk.W)
        self.ip_entry = ttk.Entry(frame, width=30)
        self.ip_entry.grid(row=0, column=1)
        
        # 其他输入组件...
        
        # 输出区域
        self.output_area = scrolledtext.ScrolledText(frame, width=60, height=20)
        self.output_area.grid(row=4, columnspan=2)
        
        # 按钮
        ttk.Button(frame, text="开始扫描", command=self.start_scan).grid(row=5, column=0)
        ttk.Button(frame, text="退出", command=self.root.quit).grid(row=5, column=1)
    
    def start_scan(self):
        # 在此处调用原有扫描逻辑
        pass
    
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = PortScannerGUI()
    app.run()
