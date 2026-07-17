# Silent Voice

A real-time Augmentative and Alternative Communication (AAC) system 
that gives non-verbal individuals a fast, offline, personalized voice 
using 4 Qualcomm devices.

Built for the Snapdragon Multiverse Hackathon 2026 — Qualcomm Noida Campus.

## Team

|        Name         |             Email               |
|---------------------|---------------------------------|
| [Shriya Srivastava] | [shriyasrivastava025@gmail.com] |
|    [Pranav Tyagi]   |    [tyagipranav10@gmail.com]    |
|    [Aniket Prasad]  |    [aniketprasadn@gmail.com]    |
|    [Ansh Varshney]  |  [varshneyansh9267@gmail.com]   |
|   [Shubham Chauhan] |  [shubham.23b0231028@abes.ac.in]|

## What it does

Silent Voice distributes intelligence across 4 Qualcomm devices:

- **Arduino UNO Q** — reads flex sensor gestures via MCU, bridges 
  to Python MPU via App Lab Bridge RPC, streams to AI PC
- **OnePlus 15** — runs FastVLM-0.5B on Hexagon NPU for facial 
  expression detection, sends label to AI PC
- **Surface Laptop 7 (Snapdragon X Elite)** — fuses gesture and 
  expression inputs, classifies intent, synthesizes speech on NPU 
  in under 200ms, works 100% offline
- **Qualcomm Cloud AI 100** — receives session logs, reranks phrase 
  predictions, pushes model updates back to AI PC asynchronously

## Setup

### Requirements
- Python 3.10 or above
- Arduino App Lab (download from arduino.cc/en/uno-q)
- Android Studio (for OnePlus 15 app)
- WSL2 enabled on Windows

### Install Python dependencies
pip install -r requirements.txt

### Arduino UNO Q
1. Open Arduino App Lab
2. Open the project from the /arduino folder
3. Click Run — App Lab deploys the sketch to MCU and 
   Python script to MPU automatically

### AI PC (Surface Laptop 7)
cd ai-pc
python main.py

### OnePlus 15
cd mobile
./gradlew installDebug

### Cloud sync
cd cloud
python cloud_sync.py

## How to run

1. Start main.py on the AI PC first
2. Run the Arduino App Lab project — glove connects automatically
3. Open Silent Voice app on OnePlus 15 — joins same Wi-Fi hotspot
4. Put on the sensor glove and make a gesture
5. Speech plays within 200ms

## References

- AAC phrase bank structure: https://github.com/btk/aac-native
- Google AI Edge Gallery: https://github.com/google-ai-edge/gallery
- Qualcomm Simple NPU Chatbot: https://github.com/thatrandomfrenchdude/simple_npu_chatbot
- LiteRT FastVLM models: https://huggingface.co/collections/litert-community/qualcomm
- Arduino UNO Q docs: https://docs.arduino.cc/hardware/uno-q/

## License

MIT License
