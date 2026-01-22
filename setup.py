# 1. Download the latest Google Chrome (forces a clean name)
echo "--- ⬇️  Downloading Google Chrome ---"
wget -O google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb

# 2. Install Chrome (and fix dependencies)
echo "--- 🛠️  Installing Chrome ---"
sudo apt update
sudo apt install ./google-chrome.deb -y

# 3. Install Python Libraries (Selenium, Pandas, etc.)
echo "--- 🐍 Installing Python Packages ---"
pip install pandas selenium webdriver-manager

# 4. Clean up the installer file to keep your folder clean
rm google-chrome.deb

echo "--- ✅ ALL SET! System is ready. ---"
echo "Run your tool now: python notnahid.py 'Coffee Shops in Banani'"
