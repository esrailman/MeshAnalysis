import serial
import csv
import re
import time
import os
from datetime import datetime
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# --- AYARLAR ---
SERIAL_PORT = "COM4"
BAUD_RATE = 115200

# InfluxDB Ayarlari
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "MWXgxnk2mLeVdn4WDS7y7wQEy1DFM0rME7riNAIljeuMCQbaqz_44jYwWerQTxEmLrf9Po4ttTiDGdffdfKBWw=="
INFLUX_ORG = "myorg"
INFLUX_BUCKET = "mesh_data"
CSV_FILENAME = "mesh_performans_raporu.csv"

# --- GÜNCELLENMİŞ REGEX DESENLERİ ---

# <- [ECHO GELDİ] Yanıtlayan: Zehra | Paket: 121 | Hop: 1 | Gecikme: 30725us | Jitter: 18456us | RTT: 61451us | Yerel RSSI: -40 dBm | Karşı RSSI: 0 dBm
# Not: Yeni Arduino kodundaki formatına tam uyumlu hale getirildi.
pattern_echo = r"\[ECHO GELD.\] Yan.tlayan:\s*(\w+)\s*\|\s*Paket:\s*(\d+)\s*\|\s*Hop:\s*(\d+)\s*\|\s*Gecikme:\s*(\d+)us\s*\|\s*Jitter:\s*(\d+)us\s*\|\s*RTT:\s*(\d+)us\s*\|\s*Yerel RSSI:\s*(-?\d+)\s*dBm\s*\|\s*Kar.. RSSI:\s*(-?\d+)\s*dBm"

# -> [REQ GELDİ] Gönderen: Zehra | Paket: 138 | Tek Yönlü Gecikme: 123us | RSSI: -39 dBm
# Not: REQ paketinden 'Hop' bilgisini çıkardığımız için regex güncellendi.
pattern_req = r"\[REQ GELD.\] G.nderen:\s*(\w+)\s*\|\s*Paket:\s*(\d+)\s*\|\s*Tek Y.nl. Gecikme:\s*(\d+)us\s*\|\s*RSSI:\s*(-?\d+)\s*dBm"

# Gelen Toplam Ag Trafigi: 3.0 Paket/sn | 120.5 Bayt/sn
pattern_trafik = r"Gelen Toplam Ag Trafigi:\s*([\d.]+)\s*Paket/sn\s*\|\s*([\d.]+)\s*Bayt/sn"

# Basari Orani: %85.0
pattern_basari = r"Basari Orani:\s*%([\d.]+)"

# Bos RAM (Heap): 234512 Bayt
pattern_heap = r"Bos RAM \(Heap\):\s*(\d+)\s*Bayt"

# -> Kaynak: Zehra | Alinan Paket: 5 | Kaybolan: 0
pattern_kayip = r"Kaynak:\s*(\w+)\s*\|\s*Alinan Paket:\s*(\d+)\s*\|\s*Kaybolan:\s*(\d+)"


# Sabit CSV basliklari
CSV_HEADERS = [
    "Zaman", "Metrik_Tipi", "Paket_No", "Hedef_Kaynak", "Gecikme_us", "Jitter_us",
    "RTT_us", "Hop", "Yerel_RSSI_dBm", "Karsi_RSSI_dBm", "Paket_sn", "Bayt_sn", 
    "Basari_Orani", "Bos_RAM_Bayt", "Kaybolan_Paket"
]

def init_csv():
    file_exists = os.path.isfile(CSV_FILENAME)
    with open(CSV_FILENAME, "a", newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(CSV_HEADERS)

def write_to_csv(writer, file, row_data):
    full_row = [row_data.get(header, "") for header in CSV_HEADERS]
    writer.writerow(full_row)
    file.flush()

def start_integrated_bridge():
    print(f"InfluxDB ({INFLUX_URL}) baglantisi baslatiliyor...")
    try:
        client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        write_api = client.write_api(write_options=SYNCHRONOUS)
        print("[SISTEM] InfluxDB Istemcisi Hazir.")
    except Exception as e:
        print(f"[HATA] InfluxDB Baglanti Hatasi: {e}")
        return

    init_csv()
    print(f"[SISTEM] {SERIAL_PORT} portu dinleniyor... (Cikis: CTRL+C)")

    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)

        with open(CSV_FILENAME, "a", newline='', encoding='utf-8') as file:
            writer = csv.writer(file)

            while True:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if not line:
                        continue

                    zaman_damgasi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"\n[{zaman_damgasi}] ESP32: {line}")

                    # 1. ECHO ANALİZİ (GÜNCELLENDİ: Hop dinamik geliyor)
                    match_echo = re.search(pattern_echo, line)
                    if match_echo:
                        hedef, paket_no, hop, gecikme, jitter, rtt, yerel_rssi, karsi_rssi = match_echo.groups()
                        try:
                            write_to_csv(writer, file, {
                                "Zaman": zaman_damgasi, "Metrik_Tipi": "ECHO_DONUS",
                                "Paket_No": paket_no, "Hedef_Kaynak": hedef,
                                "Gecikme_us": gecikme, "Jitter_us": jitter, "RTT_us": rtt, 
                                "Hop": hop, "Yerel_RSSI_dBm": yerel_rssi, "Karsi_RSSI_dBm": karsi_rssi
                            })

                            point = Point("mesh_performance") \
                                .tag("target_node", hedef) \
                                .field("latency_us", int(gecikme)) \
                                .field("jitter_us", int(jitter)) \
                                .field("rtt_us", int(rtt)) \
                                .field("hop_count", int(hop)) \
                                .field("local_rssi", int(yerel_rssi)) \
                                .field("remote_rssi", int(karsi_rssi)) \
                                .time(time.time_ns(), WritePrecision.NS)
                            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
                            print(f"  [OK] InfluxDB -> ECHO ({hedef}) eklendi (Hop: {hop}).")
                        except Exception as e:
                            print(f"  [HATA] InfluxDB (ECHO): {e}")
                        continue

                    # 2. REQ ANALİZİ (GÜNCELLENDİ: Hop bilgisi paketten çıktı)
                    match_req = re.search(pattern_req, line)
                    if match_req:
                        kaynak, paket_no, one_way_latency, rssi = match_req.groups()
                        try:
                            write_to_csv(writer, file, {
                                "Zaman": zaman_damgasi, "Metrik_Tipi": "REQ_GELIS",
                                "Paket_No": paket_no, "Hedef_Kaynak": kaynak,
                                "Gecikme_us": one_way_latency, "Yerel_RSSI_dBm": rssi
                            })

                            point = Point("mesh_req_received") \
                                .tag("source_node", kaynak) \
                                .field("one_way_latency_us", int(one_way_latency)) \
                                .field("local_rssi", int(rssi)) \
                                .time(time.time_ns(), WritePrecision.NS)
                            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
                            print(f"  [OK] InfluxDB -> REQ ({kaynak}) eklendi.")
                        except Exception as e:
                            print(f"  [HATA] InfluxDB (REQ): {e}")
                        continue

                    # 3. AG TRAFIGI (Aynı kaldı)
                    match_trafik = re.search(pattern_trafik, line)
                    if match_trafik:
                        pps, bps = match_trafik.groups()
                        try:
                            write_to_csv(writer, file, {
                                "Zaman": zaman_damgasi, "Metrik_Tipi": "AG_TRAFIGI",
                                "Paket_sn": pps, "Bayt_sn": bps
                            })
                            point = Point("mesh_traffic") \
                                .field("packets_per_sec", float(pps)) \
                                .field("bytes_per_sec", float(bps)) \
                                .time(time.time_ns(), WritePrecision.NS)
                            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
                        except Exception as e:
                            print(f"  [HATA] InfluxDB (Trafik): {e}")
                        continue

                    # 4. BASARI ORANI (Aynı kaldı)
                    match_basari = re.search(pattern_basari, line)
                    if match_basari:
                        basari_orani = match_basari.group(1)
                        try:
                            write_to_csv(writer, file, {
                                "Zaman": zaman_damgasi, "Metrik_Tipi": "BASARI_ORANI",
                                "Basari_Orani": basari_orani
                            })
                            point = Point("mesh_health") \
                                .field("success_rate", float(basari_orani)) \
                                .time(time.time_ns(), WritePrecision.NS)
                            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
                        except Exception as e:
                            print(f"  [HATA] InfluxDB (Basari): {e}")
                        continue

                    # 5. BOS RAM (Aynı kaldı)
                    match_heap = re.search(pattern_heap, line)
                    if match_heap:
                        bos_ram = match_heap.group(1)
                        try:
                            write_to_csv(writer, file, {
                                "Zaman": zaman_damgasi, "Metrik_Tipi": "SISTEM_DURUMU",
                                "Bos_RAM_Bayt": bos_ram
                            })
                            point = Point("mesh_health") \
                                .field("free_heap_bytes", int(bos_ram)) \
                                .time(time.time_ns(), WritePrecision.NS)
                            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
                        except Exception as e:
                            print(f"  [HATA] InfluxDB (RAM): {e}")
                        continue

                    # 6. KAYIP PAKET (Aynı kaldı)
                    match_kayip = re.search(pattern_kayip, line)
                    if match_kayip:
                        kaynak, alinan_paket, kaybolan = match_kayip.groups()
                        try:
                            write_to_csv(writer, file, {
                                "Zaman": zaman_damgasi, "Metrik_Tipi": "KAYIP_PAKET",
                                "Hedef_Kaynak": kaynak, "Kaybolan_Paket": kaybolan
                            })
                            point = Point("mesh_health") \
                                .tag("source_node", kaynak) \
                                .field("lost_packets", int(kaybolan)) \
                                .time(time.time_ns(), WritePrecision.NS)
                            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
                        except Exception as e:
                            print(f"  [HATA] InfluxDB (Kayip): {e}")
                        continue

    except serial.SerialException:
        print("\n[HATA] COM portu acilamadi.")
    except KeyboardInterrupt:
        print("\n[SISTEM] Islem durduruldu.")
    finally:
        if 'client' in locals():
            client.close()
        if 'ser' in locals() and ser.is_open:
            ser.close()

if __name__ == "__main__":
    start_integrated_bridge()