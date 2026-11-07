import socket

client = socket.socket()
client.connect(('localhost', 12345))
print("Connected to the server on port 12345.")    

while True:
    message = input("You: ")
    client.send(message.encode())
    if message.lower() == 'exit':
        print("You have exited the chat.")
        break   

    response = client.recv(1024).decode()
    if response.lower() == 'exit':
        print("Server has exited the chat.")
        break  
    print(f"Server: {response}")

client.close()

#localhost: 127.0.0.1
#IP: 192.168.0.121