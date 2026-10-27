# Termux Setup — Android App Reverse Engineering

> **⚠️ Responsible use — read first**
>
> Only reverse engineer apps that **you own, developed, or have explicit written permission to test** (e.g. your own apps, authorized bug-bounty/pen-test targets, malware samples in a lab).
>
> Reverse engineering third-party apps without authorization may violate their Terms of Service and applicable law — including India's IT Act, 2000, the U.S. CFAA / DMCA §1201, and similar laws elsewhere. You are solely responsible for staying legal. Do not use these techniques to bypass licensing, payments, or in-app purchases of apps you do not own.

This guide turns an Android phone running [Termux](https://termux.com/) into a portable reverse-engineering environment for Android apps (APKs). It covers static analysis (decompilation) and basic dynamic analysis (runtime inspection / traffic interception).

---

## 1. Prepare Termux

Install Termux from **F-Droid** (not the Play Store version — it is deprecated). Open it and run:

```bash
pkg update && pkg upgrade -y
pkg install -y git python python-pip openjdk-17 android-tools \
  wget curl unzip zip coreutils busybox termux-tools
termux-setup-storage
termux-wake-lock
```

- **`termux-setup-storage`** — grant storage permission so you can read/write APKs from `/sdcard`.
- **`termux-wake-lock`** — keeps the CPU awake while long decompilations run.
- Disable Android battery optimization for Termux, or builds will be killed in the background.

Verify Java:

```bash
java -version
```

Create a workspace:

```bash
mkdir -p ~/re/{apks,tools,output,scripts}
cd ~/re/tools
echo 'export PATH="$HOME/re/tools:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

---

## 2. Static analysis toolchain

### A. apktool — decode/rebuild resources + smali

```bash
cd ~/re/tools
wget https://bitbucket.org/iBotPeaches/apktool/downloads/apktool.jar
wget https://raw.githubusercontent.com/iBotPeaches/apktool/master/scripts/linux/apktool
chmod +x apktool
apktool --version
```

Usage:

```bash
# decode an APK
apktool d ~/re/apks/target.apk -o ~/re/output/decoded

# rebuild (e.g. after editing smali/resources)
apktool b ~/re/output/decoded -o ~/re/output/modified.apk
```

What you get: `AndroidManifest.xml` (decoded XML), `res/` (layouts, strings, images), and `smali/` (bytecode you can edit).

### B. jadx-cli — DEX → Java-like source

```bash
cd ~/re/tools
wget https://github.com/skylot/jadx/releases/download/v1.5.0/jadx-1.5.0.zip
unzip jadx-1.5.0.zip -d jadx
chmod +x jadx/bin/jadx-cli
jadx-cli --version
```

Usage:

```bash
jadx-cli -d ~/re/output/java ~/re/apks/target.apk
```

Open `~/re/output/java/` sources in any text editor. For day-to-day work, the jadx GUI on a PC is more comfortable; jadx-cli is the Termux equivalent.

### C. dex2jar + smali / baksmali (lower-level bytecode, optional)

```bash
cd ~/re/tools
# dex2jar
wget https://github.com/pxb1988/dex2jar/releases/download/2.3/dex2jar-2.3.zip
unzip dex2jar-2.3.zip -d dex2jar
chmod +x dex2jar/*.sh

# smali / baksmali (assembler/disassembler for smali)
wget https://github.com/JesusFreke/smali/releases/download/v2.5.2/baksmali-2.5.2.jar
wget https://github.com/JesusFreke/smali/releases/download/v2.5.2/smali-2.5.2.jar
```

Usage:

```bash
# extract classes.dex from an APK (APKs are ZIP files)
unzip -o ~/re/apks/target.apk classes.dex -d ~/re/output/

# DEX → JAR (then open with JD-GUI / your favorite Java decompiler on PC)
~/re/tools/dex2jar/d2j-dex2jar.sh ~/re/output/classes.dex

# DEX → smali
java -jar ~/re/tools/baksmali-2.5.2.jar d ~/re/output/classes.dex -o ~/re/output/smali_out

# smali → DEX
java -jar ~/re/tools/smali-2.5.2.jar a ~/re/output/smali_out -o ~/re/output/classes_new.dex
```

### D. Quick text searching

```bash
cd ~/re/output
grep -ri "api_key\|apikey\|http\|https\|\.php\|token\|password" decoded/ java/ 2>/dev/null | head -100
strings classes.dex | grep -i "http" | head -50
```

---

## 3. Dynamic analysis toolchain

### A. ADB (device connection)

```bash
pkg install android-tools   # usually already installed above
adb devices
adb shell pm list packages
adb shell pm path com.example.app
adb pull $(adb shell pm path com.example.app | cut -d: -f2) ~/re/apks/base.apk
adb logcat | grep -i "your.package"
```

### B. Frida + Objection (runtime instrumentation)

```bash
pip install frida-tools objection
```

1. On the host, check architecture: `uname -m` (usually `aarch64`).
2. Download the matching **frida-server-android-…-android-aarch64.xz** from https://github.com/frida/frida/releases.
3. Push and run on the device (requires root, or a debuggable build of your own app):

```bash
adb push frida-server-*.xz /data/local/tmp/
adb shell "cd /data/local/tmp && tar xJf frida-server-*.xz && chmod +x frida-server-... && ./frida-server-... &"
```

4. From Termux (or your PC):

```bash
frida-ps -U
objection explore
```

> Frida on a non-rooted device only works with debuggable apps you built yourself, or via repackaging with `frida-gadget` (advanced). Never use it to bypass checks in apps you don't own.

### C. mitmproxy — intercept HTTP/HTTPS traffic

```bash
pkg install mitmproxy
ip addr show wlan0   # note your Termux device's IP
mitmweb              # web UI, or 'mitmproxy' for terminal UI
```

1. On the Android device, set the Wi-Fi proxy to your Termux IP, port `8080`.
2. Install the mitmproxy CA certificate on the device (visit `http://mitm.it` from the device browser) to decrypt HTTPS.
3. Inspect all requests/responses from the target app.

---

## 4. Example end-to-end workflow (your own / authorized app)

```bash
# 1. Get the APK
adb shell pm path com.example.myapp
adb pull /data/app/com.example.myapp-.../base.apk ~/re/apks/myapp.apk

# 2. Static: resources + manifest
apktool d ~/re/apks/myapp.apk -o ~/re/output/myapp_decoded
cat ~/re/output/myapp_decoded/AndroidManifest.xml

# 3. Static: Java-like source
jadx-cli -d ~/re/output/myapp_java ~/re/apks/myapp.apk

# 4. Grep for interesting endpoints/secrets
grep -ri "http\|api_key\|token\|firebase" ~/re/output/myapp_java ~/re/output/myapp_decoded/res | head -50

# 5. Dynamic (authorized debuggable build only)
# frida-server on device → objection explore → inspect methods at runtime

# 6. Network
mitmweb → proxy device traffic → observe API calls
```

Save anything you want to keep under `~/storage/shared/re/` so it survives a Termux uninstall (`termux-setup-storage` maps `~/storage/shared` to `/sdcard`).

---

## 5. If a package is missing in Termux

Some heavy Java/Node tools aren't packaged for Termux. Options:

- Download standalone jars/releases manually (as done above for apktool, jadx, dex2jar, smali).
- Or install a full distro inside Termux:

```bash
pkg install proot-distro
proot-distro install ubuntu
proot-distro login ubuntu
apt update && apt install -y default-jdk maven gradle
```

---

## 6. Useful references

| Tool | Purpose | Home |
|------|---------|------|
| apktool | APK decode/rebuild | https://apktool.org |
| jadx | DEX → Java source | https://github.com/skylot/jadx |
| dex2jar | DEX → JAR | https://github.com/pxb1988/dex2jar |
| smali / baksmali | smali assembler/disassembler | https://github.com/JesusFreke/smali |
| Frida | dynamic instrumentation | https://frida.re |
| Objection | runtime mobile exploration | https://github.com/sensepost/objection |
| mitmproxy | traffic interception | https://mitmproxy.org |
| ADB | device bridge | https://developer.android.com/studio/command-line/adb |

---

*Keep it ethical: analyze what you own or are explicitly authorized to test, and respect the law and the platforms' terms of service.*