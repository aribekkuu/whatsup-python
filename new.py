import socket
import threading

HOST = "0.0.0.0"
PORT = 33000

stop = threading.Event()


def show(text, my_name):
    """Печатает входящее, не ломая строку ввода: стирает текущую строку,
    выводит сообщение и заново рисует приглашение."""
    print(f"\r\033[K{text}\n{my_name}: ", end="", flush=True)


def receive(conn, reader, my_name, peer_name):
    """Поток 1: постоянно слушает собеседника."""
    while not stop.is_set():
        try:
            line = reader.readline()
        except OSError:
            break
        if not line:  # собеседник закрыл nc / терминал
            show(f"*** {peer_name} disconnected. Press Enter to exit.", my_name)
            break
        msg = line.strip()
        if not msg:
            continue
        if msg.lower() == "exit":
            show(f"*** {peer_name} left the chat. Press Enter to exit.", my_name)
            break
        show(f"{peer_name}: {msg}", my_name)
        try:
            conn.sendall(f"{peer_name}: ".encode())  # новая строка ввода у собеседника
        except OSError:
            break
    stop.set()


def send(conn, my_name, peer_name):
    """Поток 2 (главный): читает клавиатуру и отправляет."""
    while not stop.is_set():
        try:
            text = input(f"{my_name}: ").strip()
        except (EOFError, KeyboardInterrupt):
            text = "exit"
        if stop.is_set():
            break
        if not text:
            continue
        try:
            if text.lower() == "exit":
                conn.sendall(f"\r\033[K*** {my_name} left the chat.\n".encode())
                break
            # стираем его строку ввода, печатаем твоё сообщение, рисуем его приглашение заново
            conn.sendall(f"\r\033[K{my_name}: {text}\n{peer_name}: ".encode())
        except OSError:
            break
    stop.set()


def main():
    my_name = input("Your name: ").strip() or "Server"

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    print(f"RIVER IS OPENED... waiting on port {PORT}")

    conn, addr = server.accept()
    print(f"*** Connection from {addr[0]}")
    reader = conn.makefile("r", encoding="utf-8", errors="replace")

    # Знакомство: просим имя у того, кто зашёл через nc
    conn.sendall(f"Welcome to {my_name}'s chat!\nEnter your name: ".encode())
    peer_name = reader.readline().strip() or "Guest"

    conn.sendall(
        f"*** Hi {peer_name}! You're chatting with {my_name}. "
        f"Type a message and press Enter. 'exit' to leave.\n".encode()
    )
    conn.sendall(f"{peer_name}: ".encode())
    print(f"*** {peer_name} joined the chat. 'exit' to leave.")

    threading.Thread(target=receive, args=(conn, reader, my_name, peer_name), daemon=True).start()
    send(conn, my_name, peer_name)

    try:
        conn.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    conn.close()
    server.close()
    print("\nConnection closed.")


if __name__ == "__main__":
    main()