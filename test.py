import asyncio
import random
import ssl
import json
import time
import uuid
import requests
import shutil
from loguru import logger
from websockets_proxy import Proxy, proxy_connect
from fake_useragent import UserAgent

# Konfigurasi log
logger.add("logs/{time:YYYY-MM-DD}.log", rotation="1 day", retention="7 days", level="INFO")
logger.info("Program dimulai")

# URL untuk mengambil proxy dari Proxyscrape
PROXY_URL = "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=protocolipport&format=text"

# Fungsi untuk mengambil proxy dari Proxyscrape dan menambahkan proxy unik ke file
def fetch_proxies():
    try:
        logger.info(f"Mengambil proxy dari {PROXY_URL}")
        response = requests.get(PROXY_URL)
        response.raise_for_status()
        proxies = response.text.splitlines()
        
        # Membaca proxy yang sudah ada dalam file
        try:
            with open("local_proxies.txt", "r") as file:
                existing_proxies = file.readlines()
        except FileNotFoundError:
            existing_proxies = []
        
        # Tambahkan hanya proxy yang belum ada dalam file
        new_proxies = [proxy for proxy in proxies if proxy + '\n' not in existing_proxies]
        
        # Jika ada proxy baru, tambahkan ke file
        if new_proxies:
            with open("local_proxies.txt", "a") as file:
                file.write("\n".join(new_proxies) + "\n")
            logger.info(f"Berhasil menyimpan {len(new_proxies)} proxy ke local_proxies.txt")
        else:
            logger.info("Tidak ada proxy baru untuk ditambahkan.")
        
        return new_proxies
    except Exception as e:
        logger.error(f"Gagal mengambil proxy: {e}")
        return []

# User-Agent generator
user_agent = UserAgent(os='windows', platforms='pc', browsers='chrome')
random_user_agent = user_agent.random

# Fungsi utama untuk koneksi WebSocket
async def connect_to_wss(socks5_proxy, user_id):
    device_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, socks5_proxy))
    logger.info(f"Device ID: {device_id} | Proxy: {socks5_proxy}")

    while True:
        try:
            await asyncio.sleep(random.randint(1, 10) / 10)
            custom_headers = {"User-Agent": random_user_agent}
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            urilist = ["wss://proxy.wynd.network:4444/", "wss://proxy.wynd.network:4650/"]
            uri = random.choice(urilist)
            server_hostname = "proxy.wynd.network"
            proxy = Proxy.from_url(socks5_proxy)

            async with proxy_connect(uri, proxy=proxy, ssl=ssl_context, server_hostname=server_hostname,
                                     extra_headers=custom_headers) as websocket:

                async def send_ping():
                    while True:
                        send_message = json.dumps(
                            {"id": str(uuid.uuid4()), "version": "1.0.0", "action": "PING", "data": {}})
                        logger.debug(f"Ping Dikirim: {send_message}")
                        await websocket.send(send_message)
                        await asyncio.sleep(5)

                await asyncio.sleep(1)
                asyncio.create_task(send_ping())

                while True:
                    response = await websocket.recv()
                    message = json.loads(response)
                    logger.info(f"Pesan Diterima: {message}")

                    if message.get("action") == "AUTH":
                        auth_response = {
                            "id": message["id"],
                            "origin_action": "AUTH",
                            "result": {
                                "browser_id": device_id,
                                "user_id": user_id,
                                "user_agent": custom_headers['User-Agent'],
                                "timestamp": int(time.time()),
                                "device_type": "desktop",
                                "version": "4.28.1",
                            }
                        }
                        logger.debug(f"AUTH Response: {auth_response}")
                        await websocket.send(json.dumps(auth_response))

                    elif message.get("action") == "PONG":
                        logger.success(f"Pong Response Berhasil: {message}")
                        pong_response = {"id": message["id"], "origin_action": "PONG"}
                        logger.debug(pong_response)
                        await websocket.send(json.dumps(pong_response))
        except Exception as e:
            logger.error(f"Kesalahan: {e} | Proxy: {socks5_proxy}")
            break  # Keluar dari loop jika terjadi error

# Fungsi utama program
async def main():
    logger.info("Memulai program")

    # Ambil proxy dari Proxyscrape
    proxies = fetch_proxies()
    if not proxies:
        logger.error("Tidak ada proxy yang tersedia, program dihentikan")
        return

    # Muat User ID dari file
    try:
        with open('user_id.txt', 'r') as user_file:
            user_ids = user_file.read().splitlines()
        if not user_ids:
            logger.error("File user_id.txt kosong, program dihentikan")
            return
    except FileNotFoundError:
        logger.error("File user_id.txt tidak ditemukan, program dihentikan")
        return

    tasks = []
    proxy_count = len(proxies)
    user_count = len(user_ids)
    start_time = time.time()

    # Log jumlah data yang dimuat
    logger.info(f"Jumlah User ID: {user_count}")
    logger.info(f"Jumlah Proxy: {proxy_count}")

    # Buat task untuk setiap kombinasi proxy dan user ID
    for i in range(max(proxy_count, user_count)):
        user_id = user_ids[i % user_count]
        proxy = proxies[i % proxy_count]
        tasks.append(asyncio.ensure_future(connect_to_wss(proxy, user_id)))

    await asyncio.gather(*tasks)
    logger.info(f"Program selesai dalam {time.time() - start_time:.2f} detik")

if __name__ == "__main__":
    asyncio.run(main())