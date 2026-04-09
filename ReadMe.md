# 🚀 LocalizeIt – Automated 71-Language Localization Tool  
### One-click translations for JSON & Dart string files.

LocalizeIt is a desktop application that automates the entire localization workflow — converting a single base language file into **70+ translated files** with minimal setup.

Built to eliminate repetitive manual steps and multiple-tool workflows.

---

## 💡 Why This Tool Exists

A typical localization workflow often looks like this:

- Extract keys & values manually or using AI tools  
- Move data into Excel  
- Translate into multiple languages  
- Upload into another tool  
- Generate files → download ZIP → extract → move files  

This process is slow, repetitive, and error-prone.

---

## ✅ With LocalizeIt

- Drop your English file into the folder  
- Select languages & settings  
- Click start  

**Everything else is handled automatically.**

---

## 🌍 Key Features

- JSON & Dart file support (auto-detection)  
- 70+ language translations  
- Parallel processing (fast)  
- Automatic retries & failure handling  
- Built-in rate limiting (chunk + cooldown system)  
- Direct file generation (no ZIP/manual work)  

---

## 🖥️ Setup & Build (Create EXE)

### 1. Open Terminal in Project Folder

Make sure you are inside the project directory where `main.py` exists.

---

### 2. Install Dependencies

```bash
python -m pip install -r requirements.txt

or:

py -m pip install -r requirements.txt
3. Build the EXE
python -m PyInstaller --noconsole --onefile --name LocalizeIt main.py

or:

py -m PyInstaller --noconsole --onefile --name LocalizeIt main.py
4. Run the Application
After build completes, go to the dist folder
You will find: LocalizeIt.exe
Copy it anywhere and run directly

✅ No Python required after building the EXE

⚙️ How to Use
Place your base language file (en.json or .dart)
Run the application
Select:
Languages
Chunk size
Cooldown
Click Start Translation
📁 Output
All translated files are generated automatically
Saved in the same directory
Named by language code (e.g., es.json, fr.json)
🔒 Notes
Internet connection required (uses translation APIs)
Large files → use lower chunk sizes for stability
Built-in retry system handles failures automatically