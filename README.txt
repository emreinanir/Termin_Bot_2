Mainz Bürgeramt Appointment Bot – User Guide

1) Target site
https://termine-reservieren.de/termine/buergeramt.mainz/

2) Requirements
Google Chrome must be installed, and you need a Gmail account.

3) Playwright installation
Playwright must be installed via Command Prompt (cmd).

Useful commands (paste into cmd and hit Enter):

pip install playwright python-dotenv
playwright install

4) Create a virtual environment (venv)
Run these commands in cmd, in order:

python -m venv venv
venv\Scripts\activate

5) Bot operation
The bot runs with a visible Chrome window so you can follow its actions.
When you start the bot, Chrome will open automatically and the bot will operate there.
If you don’t want this, set headless=False to headless=True in the code.

6) Appointment tracking window
The tracking window is 180 days (6 months). The bot scans all appointments within this range and sends you an email with the earliest available date/time.
To change this, adjust in the code:
WINDOW_DAYS = 180

7) Check interval
The bot checks every 15 minutes.
To modify, change in the code:
INTERVAL_MIN = 15  # minutes
It’s not recommended to go below 10 minutes, as the site may block/ban you.

8) Email configuration
You must add your own Gmail credentials, otherwise the bot cannot send you emails.

Code snippet:
SMTP_HOST = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USER = 'YourGmail@gmail.com'
SMTP_PASS = 'GmailAppPassword'
MAIL_TO = 'YourGmail@gmail.com'

9) Personal data form
This site requires personal details before showing appointment dates. Update these fields with your data and save the file:

FORM = {
 'vorname': 'Erik',
 'nachname': 'Imanov',
 'email': 'erikimanov@gmail.com',
 'telefon': '015259572012',
 'geburt': ('01', '07', '1995')
}

10) Run the bot
Commands to start the bot (enter in order):

cd 'C:\Users\X\Y\Z'
venv\Scripts\activate
python mainz_studium_bot_full.py

Replace X, Y, Z with your actual folder path. Example:
cd 'C:\Users\John'sPC\Desktop\Mainz_bot_studium_2'

Tip: Keep the bot files in a dedicated folder for clarity.

11: Disclaimer
This project is for personal and educational purposes only. It should not be used for large-scale scraping or in violation of any website’s terms of service. Users are responsible for complying with applicable data protection and automation regulations.
