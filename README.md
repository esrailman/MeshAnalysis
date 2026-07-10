# ESP32-Based Wireless Mesh Network (painlessMesh) Performance Analysis

This project aims to analyze the performance, dynamic topology management, and self-healing capacity of a wireless mesh network created using three autonomous ESP32 microcontrollers. 
Communication across the network is established using the `painlessMesh` library. Quality of Service (QoS) metrics such as Latency, Jitter, RTT, Hop Count, and RSSI are transferred to InfluxDB via a custom-developed Python bridge and monitored in real-time through a Grafana dashboard.

## 👥 Contributers (Gazi University)
This project was carried out in collaboration **with**  **Fatıma Zehra Özyürek** - [GitHub Profile](https://github.com/ozyrkzhr),  **Merve Keleş** - [GitHub Profile](https://github.com/kelesmerve).

## 🏗 System Architecture

The project consists of four main layers (Telemetry Pipeline):

1. **Hardware Layer:** 3x dual-core ESP32s (Merve, Esra, and Zehra nodes). The nodes operate simultaneously in AP (Access Point) and STA (Station) modes.
2. **Logic Layer (C++ / PlatformIO):** Autonomous routing and a REQ-ECHO-based metric calculation mechanism utilizing `painlessMesh` and `ArduinoJson`.
3. **Data Capture Layer (Python):** An asynchronous serial port bridge (`pyserial` & `influxdb-client`) that reads JSON-formatted telemetry data flowing from the ESP32 via the serial port and pushes it to InfluxDB.
4. **Data Storage and Visualization:** Time-series data storage in InfluxDB and real-time performance tracking via Grafana.

## 🧪 Tested Scenarios and Findings

The system was evaluated under different stress and environmental factors through 5 core scenarios:

* **Scenario 1 (Ideal Baseline):** 100% success rate, maintaining low latency between 50-200ms.
* **Scenario 2 (Physical Obstacle / Metal Barrier):** Sudden latency spikes exceeding 125ms caused by signal attenuation (-65 to -75 dBm) and packet retransmissions.
* **Scenario 3 (Autonomous Self-Healing):** In the event of a sudden shutdown of a root node, the network detects the collapse within seconds, flushes old routes, and restores a 100% success rate by dynamically electing a new root and rebuilding the spanning tree.
* **Scenario 4 (Multi-Hop Processing Tax):** Delays caused by topological depth. Even with pristine signal strength (-27 dBm), data packets requiring 2 hops increase the total propagation delay by roughly 240%.
* **Scenario 5 (High Traffic / Burst Mode):** Significant Jitter spikes due to CPU bottlenecks and buffer saturation during a stress test where 5 packets were sent per burst.

## 🚀 Setup and Execution

### Requirements
* **Hardware:** 3x ESP32 Development Boards
* **IDE:** VS Code & PlatformIO extension
* **Database and Visualization:** InfluxDB (v2.x) and Grafana
* **Python Environment:** Python 3.8+

### 1. Flashing the ESP32 Code
Open the project using VS Code (PlatformIO). The `platformio.ini` file will automatically resolve and download the required dependencies (`ArduinoJson` and `TaskScheduler`). Build and Upload the firmware to each ESP32 board.

### 2. Starting the Python Data Bridge
To install the necessary Python dependencies, open a terminal in the project directory and run:

```bash
pip install -r requirements.txt

```

Next, launch the Python script to begin transferring data to InfluxDB and generating a local CSV report (mesh_performans_raporu.csv):

```bash
python data_bridge.py

```

*(Note: Make sure to update the `SERIAL_PORT` and InfluxDB `INFLUX_TOKEN` variables inside `data_bridge.py` to match your local environment.)*
