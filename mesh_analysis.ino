#include "painlessMesh.h"
#include <ArduinoJson.h>
#include <map>

// --- AĞ İZOLASYONU ---
#define MESH_PREFIX     "TrioAnalizMesh" 
#define MESH_PASSWORD   "123456789"
#define MESH_PORT       5555

// --- 4. SENARYO (STRES TESTİ) AYARLARI ---
#define BURST_SIZE      5  
#define CALC_WINDOW     10  

// --- İSİMLENDİRME FONKSİYONU ---
String getNameFromID(uint32_t id) {
  switch(id) {
    case 3724407101: return "Merve";
    case 3711136689: return "Esra";
    case 3724369149: return "Zehra"; 
    default: return "Bilinmeyen_Cihaz";
  }
}

// --- GELEN PAKET ANALİZİ İÇİN HARİTALAR ---
std::map<uint32_t, uint32_t> node_packet_count; 
std::map<uint32_t, uint32_t> last_seen_id;      
std::map<uint32_t, uint32_t> lost_packet_count; 
uint32_t duplicate_req = 0;                     

std::map<uint32_t, uint8_t> echo_tracker; 
Scheduler userScheduler;
painlessMesh mesh;

uint32_t msg_id = 0;

// Toplam ve Aralık (Interval) Sayaçları
uint32_t rx_packets = 0;
uint32_t rx_bytes = 0;
uint32_t successful_echos = 0; 

// SADECE 5 SANİYELİK ARALIK İÇİN SAYAÇLAR 
uint32_t interval_sent_msgs = 0;
uint32_t interval_successful_echos = 0;

// --- JİTTER HESABI İÇİN ÖNCEKİ GECİKME ---
uint32_t prev_latency = 0; 

// --- GERÇEK HOP SAYISI HESAPLAMA FONKSİYONU ---
int calculateTrueHopCount(String topologyJson, uint32_t targetNode, int currentDepth) {
    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, topologyJson);
    if (error) return -1;

    JsonArray subs = doc["subs"];
    if (subs.isNull()) return -1; 

    for (JsonObject sub : subs) {
        uint32_t subNodeId = sub["nodeId"];
        if (subNodeId == targetNode) return currentDepth;
        
        if (sub.containsKey("subs")) {
            String subJson;
            serializeJson(sub, subJson);
            int subHop = calculateTrueHopCount(subJson, targetNode, currentDepth + 1);
            if (subHop != -1) return subHop;
        }
    }
    return -1;
}

void calcThroughput() {
  float pps = rx_packets / (float)CALC_WINDOW; 
  float bps = rx_bytes / (float)CALC_WINDOW;   

  // --- Cihaz sayısı dinamik veya sabit (Orijinal Mantık) ---
  uint32_t expected_peers = 2; 
  uint32_t beklenen_echo_sayisi = interval_sent_msgs * expected_peers;

  float success_rate = (beklenen_echo_sayisi > 0) ? ((float)interval_successful_echos / beklenen_echo_sayisi) * 100.0 : 0.0;
  
  if (success_rate > 100.0) success_rate = 100.0;

  uint32_t free_heap = ESP.getFreeHeap();

  Serial.printf("\n=== [THROUGHPUT ANALIZI - Son %d Saniye] ===\n", CALC_WINDOW);
  Serial.printf("Beklenen Toplam ECHO: %u | Gelen Basarili ECHO: %u\n", beklenen_echo_sayisi, interval_successful_echos);
  Serial.printf("Gelen Toplam Ag Trafigi: %.1f Paket/sn | %.1f Bayt/sn\n", pps, bps);
  Serial.printf("Basari Orani: %%%.1f\n", success_rate);
  Serial.printf("Bos RAM (Heap): %u Bayt\n", free_heap); 
  
  Serial.println("--- [BANA GELEN PAKETLERIN (REQ) ANALIZI] ---");
  if (node_packet_count.empty()) {
      Serial.println("  -> Henuz baska cihazlardan paket alinmadi.");
  } else {
      for (auto const& pair : node_packet_count) {
          uint32_t senderNode = pair.first;
          uint32_t count = pair.second;
          uint32_t lost = lost_packet_count[senderNode];
          
          Serial.printf("  -> Kaynak: %s | Alinan Paket: %u | Kaybolan: %u\n", getNameFromID(senderNode).c_str(), count, lost);
      }
      if(duplicate_req > 0) {
          Serial.printf("  -> Sirasiz/Tekrar Eden Paket (Duplicate): %u adet\n", duplicate_req);
      }
  }
  Serial.println("===========================================\n");

  rx_packets = 0;
  rx_bytes = 0;
  interval_sent_msgs = 0;          
  interval_successful_echos = 0;   
  echo_tracker.clear(); 
  
  node_packet_count.clear();
  lost_packet_count.clear();
  duplicate_req = 0;
}

void sendMessage() {
  for (int i = 0; i < BURST_SIZE; i++) {
    msg_id++;
    interval_sent_msgs++; 
    
    JsonDocument doc;
    doc["id"] = msg_id;
    doc["t"] = mesh.getNodeTime(); 
    // "h" kaldırıldı çünkü artık otonom hesaplanıyor
    doc["type"] = "REQ";
    doc["sender"] = mesh.getNodeId();

    String msg;
    serializeJson(doc, msg);
    
    mesh.sendBroadcast(msg);
    mesh.update(); 
  }
  
  Serial.printf("[STRES TESTI] %d adet paket burst gonderildi. (Son ID: %u)\n", BURST_SIZE, msg_id);
}

Task taskSendMessage(TASK_SECOND * CALC_WINDOW, TASK_FOREVER, &sendMessage); 
Task taskCalcThroughput(TASK_SECOND * CALC_WINDOW, TASK_FOREVER, &calcThroughput);

void receivedCallback(uint32_t from, String &msg) {
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, msg);

  if (error) {
    return;
  }

  String type = doc["type"].as<String>();
  uint32_t id = doc["id"];
  uint32_t send_time = doc["t"];
  uint32_t original_sender = doc["sender"];
  
  int rssi = WiFi.RSSI(); 
  uint32_t now = mesh.getNodeTime(); 

  if (type == "REQ") {
    rx_packets++;
    rx_bytes += msg.length();

    uint32_t one_way_latency = (now >= send_time) ? (now - send_time) : 0;
    
    // REQ kısmında hop bilgisini yazdırmak istersen dinamik hesaplatabilirsin
    // Ancak orijinal çıktıyı bozmamak adına ECHO kısmına odaklandık.
    Serial.printf("  -> [REQ GELDİ] Gönderen: %s | Paket: %u | Tek Yönlü Gecikme: %uus | RSSI: %d dBm\n", 
                  getNameFromID(original_sender).c_str(), id, one_way_latency, rssi);

    node_packet_count[original_sender]++; 
    if (last_seen_id.count(original_sender) > 0) {
        uint32_t expected_id = last_seen_id[original_sender] + 1;
        if (id > expected_id) {
            lost_packet_count[original_sender] += (id - expected_id);
        }
    }
    if (last_seen_id.count(original_sender) == 0 || id > last_seen_id[original_sender]) {
        last_seen_id[original_sender] = id; 
    } else if (id < last_seen_id[original_sender]) {
        duplicate_req++;
    }

    JsonDocument replyDoc;
    replyDoc["id"] = id;
    replyDoc["t"] = send_time; 
    replyDoc["type"] = "ECHO";
    replyDoc["sender"] = original_sender;
    replyDoc["rrssi"] = rssi; 

    String replyMsg;
    serializeJson(replyDoc, replyMsg);
    
    mesh.sendSingle(from, replyMsg);
  }
  else if (type == "ECHO" && original_sender == mesh.getNodeId()) {
    successful_echos++;
    interval_successful_echos++; 
    echo_tracker[id]++; 

    uint32_t rtt = now - send_time; 
    uint32_t latency = rtt / 2;     

    uint32_t jitter = 0;
    if (prev_latency > 0) {
        jitter = (latency > prev_latency) ? (latency - prev_latency) : (prev_latency - latency);
    }
    prev_latency = latency;

    int remote_rssi = doc["rrssi"];

    // --- GÜNCEL HOP HESABI ---
    String networkTopology = mesh.subConnectionJson(true); 
    int trueHopCount = calculateTrueHopCount(networkTopology, from, 1);
    if (trueHopCount <= 0) trueHopCount = 1;

    Serial.printf("  <- [ECHO GELDİ] Yanıtlayan: %s | Paket: %u | Hop: %d | Gecikme: %uus | Jitter: %uus | RTT: %uus | Yerel RSSI: %d dBm | Karşı RSSI: %d dBm\n", 
                  getNameFromID(from).c_str(), id, trueHopCount, latency, jitter, rtt, rssi, remote_rssi);
  }
}

void newConnectionCallback(uint32_t nodeId) {
  Serial.printf("\n[AĞ BİLGİSİ] Yeni Cihaz Katıldı: %s (%u)\n", getNameFromID(nodeId).c_str(), nodeId);
}

void changedConnectionCallback() {
  Serial.printf("\n[DİNAMİK YAPI] Ağ Haritası Değişti! Zaman(ms): %u\n", millis());
}

void setup() {
  Serial.begin(115200);

  mesh.setDebugMsgTypes(ERROR | STARTUP);
  mesh.init(MESH_PREFIX, MESH_PASSWORD, &userScheduler, MESH_PORT);

  mesh.onReceive(&receivedCallback);
  mesh.onNewConnection(&newConnectionCallback);
  mesh.onChangedConnections(&changedConnectionCallback);

  userScheduler.addTask(taskSendMessage);
  userScheduler.addTask(taskCalcThroughput); 
  
  taskSendMessage.enable();
  taskCalcThroughput.enable(); 
}

void loop() {
  mesh.update();
}