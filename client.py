
import socket
import threading
import sys

# --- Configuration ---
TCP_PORT = 8888

# --- Functions ---

def receive_messages(client_socket: socket.socket):
    """
    Runs in a separate thread to receive messages from the server.
    """
    while True:
        try:
            message = client_socket.recv(2048).decode('utf-8')
            if message:
                # Print the message to the console
                # Use sys.stdout.write and flush to avoid issues with input()
                sys.stdout.write(message)
                sys.stdout.flush()
            else:
                # Server closed the connection
                print("\nSunucu bağlantısı kesildi. Çıkmak için Enter'a basın.")
                client_socket.close()
                break
        except (ConnectionResetError, ConnectionAbortedError, OSError):
            print("\nSunucu ile bağlantı koptu.")
            client_socket.close()
            break
        except Exception as e:
            print(f"Bir hata oluştu: {e}")
            client_socket.close()
            break

def main():
    """
    Main function to connect to the server and send messages.
    """
    # 1. Get server IP and username from user
    server_ip = input("Sunucu IP adresini girin (varsayılan: 127.0.0.1): ")
    if not server_ip:
        server_ip = '127.0.0.1'

    while True:
        username = input("Kullanıcı adınızı girin: ")
        if username:
            break
        print("Kullanıcı adı boş olamaz.")

    # 2. Create and connect the socket
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((server_ip, TCP_PORT))
        print(f"✅ Sunucuya ({server_ip}:{TCP_PORT}) bağlanıldı.")
    except ConnectionRefusedError:
        print(f"❌ Bağlantı reddedildi. Sunucunun çalıştığından ve IP adresinin doğru olduğundan emin olun.")
        return
    except Exception as e:
        print(f"❌ Sunucuya bağlanırken bir hata oluştu: {e}")
        return

    # 3. Send the username to the server
    client.send((username + '\n').encode('utf-8'))

    # 4. Start a thread to listen for incoming messages
    receive_thread = threading.Thread(target=receive_messages, args=(client,), daemon=True)
    receive_thread.start()

    # 5. Main loop to get user input and send it
    print("Mesajınızı yazıp Enter'a basın. Çıkmak için 'exit' yazın.")
    try:
        while True:
            message = input()
            if not receive_thread.is_alive():
                break
                
            if message.lower() == 'exit':
                break
                
            if message:
                full_message = (message + '\n').encode('utf-8')
                client.send(full_message)

    except KeyboardInterrupt:
        print("\nÇıkış yapılıyor...")
    finally:
        # 6. Clean up and close the connection
        print("Bağlantı kapatılıyor.")
        client.close()

if __name__ == "__main__":
    main()
