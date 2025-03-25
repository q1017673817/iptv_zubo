import socket
import threading
from ipaddress import ip_network
import PySimpleGUI as sg


def scan_port(ip, port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((str(ip), port))
        if result == 0:
            return f"Port {port} is open on {ip}"
        sock.close()
    except socket.error:
        pass
    return None


def scan_ip(ip, start_port, end_port, output_window):
    for port in range(start_port, end_port + 1):
        result = scan_port(ip, port)
        if result:
            output_window.write_event_value('-OUTPUT-', result)


def scan_network(network, start_port, end_port, num_threads, output_window):
    threads = []
    for ip in network:
        thread = threading.Thread(target=scan_ip, args=(ip, start_port, end_port, output_window))
        threads.append(thread)
        thread.start()

        if len(threads) >= num_threads:
            for t in threads:
                t.join()
            threads = []

    for t in threads:
        t.join()
    output_window.write_event_value('-OUTPUT-', '扫描完成')


def main():
    layout = [
        [sg.Text('请输入 IP 范围（如 192.168.1.0/24）:'), sg.Input(key='-IP_RANGE-')],
        [sg.Text('请输入起始端口号:'), sg.Input(key='-START_PORT-')],
        [sg.Text('请输入结束端口号:'), sg.Input(key='-END_PORT-')],
        [sg.Text('请输入线程数:'), sg.Input(key='-NUM_THREADS-')],
        [sg.Button('开始扫描'), sg.Button('退出')],
        [sg.Multiline(size=(60, 20), key='-OUTPUT-', autoscroll=True)]
    ]

    window = sg.Window('端口扫描工具', layout)

    while True:
        event, values = window.read()
        if event == sg.WINDOW_CLOSED or event == '退出':
            break
        elif event == '开始扫描':
            try:
                ip_range = values['-IP_RANGE-']
                start_port = int(values['-START_PORT-'])
                end_port = int(values['-END_PORT-'])
                num_threads = int(values['-NUM_THREADS-'])
                network = ip_network(ip_range, strict=False)
                threading.Thread(target=scan_network, args=(
                    network, start_port, end_port, num_threads, window), daemon=True).start()
            except ValueError:
                window['-OUTPUT-'].print('输入的端口号或线程数必须为整数')
            except Exception as e:
                window['-OUTPUT-'].print(f'发生错误: {e}')
        elif event == '-OUTPUT-':
            window['-OUTPUT-'].print(values[event])

    window.close()


if __name__ == "__main__":
    main()
    
