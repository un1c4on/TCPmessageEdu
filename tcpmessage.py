import socket
import threading

MY_PORT = int(input("Kendi Port Numaranızı girin: "))

def mesajlari_dinle():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("0.0.0.0", MY_PORT))
    server.listen()

    while True:
        conn, addr = server.accept()
        mesaj = conn.recv(1024).decode('utf-8')
        print(f"\n[{addr[0]}]: {mesaj}")
        conn.close()

def mesaj_gonder():
    hedef_ip = input("Bağlanılacak IP: ")
    hedef_port = int(input("Bağlanılacak Port: "))

    while True:
        msg = input("Sen: ")
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client.connect((hedef_ip, hedef_port))
            client.send(msg.encode('utf-8'))
            client.close()
        except Exception as e:
            print(f"Hata: {e}")

dinleme_threadi = threading.Thread(target=mesajlari_dinle)
dinleme_threadi.daemon = True
dinleme_threadi.start()

mesaj_gonder()
