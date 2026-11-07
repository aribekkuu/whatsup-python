import socket

server = socket.socket()
server.bind(('0.0.0.0', 33000))
server.listen(1)

print("RIVER IS OPENED..."+'\n'+"Waiting for a connection on port 33000...")
conn, addr = server.accept()
if conn is not None:
    print(f"Connection established with {addr}")

name = input("Type your name: ")

while True:
    msg = conn.recv(1024).decode()
    if msg.lower() == 'exit':
        print("Closing connection.")
        break
    print(f"{name}: {msg}")  
    response = input("You: ")
    conn.send((response+'\n').encode())
    if response.lower() == 'exit':
        print("Closing connection.")
        break
conn.close() 

#localhost: 127.0.0.1
#IP: 192.168.0.121