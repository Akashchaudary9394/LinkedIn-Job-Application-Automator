if ! (python -V &> /dev/null || py -V &> /dev/null); then
    while ! (python -V &> /dev/null || py -V &> /dev/null);
    do
        echo "Python is not installed or not accessible!"
        echo "Please install Python and make sure it is added to your system's PATH environment variable."
        echo "Hold Ctrl and click on the link below or search 'Python Download' in your browser."
        echo "https://www.python.org/downloads/"
        echo "After installing Python and adding it to PATH, close and reopen setup file."
        read -p ""
    done
else
    echo "Python is already installed."
fi

if ! command -v "C:\Program Files\Google\Chrome\Application\chrome.exe" &> /dev/null; then
    while ! command -v "C:\Program Files\Google\Chrome\Application\chrome.exe" &> /dev/null;
    do
        echo "Google Chrome is not installed or not installed in the default location."
        echo "Please install Google Chrome to continue..."
        echo "Hold Ctrl and click on the link below or search 'google chrome download' in your browser."
        echo "https://www.google.com/chrome/"
        echo "Please follow the Google Chrome installation wizard."
        echo "After the installation is complete, press Enter to continue, if that does not work then close and reopen setup file.."
        read -p ""
    done
else
    echo "Google Chrome is already installed."
fi

latest_versions_info=$(curl -sS "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json")

echo $latest_versions_info

download_url=$(echo "$latest_versions_info" | 
               grep -A 5 '"platform": "win64",' | 
               grep 'url":' | 
               awk -F'"' '{print $4}')

echo "Download URL: '$download_url'"

curl -o chromedriver.zip "$download_url"

chrome_install_dir="/c/Program Files/Google/Chrome"
mkdir -p "$chrome_install_dir"

unzip -q chromedriver.zip -d "$chrome_install_dir"
mv "$chrome_install_dir/chromedriver_win64/chromedriver.exe" "$chrome_install_dir"
rm -r "$chrome_install_dir/chromedriver_win64" chromedriver.zip

echo "export PATH=\"\$PATH:${chrome_install_dir}\"" >> ~/.bashrc
source ~/.bashrc

echo "Setup complete. You can now use the web scraping tool."

read -rsn1 -p "Press any key to continue..."