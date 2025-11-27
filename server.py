import asyncio
import websockets
import socket
from datetime import datetime
import os
import subprocess
import re

# --- Configuration ---
HOST = '0.0.0.0'  # Listen on all available network interfaces
TCP_PORT = 8888
WEBSOCKET_PORT = 8765
HTTP_PORT = 8000  # Port for serving the HTML file

# --- State ---
# Stores connected TCP clients (writer objects) and their usernames
tcp_clients = {}
# Stores connected WebSocket clients
websocket_clients = set()

# --- Core Logic ---

async def get_device_info(ip_address: str) -> dict:
    """
    Tries to find the MAC address and hostname for a given local IP address.
    """
    info = {'ip': ip_address, 'mac': 'N/A', 'hostname': 'N/A'}

    # 1. Try to get hostname
    try:
        info['hostname'] = socket.gethostbyaddr(ip_address)[0]
    except (socket.herror, socket.gaierror):
        info['hostname'] = 'N/A' # Could not resolve

    # 2. Try to get MAC address by parsing the system's ARP table
    try:
        # Run 'arp -a' command
        arp_output = subprocess.check_output(['arp', '-a', ip_address]).decode('utf-8')
        
        # Search for a MAC address pattern in the output
        mac_match = re.search(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', arp_output)
        if mac_match:
            info['mac'] = mac_match.group(0)

    except (subprocess.CalledProcessError, FileNotFoundError):
        # Command failed or 'arp' is not available
        info['mac'] = 'N/A (ARP komutu başarısız)'
        
    return info

async def broadcast(message: str):
    """
    Sends a message to all connected TCP and WebSocket clients.
    """
    print(f"Broadcasting: {message}")
    
    # 1. Send to WebSocket clients (for the HTML interface)
    if websocket_clients:
        await asyncio.gather(*[ws.send(message) for ws in websocket_clients])

    # 2. Send to TCP clients (Python clients)
    if tcp_clients:
        encoded_message = (message + '\n').encode('utf-8')
        for client in tcp_clients.values():
            client['writer'].write(encoded_message)
        drain_tasks = [client['writer'].drain() for client in tcp_clients.values()]
        await asyncio.gather(*drain_tasks)


async def handle_tcp_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """
    Handles a single TCP client connection.
    """
    peer_info = writer.get_extra_info('peername')
    client_ip = peer_info[0]
    print(f"New TCP connection from {peer_info}")

    try:
        username_data = await reader.readuntil(b'\n')
        username = username_data.decode('utf-8').strip()
        
        # Get device info
        device_info = await get_device_info(client_ip)
        
        tcp_clients[peer_info] = {
            "writer": writer, 
            "username": username,
            "device_info": device_info
        }
        
        print(f"User '{username}' connected. Device Info: {device_info}")
        
        await broadcast(f"[{datetime.now().strftime('%H:%M')}] Sunucu: {username} sohbete katıldı.")
        await broadcast(f"[{datetime.now().strftime('%H:%M')}] Sistem: {username} için cihaz bilgisi -> IP: {device_info['ip']}, MAC: {device_info['mac']}, Hostname: {device_info['hostname']}")
        await broadcast_user_list() # Broadcast updated user list

    except (asyncio.IncompleteReadError, ConnectionResetError):
        print(f"Client {peer_info} disconnected before sending username.")
        return

    try:
        while True:
            data = await reader.readuntil(b'\n')
            if not data:
                break
            
            message = data.decode('utf-8').strip()
            full_message = f"[{datetime.now().strftime('%H:%M')}] {username}: {message}"
            
            await broadcast(full_message)
            
    except (asyncio.IncompleteReadError, ConnectionResetError):
        print(f"User '{username}' from {peer_info} disconnected.")
    finally:
        if peer_info in tcp_clients:
            del tcp_clients[peer_info]
        
        writer.close()
        await writer.wait_closed()
        await broadcast(f"[{datetime.now().strftime('%H:%M')}] Sunucu: {username} sohbetten ayrıldı.")
        await broadcast_user_list() # Broadcast updated user list


async def handle_websocket_client(websocket: websockets.WebSocketServerProtocol, path: str = None):
    """
    Handles a single WebSocket client connection.
    """
    print(f"New WebSocket connection from {websocket.remote_address}")
    websocket_clients.add(websocket)
    # Send current user list to the newly connected WebSocket client
    await broadcast_user_list_to_single_client(websocket)
    try:
        await websocket.wait_closed()
    finally:
        print(f"WebSocket connection from {websocket.remote_address} closed.")
        websocket_clients.remove(websocket)

async def handle_http_request(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """
    Handles a simple HTTP GET request to serve index.html.
    """
    addr = writer.get_extra_info('peername')
    print(f"New HTTP request from {addr}")
    
    try:
        await reader.readuntil(b'\r\n\r\n')

        if os.path.exists("index.html"):
            with open("index.html", "r", encoding="utf-8") as f:
                html_content = f.read()
            
            content_bytes = html_content.encode('utf-8')
            
            response = (
                b"HTTP/1.1 200 OK\r\n" +
                b"Content-Type: text/html; charset=utf-8\r\n" +
                f"Content-Length: {len(content_bytes)}\r\n".encode('utf-8') +
                b"Connection: close\r\n\r\n" +
                content_bytes
            )
        else:
            error_message = b"404 Not Found: index.html not found."
            response = (
                b"HTTP/1.1 404 Not Found\r\n" +
                b"Content-Type: text/plain; charset=utf-8\r\n" +
                f"Content-Length: {len(error_message)}\r\n".encode('utf-8') +
                b"Connection: close\r\n\r\n" +
                error_message
            )

        writer.write(response)
        await writer.drain()

    except Exception as e:
        print(f"Error handling HTTP request: {e}")
    finally:
        writer.close()
        await writer.wait_closed()

def get_current_tcp_clients_info() -> str:
    """
    Returns a semicolon-separated string of current TCP clients info (username,ip).
    Format: "user1,192.168.1.10;user2,192.168.1.11"
    """
    clients_info = []
    for client in tcp_clients.values():
        username = client.get('username', 'N/A')
        ip = client.get('device_info', {}).get('ip', 'N/A')
        clients_info.append(f"{username},{ip}")
    return ";".join(sorted(clients_info))

async def broadcast_user_list():
    """
    Sends the current TCP user list to all connected WebSocket clients.
    """
    user_list_str = get_current_tcp_clients_info()
    message = f"[USER_LIST]:{user_list_str}"
    print(f"Broadcasting user list: {message}")
    if websocket_clients:
        await asyncio.gather(*[ws.send(message) for ws in websocket_clients])

async def broadcast_user_list_to_single_client(websocket: websockets.WebSocketServerProtocol):
    """
    Sends the current TCP user list to a single WebSocket client.
    """
    user_list_str = get_current_tcp_clients_info()
    message = f"[USER_LIST]:{user_list_str}"
    print(f"Sending user list to new WebSocket client: {message}")
    await websocket.send(message)



async def main():
    """
    Starts the TCP, WebSocket, and HTTP servers.
    """
    tcp_server = await asyncio.start_server(handle_tcp_client, HOST, TCP_PORT)
    websocket_server = await websockets.serve(handle_websocket_client, HOST, WEBSOCKET_PORT)
    http_server = await asyncio.start_server(handle_http_request, HOST, HTTP_PORT)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            display_host = s.getsockname()[0]
    except Exception:
        display_host = '127.0.0.1'

    print("--- Sunucu Başlatıldı ---")
    print(f"💬 TCP İstemcileri için: {display_host}:{TCP_PORT}")
    print(f"🔌 WebSocket Bağlantısı: {display_host}:{WEBSOCKET_PORT}")
    print(f"🌐 Web Arayüzü: http://{display_host}:{HTTP_PORT}")
    print("-------------------------")
    print("Sunucu çalışıyor... Kapatmak için CTRL+C'ye basın.")

    await asyncio.gather(
        tcp_server.serve_forever(),
        websocket_server.serve_forever(),
        http_server.serve_forever()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSunucu kapatılıyor.")
    except OSError as e:
        print(f"Hata: Portlar ({TCP_PORT}, {WEBSOCKET_PORT}, {HTTP_PORT}) zaten kullanılıyor olabilir. {e}")
