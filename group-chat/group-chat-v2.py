"""Групповой терминальный чат, версия 2.

Новое: /who, /msg (личные сообщения), время у сообщений, цвет ников, /kick (только хост),
пароль на вход (спрашивается при запуске, Enter — без пароля).
Запуск:      uv run group_chat_v2.py
Подключение: nc <ip-хоста> 33000
"""
import getpass
import hmac
import socket
import threading
import time
from datetime import datetime

HOST = "0.0.0.0"
PORT = 33000
MAX_PASSWORD_TRIES = 3
COLORS = [32, 33, 34, 35, 36, 91, 92, 93, 94, 95, 96, 31]  # ANSI-цвета для ников

clients = {}                  # conn -> name
colors = {}                   # name -> код цвета
kicked = set()                # conn, которых выкинул хост
clients_lock = threading.Lock()
send_lock = threading.Lock()  # чтобы два потока не писали в сокеты вперемешку
my_name = ""
password = ""                 # пустой — чат без пароля
color_i = 0


# ---------- оформление ----------

def ts():
    return datetime.now().strftime("%H:%M")


def tag(name):
    """Ник жирным и своим цветом."""
    return f"\033[1;{colors.get(name, 37)}m{name}\033[0m"


def assign_color(name):
    global color_i
    colors[name] = COLORS[color_i % len(COLORS)]
    color_i += 1


def insert_above(text):
    """Вставить строку НАД строкой ввода, не трогая набранное.
      ESC D, ESC M  — гарантировать место под строкой (внизу экрана — прокрутка)
      ESC 7         — запомнить позицию курсора
      \\r ESC[1L     — в начало строки, вставить пустую (строка ввода съезжает вниз)
      text          — напечатать сообщение
      ESC 8, ESC D  — вернуть курсор и опустить на строку вниз, к набираемому тексту
    """
    return f"\033D\033M\0337\r\033[1L{text}\0338\033D"


# ---------- доставка ----------

def show(text):
    """Вывести у хоста."""
    print(insert_above(text), end="", flush=True)


def send_line(conn, text):
    """Вывести у участника."""
    with send_lock:
        conn.sendall(insert_above(text).encode())


def send_prompt(conn, name):
    with send_lock:
        conn.sendall(f"{name}: ".encode())


def broadcast(text, exclude=None):
    """Разослать всем участникам, кроме exclude."""
    with clients_lock:
        targets = list(clients)
    for conn in targets:
        if conn is exclude:
            continue
        try:
            send_line(conn, text)
        except OSError:
            # мёртвый сокет: обрываем, его поток сам увидит EOF и уберёт клиента
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def find_conn(name):
    with clients_lock:
        for conn, n in clients.items():
            if n == name:
                return conn
    return None


def online_names():
    with clients_lock:
        return [my_name] + list(clients.values())


def deliver(name, text):
    """Отправить одному человеку по имени (хосту или участнику). False, если такого нет."""
    if name == my_name:
        show(text)
        return True
    conn = find_conn(name)
    if conn is None:
        return False
    try:
        send_line(conn, text)
    except OSError:
        pass
    return True


# ---------- команды ----------

def command(sender, msg):
    """Обработать команду. Возвращает ответ для отправителя (или None)."""
    parts = msg.split(maxsplit=2)
    cmd = parts[0].lower()

    if cmd == "/help":
        # одной строкой: вставка над строкой ввода рассчитана на одну строку
        cmds = ["/who — кто онлайн", "/msg имя текст — личное сообщение"]
        if sender == my_name:
            cmds.append("/kick имя — выкинуть участника")
        cmds.append("exit — выйти")
        return "*** " + " | ".join(cmds)

    if cmd == "/who":
        names = online_names()
        return f"*** Online ({len(names)}): " + ", ".join(tag(n) for n in names)

    if cmd == "/msg":
        if len(parts) < 3:
            return "*** Usage: /msg имя текст"
        target, text = parts[1], parts[2]
        if target == sender:
            return "*** Нельзя писать самому себе"
        if not deliver(target, f"[{ts()}] \033[3m(личное)\033[0m {tag(sender)}: {text}"):
            return f"*** Нет участника с именем {target}"
        return f"[{ts()}] \033[3m(личное → {tag(target)})\033[0m {text}"

    if cmd == "/kick":
        if sender != my_name:
            return "*** Выкидывать может только хост"
        if len(parts) < 2:
            return "*** Usage: /kick имя"
        target = parts[1]
        conn = find_conn(target)
        if conn is None:
            return f"*** Нет участника с именем {target}"
        kicked.add(conn)
        try:
            send_line(conn, "*** Вас выкинул хост")
            conn.shutdown(socket.SHUT_RDWR)  # его поток увидит EOF и сам всё уберёт
        except OSError:
            pass
        return None

    return f"*** Неизвестная команда {cmd}. Список: /help"


# ---------- участники ----------

def check_password(conn, reader, addr):
    """Спросить пароль (до MAX_PASSWORD_TRIES попыток). True — можно входить."""
    conn.sendall(f"Welcome to {my_name}'s chat!\nPassword: ".encode())
    for attempt in range(1, MAX_PASSWORD_TRIES + 1):
        line = reader.readline()
        if not line:
            return False
        # compare_digest сравнивает за одинаковое время: по скорости ответа пароль не подобрать
        if hmac.compare_digest(line.rstrip("\r\n").encode(), password.encode()):
            return True
        time.sleep(1)  # тормозим перебор
        show(f"[{ts()}] *** неверный пароль с {addr[0]}")
        if attempt < MAX_PASSWORD_TRIES:
            conn.sendall(b"Wrong password, try again: ")
    conn.sendall(b"Wrong password. Bye.\n")
    return False


def ask_name(conn, reader):
    """Спросить имя, пока не введут свободное. None, если человек отключился."""
    if not password:
        conn.sendall(f"Welcome to {my_name}'s chat!\n".encode())
    conn.sendall(b"Enter your name: ")
    while True:
        line = reader.readline()
        if not line:
            return None
        name = line.strip()
        ok = name and " " not in name and not name.startswith("/")
        if ok and name not in online_names():
            return name
        conn.sendall(b"Name is empty, has spaces or is taken. Try another: ")


def handle_client(conn, addr):
    """Отдельный поток на каждого участника."""
    reader = conn.makefile("r", encoding="utf-8", errors="replace")
    name = None
    try:
        if password and not check_password(conn, reader, addr):
            return
        name = ask_name(conn, reader)
        if name is None:
            return

        with clients_lock:
            assign_color(name)
            clients[conn] = name

        send_line(conn, f"*** Hi {tag(name)}! /help — команды, exit — выйти")
        send_line(conn, command(name, "/who"))
        send_prompt(conn, name)
        show(f"[{ts()}] *** {tag(name)} joined the chat")
        broadcast(f"[{ts()}] *** {tag(name)} joined the chat", exclude=conn)

        while True:
            line = reader.readline()
            if not line:            # закрыл nc / терминал / кикнули
                break
            msg = line.strip()
            if msg.lower() == "exit":
                break
            if msg.startswith("/"):
                reply = command(name, msg)
                if reply:
                    send_line(conn, reply)
            elif msg:
                text = f"[{ts()}] {tag(name)}: {msg}"
                show(text)
                broadcast(text, exclude=conn)
            send_prompt(conn, name)  # новая строка ввода у автора
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
            how = "was kicked" if conn in kicked else "left the chat"
            kicked.discard(conn)
            show(f"[{ts()}] *** {tag(left)} {how}")
            broadcast(f"[{ts()}] *** {tag(left)} {how}")


def accept_loop(server):
    """Отдельный поток: принимает новых участников."""
    while True:
        try:
            conn, addr = server.accept()
        except OSError:
            break
        show(f"*** Connection from {addr[0]}")
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


def main():
    global my_name, password
    my_name = input("Your name: ").strip().replace(" ", "_") or "Host"
    password = getpass.getpass("Chat password (Enter = без пароля): ")
    assign_color(my_name)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()
    print(f"RIVER IS OPENED... others join with: nc <your-ip> {PORT}")
    print("password: " + ("on" if password else "off (чат открыт для всех)"))
    print("/help — команды, /kick имя — выкинуть, exit — закрыть чат")

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
        if text.startswith("/"):
            reply = command(my_name, text)
            if reply:
                show(reply)
            continue
        broadcast(f"[{ts()}] {tag(my_name)}: {text}")

    broadcast(f"[{ts()}] *** {tag(my_name)} closed the chat")
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