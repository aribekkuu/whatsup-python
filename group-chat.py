import socket
import threading

HOST = "0.0.0.0"
PORT = 33000

clients = {}                  # conn -> name
clients_lock = threading.Lock()
send_lock = threading.Lock()  # чтобы два потока не писали в сокеты вперемешку
my_name = ""


def insert_above(text):
    """ANSI-последовательность: вставить строку НАД текущей строкой ввода,
    не трогая то, что там уже набрано.
      ESC D, ESC M  — гарантировать место под строкой (внизу экрана — прокрутка)
      ESC 7         — запомнить позицию курсора
      \\r ESC[1L     — в начало строки, вставить пустую (строка ввода съезжает вниз)
      text          — напечатать сообщение в освободившейся строке
      ESC 8, ESC D  — вернуть курсор и опустить на строку вниз, к набираемому тексту
    """
    return f"\033D\033M\0337\r\033[1L{text}\0338\033D"


def show(text):
    """Печатает у тебя (хоста) над строкой ввода, не стирая то, что ты набираешь."""
    print(insert_above(text), end="", flush=True)


def send_line(conn, name, text):
    """У участника: вставить сообщение над его строкой ввода, не стирая набранное."""
    with send_lock:
        conn.sendall(insert_above(text).encode())


def broadcast(text, exclude=None):
    """Разослать всем подключённым, кроме exclude."""
    with clients_lock:
        targets = list(clients.items())
    for conn, name in targets:
        if conn is exclude:
            continue
        try:
            send_line(conn, name, text)
        except OSError:
            # мёртвый сокет: обрываем, его поток сам увидит EOF и уберёт клиента
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def ask_name(conn, reader):
    """Спросить имя, пока не введут свободное. None, если человек отключился."""
    conn.sendall(f"Welcome to {my_name}'s chat!\nEnter your name: ".encode())
    while True:
        line = reader.readline()
        if not line:
            return None
        name = line.strip()
        with clients_lock:
            taken = name == my_name or name in clients.values()
        if name and not taken:
            return name
        conn.sendall(b"Name is empty or taken, try another: ")


def handle_client(conn, addr):
    """Отдельный поток на каждого участника: слушает только его."""
    reader = conn.makefile("r", encoding="utf-8", errors="replace")
    try:
        name = ask_name(conn, reader)
        if name is None:
            return

        with clients_lock:
            online = [my_name] + list(clients.values())
            clients[conn] = name

        with send_lock:
            conn.sendall(
                f"*** Hi {name}! Online: {', '.join(online)}. 'exit' to leave.\n{name}: ".encode()
            )
        show(f"*** {name} joined the chat")
        broadcast(f"*** {name} joined the chat", exclude=conn)

        while True:
            line = reader.readline()
            if not line:            # закрыл nc / терминал
                break
            msg = line.strip()
            if msg.lower() == "exit":
                break
            if msg:
                show(f"{name}: {msg}")
                broadcast(f"{name}: {msg}", exclude=conn)
            with send_lock:
                conn.sendall(f"{name}: ".encode())  # новая строка ввода у автора
    except OSError:
        pass
    finally:
        with clients_lock:
            left = clients.pop(conn, None)
        try:
            conn.close()
        except OSError:
            pass
        if left:
            show(f"*** {left} left the chat")
            broadcast(f"*** {left} left the chat")


def accept_loop(server):
    """Отдельный поток: принимает новых участников, пока сервер открыт."""
    while True:
        try:
            conn, addr = server.accept()
        except OSError:
            break
        show(f"*** Connection from {addr[0]}")
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


def main():
    global my_name
    my_name = input("Your name: ").strip() or "Host"

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()
    print(f"RIVER IS OPENED... others join with: nc <your-ip> {PORT}")

    threading.Thread(target=accept_loop, args=(server,), daemon=True).start()

    # Главный поток: твой ввод
    while True:
        try:
            text = input(f"{my_name}: ").strip()
        except (EOFError, KeyboardInterrupt):
            text = "exit"
        if not text:
            continue
        if text.lower() == "exit":
            break
        broadcast(f"{my_name}: {text}")

    broadcast(f"*** {my_name} closed the chat")
    with clients_lock:
        conns = list(clients)
    for c in conns:
        try:
            c.shutdown(socket.SHUT_RDWR)
            c.close()
        except OSError:
            pass
    server.close()
    print("\nChat closed.")


if __name__ == "__main__":
    main()
